#!/usr/bin/env python3
"""Sweep 80287 R87-1 and measure receiver mixer products."""

from __future__ import annotations

import csv
import re

import matplotlib.pyplot as plt
import numpy as np

import run_80287_operation as op


FREQUENCIES = (op.RX_INPUT_HZ, op.IF_HZ, op.VFO_HZ, op.VFO_HZ + op.RX_INPUT_HZ)


def set_position(text: str, position: float) -> str:
    pattern = r"(?m)^(\.model __R87-1 potentiometer\( r=1k position=)\S+( \))$"
    updated, count = re.subn(pattern, rf"\g<1>{position:.4f}\g<2>", text)
    if count != 1:
        raise ValueError(f"Expected one R87-1 model; found {count}")
    return updated


def measure(base: str, position: float):
    text = set_position(base, position)
    time, traces = op.run_state(f"rx-balance-{position:.4f}", text, 12.8, 0.2)
    products = op.fit_tones_vpp(time, traces["rx_if"], FREQUENCIES)
    return tuple(products[frequency] for frequency in FREQUENCIES)


def main() -> int:
    op.DATA.mkdir(parents=True, exist_ok=True)
    op.FIGURES.mkdir(parents=True, exist_ok=True)
    base = op.export_netlist()
    coarse = np.linspace(0.0, 1.0, 11)
    rows = [(float(position), *measure(base, float(position))) for position in coarse]
    best_coarse = min(rows, key=lambda row: row[3])[0]
    fine = np.linspace(max(0, best_coarse - 0.1), min(1, best_coarse + 0.1), 21)
    seen = {round(row[0], 6) for row in rows}
    for position in fine:
        if round(float(position), 6) not in seen:
            rows.append((float(position), *measure(base, float(position))))
    rows.sort()

    out = op.DATA / "80287-r87-1-rx-balance-sweep.csv"
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "position",
                "rf_3p499mhz_vpp",
                "wanted_9p001mhz_vpp",
                "vfo_12p5mhz_vpp",
                "sum_15p999mhz_vpp",
            )
        )
        writer.writerows(rows)

    best = min(rows, key=lambda row: row[3])
    positions = np.asarray([row[0] for row in rows])
    fig, axis = plt.subplots(figsize=(9, 5))
    for column, label in (
        (1, "RF 3.499 MHz"),
        (2, "Wanted 9.001 MHz"),
        (3, "VFO 12.5 MHz"),
        (4, "Sum 15.999 MHz"),
    ):
        axis.semilogy(
            positions,
            [max(row[column], 1e-12) for row in rows],
            marker="o",
            label=label,
        )
    axis.axvline(
        best[0],
        color="black",
        linestyle="--",
        linewidth=1,
        label=f"VFO null {best[0]:.3f}",
    )
    axis.set_xlabel("R87-1 normalized wiper position")
    axis.set_ylabel("Fitted Rx 9 MHz node component (V p-p)")
    axis.set_title("80287 receiver mixer-balance sweep")
    axis.grid(True, which="both", alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(op.FIGURES / "80287-r87-1-rx-balance.png", dpi=180)
    plt.close(fig)

    print(f"best_position={best[0]:.6f}")
    print(f"rf_feedthrough_vpp={best[1]:.9g}")
    print(f"wanted_vpp={best[2]:.9g}")
    print(f"vfo_feedthrough_vpp={best[3]:.9g}")
    print(f"sum_product_vpp={best[4]:.9g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
