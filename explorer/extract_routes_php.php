#!/usr/bin/env php
<?php
/**
 * Route extractor for Laravel/Lumen projects
 * Parses routes/ files and outputs JSON with route -> controller mapping
 */

if ($argc < 2) {
    fwrite(STDERR, "Usage: php extract_routes_php.php <routes_directory>\n");
    exit(1);
}

$dir = $argv[1];
$routes = [];

foreach (glob("$dir/*.php") as $file) {
    $content = file_get_contents($file);
    
    // Match: $router->method('uri', 'Controller@method')
    // Match: $router->method('uri', ['uses' => 'Controller@method'])
    preg_match_all(
        '/\$router->(get|post|put|patch|delete)\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*(?:' .
        '[\'"]([^@\'"]+)@([^\'"]+)[\'"]' .  // direct: 'Controller@method'
        '|' .
        '\[.*?[\'"]uses[\'"]\s*=>\s*[\'"]([^@\'"]+)@([^\'"]+)[\'"].*?\]' . // array: ['uses' => 'Controller@method']
        ')/s',
        $content,
        $matches,
        PREG_SET_ORDER
    );

    // Get prefix from group
    $prefixes = [];
    preg_match_all(
        '/group\s*\(\s*\[\s*[\'"]prefix[\'"]\s*=>\s*[\'"]([^\'"]+)[\'"]/',
        $content,
        $prefixMatches
    );
    
    foreach ($matches as $m) {
        $method = strtoupper($m[1]);
        $uri = $m[2];
        $controller = !empty($m[3]) ? $m[3] : (!empty($m[5]) ? $m[5] : '');
        $action = !empty($m[4]) ? $m[4] : (!empty($m[6]) ? $m[6] : '');
        
        // Clean controller name
        $controller = str_replace('App\\Http\\Controllers\\', '', $controller);
        
        $routes[] = [
            'method' => $method,
            'uri' => $uri,
            'controller' => $controller,
            'action' => $action,
            'file' => basename($file),
        ];
    }
}

// Try to resolve prefixes by re-parsing with context
$content = '';
foreach (glob("$dir/*.php") as $file) {
    $content .= file_get_contents($file) . "\n";
}

// Find group prefixes and their routes
$finalRoutes = [];
$lines = explode("\n", $content);
$currentPrefix = '';

foreach ($lines as $line) {
    if (preg_match('/group\s*\(\s*\[\s*[\'"]prefix[\'"]\s*=>\s*[\'"]([^\'"]+)[\'"]/', $line, $pm)) {
        $currentPrefix = $pm[1];
    }
    if (preg_match('/\$router->(get|post|put|patch|delete)\s*\(\s*[\'"]([^\'"]+)[\'"]/', $line, $rm)) {
        $uri = $rm[2];
        if ($currentPrefix && strpos($uri, '/') === 0) {
            // uri already absolute
        } elseif ($currentPrefix) {
            $uri = '/' . $currentPrefix . '/' . ltrim($uri, '/');
        }
        // Find this route in our matches
        foreach ($routes as &$r) {
            if ($r['uri'] === $rm[2] && strtolower($r['method']) === $rm[1]) {
                $r['uri'] = $uri;
                break;
            }
        }
    }
    if (preg_match('/\}\s*\)\s*;/', $line)) {
        // Could be end of group, but simple heuristic
    }
}

echo json_encode($routes);
