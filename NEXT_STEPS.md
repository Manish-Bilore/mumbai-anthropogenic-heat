# NEXT_STEPS — updated 19 September 2026

Modelling paused after the ABM and sensitivity screening. Current phase: **Quarto
documentation and site redesign**. `STATUS.md` records what exists and how far it can be
trusted.

---

## Phase now: documentation

- [x] README rewritten for the dynamic ABM
- [x] viewer reads `web/series.json` instead of hardcoded numbers
- [x] Quarto site scaffolded (`_quarto.yml`, 7 pages, custom theme)
- [ ] render, check figures and tables build from the CSVs
- [ ] switch Pages to `main` + `/docs`, retire `gh-pages`
- [ ] one figure worth making that does not exist yet: ward-level map of discomfort vs
      AC penetration by income band — the inequality result currently lives only in a table

---

## Immediate, not blocked by anything

**Send the data requests.** The RTI ones take weeks; everything in Phase A waits on them.

| request | to | for |
|---|---|---|
| AC ownership by income band | CEEW (IRES Maharashtra subset) | calibration |
| feeder / division monthly load | AEML, BEST, Tata Power, MSEDCL | validation |
| tariff slabs + ToD structure | MERC orders (public, no request needed) | tariff term |
| household travel / traffic counts | MMRDA CTS | vehicle heat |
| machine-readable ASR | IGR Maharashtra | income proxy |

---

## Phase A — calibration (changes the model's status)

Morris says `p_cap` and `b0` dominate; both are pure knobs. Fit them, leave the rest.

1. History matching to rule out implausible coefficient space, using two anchors: current
   AC ownership by income band, and the observed licensee summer load trend.
2. ABC for credible intervals on the surviving space.
3. Report trajectories as bands over coefficient uncertainty, not over seeds.

## Phase B — replace the uniform ΔT

SUEWS through UMEP, one run per LCZ class, forced by MCGM AWS. Gives night-vs-day and
dense-vs-sparse differentiation, which is where the AC feedback literature finds its
signal. The MMR LCZ map already exists.

## Phase C — behavioural additions, cheapest first

1. **Tariff slabs** — free from MERC orders, affects adoption and runtime.
2. **Tenure** — one binary attribute from Census ward ownership share; split incentives.
3. **Replacement cycle** — lets efficiency standards be tested at all.
4. **Commercial cooling inside the ABM** — currently exogenous, 43% of energy.

## Phase D — structural

1. **Redevelopment pipeline**: chawls → towers changes archetype mix over 15 years.
2. **Daytime population** from Time Use Survey schedules.
3. **Extend to MMR** once ward-equivalent population exists for Thane and Navi Mumbai
   (92,693 buildings already extracted, saved in `data/interim/buildings_out_of_scope.parquet`).

---

## Decisions made, with reasons

| decision | reason |
|---|---|
| Greater Mumbai only | ward population and boundaries exist for the 24 BMC wards |
| Q_f is an output of the UBEM, not an input | Sailor's extrapolation is the benchmark, not the source |
| built-cell mean, not all-cell | 18,173 of 48,428 cells are sea, creek, SGNP, Aarey |
| station-era weather only (2020+) | the record splices two sources differing by ~1.5 °C Tmax |
| ΔT as a scalar coefficient | no surface energy balance model available; flagged as the largest assumption |
| 3 replicates, not 30 | seed variance <0.1 pp at city scale |
| Morris r = 2, not 10 | ranking unambiguous; 90 evaluations add nothing |
| grid + 3×3 smoothing for peer effects | radius queries over 580k buildings × 15 years are not worth the fidelity |
| `res_slum` by polygon, not height | only 0.8% of slum-flagged buildings exceed three floors |

---

## Traps already hit

- Multi-line Python pasted into bash: always `cat > file <<'PYEOF'` or `python - <<'PYEOF'`.
- `pip install` into conda `base` broke NumPy compatibility across pandas/pyarrow/numba.
  The project has its own env now; NumPy pinned <2.
- `python -m http.server` ignores Range requests, so PMTiles fails silently. Use
  `RangeHTTPServer`; GitHub Pages handles ranges correctly.
- Tippecanoe drops up to 97% of features when tiles exceed 500 KB. Use
  `--no-feature-limit --no-tile-size-limit`, drop empty cells, round to integers.
- MCGM ward codes arrive as `F/ S`, `G /N` with stray spaces — normalise before joining.
- Slum sjoin produced 860 duplicate rows from overlapping polygons — dissolve first.
- Population allocation fails silently on ward-code mismatch; `02` now raises below 90%.
- SALib 1.6 requires NumPy ≥2 — pin SALib <1.6.
