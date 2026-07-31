#!/usr/bin/env python3
"""Report the aligned 80289 filter shapes without rerunning optimization."""

from __future__ import annotations

import csv
import os
import re

import numpy as np

import run_80289_filter_ac_alignment as alignment
import run_80289_filter_response as transient


OUTPUT_CSV = (
    alignment.DATA_DIR / "80289-vfo-filter-ac-response.csv"
)
OUTPUT_PNG = (
    alignment.STUDY_DIR
    / "figures"
    / "80289-vfo-filter-ac-response.png"
)


def saved_parameters(netlist_text: str) -> dict[str, float]:
    parameters: dict[str, float] = {}
    for name in alignment.PARAMETER_ORDER:
        match = re.search(
            rf"(?m)^\.param {re.escape(name)}=(\S+)\s*$", netlist_text
        )
        if not match:
            raise ValueError(f"Missing {name} in exported netlist")
        value = match.group(1)
        parameters[name] = float(value.rstrip("uUpP"))
    return parameters


def main() -> None:
    base_text = alignment.export_netlist()
    parameters = saved_parameters(base_text)
    rows: list[dict[str, float | int | str]] = []
    summaries: list[tuple[str, dict[str, float]]] = []

    for path in transient.FILTERS:
        span = path.manual_high_mhz - path.manual_low_mhz
        netlist = alignment.make_ac_netlist(
            base_text,
            parameters,
            path.s4_pos,
            path.manual_low_mhz - 0.15 * span,
            path.manual_high_mhz + 0.15 * span,
        )
        frequency_hz, response = alignment.run_ac(
            f"final_{path.name.replace(' ', '').lower()}", netlist
        )
        metrics = alignment.response_metrics(
            frequency_hz,
            response,
            path.manual_low_mhz,
            path.manual_high_mhz,
        )
        summaries.append((path.name, metrics))
        frequency_mhz = frequency_hz / 1e6
        in_band = (
            (frequency_mhz >= path.manual_low_mhz)
            & (frequency_mhz <= path.manual_high_mhz)
        )
        reference = float(np.max(response[in_band]))
        normalized_db = 20.0 * np.log10(
            np.maximum(response / reference, 1e-30)
        )
        for frequency, magnitude, magnitude_db in zip(
            frequency_mhz, response, normalized_db
        ):
            rows.append(
                {
                    "filter_path": path.name,
                    "filter_components": path.components,
                    "s4_pos": path.s4_pos,
                    "frequency_mhz": float(frequency),
                    "transimpedance_ohm": float(magnitude),
                    "normalized_db": float(magnitude_db),
                    "inside_manual_range": (
                        "yes"
                        if path.manual_low_mhz
                        <= frequency
                        <= path.manual_high_mhz
                        else "no"
                    ),
                }
            )

    alignment.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            formatted = dict(row)
            for field in ("frequency_mhz", "transimpedance_ohm", "normalized_db"):
                formatted[field] = f"{float(row[field]):.9g}"
            writer.writerow(formatted)

    os.environ.setdefault(
        "MPLCONFIGDIR", str(alignment.GENERATED_DIR / "matplotlib")
    )
    import matplotlib.pyplot as plt

    OUTPUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(
        2, 2, figsize=(12.5, 8.2), constrained_layout=True
    )
    for axis, path in zip(axes.flat, transient.FILTERS):
        selected = [row for row in rows if row["filter_path"] == path.name]
        axis.axvspan(
            path.manual_low_mhz,
            path.manual_high_mhz,
            color="#2ca02c",
            alpha=0.10,
            label="Documented range",
        )
        axis.plot(
            [float(row["frequency_mhz"]) for row in selected],
            [float(row["normalized_db"]) for row in selected],
            color="#1f77b4",
            linewidth=1.6,
            label="Loaded filter response",
        )
        axis.axhline(-3.0, color="#777777", linestyle="--", linewidth=0.9)
        axis.set(
            title=f"{path.name}: {path.components}, S4={path.s4_pos}",
            xlabel="Frequency (MHz)",
            ylabel="Normalized response (dB)",
            ylim=(-12.0, 1.0),
        )
        axis.grid(True, alpha=0.3)
        axis.legend(loc="lower center", fontsize=8)
    figure.suptitle(
        "80289 VFO aligned switched-filter response\n"
        "AC current excitation at mixer/filter interface; normal circuit loading retained",
        fontsize=13,
    )
    figure.savefig(OUTPUT_PNG, dpi=170)
    plt.close(figure)

    print("Saved parameters:")
    for name in alignment.PARAMETER_ORDER:
        print(f"  {name}={alignment.parameter_text(name, parameters[name])}")
    for name, metrics in summaries:
        print(
            f"{name}: low={metrics['low_db']:.3f} dB, "
            f"center={metrics['center_db']:.3f} dB, "
            f"high={metrics['high_db']:.3f} dB, "
            f"ripple={metrics['ripple_db']:.3f} dB"
        )
    print(f"CSV: {OUTPUT_CSV.relative_to(alignment.ROOT)}")
    print(f"Figure: {OUTPUT_PNG.relative_to(alignment.ROOT)}")


if __name__ == "__main__":
    main()
