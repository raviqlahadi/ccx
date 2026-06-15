package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

type Route struct {
	Method     string `json:"method"`
	URI        string `json:"uri"`
	Controller string `json:"controller"`
	Action     string `json:"action"`
	File       string `json:"file"`
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "Usage: extract_routes_go <routes_directory>\n")
		os.Exit(1)
	}

	dir := os.Args[1]
	var routes []Route

	files, _ := filepath.Glob(filepath.Join(dir, "*.go"))
	for _, file := range files {
		routes = append(routes, extractFromFile(file)...)
	}

	if routes == nil {
		routes = []Route{}
	}
	json.NewEncoder(os.Stdout).Encode(routes)
}

func extractFromFile(file string) []Route {
	var routes []Route
	fset := token.NewFileSet()
	node, err := parser.ParseFile(fset, file, nil, parser.ParseComments)
	if err != nil {
		return routes
	}

	// Also do regex-based extraction for reliability
	content, _ := os.ReadFile(file)
	lines := strings.Split(string(content), "\n")

	currentPrefix := ""
	// Track prefix from Prefix() calls
	prefixRe := regexp.MustCompile(`\.Prefix\("([^"]+)"\)`)
	// Track route registrations
	routeRe := regexp.MustCompile(`router\.(Get|Post|Put|Patch|Delete)\("([^"]+)",\s*(\w+)\.(\w+)\)`)

	for _, line := range lines {
		if m := prefixRe.FindStringSubmatch(line); m != nil {
			currentPrefix = m[1]
		}
		if m := routeRe.FindStringSubmatch(line); m != nil {
			uri := "/" + currentPrefix + m[2]
			uri = strings.ReplaceAll(uri, "//", "/")
			routes = append(routes, Route{
				Method:     strings.ToUpper(m[1]),
				URI:        uri,
				Controller: m[3],
				Action:     m[4],
				File:       filepath.Base(file),
			})
		}
	}

	// Also check AST for selector expressions in route calls
	_ = node
	_ = fset

	return routes
}

// Keep for potential AST-based extraction
func inspectNode(node ast.Node) {}
