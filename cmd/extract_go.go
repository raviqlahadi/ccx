package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"strings"
)

type MethodInfo struct {
	Params     []ParamInfo `json:"params"`
	Returns    string      `json:"returns"`
	Line       int         `json:"line"`
	Calls      []string    `json:"calls"`
	Visibility string      `json:"visibility"`
}

type ParamInfo struct {
	Name string `json:"name"`
	Type string `json:"type"`
}

type StructInfo struct {
	Methods      map[string]MethodInfo `json:"methods"`
	Dependencies []string              `json:"dependencies"`
	Implements   []string              `json:"implements"`
}

type FileResult struct {
	Structs   map[string]StructInfo `json:"structs"`
	Functions map[string]MethodInfo `json:"functions"`
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "Usage: extract_go <file>\n")
		os.Exit(1)
	}

	fset := token.NewFileSet()
	node, err := parser.ParseFile(fset, os.Args[1], nil, parser.ParseComments)
	if err != nil {
		json.NewEncoder(os.Stdout).Encode(FileResult{
			Structs:   map[string]StructInfo{},
			Functions: map[string]MethodInfo{},
		})
		os.Exit(0)
	}

	result := FileResult{
		Structs:   make(map[string]StructInfo),
		Functions: make(map[string]MethodInfo),
	}

	// Collect struct types and their fields (for dependency detection)
	structFields := map[string][]string{} // struct -> field types
	for _, decl := range node.Decls {
		genDecl, ok := decl.(*ast.GenDecl)
		if !ok || genDecl.Tok != token.TYPE {
			continue
		}
		for _, spec := range genDecl.Specs {
			typeSpec, ok := spec.(*ast.TypeSpec)
			if !ok {
				continue
			}
			structType, ok := typeSpec.Type.(*ast.StructType)
			if !ok {
				continue
			}
			name := typeSpec.Name.Name
			var deps []string
			if structType.Fields != nil {
				for _, field := range structType.Fields.List {
					typeName := exprToString(field.Type)
					if typeName != "" && isExportedOrInterface(typeName) {
						deps = append(deps, typeName)
					}
				}
			}
			structFields[name] = deps
			result.Structs[name] = StructInfo{
				Methods:      make(map[string]MethodInfo),
				Dependencies: deps,
			}
		}
	}

	// Collect functions and methods
	for _, decl := range node.Decls {
		funcDecl, ok := decl.(*ast.FuncDecl)
		if !ok {
			continue
		}

		info := MethodInfo{
			Line:       fset.Position(funcDecl.Pos()).Line,
			Visibility: visibility(funcDecl.Name.Name),
			Params:     extractParams(funcDecl.Type.Params),
			Returns:    extractReturns(funcDecl.Type.Results),
			Calls:      extractCalls(funcDecl.Body),
		}

		if funcDecl.Recv != nil && len(funcDecl.Recv.List) > 0 {
			// Method
			recvType := exprToString(funcDecl.Recv.List[0].Type)
			recvType = strings.TrimPrefix(recvType, "*")
			if _, exists := result.Structs[recvType]; !exists {
				result.Structs[recvType] = StructInfo{
					Methods:      make(map[string]MethodInfo),
					Dependencies: []string{},
				}
			}
			s := result.Structs[recvType]
			s.Methods[funcDecl.Name.Name] = info
			result.Structs[recvType] = s
		} else {
			// Standalone function
			result.Functions[funcDecl.Name.Name] = info
		}
	}

	json.NewEncoder(os.Stdout).Encode(result)
}

func extractParams(fields *ast.FieldList) []ParamInfo {
	if fields == nil {
		return []ParamInfo{}
	}
	var params []ParamInfo
	for _, f := range fields.List {
		typeName := exprToString(f.Type)
		if len(f.Names) == 0 {
			params = append(params, ParamInfo{Type: typeName})
		}
		for _, name := range f.Names {
			params = append(params, ParamInfo{Name: name.Name, Type: typeName})
		}
	}
	return params
}

func extractReturns(fields *ast.FieldList) string {
	if fields == nil || len(fields.List) == 0 {
		return ""
	}
	var types []string
	for _, f := range fields.List {
		types = append(types, exprToString(f.Type))
	}
	if len(types) == 1 {
		return types[0]
	}
	return "(" + strings.Join(types, ", ") + ")"
}

func extractCalls(body *ast.BlockStmt) []string {
	if body == nil {
		return []string{}
	}
	seen := map[string]bool{}
	var calls []string

	ast.Inspect(body, func(n ast.Node) bool {
		call, ok := n.(*ast.CallExpr)
		if !ok {
			return true
		}
		var callName string
		switch fn := call.Fun.(type) {
		case *ast.SelectorExpr:
			obj := exprToString(fn.X)
			callName = obj + "." + fn.Sel.Name
		case *ast.Ident:
			callName = fn.Name
		}
		if callName != "" && !seen[callName] {
			seen[callName] = true
			calls = append(calls, callName)
		}
		return true
	})
	return calls
}

func exprToString(expr ast.Expr) string {
	switch e := expr.(type) {
	case *ast.Ident:
		return e.Name
	case *ast.StarExpr:
		return "*" + exprToString(e.X)
	case *ast.SelectorExpr:
		return exprToString(e.X) + "." + e.Sel.Name
	case *ast.ArrayType:
		return "[]" + exprToString(e.Elt)
	case *ast.MapType:
		return "map[" + exprToString(e.Key) + "]" + exprToString(e.Value)
	case *ast.InterfaceType:
		return "interface{}"
	case *ast.Ellipsis:
		return "..." + exprToString(e.Elt)
	}
	return ""
}

func visibility(name string) string {
	if len(name) > 0 && name[0] >= 'A' && name[0] <= 'Z' {
		return "public"
	}
	return "private"
}

func isExportedOrInterface(name string) bool {
	name = strings.TrimPrefix(name, "*")
	if strings.Contains(name, ".") {
		return true
	}
	if len(name) > 0 && name[0] >= 'A' && name[0] <= 'Z' {
		return true
	}
	return false
}
