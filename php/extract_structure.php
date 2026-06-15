#!/usr/bin/env php
<?php
/**
 * PHP Codebase Structure Extractor
 * Extracts classes, methods, calls, and dependencies using nikic/php-parser
 * Output: JSON
 */

$autoloaders = [
    __DIR__ . '/vendor/autoload.php',
    __DIR__ . '/../vendor/autoload.php',
    getcwd() . '/vendor/autoload.php',
    '/home/entru/BrispotProject/brispot_microservice_activity/vendor/autoload.php',
];

$found = false;
foreach ($autoloaders as $al) {
    if (file_exists($al)) { require_once $al; $found = true; break; }
}
if (!$found) { fwrite(STDERR, "Cannot find autoloader\n"); exit(1); }

use PhpParser\Node;
use PhpParser\NodeTraverser;
use PhpParser\NodeVisitorAbstract;
use PhpParser\ParserFactory;

class StructureVisitor extends NodeVisitorAbstract
{
    public array $classes = [];
    public array $functions = [];
    private ?string $currentClass = null;
    private ?string $currentMethod = null;
    private array $currentCalls = [];
    private array $methods = [];
    private array $dependencies = [];
    private array $constructorParams = [];

    public function enterNode(Node $node)
    {
        if ($node instanceof Node\Stmt\Class_ || $node instanceof Node\Stmt\Trait_) {
            $this->currentClass = (string)$node->name;
            $this->methods = [];
            $this->dependencies = [];
            $this->constructorParams = [];

            // Get implements/extends
            $extends = $node instanceof Node\Stmt\Class_ && $node->extends
                ? $node->extends->toString() : null;
            $implements = [];
            if ($node instanceof Node\Stmt\Class_) {
                foreach ($node->implements as $impl) {
                    $implements[] = $impl->toString();
                }
            }
            $this->classes[$this->currentClass] = [
                'extends' => $extends,
                'implements' => $implements,
            ];
        }

        if ($node instanceof Node\Stmt\ClassMethod) {
            $this->currentMethod = (string)$node->name;
            $this->currentCalls = [];

            // Extract params
            $params = [];
            foreach ($node->params as $param) {
                $type = $param->type ? $this->resolveType($param->type) : null;
                $params[] = [
                    'name' => '$' . $param->var->name,
                    'type' => $type,
                ];
                // Constructor injection = dependency
                if ($this->currentMethod === '__construct' && $type) {
                    $this->dependencies[] = $type;
                    $this->constructorParams[] = $type;
                }
            }

            $returnType = $node->returnType ? $this->resolveType($node->returnType) : null;

            $this->methods[$this->currentMethod] = [
                'params' => $params,
                'returns' => $returnType,
                'line' => $node->getStartLine(),
                'calls' => [],
                'visibility' => $this->getVisibility($node),
            ];
        }

        // Track method calls
        if ($this->currentMethod) {
            if ($node instanceof Node\Expr\MethodCall) {
                $call = $this->resolveCall($node);
                if ($call) $this->currentCalls[] = $call;
            } elseif ($node instanceof Node\Expr\StaticCall) {
                $class = $node->class instanceof Node\Name ? $node->class->toString() : null;
                $method = $node->name instanceof Node\Identifier ? (string)$node->name : null;
                if ($class && $method) {
                    $this->currentCalls[] = "$class::$method";
                }
            } elseif ($node instanceof Node\Expr\FuncCall) {
                if ($node->name instanceof Node\Name) {
                    $this->currentCalls[] = $node->name->toString();
                }
            }
        }

        // Standalone functions
        if ($node instanceof Node\Stmt\Function_) {
            $this->currentMethod = (string)$node->name;
            $this->currentCalls = [];
            $params = [];
            foreach ($node->params as $param) {
                $params[] = [
                    'name' => '$' . $param->var->name,
                    'type' => $param->type ? $this->resolveType($param->type) : null,
                ];
            }
            $this->functions[$this->currentMethod] = [
                'params' => $params,
                'returns' => $node->returnType ? $this->resolveType($node->returnType) : null,
                'line' => $node->getStartLine(),
                'calls' => [],
            ];
        }
    }

    public function leaveNode(Node $node)
    {
        if ($node instanceof Node\Stmt\ClassMethod && $this->currentMethod) {
            $this->methods[$this->currentMethod]['calls'] = array_values(array_unique($this->currentCalls));
            $this->currentMethod = null;
            $this->currentCalls = [];
        }

        if ($node instanceof Node\Stmt\Function_ && $this->currentMethod) {
            $this->functions[$this->currentMethod]['calls'] = array_unique($this->currentCalls);
            $this->currentMethod = null;
            $this->currentCalls = [];
        }

        if ($node instanceof Node\Stmt\Class_ || $node instanceof Node\Stmt\Trait_) {
            $this->classes[$this->currentClass]['methods'] = $this->methods;
            $this->classes[$this->currentClass]['dependencies'] = array_values(array_unique($this->dependencies));
            $this->currentClass = null;
        }
    }

    private function resolveType($type): ?string
    {
        if ($type instanceof Node\Name) return $type->toString();
        if ($type instanceof Node\Identifier) return (string)$type;
        if ($type instanceof Node\NullableType) return '?' . $this->resolveType($type->type);
        if ($type instanceof Node\UnionType) {
            return implode('|', array_map(fn($t) => $this->resolveType($t), $type->types));
        }
        return null;
    }

    private function resolveCall(Node\Expr\MethodCall $node): ?string
    {
        $method = $node->name instanceof Node\Identifier ? (string)$node->name : null;
        if (!$method) return null;

        $var = $node->var;
        if ($var instanceof Node\Expr\Variable) {
            $varName = is_string($var->name) ? $var->name : null;
            if ($varName === 'this') return "this->$method";
            return "\$$varName->$method";
        }
        if ($var instanceof Node\Expr\PropertyFetch) {
            $prop = $var->name instanceof Node\Identifier ? (string)$var->name : '?';
            return "\$this->$prop->$method";
        }
        return $method;
    }

    private function getVisibility(Node\Stmt\ClassMethod $node): string
    {
        if ($node->isPublic()) return 'public';
        if ($node->isProtected()) return 'protected';
        if ($node->isPrivate()) return 'private';
        return 'public';
    }
}

// Main
if ($argc < 2) {
    fwrite(STDERR, "Usage: php extract_php.php <file>\n");
    exit(1);
}

$file = $argv[1];
$code = file_get_contents($file);
$parser = (new ParserFactory)->create(ParserFactory::PREFER_PHP7);

try {
    $ast = $parser->parse($code);
} catch (\PhpParser\Error $e) {
    echo json_encode(['classes' => [], 'functions' => []]);
    exit(0);
}

$traverser = new NodeTraverser();
$visitor = new StructureVisitor();
$traverser->addVisitor($visitor);
$traverser->traverse($ast);

echo json_encode([
    'classes' => $visitor->classes,
    'functions' => $visitor->functions,
], JSON_PRETTY_PRINT);
