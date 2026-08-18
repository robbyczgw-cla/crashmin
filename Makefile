.PHONY: test bench demo fixtures

PYTHON ?= python3

test:
	$(PYTHON) -m pytest -q

bench:
	$(PYTHON) scripts/bench.py

demo:
	bash scripts/demo.sh

fixtures:
	$(PYTHON) -m crashmin.fixtures --port 18765
