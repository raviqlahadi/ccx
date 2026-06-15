package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
)

type FuncResult struct {
	Name       string `json:"name"`
	Line       int    `json:"line"`
	Complexity int    `json:"complexity"`
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "Usage: analyze_go <file>\n")
		os.Exit(1)
	}

	file := os.Args[1]
	fset := token.NewFileSet()
	node, err := parser.ParseFile(fset, file, nil, parser.ParseComments)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Parse error: %v\n", err)
		json.NewEncoder(os.Stdout).Encode([]FuncResult{})
		os.Exit(0)
	}

	var results []FuncResult

	ast.Inspect(node, func(n ast.Node) bool {
		fn, ok := n.(*ast.FuncDecl)
		if !ok {
			return true
		}
		name := fn.Name.Name
		line := fset.Position(fn.Pos()).Line
		complexity := calcComplexity(fn.Body, 0)
		results = append(results, FuncResult{Name: name, Line: line, Complexity: complexity})
		return false // don't recurse into function again
	})

	if results == nil {
		results = []FuncResult{}
	}
	json.NewEncoder(os.Stdout).Encode(results)
}

func calcComplexity(node ast.Node, nesting int) int {
	if node == nil {
		return 0
	}

	complexity := 0

	switch n := node.(type) {
	case *ast.BlockStmt:
		for _, stmt := range n.List {
			complexity += calcComplexity(stmt, nesting)
		}

	case *ast.IfStmt:
		// if: +1 + nesting
		complexity += 1 + nesting
		// condition may have logical ops
		complexity += countLogicalOps(n.Cond)
		// init statement
		complexity += calcComplexity(n.Init, nesting)
		// body
		complexity += calcComplexity(n.Body, nesting+1)
		// else
		if n.Else != nil {
			switch n.Else.(type) {
			case *ast.IfStmt:
				// else if: handled recursively but counts as +1 (not +1+nesting)
				elseIf := n.Else.(*ast.IfStmt)
				complexity += 1 // else if: +1 only
				complexity += countLogicalOps(elseIf.Cond)
				complexity += calcComplexity(elseIf.Init, nesting)
				complexity += calcComplexity(elseIf.Body, nesting+1)
				if elseIf.Else != nil {
					complexity += calcElse(elseIf.Else, nesting)
				}
			case *ast.BlockStmt:
				// else: +1
				complexity += 1
				complexity += calcComplexity(n.Else, nesting+1)
			}
		}

	case *ast.ForStmt:
		complexity += 1 + nesting
		complexity += countLogicalOps(n.Cond)
		complexity += calcComplexity(n.Body, nesting+1)

	case *ast.RangeStmt:
		complexity += 1 + nesting
		complexity += calcComplexity(n.Body, nesting+1)

	case *ast.SwitchStmt:
		complexity += 1 + nesting
		complexity += calcComplexity(n.Body, nesting+1)

	case *ast.TypeSwitchStmt:
		complexity += 1 + nesting
		complexity += calcComplexity(n.Body, nesting+1)

	case *ast.SelectStmt:
		complexity += 1 + nesting
		complexity += calcComplexity(n.Body, nesting+1)

	case *ast.CaseClause:
		// case clauses don't add complexity themselves
		for _, stmt := range n.Body {
			complexity += calcComplexity(stmt, nesting)
		}

	case *ast.CommClause:
		for _, stmt := range n.Body {
			complexity += calcComplexity(stmt, nesting)
		}

	case *ast.FuncLit:
		// nested function literal: nesting increase
		complexity += calcComplexity(n.Body, nesting+1)

	case *ast.ExprStmt:
		complexity += countLogicalOps(n.X)

	case *ast.AssignStmt:
		for _, rhs := range n.Rhs {
			complexity += countLogicalOps(rhs)
		}

	case *ast.ReturnStmt:
		for _, r := range n.Results {
			complexity += countLogicalOps(r)
		}

	case *ast.SendStmt:
		complexity += countLogicalOps(n.Value)

	case *ast.GoStmt:
		if fn, ok := n.Call.Fun.(*ast.FuncLit); ok {
			complexity += calcComplexity(fn.Body, nesting+1)
		}

	case *ast.DeferStmt:
		if fn, ok := n.Call.Fun.(*ast.FuncLit); ok {
			complexity += calcComplexity(fn.Body, nesting+1)
		}

	case *ast.LabeledStmt:
		complexity += calcComplexity(n.Stmt, nesting)

	case *ast.BranchStmt:
		// goto: +1
		if n.Tok == token.GOTO {
			complexity += 1
		}
		// break/continue to label: +1
		if n.Label != nil && (n.Tok == token.BREAK || n.Tok == token.CONTINUE) {
			complexity += 1
		}

	case *ast.DeclStmt:
		// skip

	default:
		// For other statement types, try to walk children
	}

	return complexity
}

func calcElse(node ast.Node, nesting int) int {
	complexity := 0
	switch n := node.(type) {
	case *ast.IfStmt:
		complexity += 1 // else if: +1
		complexity += countLogicalOps(n.Cond)
		complexity += calcComplexity(n.Init, nesting)
		complexity += calcComplexity(n.Body, nesting+1)
		if n.Else != nil {
			complexity += calcElse(n.Else, nesting)
		}
	case *ast.BlockStmt:
		complexity += 1 // else: +1
		complexity += calcComplexity(n, nesting+1)
	}
	return complexity
}

func countLogicalOps(expr ast.Expr) int {
	if expr == nil {
		return 0
	}

	switch e := expr.(type) {
	case *ast.BinaryExpr:
		count := 0
		if e.Op == token.LAND || e.Op == token.LOR {
			// +1 for each sequence change
			count += countLogicalSequence(e)
		} else {
			count += countLogicalOps(e.X)
			count += countLogicalOps(e.Y)
		}
		return count
	case *ast.ParenExpr:
		return countLogicalOps(e.X)
	case *ast.UnaryExpr:
		return countLogicalOps(e.X)
	case *ast.CallExpr:
		count := 0
		for _, arg := range e.Args {
			count += countLogicalOps(arg)
		}
		return count
	}
	return 0
}

func countLogicalSequence(expr *ast.BinaryExpr) int {
	if expr.Op != token.LAND && expr.Op != token.LOR {
		return 0
	}

	// Flatten the logical expression tree
	ops := flattenLogical(expr)
	if len(ops) == 0 {
		return 0
	}

	// Count operator type switches
	count := 1 // first sequence = +1
	prev := ops[0]
	for i := 1; i < len(ops); i++ {
		if ops[i] != prev {
			count++
			prev = ops[i]
		}
	}
	return count
}

func flattenLogical(expr ast.Expr) []token.Token {
	switch e := expr.(type) {
	case *ast.BinaryExpr:
		if e.Op == token.LAND || e.Op == token.LOR {
			left := flattenLogical(e.X)
			right := flattenLogical(e.Y)
			return append(append(left, e.Op), right...)
		}
	case *ast.ParenExpr:
		return flattenLogical(e.X)
	}
	return nil
}
