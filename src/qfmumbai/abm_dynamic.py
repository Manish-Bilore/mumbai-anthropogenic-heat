"""Household-agent model of air-conditioner adoption, with a heat feedback.

Agents
------
One cohort per residential building: N integer households sharing an income band,
an archetype and a location. Adoption is tracked as a count of AC-owning
households per building, so 3.3M household agents cost one integer array.

Each simulated year, every non-owning household draws against a purchase
probability built from four terms:

    u = b0 + b_afford*(afford - 1) + b_discomfort*(cdh/cdh_ref - 1)
           + b_peer*peer_share
    p = p_cap / (1 + exp(-u))

    afford     rises as real incomes grow and AC prices fall
    cdh        cooling degree-hours experienced last summer, INCLUDING the
               temperature increment caused by the city's own waste heat
    peer_share share of neighbouring households (within peer_cell_m) that own
               an AC, smoothed over a 3x3 cell window
    p_cap      ceiling on the annual hazard rate

Feedback
--------
    delta_T(t+1) = k * (Qf_mean(t) - Qf_mean(baseline))

k is a transfer coefficient in K per W/m2. It stands in for a surface energy
balance model (SUEWS/PALM-4U). Literature on AC waste heat puts nighttime
warming near 0.6-1.5 C when cooling is widespread, so k ~ 0.05 K/(W/m2) is the
central guess. It is the single largest assumption in this module: always run
the sensitivity sweep over k before quoting any result.

Penetration is an OUTPUT here, not an input. Nothing forces the trajectory to
hit a target.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.ndimage import uniform_filter

HOURS = 24


# --------------------------------------------------------------------------
# agent state
# --------------------------------------------------------------------------

@dataclass
class Agents:
    """Household cohorts, one row per residential building."""
    households: np.ndarray        # int, households in the building
    adopted: np.ndarray           # int, households owning an AC
    income_rank: np.ndarray       # float 0-1, from the ready-reckoner proxy
    x: np.ndarray                 # projected coords of the building centroid
    y: np.ndarray
    is_res: np.ndarray            # bool mask over the FULL stock
    _ix: np.ndarray = field(default=None, repr=False)
    _iy: np.ndarray = field(default=None, repr=False)

    @property
    def penetration(self) -> float:
        n = self.households.sum()
        return float(self.adopted.sum() / n) if n else 0.0

    def saturation(self) -> np.ndarray:
        """AC-owning fraction per building (0-1)."""
        out = np.zeros_like(self.households, dtype=float)
        nz = self.households > 0
        out[nz] = self.adopted[nz] / self.households[nz]
        return out


def build_agents(stock: pd.DataFrame, cfg) -> Agents:
    res = stock["is_residential"].to_numpy()
    sub = stock[res]

    hh = np.maximum(np.round(sub["households"].to_numpy(float)), 0).astype(np.int64)
    sat0 = sub["ac_saturation_base"].to_numpy(float)
    adopted = np.minimum(np.round(hh * sat0), hh).astype(np.int64)

    rank = sub["income_band"].to_numpy(float)
    rank = (rank - rank.min()) / max(rank.max() - rank.min(), 1e-9)

    cent = sub.geometry.centroid
    return Agents(households=hh, adopted=adopted, income_rank=rank,
                  x=cent.x.to_numpy(), y=cent.y.to_numpy(), is_res=res)


# --------------------------------------------------------------------------
# environment terms
# --------------------------------------------------------------------------

def cooling_degree_hours(weather: pd.DataFrame, cfg, delta_t: float = 0.0) -> float:
    """CDH for one typical day, scaled to a cooling season."""
    t = weather["temp_c"].to_numpy(float) + delta_t
    t_set = float(cfg["cooling"]["setpoint_c"])
    days = float(cfg.get_in("abm_dynamic.cooling_season_days", 210))
    return float(np.clip(t - t_set, 0, None).sum() * days)


def peer_share(ag: Agents, cfg) -> np.ndarray:
    """Share of nearby households owning an AC, on a coarse grid with 3x3 smoothing.

    Grid + convolution rather than a KD-tree: this runs every simulated year, and
    a radius query over 500k buildings x 15 years is not worth the fidelity.
    """
    cell = float(cfg.get_in("abm_dynamic.peer_cell_m", 500))
    if ag._ix is None:
        ag._ix = np.floor((ag.x - ag.x.min()) / cell).astype(int)
        ag._iy = np.floor((ag.y - ag.y.min()) / cell).astype(int)
    ix, iy = ag._ix, ag._iy

    shape = (ix.max() + 1, iy.max() + 1)
    tot = np.zeros(shape, dtype=float)
    own = np.zeros(shape, dtype=float)
    np.add.at(tot, (ix, iy), ag.households)
    np.add.at(own, (ix, iy), ag.adopted)

    tot_s = uniform_filter(tot, size=3, mode="constant")
    own_s = uniform_filter(own, size=3, mode="constant")
    share = np.divide(own_s, tot_s, out=np.zeros_like(own_s), where=tot_s > 0)
    return share[ix, iy]


# --------------------------------------------------------------------------
# the decision
# --------------------------------------------------------------------------

def purchase_probability(ag: Agents, cfg, afford: float, cdh, cdh_ref) -> np.ndarray:
    c = cfg["abm_dynamic"]
    peer = peer_share(ag, cfg)

    # affordability differs by income band: the same price is a smaller barrier
    # higher up the distribution
    afford_i = afford * (float(c["afford_low_band"])
                         + (1.0 - float(c["afford_low_band"])) * ag.income_rank)

    u = (float(c["b0"])
         + float(c["b_afford"]) * (afford_i - 1.0)
         + float(c["b_discomfort"]) * (np.asarray(cdh) / cdh_ref - 1.0)
         + float(c["b_peer"]) * peer)
    return float(c["p_cap"]) / (1.0 + np.exp(-u))


def step(ag: Agents, cfg, rng, afford: float, cdh, cdh_ref) -> np.ndarray:
    """One year. Mutates ag.adopted, returns the per-building probabilities."""
    p = purchase_probability(ag, cfg, afford, cdh, cdh_ref)
    free = ag.households - ag.adopted
    new = rng.binomial(np.maximum(free, 0), np.clip(p, 0.0, 1.0))
    ag.adopted = ag.adopted + new
    return p


def afford_index(cfg, year: int, year0: int) -> float:
    """Real income growth against a falling AC price. 1.0 in the base year."""
    c = cfg["abm_dynamic"]
    n = year - year0
    income = (1.0 + float(c["income_growth_pa"])) ** n
    price = (1.0 - float(c["ac_price_decline_pa"])) ** n
    return float(income / price)


def stock_saturation(ag: Agents, stock: pd.DataFrame) -> np.ndarray:
    """Per-building AC fraction over the FULL stock (non-residential = untouched)."""
    sat = np.zeros(len(stock), dtype=float)
    sat[ag.is_res] = ag.saturation()
    return sat


def agent_discomfort(stock_with_thermal: pd.DataFrame, ag: Agents) -> np.ndarray:
    """Per-agent indoor discomfort degree-hours, aligned to the residential subset."""
    return stock_with_thermal.loc[ag.is_res, "discomfort_dh"].to_numpy(float)
