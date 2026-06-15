# CCX - Cognitive Complexity & Codebase Explorer

CLI toolkit for PHP and Go projects: calculates cognitive complexity (SonarQube-compatible) and generates interactive codebase visualizations.

## Features

### `ccx` — Cognitive Complexity Analyzer
- AST-based analysis using `nikic/php-parser` and `go/ast`
- Fast regex mode (`--quick`) for instant feedback
- SonarQube-compatible scoring
- Progress indicator for large codebases

### `explore` — Codebase Explorer
- Interactive HTML visualization (D3.js force graph)
- Route mapping (Laravel/Lumen + Go/Goravel)
- Complexity heatmap (green → red per class)
- Layer grouping (Controllers / Usecases / Repos)
- Service-to-service map (from .env URLs)
- DB table extraction (`DB::table()` + Go `TableName()`)
- Kafka topic detection
- Filter by layer (toggle visibility)
- VS Code click-to-open links (`vscode://file/...`)
- Diff mode (highlight changed files vs branch)
- Mermaid diagram export
- Dependency direction arrows

### `ccx-analyze` — Code Analysis Tools
- **Request Trace** — follow an API endpoint through the full call chain down to DB tables
- **Impact Analysis** — see all upstream callers of a function + which routes are affected
- **Dead Code Detector** — find functions unreachable from any route

## Requirements

- Python 3.6+
- PHP 7.4+ with `nikic/php-parser`
- Go 1.18+

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/ccx.git ~/ccx

# 2. Build Go binaries
cd ~/ccx && make build

# 3. PHP parser (symlink from any Laravel project, or install)
cd ~/ccx/php && ln -s ~/your-laravel-project/vendor vendor
# OR: composer require nikic/php-parser

# 4. Download D3.js for explorer
curl -sL https://d3js.org/d3.v7.min.js -o ~/ccx/web/d3.min.js

# 5. Add aliases
echo 'alias ccx="python3 ~/ccx/ccx.py"' >> ~/.bashrc
echo 'alias explore="python3 ~/ccx/explore.py"' >> ~/.bashrc
echo 'alias ccx-analyze="python3 ~/ccx/analyze.py"' >> ~/.bashrc
source ~/.bashrc
```

## Usage

### Cognitive Complexity

```bash
# Scan a directory (AST-based, shows progress)
ccx app/

# Scan a single file
ccx app/Http/Controllers/SomeController.php

# Custom threshold (default: 15, same as SonarQube)
ccx app/ --threshold 10

# Quick regex scan (instant, less accurate)
ccx app/ --quick

# Check changed files before commit
git diff --name-only | xargs ccx

# Help
ccx --help
```

### Codebase Explorer

```bash
# Generate interactive HTML visualization
explore app/

# Custom output file
explore app/ --output my_project.html

# Highlight changes vs a branch
explore app/ --diff main

# Export Mermaid diagram
explore app/ --mermaid architecture.mmd

# JSON output (for Kiro steering, docs, or other tools)
explore app/ --json > structure.json

# Help
explore --help
```

Then open the generated HTML in your browser.

### Code Analysis (Trace, Impact, Dead Code)

```bash
# Trace a request through the full call chain
# Route → Controller → Usecase → Repository → DB Tables
ccx-analyze app/ trace /v1/createPenagihan
ccx-analyze app/ trace createKunjungan        # partial match works

# Impact analysis: "what breaks if I change this?"
ccx-analyze app/ impact ActivityRepository.setActivity
ccx-analyze app/ impact insertLKNPemasaranDanaDirect  # method name only

# Find dead code (unreachable from any route)
ccx-analyze app/ deadcode

# Help
ccx-analyze --help
```

### Explorer UI Controls

| Button | Action |
|--------|--------|
| **Graph** | Default force-directed layout |
| **🔥 Heatmap** | Color nodes by max cognitive complexity |
| **📦 Layers** | Group nodes by layer (Controller/Usecase/Repo) |
| **📐 Mermaid** | Copy Mermaid diagram to clipboard |
| **↺ Reset** | Reset view and deselect |
| **Filter buttons** | Toggle layer visibility |

- Click a node → see methods, routes, DB tables, dependencies, complexity scores
- Click a dependency → navigate to that class
- Method names link to VS Code (`vscode://file/...`)
- Search box filters classes, routes, and tables

## File Structure

```
ccx/
├── Makefile                # make build / make clean / make install
├── README.md
├── .gitignore
├── ccx.py                  # CLI: complexity checker
├── explore.py              # CLI: explorer + HTML generator
├── analyze.py              # CLI: trace / impact / deadcode
├── quick_scan.py           # CLI: fast regex scan
├── bin/                    # Compiled Go binaries (gitignored)
│   ├── complexity_go
│   ├── extract_go
│   └── extract_routes_go
├── cmd/                    # Go sources
│   ├── complexity_go.go
│   ├── extract_go.go
│   └── extract_routes_go.go
├── php/                    # PHP scripts
│   ├── complexity.php
│   ├── extract_structure.php
│   └── extract_routes.php
├── lib/                    # Shared Python modules
│   ├── graph.py            # Call graph builder + JSON cache
│   └── extract_infra.py    # Service/DB/Kafka extractor
└── web/
    ├── visualizer.html     # D3.js interactive template
    └── d3.min.js           # Bundled D3 (no CDN needed)
```

### Caching

`ccx-analyze` and `explore` cache the extracted data at `~/.cache/ccx/`. Cache auto-invalidates when any source file in the project changes. Second runs are instant (~40ms vs minutes).

Clear cache manually: `make clean`

## How Cognitive Complexity Works

Per [SonarQube's specification](https://www.sonarsource.com/docs/CognitiveComplexity.pdf):

1. **+1** for each control flow break: `if`, `for`, `while`, `switch`, `catch`
2. **+1 nesting penalty** for each level deep
3. **+1** per logical operator sequence switch (`&&` → `||`)
4. **+1** for `else`, `else if` (no nesting penalty)
5. **+1** for `goto`, `break N`, `continue N`

```php
function example($a, $b) {              // 0
    if ($a) {                           // +1 (nesting 0)
        for ($i = 0; $i < 10; $i++) {   // +2 (nesting 1)
            if ($b) {                   // +3 (nesting 2)
                return;
            }
        }
    }
}                                       // Total: 6
```

## License

MIT
