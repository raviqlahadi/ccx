#!/usr/bin/env python3
"""
Cognitive Complexity Calculator (AST-based, SonarQube-compatible)
Uses nikic/php-parser for PHP and go/ast for Go.

Usage: ccx <file_or_directory> [--threshold N] [--quick]
"""

import json
import os
import re
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PHP_ANALYZER = os.path.join(SCRIPT_DIR, 'analyze_php.php')
GO_BINARY = os.path.join(SCRIPT_DIR, 'analyze_go')
REGEX_SCRIPT = os.path.join(SCRIPT_DIR, 'quick_scan.py')

def ensure_go_binary():
    """Compile Go analyzer if not already built."""
    src = os.path.join(SCRIPT_DIR, 'analyze_go.go')
    if not os.path.exists(GO_BINARY) or os.path.getmtime(src) > os.path.getmtime(GO_BINARY):
        print("⚙  Compiling Go analyzer...", file=sys.stderr)
        result = subprocess.run(
            ['go', 'build', '-o', GO_BINARY, src],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"Error building Go analyzer: {result.stderr}", file=sys.stderr)
            return False
    return True

def analyze_php(filepath):
    result = subprocess.run(
        ['php', PHP_ANALYZER, filepath],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

def analyze_go(filepath):
    result = subprocess.run(
        [GO_BINARY, filepath],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

def scan_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.php':
        return [(r, filepath) for r in analyze_php(filepath)]
    elif ext == '.go':
        return [(r, filepath) for r in analyze_go(filepath)]
    return []

def scan_directory(path):
    skip = {'vendor', 'node_modules', '.git', 'storage', 'tests', 'mock', 'mocks'}
    # First pass: count files
    files_to_scan = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ('.php', '.go'):
                files_to_scan.append(os.path.join(root, f))

    total = len(files_to_scan)
    print(f"📂 Found {total} files to analyze", file=sys.stderr)

    results = []
    for idx, filepath in enumerate(files_to_scan, 1):
        if idx % 10 == 0 or idx == total:
            print(f"\r⏳ Analyzing... {idx}/{total} ({idx*100//total}%)", end='', file=sys.stderr)
        results.extend(scan_file(filepath))

    print(file=sys.stderr)  # newline after progress
    return results

def main():
    threshold = 15
    target = None
    quick = False

    args = sys.argv[1:]

    if not args or '--help' in args or '-h' in args:
        print("CCX - Cognitive Complexity Analyzer")
        print("")
        print("Usage: ccx <file_or_directory> [options]")
        print("")
        print("Options:")
        print("  --threshold N  Only show functions with complexity >= N (default: 15)")
        print("  --quick        Use fast regex-based scan (less accurate)")
        print("  --help, -h     Show this help message")
        print("")
        print("Examples:")
        print("  ccx app/")
        print("  ccx controller.php --threshold 10")
        print("  ccx app/ --quick")
        print("  git diff --name-only | xargs ccx")
        sys.exit(0)

    i = 0
    while i < len(args):
        if args[i] == '--threshold' and i + 1 < len(args):
            threshold = int(args[i + 1])
            i += 2
        elif args[i] == '--quick':
            quick = True
            i += 1
        else:
            target = args[i]
            i += 1

    # Quick mode: delegate to regex script
    if quick:
        if not target:
            print("Error: no file or directory specified")
            sys.exit(1)
        os.execvp('python3', ['python3', REGEX_SCRIPT, target, '--threshold', str(threshold)])

    if not target:
        print("Error: no file or directory specified. Run ccx --help for usage.")
        sys.exit(1)

    if not ensure_go_binary():
        print("Warning: Go analyzer unavailable, skipping .go files", file=sys.stderr)

    print(f"🔍 Scanning: {target}", file=sys.stderr)

    if os.path.isfile(target):
        results = scan_file(target)
    elif os.path.isdir(target):
        results = scan_directory(target)
    else:
        print(f"Error: {target} not found")
        sys.exit(1)

    # Filter and sort
    violations = [(r, f) for r, f in results if r['complexity'] >= threshold]
    violations.sort(key=lambda x: x[0]['complexity'], reverse=True)

    all_results = results

    if violations:
        print(f"\n{'='*80}")
        print(f" COGNITIVE COMPLEXITY REPORT (threshold: {threshold}) [AST-based]")
        print(f"{'='*80}")
        print(f"\n {'Complexity':<12} {'Function':<40} {'Location'}")
        print(f" {'-'*10:<12} {'-'*38:<40} {'-'*40}")
        for r, filepath in violations:
            rel = os.path.relpath(filepath)
            print(f" {r['complexity']:<12} {r['name']:<40} {rel}:{r['line']}")
        print(f"\n Total violations: {len(violations)}")
        print(f" Total functions scanned: {len(all_results)}")
    else:
        print(f"\n✅ No cognitive complexity violations (threshold: {threshold})")
        print(f"   Scanned {len(all_results)} functions")

    if all_results:
        avg = sum(r['complexity'] for r, _ in all_results) / len(all_results)
        max_r = max(all_results, key=lambda x: x[0]['complexity'])
        print(f"\n   Average complexity: {avg:.1f}")
        print(f"   Highest: {max_r[0]['name']} = {max_r[0]['complexity']} ({os.path.relpath(max_r[1])}:{max_r[0]['line']})")

if __name__ == '__main__':
    main()
