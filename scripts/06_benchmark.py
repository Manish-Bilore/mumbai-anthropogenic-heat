"""Model vs Sailor extrapolation: table + figure."""
import _bootstrap  # noqa: F401
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from qfmumbai.benchmark import compare, summary
from qfmumbai.config import Config, ROOT
from qfmumbai.io_utils import read_vector, write_table
from qfmumbai.logging_utils import get_logger


def main():
    cfg = Config.load()
    log = get_logger("06_benchmark", cfg)

    grid = read_vector(cfg.path("grid"))
    table = compare(grid, cfg)
    s = summary(grid, cfg)
    for k, v in s.items():
        log.info("%s = %s", k, round(v, 3) if isinstance(v, float) else v)

    out_csv = ROOT / "data" / "processed" / "benchmark_sailor.csv"
    write_table(table, out_csv)

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(table.hour, table.model_wm2, label="This model (bottom-up)", lw=2)
    ax.plot(table.hour, table.sailor_wm2, label="Sailor et al. 2015 (extrapolated)", ls="--", lw=2)
    ax.set_xlabel("Hour (IST)")
    ax.set_ylabel("Q$_f$ (W m$^{-2}$)")
    ax.set_title("Mumbai anthropogenic heat, typical summer day")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig_path = ROOT / "figures" / "qf_profile_vs_sailor.png"
    fig.savefig(fig_path, dpi=150)
    log.info("wrote %s and %s", out_csv, fig_path)


if __name__ == "__main__":
    main()
