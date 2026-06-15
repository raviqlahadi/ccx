#!/usr/bin/env python3
"""
CCX Analysis Tools - Request Trace, Impact Analysis, Dead Code Detection
Uses the call graph from explore --json output.

Usage:
  ccx-analyze <project_dir> trace <endpoint>
  ccx-analyze <project_dir> impact <Class.method>
  ccx-analyze <project_dir> deadcode
  ccx-analyze <project_dir> --help
"""

import json
import os
import re
import subprocess
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from lib.graph import build_project_data

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EXPLORE_PY = os.path.join(SCRIPT_DIR, 'explore.py')

def build_graph(project_dir):
    """Build call graph using shared lib (cached)"""
    return build_project_data(project_dir, progress=True, with_complexity=False)

def normalize_calls(calls):
    if not calls:
        return []
    if isinstance(calls, dict):
        return list(calls.values())
    return calls

def build_indices(data):
    """Build lookup indices from data"""
    # class_methods: {ClassName: {methodName: {calls, file, line}}}
    class_methods = {}
    # method_to_class: {methodName: [ClassName, ...]}
    method_to_class = defaultdict(list)
    # call_graph: {ClassName.method: [ClassName.method, ...]} (outgoing)
    call_graph = defaultdict(set)
    # reverse_graph: {ClassName.method: [ClassName.method, ...]} (incoming/callers)
    reverse_graph = defaultdict(set)
    # routes: [{method, uri, controller, action}]
    routes = data.get('routes', [])
    # tables by file
    tables_by_file = {}
    for tbl, files in data.get('tables', {}).items():
        for f in (files if isinstance(files, list) else []):
            if f not in tables_by_file:
                tables_by_file[f] = []
            tables_by_file[f].append(tbl)

    for file_data in data.get('files', []):
        classes = file_data.get('classes', file_data.get('structs', {}))
        filepath = file_data.get('path', '')
        for cname, cinfo in classes.items():
            methods = cinfo.get('methods', {})
            if isinstance(methods, list):
                methods = {}
            deps = cinfo.get('dependencies', [])
            if not deps:
                deps = []
            if isinstance(deps, dict):
                deps = list(deps.values())

            class_methods[cname] = {
                'methods': methods,
                'file': filepath,
                'deps': deps,
                'tables': tables_by_file.get(filepath, []),
            }

            for mname, minfo in methods.items():
                method_to_class[mname].append(cname)
                calls = normalize_calls(minfo.get('calls', []))

                for call in calls:
                    target = resolve_call(call, cname, class_methods, method_to_class)
                    if target:
                        call_graph[f"{cname}.{mname}"].add(target)
                        reverse_graph[target].add(f"{cname}.{mname}")

    return class_methods, method_to_class, call_graph, reverse_graph, routes, tables_by_file

def resolve_call(call, current_class, class_methods, method_to_class):
    """Resolve a call string to ClassName.method"""
    # this->method or $this->prop->method
    if call.startswith('this->'):
        method = call.replace('this->', '')
        if current_class in class_methods and method in class_methods[current_class]['methods']:
            return f"{current_class}.{method}"

    # $this->prop->method (dependency call)
    if call.startswith('$this->'):
        parts = call.replace('$this->', '').split('->')
        if len(parts) == 2:
            prop, method = parts
            # Find which class has this method among deps
            if current_class in class_methods:
                for dep in class_methods[current_class].get('deps', []):
                    dep_clean = dep.replace('*', '').split('.')[-1]
                    if dep_clean in class_methods and method in class_methods[dep_clean].get('methods', {}):
                        return f"{dep_clean}.{method}"
            # Fallback: find any class with this method
            if method in method_to_class:
                for cls in method_to_class[method]:
                    return f"{cls}.{method}"

    # obj.Method (Go style)
    if '.' in call and not call.startswith('$'):
        parts = call.split('.')
        if len(parts) == 2:
            obj, method = parts
            # Try to find the type
            if obj in class_methods and method in class_methods[obj].get('methods', {}):
                return f"{obj}.{method}"
            # Check by method name
            if method in method_to_class:
                for cls in method_to_class[method]:
                    return f"{cls}.{method}"

    # Plain method name
    plain = call.split('->')[-1].split('.')[-1].replace('$', '')
    if plain in method_to_class:
        for cls in method_to_class[plain]:
            if cls != current_class:
                return f"{cls}.{plain}"
        # Could be self-call
        if current_class in method_to_class.get(plain, []):
            return f"{current_class}.{plain}"

    return None

# ============================================================
# COMMAND: trace
# ============================================================
def cmd_trace(data, endpoint, class_methods, method_to_class, call_graph, routes, tables_by_file):
    """Trace a request from endpoint through the call chain"""
    # Find matching route
    endpoint_lower = endpoint.lower().strip('/')
    matched = []
    for r in routes:
        uri = r.get('uri', '').lower().strip('/')
        if endpoint_lower in uri or uri in endpoint_lower:
            matched.append(r)

    if not matched:
        # Try fuzzy match
        for r in routes:
            if endpoint_lower in r.get('action', '').lower() or endpoint_lower in r.get('controller', '').lower():
                matched.append(r)

    if not matched:
        print(f"❌ No route found matching: {endpoint}")
        print(f"   Try: ccx-analyze <dir> trace /v1/createKunjungan")
        return

    for route in matched[:3]:
        controller = route['controller'].replace('\\', '/').split('/')[-1]
        action = route['action']
        print(f"\n{'='*70}")
        print(f" {route['method']} {route['uri']}")
        print(f" → {controller}@{action}")
        print(f"{'='*70}")

        entry = f"{controller}.{action}"
        visited = set()
        trace_recursive(entry, call_graph, class_methods, tables_by_file, visited, depth=0)

def trace_recursive(node, call_graph, class_methods, tables_by_file, visited, depth, max_depth=8):
    if node in visited or depth > max_depth:
        return
    visited.add(node)

    parts = node.split('.', 1)
    if len(parts) != 2:
        return
    cls, method = parts

    # Classify layer
    cls_lower = cls.lower()
    if 'controller' in cls_lower:
        icon = '🎯'
        layer = 'Controller'
    elif 'usecase' in cls_lower or 'service' in cls_lower:
        icon = '⚙️'
        layer = 'Usecase'
    elif 'repo' in cls_lower:
        icon = '💾'
        layer = 'Repository'
    else:
        icon = '📦'
        layer = 'Other'

    indent = '  │ ' * depth
    connector = '  ├─' if depth > 0 else '  '

    # Get file info
    file_info = ''
    if cls in class_methods:
        f = class_methods[cls].get('file', '')
        if f:
            file_info = f" ({f})"

    print(f"{indent}{connector}{icon} {cls}.{method}{file_info}")

    # Show DB tables if repo
    if 'repo' in cls_lower and cls in class_methods:
        tables = class_methods[cls].get('tables', [])
        if tables:
            print(f"{indent}  │   🗄  Tables: {', '.join(tables)}")

    # Follow calls
    callees = call_graph.get(node, set())
    for callee in sorted(callees):
        trace_recursive(callee, call_graph, class_methods, tables_by_file, visited, depth + 1, max_depth)

# ============================================================
# COMMAND: impact
# ============================================================
def cmd_impact(data, target, class_methods, method_to_class, reverse_graph, routes):
    """Show all upstream callers of a function recursively"""
    # Resolve target
    if '.' in target:
        entry = target
    else:
        # Find by method name
        if target in method_to_class:
            for cls in method_to_class[target]:
                entry = f"{cls}.{target}"
                break
        else:
            print(f"❌ Function not found: {target}")
            print(f"   Try: ccx-analyze <dir> impact ClassName.methodName")
            return

    print(f"\n{'='*70}")
    print(f" IMPACT ANALYSIS: {entry}")
    print(f" \"If I change this, what's affected upstream?\"")
    print(f"{'='*70}\n")

    # Find all callers recursively
    all_callers = set()
    affected_routes = []
    impact_recursive(entry, reverse_graph, all_callers, depth=0)

    # Find which routes are affected
    for r in routes:
        controller = r['controller'].replace('\\', '/').split('/')[-1]
        action = r['action']
        route_entry = f"{controller}.{action}"
        if route_entry in all_callers:
            affected_routes.append(r)

    # Print tree
    visited = set()
    print(f" 🎯 {entry}")
    print_callers_tree(entry, reverse_graph, visited, depth=1)

    # Summary
    print(f"\n{'─'*70}")
    print(f" 📊 Summary:")
    print(f"    {len(all_callers)} functions affected upstream")
    if affected_routes:
        print(f"    {len(affected_routes)} API routes affected:")
        for r in affected_routes:
            print(f"      {r['method']} {r['uri']}")
    else:
        print(f"    No routes directly affected (internal function)")

def impact_recursive(node, reverse_graph, all_callers, depth, max_depth=15):
    if node in all_callers or depth > max_depth:
        return
    all_callers.add(node)
    for caller in reverse_graph.get(node, set()):
        impact_recursive(caller, reverse_graph, all_callers, depth + 1, max_depth)

def print_callers_tree(node, reverse_graph, visited, depth, max_depth=6):
    if node in visited or depth > max_depth:
        return
    visited.add(node)
    callers = sorted(reverse_graph.get(node, set()))
    for caller in callers:
        indent = '  │ ' * (depth - 1) + '  ├─'
        cls = caller.split('.')[0].lower()
        if 'controller' in cls:
            icon = '🎯'
        elif 'usecase' in cls or 'service' in cls:
            icon = '⚙️'
        elif 'repo' in cls:
            icon = '💾'
        else:
            icon = '📦'
        print(f" {indent}{icon} {caller}")
        print_callers_tree(caller, reverse_graph, visited, depth + 1, max_depth)

# ============================================================
# COMMAND: deadcode
# ============================================================
def cmd_deadcode(data, class_methods, method_to_class, call_graph, reverse_graph, routes):
    """Find functions never reachable from any route"""
    # Find all methods reachable from routes
    reachable = set()

    for r in routes:
        controller = r['controller'].replace('\\', '/').split('/')[-1]
        action = r['action']
        entry = f"{controller}.{action}"
        trace_reachable(entry, call_graph, reachable)

    # All methods
    all_methods = set()
    for cls, info in class_methods.items():
        for method in info.get('methods', {}):
            all_methods.add(f"{cls}.{method}")

    # Dead = not reachable and not a constructor/lifecycle method
    skip_methods = {'__construct', 'boot', 'register', 'handle', 'rules', 'messages',
                    'authorize', 'setUp', 'tearDown', 'TableName', 'main'}

    dead = []
    for m in sorted(all_methods):
        if m in reachable:
            continue
        method_name = m.split('.', 1)[1] if '.' in m else m
        if method_name in skip_methods or method_name.startswith('__'):
            continue
        # Skip if it has callers (reachable from non-route entry points)
        if reverse_graph.get(m):
            continue
        dead.append(m)

    print(f"\n{'='*70}")
    print(f" DEAD CODE DETECTOR")
    print(f" Functions with no callers and unreachable from any route")
    print(f"{'='*70}\n")

    if not dead:
        print(" ✅ No dead code found!")
        return

    # Group by class
    by_class = defaultdict(list)
    for m in dead:
        cls, method = m.split('.', 1)
        by_class[cls].append(method)

    for cls in sorted(by_class.keys()):
        methods = by_class[cls]
        file_info = class_methods.get(cls, {}).get('file', '')
        print(f" 💀 {cls} ({file_info})")
        for method in sorted(methods):
            line = class_methods.get(cls, {}).get('methods', {}).get(method, {}).get('line', '')
            print(f"    • {method}" + (f" (line {line})" if line else ''))
        print()

    print(f"{'─'*70}")
    print(f" Total: {len(dead)} potentially dead functions in {len(by_class)} classes")
    print(f" Scanned: {len(all_methods)} functions, {len(routes)} routes")
    print(f" Reachable from routes: {len(reachable)}")

def trace_reachable(node, call_graph, reachable, max_depth=15):
    if node in reachable or max_depth <= 0:
        return
    reachable.add(node)
    for callee in call_graph.get(node, set()):
        trace_reachable(callee, call_graph, reachable, max_depth - 1)

# ============================================================
# MAIN
# ============================================================
def main():
    args = sys.argv[1:]

    if not args or '--help' in args or '-h' in args:
        print("CCX Analysis Tools")
        print("")
        print("Usage:")
        print("  ccx-analyze <project_dir> trace <endpoint>    Trace request call chain")
        print("  ccx-analyze <project_dir> impact <function>   Show upstream callers")
        print("  ccx-analyze <project_dir> deadcode            Find unreachable functions")
        print("")
        print("Examples:")
        print("  ccx-analyze app/ trace /v1/createKunjungan")
        print("  ccx-analyze app/ trace createPenagihan")
        print("  ccx-analyze app/ impact ActivityRepository.insert")
        print("  ccx-analyze app/ impact insertLKNPemasaranDanaDirect")
        print("  ccx-analyze app/ deadcode")
        sys.exit(0)

    if len(args) < 2:
        print("Error: need <project_dir> and command. Run with --help.")
        sys.exit(1)

    project_dir = args[0]
    command = args[1]
    target = args[2] if len(args) > 2 else None

    # Build data
    data = build_graph(project_dir)
    class_methods, method_to_class, call_graph, reverse_graph, routes, tables_by_file = build_indices(data)

    print(f"✅ Graph built: {len(class_methods)} classes, {sum(len(call_graph[k]) for k in call_graph)} edges, {len(routes)} routes\n", file=sys.stderr)

    if command == 'trace':
        if not target:
            print("Error: trace needs an endpoint. e.g. trace /v1/createKunjungan")
            sys.exit(1)
        cmd_trace(data, target, class_methods, method_to_class, call_graph, routes, tables_by_file)
    elif command == 'impact':
        if not target:
            print("Error: impact needs a function. e.g. impact ClassName.method")
            sys.exit(1)
        cmd_impact(data, target, class_methods, method_to_class, reverse_graph, routes)
    elif command == 'deadcode':
        cmd_deadcode(data, class_methods, method_to_class, call_graph, reverse_graph, routes)
    else:
        print(f"Unknown command: {command}. Use trace, impact, or deadcode.")
        sys.exit(1)

if __name__ == '__main__':
    main()
