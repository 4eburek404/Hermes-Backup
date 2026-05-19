PYTHON ?= python3
PREFIX ?= $(HOME)/.local
BIN := $(PREFIX)/bin/flights
PROJECT := $(CURDIR)

.PHONY: install-local test smoke

install-local:
	mkdir -p "$(PREFIX)/bin"
	printf '%s\n' '#!/usr/bin/env bash' 'PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" exec $(PYTHON) -m flights_cli "$$@"' > "$(BIN)"
	chmod +x "$(BIN)"
	@echo "installed $(BIN)"

test:
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m unittest discover -s tests

smoke:
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m flights_cli --json doctor
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m flights_cli --json cities search London --limit 3
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m flights_cli --json airports explain IST SAW AYT
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m flights_cli --json route plan SVX LON --depart-date 2026-07-19 --return-date 2026-07-23 --hub IST --hub SAW --hub AYT
	printf '%s\n' '{"price":92817,"segments":[{"origin":"SVX","destination":"IST","departure_at":"2026-07-19T10:30:00","arrival_at":"2026-07-19T13:55:00","carrier":"SU"},{"origin":"IST","destination":"LHR","departure_at":"2026-07-19T20:25:00","arrival_at":"2026-07-19T22:25:00","carrier":"TK"}]}' | PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m flights_cli --json route validate --profile safe --input -
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m flights_cli --json route assemble --profile safe --input tests/fixtures/segment-results.json
