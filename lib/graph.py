"""
Shared call graph builder with JSON file caching.
Used by explore.py and analyze.py.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, 'bin')
PHP_DIR = os.path.join(ROOT, 'php')
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT, 'web')

CACHE_DIR = os.path.expanduser('~/.cache/ccx')

def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)

def _cache_key(target_dir):
    """Generate cache key from directory path + mtime of newest file"""
    abs_path = os.path.abspath(target_dir)
    latest = 0
    skip = {'vendor', 'node_modules', '.git', 'storage', 'tests', 'mock', 'mocks', '.kiro'}
    for root, dirs, files in os.walk(abs_path):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ('.php', '.go'):
                mtime = os.path.getmtime(os.path.join(root, f))
                if mtime > latest:
                    latest = mtime
    key_str = f"{abs_path}:{latest}"
    return hashlib.md5(key_str.encode()).hexdigest()

def get_cached(target_dir):
    """Return cached JSON data if valid, else None"""
    _ensure_cache_dir()
    key = _cache_key(target_dir)
    cache_file = os.path.join(CACHE_DIR, f"{key}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return None

def save_cache(target_dir, data):
    """Save data to cache"""
    _ensure_cache_dir()
    key = _cache_key(target_dir)
    cache_file = os.path.join(CACHE_DIR, f"{key}.json")
    with open(cache_file, 'w') as f:
        json.dump(data, f)

def scan_files(path):
    """Find all PHP/Go source files"""
    skip = {'vendor', 'node_modules', '.git', 'storage', 'tests', 'mock', 'mocks', '.kiro'}
    files = []
    for root, dirs, filenames in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if ext in ('.php', '.go'):
                files.append(os.path.join(root, f))
    return files

def extract_structure_php(filepath):
    r = subprocess.run(['php', os.path.join(PHP_DIR, 'extract_structure.php'), filepath], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except:
        return None

def extract_structure_go(filepath):
    binary = os.path.join(BIN, 'extract_go')
    r = subprocess.run([binary, filepath], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except:
        return None

def extract_complexity_php(filepath):
    r = subprocess.run(['php', os.path.join(PHP_DIR, 'complexity.php'), filepath], capture_output=True, text=True)
    if r.returncode != 0:
        return {}
    try:
        return {item['name']: item['complexity'] for item in json.loads(r.stdout)}
    except:
        return {}

def extract_complexity_go(filepath):
    binary = os.path.join(BIN, 'complexity_go')
    r = subprocess.run([binary, filepath], capture_output=True, text=True)
    if r.returncode != 0:
        return {}
    try:
        return {item['name']: item['complexity'] for item in json.loads(r.stdout)}
    except:
        return {}

def extract_routes(target):
    """Extract routes from routes/ directory"""
    routes_dir = None
    for candidate in [os.path.join(target, 'routes'), os.path.join(target, '..', 'routes')]:
        if os.path.isdir(candidate):
            routes_dir = os.path.abspath(candidate)
            break
    if not routes_dir:
        return []

    routes = []
    php_files = [f for f in os.listdir(routes_dir) if f.endswith('.php')]
    if php_files:
        r = subprocess.run(['php', os.path.join(PHP_DIR, 'extract_routes.php'), routes_dir], capture_output=True, text=True)
        if r.returncode == 0:
            try:
                routes.extend(json.loads(r.stdout))
            except:
                pass

    go_files = [f for f in os.listdir(routes_dir) if f.endswith('.go')]
    if go_files:
        binary = os.path.join(BIN, 'extract_routes_go')
        if os.path.exists(binary):
            r = subprocess.run([binary, routes_dir], capture_output=True, text=True)
            if r.returncode == 0:
                try:
                    routes.extend(json.loads(r.stdout))
                except:
                    pass
    return routes

def extract_infra(project_dir):
    r = subprocess.run(['python3', os.path.join(LIB_DIR, 'extract_infra.py'), project_dir], capture_output=True, text=True)
    if r.returncode == 0:
        try:
            return json.loads(r.stdout)
        except:
            pass
    return {'services': {}, 'tables': {}, 'kafka_topics': {}}

def build_project_data(target, progress=True, with_complexity=True):
    """Full extraction: structure + complexity + routes + infra. Uses cache."""
    cached = get_cached(target)
    if cached:
        if progress:
            print("⚡ Using cached data (files unchanged)", file=sys.stderr)
        return cached

    files_to_scan = scan_files(target)
    total = len(files_to_scan)
    if progress:
        print(f"🔍 Scanning: {target}", file=sys.stderr)
        print(f"📂 Found {total} source files", file=sys.stderr)

    result = {"project": os.path.basename(os.path.abspath(target)), "projectRoot": os.path.abspath(target), "files": [], "routes": []}

    for idx, filepath in enumerate(files_to_scan, 1):
        if progress and (idx % 10 == 0 or idx == total):
            print(f"\r⏳ Extracting... {idx}/{total} ({idx*100//total}%)", end='', file=sys.stderr)

        ext = os.path.splitext(filepath)[1].lower()
        rel_path = os.path.relpath(filepath, target)

        if ext == '.php':
            data = extract_structure_php(filepath)
            if data and (data.get('classes') or data.get('functions')):
                entry = {'path': rel_path, 'lang': 'php', 'classes': data.get('classes', {}), 'functions': data.get('functions', {})}
                if with_complexity:
                    entry['complexity'] = extract_complexity_php(filepath)
                result['files'].append(entry)
        elif ext == '.go':
            data = extract_structure_go(filepath)
            if data and (data.get('structs') or data.get('functions')):
                entry = {'path': rel_path, 'lang': 'go', 'structs': data.get('structs', {}), 'functions': data.get('functions', {})}
                if with_complexity:
                    entry['complexity'] = extract_complexity_go(filepath)
                result['files'].append(entry)

    if progress:
        print(file=sys.stderr)

    # Routes
    if progress:
        print("🛤  Extracting routes...", file=sys.stderr)
    result['routes'] = extract_routes(target)
    if progress:
        print(f"   Found {len(result['routes'])} routes", file=sys.stderr)

    # Infra
    if progress:
        print("🔗 Extracting services & DB tables...", file=sys.stderr)
    infra = extract_infra(os.path.abspath(os.path.join(target, '..')))
    result['services'] = infra.get('services', {})
    result['tables'] = infra.get('tables', {})
    result['kafka_topics'] = infra.get('kafka_topics', {})
    if progress:
        print(f"   {len(result['services'])} services, {len(result['tables'])} tables", file=sys.stderr)

    save_cache(target, result)
    return result
