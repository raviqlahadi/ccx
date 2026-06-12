# CCX - Cognitive Complexity Analyzer

A CLI tool to calculate [Cognitive Complexity](https://www.sonarsource.com/docs/CognitiveComplexity.pdf) for PHP and Go files, compatible with SonarQube's metric.

## Features

- **AST-based analysis** (default) — uses `nikic/php-parser` for PHP and `go/ast` for Go
- **Quick regex scan** — fast but less accurate, no dependencies needed
- Progress indicator for large codebases
- Configurable threshold
- Directory scanning with auto-skip of `vendor/`, `node_modules/`, `.git/`

## Requirements

- Python 3.6+
- PHP 7.4+ with `nikic/php-parser` (available via any Laravel/Lumen project's vendor)
- Go 1.18+ (for Go file analysis)

## Installation

```bash
# 1. Clone/copy the ccx folder to your home directory
cp -r ccx ~/ccx

# 2. Build the Go analyzer
cd ~/ccx && go build -o analyze_go analyze_go.go

# 3. Add alias to your shell
echo 'alias ccx="python3 ~/ccx/ccx.py"' >> ~/.bashrc
source ~/.bashrc
```

### PHP Parser Setup

The PHP analyzer requires `nikic/php-parser`. If you have any Laravel/Lumen project, it's already in your `vendor/` folder. The tool looks for autoloader in these locations:

1. `~/ccx/vendor/autoload.php`
2. Current working directory's `vendor/autoload.php`
3. Fallback: `/home/entru/BrispotProject/brispot_microservice_activity/vendor/autoload.php`

To make it work from anywhere, create a symlink:

```bash
cd ~/ccx
composer require nikic/php-parser
# OR symlink from an existing project:
ln -s ~/your-laravel-project/vendor vendor
```

## Usage

```bash
# Scan a directory (AST-based, shows progress)
ccx app/

# Scan a single file
ccx app/Http/Controllers/SomeController.php

# Set custom threshold (default: 15, same as SonarQube)
ccx app/ --threshold 10

# Quick scan (regex-based, instant, less accurate)
ccx app/ --quick

# Check only changed files before commit
git diff --name-only | xargs ccx
```

## Output Example

```
🔍 Scanning: app/
📂 Found 612 files to analyze
⏳ Analyzing... 612/612 (100%)

================================================================================
 COGNITIVE COMPLEXITY REPORT (threshold: 15) [AST-based]
================================================================================

 Complexity   Function                                 Location
 ----------   --------------------------------------   ----------------------------------------
 287          createLKNPemasaranDana                   app/Http/Controllers/V1/ActivityController.php:470
 182          createKunjungan                          app/Http/Controllers/V1/ActivityController.php:53

 Total violations: 2
 Total functions scanned: 1520

   Average complexity: 4.2
   Highest: createLKNPemasaranDana = 287 (app/Http/Controllers/V1/ActivityController.php:470)
```

## Modes

| Flag | Mode | Speed | Accuracy |
|------|------|-------|----------|
| *(default)* | AST parsing | Slower | High (SonarQube-compatible) |
| `--quick` | Regex matching | Instant | Approximate |

## File Structure

```
ccx/
├── ccx.py            # Main entry point (Python wrapper)
├── analyze_php.php   # PHP analyzer using nikic/php-parser
├── analyze_go.go     # Go analyzer source (go/ast)
├── analyze_go        # Go analyzer binary (compiled)
├── quick_scan.py     # Fast regex-based scanner
└── README.md
```

## How It Works

Cognitive complexity is calculated per SonarQube's specification:

1. **+1** for each control flow break: `if`, `for`, `while`, `switch`, `catch`, etc.
2. **+1 nesting penalty** for each level of nesting when inside another structure
3. **+1** for each logical operator sequence switch (`&&` → `||` or vice versa)
4. **+1** for `else`, `else if` (no nesting penalty)
5. **+1** for `goto`, `break N`, `continue N`

### Example

```php
function example($a, $b) {        // 0
    if ($a) {                     // +1 (nesting 0)
        for ($i = 0; $i < 10; $i++) { // +2 (nesting 1)
            if ($b) {             // +3 (nesting 2)
                return;
            }
        }
    }
}                                 // Total: 6
```
