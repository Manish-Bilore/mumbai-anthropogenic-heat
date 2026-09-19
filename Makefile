PY=.venv/bin/python

venv:
	python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -r requirements.txt

sample:
	$(PY) scripts/00_make_sample_data.py

stock:
	$(PY) scripts/01_prepare_stock.py

pop:
	$(PY) scripts/02_assign_population.py

loads:
	$(PY) scripts/03_run_loads.py

grid:
	$(PY) scripts/04_gridify.py

abm:
	$(PY) scripts/05_abm_sweep.py

bench:
	$(PY) scripts/06_benchmark.py

tiles:
	bash scripts/07_make_tiles.sh

web:
	$(PY) scripts/12_export_web_series.py
	$(PY) scripts/14_export_diurnal.py
	$(PY) scripts/15_render_poster.py

site: web
	quarto render

demo: sample stock pop loads grid abm bench
	@echo "demo pipeline complete - see data/processed and figures/"

clean:
	rm -f data/interim/* data/processed/* logs/*.log
