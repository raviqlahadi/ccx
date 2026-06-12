#!/usr/bin/env python3
"""
Cognitive Complexity Calculator (SonarQube-compatible)
Supports: PHP and Go
Usage: python3 cognitive_complexity.py <file_or_directory> [--threshold N]
"""

import re
import sys
import os
from dataclasses import dataclass, field

@dataclass
class FunctionComplexity:
    name: str
    file: str
    line: int
    complexity: int

def detect_language(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.php':
        return 'php'
    elif ext == '.go':
        return 'go'
    return None

def calculate_cognitive_complexity(filepath):
    lang = detect_language(filepath)
    if not lang:
        return []

    with open(filepath, 'r', errors='ignore') as f:
        lines = f.readlines()

    if lang == 'php':
        return _calc_php(lines, filepath)
    elif lang == 'go':
        return _calc_go(lines, filepath)

def _calc_php(lines, filepath):
    results = []
    # Find functions/methods
    func_pattern = re.compile(r'(?:public|private|protected|static|\s)*\s*function\s+(\w+)\s*\(')
    functions = []
    brace_depth = 0
    current_func = None
    func_start_depth = 0

    for i, line in enumerate(lines):
        stripped = _strip_strings_and_comments(line)
        match = func_pattern.search(stripped)
        if match and current_func is None:
            current_func = {'name': match.group(1), 'line': i + 1, 'start': i, 'lines': []}
            func_start_depth = brace_depth

        if current_func:
            current_func['lines'].append(line)

        brace_depth += stripped.count('{') - stripped.count('}')

        if current_func and brace_depth <= func_start_depth and '{' in ''.join(lines[current_func['start']:i+1]):
            complexity = _compute_complexity_php(current_func['lines'])
            results.append(FunctionComplexity(
                name=current_func['name'], file=filepath,
                line=current_func['line'], complexity=complexity
            ))
            current_func = None

    return results

def _calc_go(lines, filepath):
    results = []
    func_pattern = re.compile(r'^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(')
    current_func = None
    brace_depth = 0
    func_start_depth = 0

    for i, line in enumerate(lines):
        stripped = _strip_strings_and_comments(line)
        match = func_pattern.search(stripped)
        if match and current_func is None:
            current_func = {'name': match.group(1), 'line': i + 1, 'start': i, 'lines': []}
            func_start_depth = brace_depth

        if current_func:
            current_func['lines'].append(line)

        brace_depth += stripped.count('{') - stripped.count('}')

        if current_func and brace_depth <= func_start_depth and i > current_func['start']:
            complexity = _compute_complexity_go(current_func['lines'])
            results.append(FunctionComplexity(
                name=current_func['name'], file=filepath,
                line=current_func['line'], complexity=complexity
            ))
            current_func = None

    return results

def _strip_strings_and_comments(line):
    # Remove single-line comments
    line = re.sub(r'//.*$', '', line)
    line = re.sub(r'#.*$', '', line)
    # Remove string literals (simple approach)
    line = re.sub(r'"(?:[^"\\]|\\.)*"', '""', line)
    line = re.sub(r"'(?:[^'\\]|\\.)*'", "''", line)
    return line

def _compute_complexity_php(lines):
    complexity = 0
    nesting = 0
    in_block_comment = False

    # Patterns that increment complexity + nesting penalty
    flow_break = re.compile(r'\b(if|else\s*if|elseif|for|foreach|while|catch)\b')
    # Patterns that only increment (no nesting penalty)
    flat_increment = re.compile(r'\b(else|switch)\b')
    # Logical operators
    logical_ops = re.compile(r'(\&\&|\|\||(\band\b)|(\bor\b))')
    # Nesting structures
    nesting_open = re.compile(r'\b(if|else\s*if|elseif|else|for|foreach|while|switch|try|catch)\b')

    prev_logical = None

    for line in lines:
        # Handle block comments
        if in_block_comment:
            if '*/' in line:
                in_block_comment = False
                line = line[line.index('*/') + 2:]
            else:
                continue
        if '/*' in line:
            in_block_comment = True
            line = line[:line.index('/*')]

        stripped = _strip_strings_and_comments(line).strip()
        if not stripped:
            continue

        # Count logical operator sequences (each switch in operator type = +1)
        for match in logical_ops.finditer(stripped):
            op = match.group(1)
            if op in ('and', 'or'):
                op = '&&' if op == 'and' else '||'
            if op != prev_logical:
                complexity += 1
                prev_logical = op
        if not logical_ops.search(stripped):
            prev_logical = None

        # Flow-breaking: +1 + nesting
        for match in flow_break.finditer(stripped):
            complexity += 1 + nesting

        # Flat increment: +1 only
        for match in flat_increment.finditer(stripped):
            keyword = match.group(1).strip()
            if keyword == 'else' and not re.search(r'\belse\s*if\b', stripped):
                complexity += 1
            elif keyword == 'switch':
                complexity += 1 + nesting

        # Update nesting
        opens = stripped.count('{')
        closes = stripped.count('}')
        # Only count nesting for control structures
        if nesting_open.search(stripped) and opens > 0:
            nesting += 1
            opens -= 1
        nesting += opens - closes
        nesting = max(0, nesting)

    return complexity

def _compute_complexity_go(lines):
    complexity = 0
    nesting = 0
    in_block_comment = False

    flow_break = re.compile(r'\b(if|else\s+if|for|select)\b')
    flat_increment = re.compile(r'\b(else|switch)\b')
    logical_ops = re.compile(r'(\&\&|\|\|)')
    nesting_open = re.compile(r'\b(if|else\s+if|else|for|switch|select|func)\b')

    prev_logical = None

    for line in lines:
        if in_block_comment:
            if '*/' in line:
                in_block_comment = False
                line = line[line.index('*/') + 2:]
            else:
                continue
        if '/*' in line:
            in_block_comment = True
            line = line[:line.index('/*')]

        stripped = _strip_strings_and_comments(line).strip()
        if not stripped:
            continue

        # Logical operators
        for match in logical_ops.finditer(stripped):
            op = match.group(1)
            if op != prev_logical:
                complexity += 1
                prev_logical = op
        if not logical_ops.search(stripped):
            prev_logical = None

        # Flow-breaking: +1 + nesting
        for match in flow_break.finditer(stripped):
            keyword = match.group(1)
            if keyword == 'else if':
                complexity += 1  # else if only +1, no nesting penalty per SonarQube
            else:
                complexity += 1 + nesting

        # Flat increment
        for match in flat_increment.finditer(stripped):
            keyword = match.group(1).strip()
            if keyword == 'else' and 'else if' not in stripped:
                complexity += 1
            elif keyword == 'switch':
                complexity += 1 + nesting

        # Update nesting
        opens = stripped.count('{')
        closes = stripped.count('}')
        if nesting_open.search(stripped) and opens > 0:
            nesting += 1
            opens -= 1
        nesting += opens - closes
        nesting = max(0, nesting)

    return complexity

def scan_directory(path, threshold=15):
    results = []
    for root, dirs, files in os.walk(path):
        # Skip vendor/node_modules
        dirs[:] = [d for d in dirs if d not in ('vendor', 'node_modules', '.git', 'storage', 'tests')]
        for f in files:
            filepath = os.path.join(root, f)
            if detect_language(filepath):
                results.extend(calculate_cognitive_complexity(filepath))
    return results

def main():
    threshold = 15
    target = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--threshold' and i + 1 < len(args):
            threshold = int(args[i + 1])
            i += 2
        else:
            target = args[i]
            i += 1

    if not target:
        print("Usage: python3 cognitive_complexity.py <file_or_directory> [--threshold N]")
        print("  --threshold N  Only show functions with complexity >= N (default: 15)")
        sys.exit(1)

    if os.path.isfile(target):
        results = calculate_cognitive_complexity(target)
    elif os.path.isdir(target):
        results = scan_directory(target, threshold)
    else:
        print(f"Error: {target} not found")
        sys.exit(1)

    # Filter and sort
    violations = [r for r in results if r.complexity >= threshold]
    violations.sort(key=lambda x: x.complexity, reverse=True)

    if violations:
        print(f"\n{'='*80}")
        print(f" COGNITIVE COMPLEXITY REPORT (threshold: {threshold})")
        print(f"{'='*80}")
        print(f"\n {'Complexity':<12} {'Function':<40} {'Location'}")
        print(f" {'-'*10:<12} {'-'*38:<40} {'-'*40}")
        for v in violations:
            rel_path = os.path.relpath(v.file, os.getcwd()) if os.path.isabs(v.file) else v.file
            print(f" {v.complexity:<12} {v.name:<40} {rel_path}:{v.line}")
        print(f"\n Total violations: {len(violations)}")
        print(f" Total functions scanned: {len(results)}")
    else:
        print(f"\n✅ No cognitive complexity violations (threshold: {threshold})")
        print(f"   Scanned {len(results)} functions")

    # Summary stats
    if results:
        avg = sum(r.complexity for r in results) / len(results)
        max_r = max(results, key=lambda x: x.complexity)
        print(f"\n   Average complexity: {avg:.1f}")
        print(f"   Highest: {max_r.name} = {max_r.complexity} ({os.path.relpath(max_r.file)}:{max_r.line})")

if __name__ == '__main__':
    main()
