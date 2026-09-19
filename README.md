# Mumbai anthropogenic heat + AC-adoption ABM

Bottom-up hourly anthropogenic heat flux (Q_f) for Greater Mumbai's 24 BMC wards, coupled
to an agent-based model of household air-conditioner adoption running 2026–2040 with a
waste-heat feedback.

**Live map:** https://manish-bilore.github.io/mumbai-anthropogenic-heat/

> **Status: uncalibrated prototype.** The physics and the agent logic are real; the
> behavioural coefficients are not fitted to observation. See [Known wrong](#known-wrong).

---

## Results (typical pre-monsoon day, feedback_k = 0.05 K per W/m²)

**Anthropogenic heat, 2026 baseline**

| | this model | Sailor et al. (2015) extrapolation |
|---|---|---|
| daily mean, built cells | 20.6 W/m² | 23.5 W/m² |
| peak hour | 18:00 | 16:00 |

The two-hour shift is the substantive difference: Sailor's diurnal profile derives from US
utility load curves, while Indian residential demand peaks in the evening.

**Adoption trajectory**

| | 2026 | 2040 |
|---|---|---|
| AC penetration | 17.9% | 56.2% |
| households with AC | 0.58 M | 1.81 M |
| Q_f mean (built cells) | 20.6 W/m² | 23.8 W/m² |
| peak electricity | 3,064 MW | 3,516 MW |
| feedback ΔT | — | +0.15 °C |

**Thermal inequality** — free-running indoor conditions and AC operation by archetype:

| archetype | indoor mean / max | discomfort | setpoint | runtime |
|---|---|---|---|---|
| res_slum | 32.2 / 38.4 °C | 22,634 Kh | 27.0 °C | **0.50** |
| res_lowrise | 31.4 / 36.6 °C | 18,290 Kh | 25.5 °C | 0.74 |
| res_midrise | 30.6 / 34.7 °C | 14,030 Kh | 25.2 °C | 0.77 |
| res_tower | 30.6 / 34.4 °C | 13,736 Kh | 25.2 °C | **0.78** |

Informal dwellings run 1.6 °C hotter on average and 4.0 °C hotter at peak than towers,
carry 65% more discomfort degree-hours, and operate cooling at 64% of the rate. The waste
heat they are exposed to is produced largely by other people's air conditioners.

**Sensitivity (Morris, r = 2, 18 evaluations)**

Ranked by μ\* on 2040 penetration: `p_cap` (0.51) > `b0` (0.22) > `price_decline` (0.12) >
`income_growth` (0.12) > `b_peer` > `b_afford` > `b_discomfort` (0.07) > `feedback_k` (0.008).

Two readings:
- The answer is set by the two parameters with no empirical anchor (`p_cap`, `b0`). Those
  are the calibration targets; everything else can stay at placeholder values.
- Indoor discomfort ranks second-last for adoption yet produces the largest spread across
  the stock. Income and price decide **who adopts**; building fabric decides **who suffers
  while not adopting**. `feedback_k` is last for adoption and second for ΔT: the feedback is
  visible in the physics, not in the behaviour.

Stochastic replicate variance is negligible (<0.1 pp on 2040 penetration across seeds).
With 3.2 M households, binomial noise averages out — the uncertainty here is in the
coefficients, not the seeds, which is why screening and calibration matter and ensembles
do not.

---

## Pipeline

```bash
conda env create -f environment.yml && conda activate mumbaiqf

python scripts/00a_normalise_ward_population.py   # BMC export -> pipeline schema
python scripts/00b_normalise_inputs.py            # wards + buildings + typology -> clean
python scripts/00c_make_typical_day.py --from-year 2020   # daily Tmax/Tmin -> hourly day
python scripts/08_build_income_proxy.py           # ASR locality rates -> ward medians
python scripts/01_prepare_stock.py                # floors, floor area, archetype, ward
python scripts/02_assign_population.py            # population, households, income band
python scripts/03_run_loads.py                    # hourly loads + waste heat
python scripts/04_gridify.py                      # 100 m Q_f grid (+ metabolism, traffic)
python scripts/06_benchmark.py                    # vs Sailor et al.
python scripts/10_abm_ensemble.py --replicates 3  # the ABM
python scripts/11_morris_screening.py --trajectories 2
python scripts/12_export_web_series.py            # web/series.json for the viewer
bash   scripts/07_make_tiles.sh
```

`05_abm_sweep.py` and `09_abm_dynamic.py` are superseded by `10_abm_ensemble.py`, kept for
reference.

---

## Method

**1. Stock.** Floors = ceil(height / storey height by use class); floor area = footprint ×
floors; archetype from Overture-derived typology refined by floor count; `res_slum` where
the centroid falls inside a mapped slum polygon; ward by centroid join with a 100 m snap.
580,890 buildings inside Greater Mumbai, 279.7 km² of floor area, 42.2% slum-flagged
(median footprint 42 m² and height 3.6 m, against 79 m² and 5.2 m elsewhere; only 0.8%
exceed three floors).

**2. Population.** Ward population (MCGM 2023, 13,014,389) distributed across residential
floor area; households = population / archetype occupancy; income band from ready-reckoner
rate quartiles, slums pinned to the lowest band.

**3. Loads.**

```
P_base(t) = Σ(appliance ownership × rated power) × schedule(t)      [residential]
            base_w_per_m2 × floor area × schedule(t)                [non-residential]
UA        = U × envelope area + 0.33 × ACH × volume
Q_cool(t) = [UA·max(0, T_out − T_set) + Q_solar + Q_int] × occupancy × runtime, capped
E_ac(t)   = Q_cool(t) / COP
Q_f(t)    = P_base + Q_cool + E_ac  ≡  base + Q_cool(1 + 1/COP)
```

Plus human metabolism (70 W asleep / 140 W awake on the occupancy schedule) and road
traffic (city vehicle-km distributed by class-weighted OSM road length).

**4. Indoor thermal state (1R1C).** Free-running indoor air temperature per building from
fabric and open-window ventilation conductance, floor and roof solar gain, appliance heat
and thermal mass, integrated hourly with a 5-day spin-up and extra night ventilation. This
is what makes archetypes differ: an uninsulated low roof over a small dwelling behaves
nothing like a tower flat.

**5. Agents.** One household cohort per residential building, tracked as integer counts of
AC-owning households. Each year every non-owning household draws against

```
u = b0 + b_afford·(afford − 1) + b_discomfort·(discomfort/ref − 1) + b_peer·peer_share
p = p_cap / (1 + exp(−u))
```

where `afford` rises with real incomes against falling AC prices, `discomfort` is that
agent's own indoor degree-hours, and `peer_share` is neighbourhood ownership on a 500 m
grid with 3×3 smoothing. Owners choose a setpoint (by income band) and an operating
fraction (logistic in indoor exceedance, damped by bill sensitivity), both feeding back
into the load model. **Penetration is an output, not a target.**

**6. Feedback.** ΔT(t+1) = k · (Q_f_mean(t) − Q_f_mean(baseline)), raising next year's
cooling demand and discomfort. k stands in for a surface energy balance model.

---

## Data

| input | source | note |
|---|---|---|
| building footprints + heights | GlobalBuildingAtlas | 673,583 raw; heights ±1.5–9 m |
| typology | Overture Maps POI matching | 12 classes, all buildings assigned |
| slum extents | mapped slums 2016 (KML) | 2,542 polygons, 33.5 km² |
| ward boundaries + population | MCGM civic demographics | mid-2023 estimates |
| income proxy | Maharashtra ASR 2026–27 via public compilations | 125 localities → ward medians |
| weather | daily Tmax/Tmin 1951–2024 | station era only (2020+), Parton–Logan expansion |
| roads | OSM via osmnx | 6,157 km |

---

## Known wrong

1. **Behavioural coefficients are unfitted.** `p_cap` and `b0` dominate the result and have
   no empirical anchor. Calibration targets: AC ownership by income band (CEEW IRES,
   Maharashtra), room-AC sales trends, licensee summer load growth.
2. **ΔT is a uniform city-mean increment.** Real AC waste heat concentrates at night and in
   dense wards (literature: 0.6–1.5 °C nighttime). This understates night warming in
   adopting wards and overstates daytime warming everywhere. Replace k with SUEWS or
   PALM-4U per LCZ class.
3. **Heights carry 1.5–9 m error**, propagating into floor counts, floor area and capacitance.
4. **Typology is ~35% evidence-supported**; the rest is a size-and-height heuristic.
5. **EUIs, appliance stocks, U-values, ACH, capacitance and roof gains are placeholders.**
   No Indian archetype library is used.
6. **Slum layer is 2016** and sets archetype, thermal properties and income band. Mumbai's
   informal stock has changed, particularly where redevelopment has occurred.
7. **Income proxy is land value**, not income. The slum override handles the worst failure
   (informal settlements inside expensive wards); the proxy is still coarse.
8. **Constant COP of 3.0.** Real COP degrades with ambient temperature, so cooling energy
   and waste heat are understated on the hottest hours.
9. **All condenser heat treated as sensible.** Commercial cooling towers reject mostly latent.
10. **Vehicle heat rests on one invented number** (city daily vehicle-km) and contributes a
    large share of total Q_f. Needs CTS traffic counts.
11. **Weather record splices two sources** (gridded 1951–2019, station 2020–2024, differing
    by ~1.5 °C in Tmax and ~3 °C in daily range). Only the station era is used, and a single
    series means no urban heat island gradient: every ward gets identical forcing.
12. **Building stock is frozen to 2040.** No redevelopment, no new construction, no
    population growth.
13. **No daytime population redistribution.** Metabolic heat sits at people's homes all day,
    understating Q_f in BKC, Nariman Point and Lower Parel during working hours.

---

## Layout

```
config/params.yaml      every parameter, tagged [placeholder] / [literature] / [official]
src/qfmumbai/           stock, population, loads, thermal, abm_dynamic, gridify, qf_other
scripts/00..12          pipeline steps, each logging to logs/run.log with the config hash
data/raw|interim|processed
web/                    MapLibre viewer (year + hour sliders) and PMTiles
figures/                benchmark, trajectory and Morris plots
NEXT_STEPS.md           where development paused and what comes next
```

The config hash appears in every log line, so any result traces back to the parameter set
that produced it.

## Licence and attribution

Code under MIT. Building footprints and heights from GlobalBuildingAtlas (TU Munich),
typology derived from Overture Maps, base map © OpenStreetMap contributors.
