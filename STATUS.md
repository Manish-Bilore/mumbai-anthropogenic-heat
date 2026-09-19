# STATUS — 19 September 2026

Snapshot of what exists, what it produces, and what is trustworthy.
Config hash of the reference run: `9b54465b8e45`.

## Built

| component | file(s) | state |
|---|---|---|
| stock assembly | `src/qfmumbai/stock.py`, `scripts/00b`, `01` | working |
| population + income | `src/qfmumbai/population.py`, `scripts/02`, `08` | working |
| loads + waste heat | `src/qfmumbai/loads.py`, `scripts/03` | working, tuned once to city peak |
| metabolism + traffic | `src/qfmumbai/qf_other.py`, `scripts/04` | working; traffic term weakly constrained |
| indoor thermal (1R1C) | `src/qfmumbai/thermal.py` | working |
| adoption ABM | `src/qfmumbai/abm_dynamic.py`, `scripts/10` | working, uncalibrated |
| sensitivity | `scripts/11` | Morris r=2 run, ranking stable |
| benchmark | `src/qfmumbai/benchmark.py`, `scripts/06` | working |
| web viewer | `web/`, `scripts/12` | published |
| superseded | `src/qfmumbai/abm.py`, `scripts/05`, `09` | kept for reference only |

## Reference run

- 673,583 buildings raw → **580,890** in Greater Mumbai, **279.7 km²** floor area
- **42.2%** slum-flagged (median footprint 42 m² vs 79 m², height 3.6 m vs 5.2 m)
- **3,223,052** households, population 13,014,389 allocated exactly
- 2026: Q_f **20.58 W/m²** mean over built cells, peak **32.30 W/m²** at 18:00, **3,064 MW**
- 2040: penetration **56.2%**, Q_f **23.81 W/m²**, peak **38.06 W/m²**, **3,516 MW**, ΔT **+0.15 °C**
- Benchmark: Sailor et al. extrapolation 23.46 W/m² mean, peak 40.07 at 16:00

## Trust levels

**Solid.** Stock geometry and typology counts; population allocation; the Q_f accounting
identity; the 1R1C indoor model's *relative* ordering across archetypes; the Morris ranking.

**Plausible, unvalidated.** Absolute Q_f magnitude (agrees with one published extrapolation
that itself rests on 2010 energy ratios); city peak electricity (~14% below the real
all-licensee peak); indoor absolute temperatures.

**Not trustworthy without calibration.** The adoption trajectory's level; ΔT magnitude;
the vehicle heat share; anything about commercial or industrial cooling.

## Publishing

- `main` → code, small derived CSVs, figures, tiles
- `gh-pages` (via `git subtree push --prefix web origin gh-pages`) → current live viewer
- **Changing with the Quarto site:** render to `docs/`, copy `web/` into `docs/map/`,
  switch Pages source to `main` + `/docs`, retire `gh-pages`

## Environment

`environment.yml`, conda env `mumbaiqf`. NumPy pinned <2.0. Installing into conda `base`
breaks pandas/pyarrow/numba — do not.

## Open threads

See `NEXT_STEPS.md`. Highest priority: send the data requests (CEEW IRES, licensee load,
MERC tariffs, CTS traffic counts), because the RTI ones take weeks and everything else
waits on them.
