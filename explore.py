#!/usr/bin/env python3
"""
Codebase Explorer - Generates an interactive visualization
Usage: explore <directory> [--output FILE] [--json] [--diff BRANCH] [--mermaid FILE]
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from lib.graph import build_project_data, ROOT as LIB_ROOT

WEB_DIR = os.path.join(ROOT, 'web')
VISUALIZER = os.path.join(WEB_DIR, 'visualizer.html')

def export_mermaid(result, output_file):
    lines = ['graph LR']
    seen_edges = set()
    for file_data in result.get('files', []):
        classes = file_data.get('classes', file_data.get('structs', {}))
        for name, info in classes.items():
            lname = (name + file_data.get('path', '')).lower()
            if 'controller' in lname:
                lines.append(f'    {name.replace(" ", "")}["{name}"]:::controller')
            elif 'usecase' in lname or 'service' in lname:
                lines.append(f'    {name.replace(" ", "")}["{name}"]:::usecase')
            elif 'repo' in lname:
                lines.append(f'    {name.replace(" ", "")}["{name}"]:::repo')
            else:
                lines.append(f'    {name.replace(" ", "")}["{name}"]')
            deps = info.get('dependencies', [])
            if not deps: deps = []
            if isinstance(deps, dict): deps = list(deps.values())
            for dep in deps:
                dep_clean = dep.replace('*', '').split('.')[-1].replace(' ', '')
                edge_key = f"{name}-->{dep_clean}"
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    lines.append(f'    {name.replace(" ", "")} --> {dep_clean}')
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
        print("Usage: explore <directory> [options]")
        print("")
        print("Options:")
        print("  --output FILE    Output HTML file (default: explorer_output.html)")
        print("  --json           Output raw JSON only (no HTML)")
        print("  --diff BRANCH    Highlight changed files vs branch")
        print("  --mermaid FILE   Export Mermaid diagram to file")
        print("  --help, -h       Show this help")
        sys.exit(0)

    i = 0
    while i < len(args):
        if args[i] == '--output' and i + 1 < len(args):
            output = args[i + 1]; i += 2
        elif args[i] == '--json':
            json_only = True; i += 1
        elif args[i] == '--diff' and i + 1 < len(args):
            diff_branch = args[i + 1]; i += 2
        elif args[i] == '--mermaid' and i + 1 < len(args):
            mermaid_out = args[i + 1]; i += 2
        else:
            target = args[i]; i += 1

    if not target:
        print("Error: specify a directory to scan"); sys.exit(1)
    if not output and not json_only:
        output = 'explorer_output.html'

    result = build_project_data(target, progress=True, with_complexity=True)

    # Diff mode
    if diff_branch:
        print(f"📊 Comparing with branch: {diff_branch}...", file=sys.stderr)
        project_root = os.path.abspath(os.path.join(target, '..'))
        diff_r = subprocess.run(['git', 'diff', '--name-only', diff_branch], capture_output=True, text=True, cwd=project_root)
        if diff_r.returncode == 0:
            changed = set(diff_r.stdout.strip().split('\n'))
            result['changed_files'] = list(changed)
            print(f"   {len(changed)} files changed", file=sys.stderr)

    # Mermaid
    if mermaid_out:
        print(f"📐 Exporting Mermaid diagram...", file=sys.stderr)
        export_mermaid(result, mermaid_out)
        print(f"   Saved to: {mermaid_out}", file=sys.stderr)

    if json_only:
        print(json.dumps(result, indent=2))
        return

    # Generate HTML
    with open(VISUALIZER, 'r') as f:
        html = f.read()
    d3_path = os.path.join(WEB_DIR, 'd3.min.js')
    if os.path.exists(d3_path):
        with open(d3_path, 'r') as f:
            d3_code = f.read()
        html = html.replace('<script src="https://d3js.org/d3.v7.min.js"></script>', f'<script>{d3_code}</script>')
    html = html.replace('/*__DATA__*/null', json.dumps(result))

    with open(output, 'w') as f:
        f.write(html)

    file_count = len(result['files'])
    class_count = sum(len(f.get('classes', f.get('structs', {}))) for f in result['files'])
    print(f"\n✅ Done! Generated: {output}", file=sys.stderr)
    print(f"   {file_count} files, {class_count} classes/structs", file=sys.stderr)
    print(f"   {len(result['routes'])} routes mapped", file=sys.stderr)
    print(f"   Open in browser: file://{os.path.abspath(output)}", file=sys.stderr)

if __name__ == '__main__':
    main()
