.PHONY: test bench demo fixtures corpus

PYTHON ?= python3

test:
	$(PYTHON) -m pytest -q

bench:
	$(PYTHON) scripts/bench.py

corpus:
	$(PYTHON) scripts/corpus.py

demo:
	bash scripts/demo.sh

fixtures:
	$(PYTHON) -m crashmin.fixtures --port 18765
