#!/usr/bin/env python3
"""Generate the 80289 VFO 80-meter signal-walk study.

The saved KiCad schematic is exported afresh. Generated netlists, raw files,
and logs stay below spice/generated; curated CSVs and figures are written to
the versioned study directory.
"""

from __future__ import annotations

import csv
import os
import subprocess
from pathlib import Path

import numpy as np

import run_80166_headless as core


ROOT = Path(__file__).resolve().parents[2]
SPICE_DIR = ROOT / "spice"
STUDY_DIR = SPICE_DIR / "studies" / "80289" / "signal-walk"
DATA_DIR = STUDY_DIR / "data"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = SPICE_DIR / "generated" / "80289-signal-walk"
NETLIST = GENERATED_DIR / "80289-vfo-80m-signal-walk.cir"
RAW_FILE = GENERATED_DIR / "80289-vfo-80m-signal-walk.raw"
LOG_FILE = GENERATED_DIR / "80289-vfo-80m-signal-walk.log"

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")
SCHEMATIC = ROOT / "triton_540.kicad_sch"

SOURCES_CSV = DATA_DIR / "80289-vfo-80m-sources.csv"
MIXER_CSV = DATA_DIR / "80289-vfo-80m-mixer.csv"
CHAIN_CSV = DATA_DIR / "80289-vfo-80m-filter-buffer-output.csv"
MEASUREMENTS_CSV = DATA_DIR / "80289-vfo-80m-signal-walk-measurements.csv"

SOURCES_PNG = FIGURE_DIR / "80289-vfo-80m-sources.png"
MIXER_PNG = FIGURE_DIR / "80289-vfo-80m-mixer.png"
CHAIN_PNG = FIGURE_DIR / "80289-vfo-80m-filter-buffer-output.png"
PRODUCTS_PNG = FIGURE_DIR / "80289-vfo-80m-product-selection.png"

PLOT_START_S = 78e-6
PLOT_STOP_S = 79e-6
TONE_FREQUENCIES_HZ = (2.25e6, 5.25e6, 7.50e6, 12.75e6)

VECTORS = {
    "pto_emitter_v": "v(net-_q89-5-e_)",
    "crystal_q89_3_drain_v": "v(net-_q89-3-d_)",
    "u89_1_pin1_v": "v(net-_r89-4-pad2_)",
    "u89_1_pin4_v": "v(net-_c89-2-pad1_)",
    "u89_1_pin8_v": "v(net-_u89-1-input_carrier_)",
    "u89_1_pin10_v": "v(net-_u89-1-carrier_input_)",
    "u89_1_pin6_v": "v(net-_s89-1c-c-com_)",
    "u89_1_pin12_v": "v(net-_r89-13-pad2_)",
    "q89_1_gate_v": "v(net-_q89-1-g_)",
    "q89_1_source_v": "v(net-_q89-1-s_)",
    "q89_2_emitter_v": "v(net-_q89-2-e_)",
    "vfo_out_v": "v(/vfo-80289/out)",
}


def run_checked(command: list[str], description: str) -> None:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        print(completed.stdout, end="")
        print(completed.stderr, end="")
        raise SystemExit(
            f"{description} failed with exit code {completed.returncode}"
        )


def run_simulation() -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    run_checked(
        [
            str(KICAD_CLI),
            "sch",
            "export",
            "netlist",
            "--format",
            "spice",
            "-o",
            str(NETLIST),
            str(SCHEMATIC),
        ],
        "KiCad netlist export",
    )
    run_checked(
        [
            str(NGSPICE),
            "-b",
            "-D",
            "ngbehavior=ltpsa",
            "-r",
            str(RAW_FILE),
            "-o",
            str(LOG_FILE),
            str(NETLIST),
        ],
        "ngspice transient analysis",
    )
    log_text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
    if "No. of Data Rows : 20001" not in log_text:
        raise ValueError("Transient run did not produce the expected 20,001 rows")
    if "error" in log_text.lower():
        raise ValueError(f"ngspice reported an error; see {LOG_FILE}")


def load_data() -> tuple[np.ndarray, dict[str, np.ndarray]]:
    names, rows = core.parse_ascii_raw(RAW_FILE)
    indices = {name: index for index, name in enumerate(names)}
    required = {"time", *VECTORS.values()}
    missing = required - indices.keys()
    if missing:
        raise ValueError(f"Raw file is missing vectors: {sorted(missing)}")

    time_s = np.asarray([row[indices["time"]].real for row in rows])
    traces = {
        label: np.asarray([row[indices[node]].real for row in rows])
        for label, node in VECTORS.items()
    }
    traces["u89_1_signal_diff_v"] = (
        traces["u89_1_pin1_v"] - traces["u89_1_pin4_v"]
    )
    traces["u89_1_carrier_diff_v"] = (
        traces["u89_1_pin8_v"] - traces["u89_1_pin10_v"]
    )
    traces["u89_1_output_diff_v"] = (
        traces["u89_1_pin6_v"] - traces["u89_1_pin12_v"]
    )
    return time_s, traces


def write_trace_csv(
    path: Path,
    time_s: np.ndarray,
    traces: dict[str, np.ndarray],
    columns: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["time_s", *columns])
        writer.writerows(
            [f"{time:.12e}", *[f"{traces[name][index]:.12e}" for name in columns]]
            for index, time in enumerate(time_s)
        )


def dominant_frequency_hz(time_s: np.ndarray, values: np.ndarray) -> float:
    mask = (time_s >= 60e-6) & (time_s <= 100e-6)
    selected = values[mask] - np.mean(values[mask])
    delta_t = float(np.median(np.diff(time_s[mask])))
    spectrum = np.abs(np.fft.rfft(selected * np.hanning(selected.size)))
    frequencies = np.fft.rfftfreq(selected.size, delta_t)
    spectrum[0] = 0.0
    return float(frequencies[int(np.argmax(spectrum))])


def fitted_tone_vpp(
    time_s: np.ndarray, values: np.ndarray, frequency_hz: float
) -> float:
    """Return the peak-to-peak amplitude of a least-squares fitted sine."""
    angle = 2.0 * np.pi * frequency_hz * time_s
    design = np.column_stack(
        (np.sin(angle), np.cos(angle), np.ones(time_s.size))
    )
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    return float(2.0 * np.hypot(coefficients[0], coefficients[1]))


def write_measurements(
    time_s: np.ndarray, traces: dict[str, np.ndarray]
) -> list[dict[str, float | str]]:
    mask = (time_s >= 60e-6) & (time_s <= 100e-6)
    rows: list[dict[str, float | str]] = []
    for name, values in traces.items():
        selected = values[mask]
        row: dict[str, float | str] = {
            "trace": name,
            "mean_v": float(np.mean(selected)),
            "minimum_v": float(np.min(selected)),
            "maximum_v": float(np.max(selected)),
            "peak_to_peak_v": float(np.ptp(selected)),
            "dominant_frequency_hz": dominant_frequency_hz(time_s, values),
        }
        for frequency_hz in TONE_FREQUENCIES_HZ:
            label = f"component_{frequency_hz / 1e6:g}mhz_vpp"
            row[label] = fitted_tone_vpp(
                time_s[mask], selected, frequency_hz
            )
        rows.append(row)
    with MEASUREMENTS_CSV.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def plot_ac_coupled(
    time_s: np.ndarray,
    traces: dict[str, np.ndarray],
    panels: list[tuple[str, str, str]],
    title: str,
    output: Path,
) -> None:
    os.environ.setdefault(
        "MPLCONFIGDIR", str(GENERATED_DIR / "matplotlib")
    )
    import matplotlib.pyplot as plt

    mask = (time_s >= PLOT_START_S) & (time_s <= PLOT_STOP_S)
    time_us = time_s[mask] * 1e6
    figure, axes = plt.subplots(
        len(panels),
        1,
        figsize=(11, 2.55 * len(panels)),
        sharex=True,
        constrained_layout=True,
    )
    axes_array = np.atleast_1d(axes)
    for axis, (name, label, color) in zip(axes_array, panels):
        selected = traces[name][mask]
        ac_values = selected - np.mean(selected)
        peak_to_peak = float(np.ptp(selected))
        axis.plot(time_us, ac_values, color=color, linewidth=1.0)
        axis.set_ylabel("AC voltage (V)")
        axis.set_title(f"{label} — {peak_to_peak:.3g} Vpp", loc="left")
        axis.grid(True, alpha=0.3)
    axes_array[-1].set_xlabel("Time (µs)")
    figure.suptitle(f"{title}\n78–79 µs; DC mean removed from each trace")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def plot_product_selection(
    time_s: np.ndarray, traces: dict[str, np.ndarray]
) -> None:
    os.environ.setdefault(
        "MPLCONFIGDIR", str(GENERATED_DIR / "matplotlib")
    )
    import matplotlib.pyplot as plt

    mask = (time_s >= 60e-6) & (time_s <= 100e-6)
    stages = (
        ("u89_1_output_diff_v", "MC1496\nraw output"),
        ("q89_1_gate_v", "Selected filter\noutput"),
        ("vfo_out_v", "Loaded\nVFO OUT"),
    )
    frequencies = (
        (2.25e6, "2.25 MHz difference"),
        (5.25e6, "5.25 MHz PTO"),
        (7.50e6, "7.50 MHz crystal"),
        (12.75e6, "12.75 MHz sum"),
    )
    x_positions = np.arange(len(stages))
    width = 0.19
    figure, axis = plt.subplots(figsize=(10.5, 5.8), constrained_layout=True)
    for offset, (frequency_hz, label) in enumerate(frequencies):
        amplitudes_mvpp = [
            1e3
            * fitted_tone_vpp(
                time_s[mask], traces[trace_name][mask], frequency_hz
            )
            for trace_name, _ in stages
        ]
        axis.bar(
            x_positions + (offset - 1.5) * width,
            amplitudes_mvpp,
            width,
            label=label,
        )
    axis.set_yscale("log")
    axis.set_ylabel("Fitted component amplitude (mVpp)")
    axis.set_xticks(x_positions, [label for _, label in stages])
    axis.set_title(
        "80289 VFO 80 m signal walk: mixer-product selection\n"
        "Least-squares sine fits over 60–100 µs"
    )
    axis.grid(True, axis="y", which="both", alpha=0.3)
    axis.legend(ncols=2)
    PRODUCTS_PNG.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(PRODUCTS_PNG, dpi=180)
    plt.close(figure)


def main() -> None:
    run_simulation()
    time_s, traces = load_data()

    write_trace_csv(
        SOURCES_CSV,
        time_s,
        traces,
        ["pto_emitter_v", "crystal_q89_3_drain_v"],
    )
    write_trace_csv(
        MIXER_CSV,
        time_s,
        traces,
        [
            "u89_1_pin1_v",
            "u89_1_pin4_v",
            "u89_1_signal_diff_v",
            "u89_1_pin8_v",
            "u89_1_pin10_v",
            "u89_1_carrier_diff_v",
            "u89_1_pin6_v",
            "u89_1_pin12_v",
            "u89_1_output_diff_v",
        ],
    )
    write_trace_csv(
        CHAIN_CSV,
        time_s,
        traces,
        [
            "u89_1_output_diff_v",
            "q89_1_gate_v",
            "q89_1_source_v",
            "q89_2_emitter_v",
            "vfo_out_v",
        ],
    )
    measurements = write_measurements(time_s, traces)

    plot_ac_coupled(
        time_s,
        traces,
        [
            ("pto_emitter_v", "PTO input at Q89-5 emitter", "#1f77b4"),
            (
                "crystal_q89_3_drain_v",
                "Crystal oscillator at Q89-3 drain",
                "#d62728",
            ),
        ],
        "80289 VFO 80 m signal walk: source oscillators",
        SOURCES_PNG,
    )
    plot_ac_coupled(
        time_s,
        traces,
        [
            (
                "u89_1_signal_diff_v",
                "MC1496 signal input, pin 1 minus pin 4",
                "#1f77b4",
            ),
            (
                "u89_1_carrier_diff_v",
                "MC1496 carrier input, pin 8 minus pin 10",
                "#ff7f0e",
            ),
            (
                "u89_1_output_diff_v",
                "MC1496 raw output, pin 6 minus pin 12",
                "#2ca02c",
            ),
        ],
        "80289 VFO 80 m signal walk: balanced mixer",
        MIXER_PNG,
    )
    plot_ac_coupled(
        time_s,
        traces,
        [
            (
                "u89_1_output_diff_v",
                "MC1496 raw differential output",
                "#9467bd",
            ),
            ("q89_1_gate_v", "Selected filter output / Q89-1 gate", "#1f77b4"),
            ("q89_1_source_v", "Q89-1 source / Q89-2 base", "#ff7f0e"),
            ("q89_2_emitter_v", "Q89-2 emitter", "#2ca02c"),
            ("vfo_out_v", "Loaded VFO OUT (50 Ω)", "#d62728"),
        ],
        "80289 VFO 80 m signal walk: filter and output buffers",
        CHAIN_PNG,
    )
    plot_product_selection(time_s, traces)

    print(f"Transient rows: {time_s.size}")
    for item in measurements:
        if item["trace"] in {
            "pto_emitter_v",
            "crystal_q89_3_drain_v",
            "u89_1_output_diff_v",
            "q89_1_gate_v",
            "vfo_out_v",
        }:
            print(
                f"{item['trace']}: {item['peak_to_peak_v']:.6g} Vpp, "
                f"{item['dominant_frequency_hz'] / 1e6:.6g} MHz"
            )
    print(f"Data: {DATA_DIR.relative_to(ROOT)}")
    print(f"Figures: {FIGURE_DIR.relative_to(ROOT)}")
    print(f"Run log: {LOG_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
