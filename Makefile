.PHONY: build clean install

build: bin/complexity_go bin/extract_go bin/extract_routes_go

bin/complexity_go: cmd/complexity_go.go
	go build -o bin/complexity_go cmd/complexity_go.go

bin/extract_go: cmd/extract_go.go
	go build -o bin/extract_go cmd/extract_go.go

bin/extract_routes_go: cmd/extract_routes_go.go
	go build -o bin/extract_routes_go cmd/extract_routes_go.go

clean:
	rm -f bin/complexity_go bin/extract_go bin/extract_routes_go
	rm -rf ~/.cache/ccx

install: build
	@echo 'Add these to ~/.bashrc:'
	@echo 'alias ccx="python3 $(CURDIR)/ccx.py"'
	@echo 'alias explore="python3 $(CURDIR)/explore.py"'
	@echo 'alias ccx-analyze="python3 $(CURDIR)/analyze.py"'
