#!/usr/bin/env python3
"""
Extract service-to-service connections and DB tables from a project.
Scans .env files for service URLs, code for HTTP calls/Kafka topics, and DB table references.
"""

import json
import os
import re
import sys

def extract_service_connections(project_dir):
    """Find service URLs from .env files"""
    services = {}
    env_files = [f for f in os.listdir(project_dir) if f.startswith('.env')]
    
    for env_file in env_files:
        path = os.path.join(project_dir, env_file)
        try:
            with open(path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if '=' not in line or line.startswith('#'):
                        continue
                    key, _, value = line.partition('=')
                    # Service URL pattern
                    if '_URL' in key and 'http' in value.lower():
                        service_name = key.replace('BRISPOT_', '').replace('_URL', '').lower()
                        services[service_name] = value
                    # Kafka topics
                    if 'TOPIC' in key:
                        services[f"kafka:{key.lower()}"] = value
        except:
            pass
    return services

def extract_db_tables_php(app_dir):
    """Extract DB::table('name') references from PHP files"""
    tables = {}  # table_name -> [files that use it]
    skip = {'vendor', 'node_modules', '.git', 'storage', 'tests'}
    
    pattern = re.compile(r"DB::table\(['\"]([^'\"]+)['\"]\)")
    
    for root, dirs, files in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            if not f.endswith('.php'):
                continue
            filepath = os.path.join(root, f)
            try:
                with open(filepath, 'r', errors='ignore') as fh:
                    content = fh.read()
                found = pattern.findall(content)
                for table in found:
                    if table not in tables:
                        tables[table] = []
                    rel = os.path.relpath(filepath, app_dir)
                    if rel not in tables[table]:
                        tables[table].append(rel)
            except:
                pass
    return tables

def extract_db_tables_go(app_dir):
    """Extract TableName() returns from Go model files"""
    tables = {}
    skip = {'vendor', 'node_modules', '.git', 'storage', 'tests'}
    
    pattern = re.compile(r'func\s+\(\w+\s+\*?(\w+)\)\s+TableName\(\)\s+string\s*\{[^}]*return\s+["\']([^"\']+)["\']', re.DOTALL)
    
    for root, dirs, files in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            if not f.endswith('.go'):
                continue
            filepath = os.path.join(root, f)
            try:
                with open(filepath, 'r', errors='ignore') as fh:
                    content = fh.read()
                for match in pattern.finditer(content):
                    model_name = match.group(1)
                    table_name = match.group(2)
                    rel = os.path.relpath(filepath, app_dir)
                    if table_name not in tables:
                        tables[table_name] = []
                    tables[table_name].append(rel)
            except:
                pass
    return tables

def extract_kafka_topics(app_dir):
    """Extract Kafka topic references from code"""
    topics = {}
    skip = {'vendor', 'node_modules', '.git', 'storage', 'tests'}
    
    patterns = [
        re.compile(r"['\"]([a-z_]+_topic[a-z_]*)['\"]", re.IGNORECASE),
        re.compile(r"topic['\"\s:=]+['\"]([^'\"]+)['\"]", re.IGNORECASE),
        re.compile(r"TOPIC[_A-Z]*['\"\s:=]+['\"]([^'\"]+)['\"]"),
    ]
    
    for root, dirs, files in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            if not (f.endswith('.php') or f.endswith('.go')):
                continue
            filepath = os.path.join(root, f)
            try:
                with open(filepath, 'r', errors='ignore') as fh:
                    content = fh.read()
                for p in patterns:
                    for match in p.finditer(content):
                        topic = match.group(1)
                        if len(topic) > 5 and '_' in topic:
                            rel = os.path.relpath(filepath, app_dir)
                            if topic not in topics:
                                topics[topic] = []
                            if rel not in topics[topic]:
                                topics[topic].append(rel)
            except:
                pass
    return topics

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 extract_infra.py <project_dir>", file=sys.stderr)
        sys.exit(1)
    
    project_dir = sys.argv[1]
    app_dir = os.path.join(project_dir, 'app') if os.path.isdir(os.path.join(project_dir, 'app')) else project_dir
    
    result = {
        'services': extract_service_connections(project_dir),
        'tables': {**extract_db_tables_php(app_dir), **extract_db_tables_go(app_dir)},
        'kafka_topics': extract_kafka_topics(app_dir),
    }
    
    print(json.dumps(result))

if __name__ == '__main__':
    main()
