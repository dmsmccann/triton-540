#!/usr/bin/env python3
"""Plot and compare 80166 rf amplifier sweeps captured by bode_80166.py.

    python plot_bode.py data/80166-80m-l1-only-*.csv data/80166-80m-composite-*.csv \
        -o plots/80166-80m-tracking.png

Overlays each sweep, marks the 3.5 and 4.0 MHz alignment points, and reports
peak frequency, -3 dB bandwidth and loaded Q for each curve.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ALIGNMENT_POINTS = (3.5e6, 4.0e6)


def read_sweep(path: Path):
    meta, freqs, gains = {}, [], []
    with path.open(encoding="utf-8") as fh:
        rows = []
        for line in fh:
            if line.startswith("#"):
                parts = line[1:].strip().split(",", 1)
                if len(parts) == 2:
                    meta[parts[0].strip()] = parts[1].strip()
                continue
            rows.append(line)
    reader = csv.DictReader(rows)
    for r in reader:
        try:
            g = float(r["gain_db"])
        except (TypeError, ValueError):
            continue
        if math.isnan(g):
            continue
        freqs.append(float(r["frequency_hz"]))
        gains.append(g)
    meta.setdefault("label", path.stem)
    return meta, freqs, gains


def interp_crossing(freqs, gains, level, lo, hi, direction):
    """Frequency where the curve crosses `level`, searching outward from the peak."""
    rng = range(lo, hi) if direction > 0 else range(lo, hi, -1)
    for i in rng:
        j = i + direction
        if j < 0 or j >= len(gains):
            break
        if (gains[i] - level) * (gains[j] - level) <= 0 and gains[i] != gains[j]:
            t = (level - gains[i]) / (gains[j] - gains[i])
            return freqs[i] + t * (freqs[j] - freqs[i])
    return None


def summarise(freqs, gains):
    pk = max(range(len(gains)), key=lambda i: gains[i])
    f_pk, g_pk = freqs[pk], gains[pk]
    lo = interp_crossing(freqs, gains, g_pk - 3.0, pk, 0, -1)
    hi = interp_crossing(freqs, gains, g_pk - 3.0, pk, len(gains), +1)
    bw = hi - lo if (lo and hi) else None
    q = f_pk / bw if bw else None
    at = {}
    for target in ALIGNMENT_POINTS:
        i = min(range(len(freqs)), key=lambda k: abs(freqs[k] - target))
        at[target] = gains[i]
    return {"f_peak": f_pk, "g_peak": g_pk, "f_lo": lo, "f_hi": hi,
            "bw": bw, "q": q, "at": at}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="+", type=Path)
    p.add_argument("-o", "--output", type=Path,
                   default=Path(__file__).parent / "plots" / "80166-80m-tracking.png")
    p.add_argument("--normalize", action="store_true",
                   help="shift each curve so its peak sits at 0 dB")
    p.add_argument("--title", default="Ten-Tec 540 - 80166 rf amplifier, 80 m response")
    p.add_argument("--dpi", type=int, default=140)
    args = p.parse_args(argv)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9.5, 5.4))

    lines = []
    for path in args.csv:
        meta, freqs, gains = read_sweep(path)
        if not freqs:
            print(f"{path}: no valid points, skipped")
            continue
        s = summarise(freqs, gains)
        offset = -s["g_peak"] if args.normalize else 0.0
        label = meta.get("label", path.stem)
        ax.plot([f / 1e6 for f in freqs], [g + offset for g in gains],
                lw=1.8, label=label)
        ax.plot(s["f_peak"] / 1e6, s["g_peak"] + offset, "o", ms=5,
                color=ax.lines[-1].get_color())
        lines.append((label, meta, s))

    for f in ALIGNMENT_POINTS:
        ax.axvline(f / 1e6, color="0.6", ls="--", lw=1.0, zorder=0)
        ax.annotate(f"{f/1e6:.1f} MHz", (f / 1e6, 0.985), xycoords=("data", "axes fraction"),
                    ha="center", va="top", fontsize=8, color="0.35")
    ax.axvspan(3.5, 4.0, color="0.9", zorder=-1)

    ax.set_xlabel("frequency (MHz)")
    ax.set_ylabel("normalised response (dB)" if args.normalize else "gain (dB)")
    ax.set_title(args.title)
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(loc="best", frameon=False)
    fig.tight_layout()
    fig.savefig(args.output, dpi=args.dpi)
    print(f"wrote {args.output}")

    print()
    hdr = f"{'sweep':<14}{'peak MHz':>10}{'peak dB':>10}{'-3dB BW kHz':>13}{'Q':>7}" \
          f"{'3.5 MHz dB':>12}{'4.0 MHz dB':>12}"
    print(hdr)
    print("-" * len(hdr))
    for label, meta, s in lines:
        bw = f"{s['bw']/1e3:.1f}" if s["bw"] else "n/a"
        q = f"{s['q']:.1f}" if s["q"] else "n/a"
        print(f"{label:<14}{s['f_peak']/1e6:>10.4f}{s['g_peak']:>10.2f}"
              f"{bw:>13}{q:>7}"
              f"{s['at'][3.5e6]:>12.2f}{s['at'][4.0e6]:>12.2f}")

    if len(lines) >= 2:
        (la, _, sa), (lb, _, sb) = lines[0], lines[1]
        delta = (sb["f_peak"] - sa["f_peak"]) / 1e3
        print(f"\npeak offset {lb} - {la}: {delta:+.1f} kHz")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
