# Mumbai anthropogenic heat — UBEM + AC adoption demo

Bottom-up hourly anthropogenic heat flux (Q_f) for Greater Mumbai's 24 BMC wards on a
typical summer day, from building stock to a 100 m grid, with an AC-penetration sweep.
**Every parameter is a placeholder.** The point is a working end-to-end pipeline, not a result.

---

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

make sample      # synthetic stock so the pipeline runs before real data lands
make demo        # 00 -> 06, end to end
```

With real data, drop the files listed below into `data/raw/` and run from step 01:

```bash
python scripts/01_prepare_stock.py
python scripts/02_assign_population.py
python scripts/03_run_loads.py
python scripts/04_gridify.py
python scripts/05_abm_sweep.py
python scripts/06_benchmark.py
bash   scripts/07_make_tiles.sh     # needs tippecanoe
python -m http.server -d web 8000   # then open localhost:8000
```

---

## Data contracts (`data/raw/`)

| File | Required columns | Notes |
|---|---|---|
| `buildings.parquet` (or `.gpkg`) | `building_id`, `height_m`, `use_class`, geometry (polygon) | optional `is_slum`; column names configurable in `config/params.yaml → schema` |
| `wards.gpkg` | `ward`, geometry (polygon) | ward codes must match the population CSV |
| `mumbai_ward_population_2023.csv` | `ward`, `population_mid2023` | from MCGM civic demographics |
| `weather_typical_day.csv` | `hour` (0–23), `temp_c` | one clear pre-monsoon day, IMD or MCGM AWS |
| `ready_reckoner.csv` *(optional)* | `ward`, `rr_rate` | income proxy; without it the model falls back to dwelling area |

---

## Method

**1. Stock** (`stock.py`) — floors = ceil(height / storey height by use class), clipped to
[1, 90]; floor area = footprint × floors; archetype from Overture use class, refined by
floor count; ward by centroid join.

**2. Population** (`population.py`) — ward population distributed across residential floor
area; households = population / archetype occupancy; income band from ready-reckoner rate
(or dwelling-area quantiles), with slums pinned to the lowest band.

**3. Loads** (`loads.py`) — three explicit terms:

```
P_base(t) = Σ(appliance ownership × rated power) × schedule(t)      [residential]
            base_w_per_m2 × floor area × schedule(t)                [non-residential]
UA        = U × envelope area + 0.33 × ACH × volume
Q_cool(t) = [UA·max(0, T_out − T_set) + Q_solar + Q_internal] × occupancy, capped at capacity
E_ac(t)   = Q_cool(t) / COP
Q_f(t)    = P_base(t) + Q_cool(t) + E_ac(t)   ≡ base + Q_cool(1 + 1/COP)
```

Base electricity becomes indoor heat 1:1 and is also an internal gain, so the base and
cooling terms are physically coupled. Splitting base from cooling is what lets the ABM
move anything.

**4. Grid** (`gridify.py`) — building watts summed to 100 m cells, divided by cell area → W/m².

**5. ABM** (`abm.py`) — adoption score = income rank × 0.7 + neighbour adoption share × 0.3
(+ noise); buildings ranked and adopted until the household-weighted penetration target is
met. Run as an offline sweep over five levels, each seeded by the previous level's pattern.

**6. Benchmark** (`benchmark.py`) — city-mean profile against the Sailor et al. (2015)
extrapolation for Mumbai (summer peak 40.07 W/m², daily mean 23.46 W/m², peak at 16:00).
The expected difference is shape: Indian residential demand peaks in the evening.

---

## Sanity arithmetic

- 1 kWh/m²·yr = 0.1142 W/m².
- At 50 kWh/m²·yr and FAR 1.5, buildings alone give ≈ 8.6 W/m² of ground area.
- A dense ward on a summer afternoon should land in the 20–60 W/m² band. 3 or 500 means a unit error.
- A 1.5 TR split unit ≈ 5.3 kW thermal.

---

## Known wrong (read before citing anything)

1. **Heights** carry 1.5–9 m error, which propagates straight into floor counts and floor area.
2. **Typology** is ~35% evidence-supported; the rest is a size-and-height heuristic.
3. **EUIs, appliance stocks, U-values and ACH are invented.** No Indian archetype library is used yet.
4. **Income proxy** is ready-reckoner rate at best, dwelling area at worst. Neither is income.
5. **COP is constant at 3.0.** Real COP degrades as ambient temperature rises, so cooling
   energy and waste heat are both understated on the hottest hours.
6. **All condenser heat is treated as sensible.** Commercial cooling towers reject mostly latent heat.
7. **No feedback.** Q_f does not raise air temperature here. Literature puts AC-driven
   nighttime warming at roughly 0.6–1.5 °C; closing the loop needs SUEWS or PALM-4U.
8. **Omitted:** vehicles, human metabolism, industrial process heat, daytime population
   redistribution, spatial weather variation.
9. **ABM is uncalibrated.** No observed AC ownership data has been fitted.

---

## Layout

```
config/params.yaml      all placeholders, tagged by provenance
src/qfmumbai/           library code
scripts/00..07          pipeline steps, each logs to logs/run.log
data/raw|interim|processed
web/                    MapLibre viewer (hour slider + penetration slider)
figures/                benchmark plot
```

Config is hashed into every log line, so a result can be traced to the parameter set
that produced it.
