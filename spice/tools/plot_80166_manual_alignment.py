#!/usr/bin/env python3
"""Plot the simulated 80166 manual-alignment sequence.

The source data are KiCad Simulator CSV exports plus the final 29 MHz CSV
generated from a fresh KiCad SPICE-netlist export with ngspice 46.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPICE_DIR = ROOT / "spice"
STUDY_DIR = SPICE_DIR / "studies" / "80166" / "manual-alignment"
FINAL_DATA_DIR = STUDY_DIR / "data" / "final"
ITERATION_DATA_DIR = STUDY_DIR / "data" / "29mhz-iterations"
PLOT_DIR = STUDY_DIR / "figures"

os.environ.setdefault(
    "MPLCONFIGDIR", str(SPICE_DIR / "generated" / "matplotlib")
)

import matplotlib.pyplot as plt
import numpy as np


@dataclass(frozen=True)
class Trace:
    frequency_hz: np.ndarray
    overall_db: np.ndarray
    input_db: np.ndarray


@dataclass(frozen=True)
class BandResult:
    label: str
    target_hz: float
    rack: str
    output_adjustment: str
    bypass_csv: Path
    final_csv: Path


def read_trace(path: Path) -> Trace:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        rows = list(reader)

    return Trace(
        frequency_hz=np.asarray([float(row["frequency"]) for row in rows]),
        overall_db=np.asarray([float(row["user0 (gain)"]) for row in rows]),
        input_db=np.asarray([float(row["user3 (gain)"]) for row in rows]),
    )


def peak(trace: Trace, values: np.ndarray) -> tuple[float, float]:
    index = int(np.argmax(values))
    return trace.frequency_hz[index], values[index]


def nearest_value(
    trace: Trace, values: np.ndarray, target_hz: float
) -> tuple[float, float]:
    index = int(np.argmin(np.abs(trace.frequency_hz - target_hz)))
    return trace.frequency_hz[index], values[index]


def normalized(values: np.ndarray) -> np.ndarray:
    return values - np.max(values)


BANDS = (
    BandResult(
        "3.5 MHz",
        3.5e6,
        "17.2 uH",
        "C19 = 36 pF",
        FINAL_DATA_DIR / "3p5_l1-bypassed.csv",
        FINAL_DATA_DIR / "3p5_aligned.csv",
    ),
    BandResult(
        "4.0 MHz",
        4.0e6,
        "7.7 uH",
        "L2 tracking fit",
        FINAL_DATA_DIR / "4p0_l1-bypassed.csv",
        FINAL_DATA_DIR / "4p0_aligned.csv",
    ),
    BandResult(
        "7.0 MHz",
        7.0e6,
        "3.43 uH",
        "C17 about 68 pF effective",
        FINAL_DATA_DIR / "7p0_l1-bypassed.csv",
        FINAL_DATA_DIR / "7p0_aligned.csv",
    ),
    BandResult(
        "14.2 MHz",
        14.2e6,
        "2.84 uH",
        "C16 = 47.2 pF",
        FINAL_DATA_DIR / "14p2_l1-bypassed.csv",
        FINAL_DATA_DIR / "14p2_aligned.csv",
    ),
    BandResult(
        "21.2 MHz",
        21.2e6,
        "2.06 uH",
        "C15 = 16.94 pF",
        FINAL_DATA_DIR / "21p2_l1-bypassed.csv",
        FINAL_DATA_DIR / "21p2_aligned.csv",
    ),
    BandResult(
        "29.0 MHz",
        29.0e6,
        "1.4253 uH",
        "C13 = 5.787 pF",
        FINAL_DATA_DIR / "29p0_l1-bypassed.csv",
        FINAL_DATA_DIR / "29p0_aligned.csv",
    ),
)


def plot_all_bands() -> None:
    figure, axis = plt.subplots(figsize=(10.5, 6.2), constrained_layout=True)
    colors = ("#2c3e50", "#2980b9", "#16a085", "#8e44ad", "#d35400", "#c0392b")

    for band, color in zip(BANDS, colors):
        trace = read_trace(band.final_csv)
        offset_percent = 100.0 * (trace.frequency_hz / band.target_hz - 1.0)
        axis.plot(
            offset_percent,
            normalized(trace.overall_db),
            label=band.label,
            color=color,
            linewidth=1.9,
        )

    axis.axvline(0, color="#222222", linestyle="--", linewidth=1.2)
    axis.set_xlim(-3.5, 3.5)
    axis.set_ylim(-25, 1)
    axis.set_xlabel("Frequency offset from the manual target (%)")
    axis.set_ylabel("ANT-to-OUT gain relative to each run's peak (dB)")
    axis.set_title("80166 Manual Alignment: Final Response on Every Band")
    axis.grid(True, alpha=0.25)
    axis.legend(ncol=2, loc="lower center")
    figure.savefig(PLOT_DIR / "all-bands.png", dpi=180)
    plt.close(figure)


def plot_29mhz_adjustment() -> None:
    bypass = read_trace(BANDS[-1].bypass_csv)
    selected = (
        (
            24.0,
            ITERATION_DATA_DIR / "29p0_c13-24p.csv",
        ),
        (
            8.07,
            ITERATION_DATA_DIR / "29p0_c13-8p07.csv",
        ),
        (
            6.13,
            ITERATION_DATA_DIR / "29p0_c13-6p13.csv",
        ),
        (5.787, BANDS[-1].final_csv),
    )

    all_trials = (
        (24.0, selected[0][1]),
        (8.07, selected[1][1]),
        (
            6.70,
            ITERATION_DATA_DIR / "29p0_c13-6p70.csv",
        ),
        (
            6.35,
            ITERATION_DATA_DIR / "29p0_c13-6p35.csv",
        ),
        (
            6.21,
            ITERATION_DATA_DIR / "29p0_c13-6p21.csv",
        ),
        (6.13, selected[2][1]),
        (
            5.95,
            ITERATION_DATA_DIR / "29p0_c13-5p95.csv",
        ),
        (
            5.865,
            ITERATION_DATA_DIR / "29p0_c13-5p865.csv",
        ),
        (
            5.81,
            ITERATION_DATA_DIR / "29p0_c13-5p81.csv",
        ),
        (5.787, BANDS[-1].final_csv),
    )

    figure, (responses, convergence) = plt.subplots(
        2,
        1,
        figsize=(10.5, 8.7),
        gridspec_kw={"height_ratios": (1.35, 1)},
        constrained_layout=True,
    )

    responses.plot(
        bypass.frequency_hz / 1e6,
        normalized(bypass.input_db),
        color="#2c3e50",
        linewidth=2.2,
        linestyle="--",
        label="L1 peaked with L2 bypassed",
    )
    colors = ("#95a5a6", "#2980b9", "#d35400", "#c0392b")
    for (capacitance, path), color in zip(selected, colors):
        trace = read_trace(path)
        responses.plot(
            trace.frequency_hz / 1e6,
            normalized(trace.overall_db),
            color=color,
            linewidth=1.9,
            label=f"Full stage, C13 = {capacitance:g} pF",
        )
    responses.axvline(29.0, color="#222222", linestyle=":", linewidth=1.2)
    responses.set_xlim(19, 30.2)
    responses.set_ylim(-32, 1)
    responses.set_ylabel("Gain relative to each trace's peak (dB)")
    responses.set_title("29 MHz Alignment: Rack First, Then C13")
    responses.grid(True, alpha=0.25)
    responses.legend(loc="lower left", fontsize=8.7)

    capacitances = []
    peak_frequencies = []
    for capacitance, path in all_trials:
        trace = read_trace(path)
        peak_frequency, _ = peak(trace, trace.overall_db)
        capacitances.append(capacitance)
        peak_frequencies.append(peak_frequency / 1e6)

    convergence.plot(
        capacitances,
        peak_frequencies,
        color="#8e44ad",
        marker="o",
        markersize=5,
        linewidth=1.8,
    )
    convergence.axhline(
        29.0,
        color="#222222",
        linestyle="--",
        linewidth=1.2,
        label="29.000 MHz target",
    )
    convergence.scatter(
        [5.787],
        [peak_frequencies[-1]],
        color="#c0392b",
        s=55,
        zorder=3,
    )
    convergence.annotate(
        "5.787 pF → 28.999365 MHz",
        (5.787, peak_frequencies[-1]),
        xytext=(18, -28),
        textcoords="offset points",
        color="#922b21",
    )
    convergence.invert_xaxis()
    convergence.set_xlabel("C13 setting (pF; decreasing to the right)")
    convergence.set_ylabel("ANT-to-OUT peak (MHz)")
    convergence.grid(True, alpha=0.25)
    convergence.legend(loc="lower right")
    figure.savefig(PLOT_DIR / "29mhz-adjustment.png", dpi=180)
    plt.close(figure)


def print_summary() -> None:
    print(
        "band,target_mhz,rack,output_adjustment,"
        "bypassed_overall_peak_mhz,bypassed_input_peak_mhz,"
        "final_output_peak_mhz,error_khz,"
        "loss_at_target_db"
    )
    for band in BANDS:
        bypass = read_trace(band.bypass_csv)
        final = read_trace(band.final_csv)
        bypass_overall_peak_hz, _ = peak(bypass, bypass.overall_db)
        bypass_input_peak_hz, _ = peak(bypass, bypass.input_db)
        final_peak_hz, final_peak_db = peak(final, final.overall_db)
        _, target_db = nearest_value(final, final.overall_db, band.target_hz)
        print(
            f"{band.label},{band.target_hz / 1e6:.6f},{band.rack},"
            f"{band.output_adjustment},{bypass_overall_peak_hz / 1e6:.6f},"
            f"{bypass_input_peak_hz / 1e6:.6f},"
            f"{final_peak_hz / 1e6:.6f},"
            f"{(final_peak_hz - band.target_hz) / 1e3:+.3f},"
            f"{final_peak_db - target_db:.3f}"
        )


def main() -> None:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    plot_all_bands()
    plot_29mhz_adjustment()
    print_summary()


if __name__ == "__main__":
    main()
