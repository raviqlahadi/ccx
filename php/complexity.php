#!/usr/bin/env php
<?php
/**
 * Cognitive Complexity Analyzer for PHP using nikic/php-parser
 * Implements SonarQube's cognitive complexity specification.
 *
 * Usage: php analyze_php.php <file>
 * Output: JSON array of {name, line, complexity}
 */

// Find autoloader
$autoloaders = [
    __DIR__ . '/vendor/autoload.php',
    __DIR__ . '/../vendor/autoload.php',
];

// Also check common project vendor paths
$cwd = getcwd();
$autoloaders[] = $cwd . '/vendor/autoload.php';

// Try to find any vendor with php-parser
$found = false;
foreach ($autoloaders as $autoloader) {
    if (file_exists($autoloader)) {
        require_once $autoloader;
        $found = true;
        break;
    }
}

if (!$found) {
    // Fallback: search in known location
    $fallback = '/home/entru/BrispotProject/brispot_microservice_activity/vendor/autoload.php';
    if (file_exists($fallback)) {
        require_once $fallback;
    } else {
        fwrite(STDERR, "Error: Cannot find composer autoloader with nikic/php-parser\n");
        exit(1);
    }
}

use PhpParser\NodeTraverser;
use PhpParser\NodeVisitorAbstract;
use PhpParser\Node;
use PhpParser\ParserFactory;

class CognitiveComplexityVisitor extends NodeVisitorAbstract
{
    private array $results = [];
    private int $nesting = 0;
    private int $complexity = 0;
    private ?string $currentFunction = null;
    private ?int $currentLine = null;

    public function getResults(): array
    {
        return $this->results;
    }

    public function enterNode(Node $node)
    {
        // Detect function/method entry
        if ($node instanceof Node\Stmt\Function_
            || $node instanceof Node\Stmt\ClassMethod
            || $node instanceof Node\Expr\Closure
            || $node instanceof Node\Expr\ArrowFunction
        ) {
            if ($this->currentFunction === null) {
                $this->currentFunction = $this->getFunctionName($node);
                $this->currentLine = $node->getStartLine();
                $this->complexity = 0;
                $this->nesting = 0;
            } else {
                // Nested function/closure: +1 nesting increment + structural complexity
                $this->nesting++;
                return null;
            }
            return null;
        }

        if ($this->currentFunction === null) {
            return null;
        }

        // B1: Increments - structures that increase complexity
        // +1 and increases nesting
        if ($node instanceof Node\Stmt\If_) {
            $this->complexity += 1 + $this->nesting;
            $this->nesting++;
        } elseif ($node instanceof Node\Stmt\ElseIf_) {
            // elseif: +1, no nesting penalty (same level as if)
            $this->complexity += 1;
        } elseif ($node instanceof Node\Stmt\Else_) {
            // else: +1, no nesting penalty
            $this->complexity += 1;
        } elseif ($node instanceof Node\Stmt\For_
            || $node instanceof Node\Stmt\Foreach_
            || $node instanceof Node\Stmt\While_
            || $node instanceof Node\Stmt\Do_
        ) {
            $this->complexity += 1 + $this->nesting;
            $this->nesting++;
        } elseif ($node instanceof Node\Stmt\Switch_) {
            $this->complexity += 1 + $this->nesting;
            $this->nesting++;
        } elseif ($node instanceof Node\Stmt\Catch_) {
            $this->complexity += 1 + $this->nesting;
            $this->nesting++;
        } elseif ($node instanceof Node\Expr\Ternary || $node instanceof Node\Expr\NullsafeMethodCall) {
            $this->complexity += 1 + $this->nesting;
        } elseif ($node instanceof Node\Expr\Match_) {
            $this->complexity += 1 + $this->nesting;
            $this->nesting++;
        }
        // Logical operators: each sequence of same operator = +1 per switch
        elseif ($node instanceof Node\Expr\BinaryOp\BooleanAnd
            || $node instanceof Node\Expr\BinaryOp\BooleanOr
            || $node instanceof Node\Expr\BinaryOp\LogicalAnd
            || $node instanceof Node\Expr\BinaryOp\LogicalOr
        ) {
            // Check if parent is same type of logical op (sequence)
            // Each "new" sequence or switch in operator type = +1
            $this->complexity += $this->countLogicalIncrement($node);
        }
        // goto and break to label
        elseif ($node instanceof Node\Stmt\Goto_) {
            $this->complexity += 1;
        } elseif ($node instanceof Node\Stmt\Break_ && $node->num !== null) {
            $this->complexity += 1;
        } elseif ($node instanceof Node\Stmt\Continue_ && $node->num !== null) {
            $this->complexity += 1;
        }

        return null;
    }

    public function leaveNode(Node $node)
    {
        if ($node instanceof Node\Stmt\Function_
            || $node instanceof Node\Stmt\ClassMethod
            || $node instanceof Node\Expr\Closure
            || $node instanceof Node\Expr\ArrowFunction
        ) {
            if ($this->getFunctionName($node) === $this->currentFunction
                && $node->getStartLine() === $this->currentLine
            ) {
                $this->results[] = [
                    'name' => $this->currentFunction,
                    'line' => $this->currentLine,
                    'complexity' => $this->complexity,
                ];
                $this->currentFunction = null;
                $this->currentLine = null;
                $this->complexity = 0;
                $this->nesting = 0;
            } else {
                // Leaving nested closure
                $this->nesting = max(0, $this->nesting - 1);
            }
            return null;
        }

        if ($this->currentFunction === null) {
            return null;
        }

        // Decrease nesting when leaving structures
        if ($node instanceof Node\Stmt\If_
            || $node instanceof Node\Stmt\For_
            || $node instanceof Node\Stmt\Foreach_
            || $node instanceof Node\Stmt\While_
            || $node instanceof Node\Stmt\Do_
            || $node instanceof Node\Stmt\Switch_
            || $node instanceof Node\Stmt\Catch_
            || $node instanceof Node\Expr\Match_
        ) {
            $this->nesting = max(0, $this->nesting - 1);
        }
    }

    private function getFunctionName(Node $node): string
    {
        if ($node instanceof Node\Stmt\Function_) {
            return (string) $node->name;
        }
        if ($node instanceof Node\Stmt\ClassMethod) {
            return (string) $node->name;
        }
        if ($node instanceof Node\Expr\Closure) {
            return '{closure}:' . $node->getStartLine();
        }
        if ($node instanceof Node\Expr\ArrowFunction) {
            return '{arrow}:' . $node->getStartLine();
        }
        return '{unknown}';
    }

    private function countLogicalIncrement(Node $node): int
    {
        // In SonarQube's model, a sequence of same operators counts as +1 total.
        // A switch to a different operator is another +1.
        // We handle this by only counting +1 when the node is NOT the right-hand
        // child of the same type of logical op.
        $parent = $node->getAttribute('parent');
        if ($parent !== null && get_class($parent) === get_class($node)) {
            // Same operator sequence continues, don't increment
            return 0;
        }
        return 1;
    }
}

// Parent-linking visitor
class ParentConnector extends NodeVisitorAbstract
{
    private array $stack = [];

    public function beforeTraverse(array $nodes)
    {
        $this->stack = [];
        return null;
    }

    public function enterNode(Node $node)
    {
        if (!empty($this->stack)) {
            $node->setAttribute('parent', end($this->stack));
        }
        $this->stack[] = $node;
        return null;
    }

    public function leaveNode(Node $node)
    {
        array_pop($this->stack);
        return null;
    }
}

// Main
if ($argc < 2) {
    fwrite(STDERR, "Usage: php analyze_php.php <file>\n");
    exit(1);
}

$file = $argv[1];
if (!file_exists($file)) {
    fwrite(STDERR, "File not found: $file\n");
    exit(1);
}

$code = file_get_contents($file);
$parser = (new ParserFactory)->create(ParserFactory::PREFER_PHP7);

try {
    $ast = $parser->parse($code);
} catch (\PhpParser\Error $e) {
    fwrite(STDERR, "Parse error in $file: " . $e->getMessage() . "\n");
    echo json_encode([]);
    exit(0);
}

$traverser = new NodeTraverser();
$parentConnector = new ParentConnector();
$visitor = new CognitiveComplexityVisitor();
$traverser->addVisitor($parentConnector);
$traverser->addVisitor($visitor);
$traverser->traverse($ast);

echo json_encode($visitor->getResults());
