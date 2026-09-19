# NEXT_STEPS — development paused 19 September 2026

Working end-to-end pipeline and ABM. Paused to write Quarto documentation and redesign the
GitHub Pages site. This file is the record of state, decisions and open work.

---

## 1. Where it stands

Built in one day from an empty folder:

- 673,583 building footprints → 580,890 inside Greater Mumbai, 279.7 km² floor area
- 12-class typology joined, 42.2% flagged informal from 2016 slum polygons
- hourly Q_f on a 100 m grid: buildings + metabolism + road traffic
- 1R1C indoor temperature per building, driving discomfort
- household-agent AC adoption 2026–2040, annual steps, stochastic draws, waste-heat feedback
- Morris screening over eight behavioural coefficients
- MapLibre viewer on PMTiles, published to GitHub Pages

**Headline numbers** (config hash `9b54465b8e45`): 2026 Q_f 20.6 W/m² mean over built cells,
peak 18:00; adoption 17.9% → 56.2% by 2040; Q_f → 23.8 W/m²; peak electricity 3,064 →
3,516 MW; ΔT +0.15 °C at k = 0.05.

---

## 2. Decisions made, with reasons

| decision | reason |
|---|---|
| Greater Mumbai only, not MMR | ward population and boundaries exist for the 24 BMC wards; the 92,693 out-of-scope buildings (Thane, Mira-Bhayandar, Navi Mumbai) are dropped and saved to `data/interim/buildings_out_of_scope.parquet` |
| Q_f is an output of the UBEM, not an input | Sailor's extrapolation is the benchmark, not the source |
| built-cell mean, not all-cell | 18,173 of 48,428 cells are sea, creek, SGNP and Aarey; Sailor's city-scale figure is over built land |
| station-era weather only (2020+) | the record splices a gridded product and station data differing by ~1.5 °C Tmax, ~3 °C daily range |
| ΔT as a scalar transfer coefficient | no surface energy balance model available; flagged as the largest physics assumption |
| 3 replicates, not 30 | seed variance <0.1 pp; identical results across seeds at city scale |
| Morris r = 2, not 10 | ranking unambiguous (top parameter 2.4× the second); 90 evaluations would take ~50 min for no new information |
| offline grid + 3×3 smoothing for peer effects | radius queries over 580k buildings × 15 years are not worth the fidelity |
| `res_slum` assigned by polygon, not height | only 0.8% of slum-flagged buildings exceed three floors, so no height guard needed |

---

## 3. Next work, ranked

**A. Calibration (the one thing that changes the model's status).**
Morris says `p_cap` and `b0` dominate; both are pure knobs. Fit them against:
1. AC ownership by income band — CEEW India Residential Energy Survey, Maharashtra subset
2. room-AC sales trends (national, scaled to Mumbai)
3. licensee summer load growth (AEML / BEST / Tata Power / MSEDCL)

Method: history matching to rule out implausible coefficient space, then ABC for credible
intervals. Everything else can stay at placeholder values.

**B. Replace the uniform ΔT with SUEWS.** Per-LCZ-class runs through UMEP give
night-vs-day and dense-vs-sparse differentiation, which is where the AC feedback literature
finds its signal. Needs the MMR LCZ map already built.

**C. Tariff slabs.** Maharashtra residential tariffs telescope steeply; crossing a slab
raises marginal cost sharply. Available free from MERC orders, affects both adoption and
runtime, and currently electricity price does not enter the decision at all.

**D. Tenure.** Renters cannot install, landlords do not pay bills. One binary attribute from
Census ward-level ownership share, real explanatory power in chawl and rental stock.

**E. Redevelopment.** The stock is frozen to 2040. Mumbai's pipeline replaces chawls with
towers, changing archetype mix and floor area more than adoption behaviour does over
15 years.

**F. Commercial and industrial cooling.** Currently a fixed AC fraction per archetype,
excluded from the ABM despite being 43% of energy.

**G. Daytime population.** Metabolic heat sits at homes all day. Time Use Survey schedules
would move several million people into the island city each morning.

---

## 4. Data still to acquire

| what | from | why it matters |
|---|---|---|
| AC ownership by income | CEEW IRES (Maharashtra) | calibration target A |
| feeder / division load | AEML, BEST, Tata Power, MSEDCL (request or RTI) | validates the 3,064 MW baseline |
| tariff slabs and ToD | MERC orders (public) | item C |
| CTS traffic counts | MMRDA | vehicle heat is ~9 W/m² on one invented number |
| current slum extents | own MQCNN classification | 2016 layer is stale |
| machine-readable ASR | IGR Maharashtra (request or RTI) | replaces 125 hand-transcribed localities |

---

## 5. Traps already hit (do not repeat)

- Pasting multi-line Python into bash: always `cat > file <<'PYEOF'` or `python - <<'PYEOF'`.
- `pip install` into conda base broke NumPy compatibility across pandas/pyarrow/numba. The
  project now has its own env (`environment.yml`), pinned to NumPy <2.
- `python -m http.server` ignores HTTP Range requests, so PMTiles silently fails locally.
  Use `RangeHTTPServer`. GitHub Pages handles ranges correctly.
- Tippecanoe drops up to 97% of features when tiles exceed 500 KB. Use
  `--no-feature-limit --no-tile-size-limit`, drop empty cells, and round values to integers.
- Ward codes: MCGM export uses `F/ S` and `G /N` with stray spaces; normalise before joining.
- Slum sjoin produced 860 duplicate rows from overlapping polygons — dissolve first.
- Population allocation fails silently if ward codes mismatch; `02_assign_population.py` now
  raises when <90% is allocated.

---

## 6. Paused deliverables

1. **Quarto documentation** — method, results, figures, reproducibility.
2. **GitHub Pages redesign** — the viewer is functional but plain; wants a landing page,
   method summary, the trajectory and Morris figures, and the map as one element rather
   than the whole site.
