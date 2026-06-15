#!/usr/bin/env python3
"""
Codebase Explorer - Generates an interactive visualization from AST data
Usage: python3 explore.py <directory> [--output output.html]
"""

import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PHP_EXTRACTOR = os.path.join(SCRIPT_DIR, 'extract_php.php')
GO_EXTRACTOR_SRC = os.path.join(SCRIPT_DIR, 'extract_go.go')
GO_EXTRACTOR_BIN = os.path.join(SCRIPT_DIR, 'extract_go_bin')
GO_ROUTES_SRC = os.path.join(SCRIPT_DIR, 'extract_routes_go.go')
GO_ROUTES_BIN = os.path.join(SCRIPT_DIR, 'extract_routes_go_bin')
PHP_ROUTES = os.path.join(SCRIPT_DIR, 'extract_routes_php.php')
PHP_COMPLEXITY = os.path.join(SCRIPT_DIR, '..', 'analyze_php.php')
GO_COMPLEXITY = os.path.join(SCRIPT_DIR, '..', 'analyze_go')
INFRA_EXTRACTOR = os.path.join(SCRIPT_DIR, 'extract_infra.py')
VISUALIZER = os.path.join(SCRIPT_DIR, 'visualizer.html')

def ensure_go_binaries():
    for src, binn in [(GO_EXTRACTOR_SRC, GO_EXTRACTOR_BIN), (GO_ROUTES_SRC, GO_ROUTES_BIN)]:
        if not os.path.exists(binn) or os.path.getmtime(src) > os.path.getmtime(binn):
            print(f"⚙  Compiling {os.path.basename(src)}...", file=sys.stderr)
            r = subprocess.run(['go', 'build', '-o', binn, src], capture_output=True, text=True)
            if r.returncode != 0:
                print(f"Error: {r.stderr}", file=sys.stderr)
                return False
    return True

def extract_php(filepath):
    r = subprocess.run(['php', PHP_EXTRACTOR, filepath], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except:
        return None

def extract_go(filepath):
    r = subprocess.run([GO_EXTRACTOR_BIN, filepath], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except:
        return None

def extract_routes(target):
    """Extract routes from routes/ directory"""
    routes_dir = None
    # Look for routes/ directory in target or parent
    for candidate in [os.path.join(target, 'routes'), os.path.join(target, '..', 'routes')]:
        if os.path.isdir(candidate):
            routes_dir = os.path.abspath(candidate)
            break

    if not routes_dir:
        return []

    routes = []

    # PHP routes
    php_files = [f for f in os.listdir(routes_dir) if f.endswith('.php')]
    if php_files:
        r = subprocess.run(['php', PHP_ROUTES, routes_dir], capture_output=True, text=True)
        if r.returncode == 0:
            try:
                routes.extend(json.loads(r.stdout))
            except:
                pass

    # Go routes
    go_files = [f for f in os.listdir(routes_dir) if f.endswith('.go')]
    if go_files and os.path.exists(GO_ROUTES_BIN):
        r = subprocess.run([GO_ROUTES_BIN, routes_dir], capture_output=True, text=True)
        if r.returncode == 0:
            try:
                routes.extend(json.loads(r.stdout))
            except:
                pass

    return routes

def extract_complexity(filepath):
    """Get cognitive complexity per function for a file"""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.php' and os.path.exists(PHP_COMPLEXITY):
        r = subprocess.run(['php', PHP_COMPLEXITY, filepath], capture_output=True, text=True)
    elif ext == '.go' and os.path.exists(GO_COMPLEXITY):
        r = subprocess.run([GO_COMPLEXITY, filepath], capture_output=True, text=True)
    else:
        return {}
    if r.returncode != 0:
        return {}
    try:
        data = json.loads(r.stdout)
        return {item['name']: item['complexity'] for item in data}
    except:
        return {}

def scan_directory(path):
    skip = {'vendor', 'node_modules', '.git', 'storage', 'tests', 'mock', 'mocks', '.kiro'}
    files_to_scan = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ('.php', '.go'):
                files_to_scan.append(os.path.join(root, f))
    return files_to_scan

def export_mermaid(result, output_file):
    """Export codebase structure as Mermaid diagram"""
    lines = ['graph LR']
    seen_edges = set()

    for file_data in result.get('files', []):
        classes = file_data.get('classes', file_data.get('structs', {}))
        for name, info in classes.items():
            # Classify
            lname = (name + file_data.get('path', '')).lower()
            if 'controller' in lname:
                lines.append(f'    {name}["{name}"]:::controller')
            elif 'usecase' in lname or 'service' in lname:
                lines.append(f'    {name}["{name}"]:::usecase')
            elif 'repo' in lname:
                lines.append(f'    {name}["{name}"]:::repo')
            else:
                lines.append(f'    {name}["{name}"]')

            deps = info.get('dependencies', [])
            if not deps:
                deps = []
            if isinstance(deps, dict):
                deps = list(deps.values())
            for dep in deps:
                dep_clean = dep.replace('*', '').split('.')[-1]
                edge_key = f"{name}-->{dep_clean}"
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    lines.append(f'    {name} --> {dep_clean}')

    lines.append('')
    lines.append('    classDef controller fill:#1f6feb33,stroke:#58a6ff')
    lines.append('    classDef usecase fill:#2ea04333,stroke:#3fb950')
    lines.append('    classDef repo fill:#a371f733,stroke:#bc8cff')

    with open(output_file, 'w') as f:
        f.write('\n'.join(lines))

def main():
    output = None
    target = None
    json_only = False
    diff_branch = None
    mermaid_out = None

    args = sys.argv[1:]
    if not args or '--help' in args or '-h' in args:
        print("Codebase Explorer - Interactive AST visualization")
        print("")
        print("Usage: python3 explore.py <directory> [options]")
        print("")
        print("Options:")
        print("  --output FILE    Output HTML file (default: explorer_output.html)")
        print("  --json           Output raw JSON only (no HTML)")
        print("  --diff BRANCH    Highlight changed files vs branch")
        print("  --mermaid FILE   Export Mermaid diagram to file")
        print("  --help, -h       Show this help")
        print("")
        print("Examples:")
        print("  python3 explore.py ./app")
        print("  python3 explore.py ./app --output my_project.html")
        print("  python3 explore.py ./app --diff main")
        print("  python3 explore.py ./app --mermaid diagram.mmd")
        print("  python3 explore.py ./app --json > structure.json")
        sys.exit(0)

    i = 0
    while i < len(args):
        if args[i] == '--output' and i + 1 < len(args):
            output = args[i + 1]
            i += 2
        elif args[i] == '--json':
            json_only = True
            i += 1
        elif args[i] == '--diff' and i + 1 < len(args):
            diff_branch = args[i + 1]
            i += 2
        elif args[i] == '--mermaid' and i + 1 < len(args):
            mermaid_out = args[i + 1]
            i += 2
        else:
            target = args[i]
            i += 1

    if not target:
        print("Error: specify a directory to scan")
        sys.exit(1)

    if not output and not json_only:
        output = 'explorer_output.html'

    ensure_go_binaries()

    files_to_scan = scan_directory(target)
    total = len(files_to_scan)
    print(f"🔍 Scanning: {target}", file=sys.stderr)
    print(f"📂 Found {total} source files", file=sys.stderr)

    result = {"project": os.path.basename(os.path.abspath(target)), "projectRoot": os.path.abspath(target), "files": [], "routes": []}

    for idx, filepath in enumerate(files_to_scan, 1):
        if idx % 10 == 0 or idx == total:
            print(f"\r⏳ Extracting structure... {idx}/{total} ({idx*100//total}%)", end='', file=sys.stderr)

        ext = os.path.splitext(filepath)[1].lower()
        rel_path = os.path.relpath(filepath, target)

        if ext == '.php':
            data = extract_php(filepath)
            if data and (data.get('classes') or data.get('functions')):
                result['files'].append({'path': rel_path, 'lang': 'php', 'classes': data.get('classes', {}), 'functions': data.get('functions', {})})
        elif ext == '.go':
            data = extract_go(filepath)
            if data and (data.get('structs') or data.get('functions')):
                result['files'].append({'path': rel_path, 'lang': 'go', 'structs': data.get('structs', {}), 'functions': data.get('functions', {})})

    print(file=sys.stderr)

    # Extract complexity
    print("⏳ Calculating complexity...", file=sys.stderr)
    for idx, filepath in enumerate(files_to_scan, 1):
        if idx % 20 == 0 or idx == total:
            print(f"\r⏳ Complexity... {idx}/{total} ({idx*100//total}%)", end='', file=sys.stderr)
        rel_path = os.path.relpath(filepath, target)
        complexity = extract_complexity(filepath)
        if complexity:
            # Attach complexity to matching file entry
            for f in result['files']:
                if f['path'] == rel_path:
                    f['complexity'] = complexity
                    break
    print(file=sys.stderr)

    # Extract routes
    print("🛤  Extracting routes...", file=sys.stderr)
    result['routes'] = extract_routes(target)
    print(f"   Found {len(result['routes'])} routes", file=sys.stderr)

    # Extract infra (services, tables, kafka)
    print("🔗 Extracting services & DB tables...", file=sys.stderr)
    infra_r = subprocess.run(['python3', INFRA_EXTRACTOR, os.path.abspath(os.path.join(target, '..'))], capture_output=True, text=True)
    if infra_r.returncode == 0:
        try:
            infra = json.loads(infra_r.stdout)
            result['services'] = infra.get('services', {})
            result['tables'] = infra.get('tables', {})
            result['kafka_topics'] = infra.get('kafka_topics', {})
            print(f"   {len(result['services'])} services, {len(result['tables'])} tables, {len(result['kafka_topics'])} kafka topics", file=sys.stderr)
        except:
            result['services'] = {}
            result['tables'] = {}
            result['kafka_topics'] = {}

    # Diff mode: if --diff branch provided, get changed files
    if diff_branch:
        print(f"📊 Comparing with branch: {diff_branch}...", file=sys.stderr)
        project_root = os.path.abspath(os.path.join(target, '..'))
        diff_r = subprocess.run(['git', 'diff', '--name-only', diff_branch], capture_output=True, text=True, cwd=project_root)
        if diff_r.returncode == 0:
            changed = set(diff_r.stdout.strip().split('\n'))
            result['changed_files'] = list(changed)
            print(f"   {len(changed)} files changed", file=sys.stderr)
        else:
            result['changed_files'] = []

    # Mermaid export
    if mermaid_out:
        print(f"📐 Exporting Mermaid diagram...", file=sys.stderr)
        export_mermaid(result, mermaid_out)
        print(f"   Saved to: {mermaid_out}", file=sys.stderr)

    if json_only:
        print(json.dumps(result, indent=2))
        return

    # Generate HTML with embedded data
    with open(VISUALIZER, 'r') as f:
        html = f.read()

    # Inline D3.js
    d3_path = os.path.join(SCRIPT_DIR, 'd3.min.js')
    if os.path.exists(d3_path):
        with open(d3_path, 'r') as f:
            d3_code = f.read()
        html = html.replace('<script src="https://d3js.org/d3.v7.min.js"></script>', f'<script>{d3_code}</script>')

    # Embed JSON data into HTML
    json_data = json.dumps(result)
    html = html.replace('/*__DATA__*/null', json_data)

    with open(output, 'w') as f:
        f.write(html)

    file_count = len(result['files'])
    class_count = sum(len(f.get('classes', f.get('structs', {}))) for f in result['files'])
    print(f"\n✅ Done! Generated: {output}", file=sys.stderr)
    print(f"   {file_count} files, {class_count} classes/structs extracted", file=sys.stderr)
    print(f"   {len(result['routes'])} API routes mapped", file=sys.stderr)
    print(f"   Open in browser: file://{os.path.abspath(output)}", file=sys.stderr)

if __name__ == '__main__':
    main()
