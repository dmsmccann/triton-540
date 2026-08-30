#!/usr/bin/env python3
"""Generate the 80166 3.5 MHz normal-operation study.

The KiCad schematic is exported afresh. Generated netlists, raw files, and
logs stay below spice/generated; only curated CSVs and figures are written to
the versioned study directory.
"""

from __future__ import annotations

import csv
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import ngspice_raw
import run_80166_headless as core


ROOT = Path(__file__).resolve().parents[2]
SPICE_DIR = ROOT / "spice"
STUDY_DIR = SPICE_DIR / "studies" / "80166" / "operation-3p5mhz"
AC_DATA_DIR = STUDY_DIR / "data" / "ac"
TRANSIENT_DATA_DIR = STUDY_DIR / "data" / "transient"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = SPICE_DIR / "generated" / "80166-operation"
RUN_DIR = GENERATED_DIR / "runs"
BASE_NETLIST = GENERATED_DIR / "80166_base.net"

NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")
KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
SCHEMATIC = ROOT / "triton_540.kicad_sch"

TARGET_HZ = 3.5e6
SOURCE_PEAK_V = 10e-6
ALIGNED_RACK_UH = 17.2
SELECTED_RACKS_UH = (15.4, 17.2, 19.4)
RACK_SWEEP_UH = (
    14.5,
    15.0,
    15.4,
    15.5,
    16.0,
    16.5,
    17.0,
    17.2,
    17.5,
    18.0,
    18.5,
    19.0,
    19.4,
    19.5,
    20.0,
    20.5,
)


def export_netlist() -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        str(KICAD_CLI),
        "sch",
        "export",
        "netlist",
        "--format",
        "spice",
        "-o",
        str(BASE_NETLIST),
        str(SCHEMATIC),
    ]
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
            f"KiCad netlist export failed with exit code {completed.returncode}"
        )


def run_ngspice(tag: str, netlist_text: str) -> tuple[Path, Path]:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    netlist_path = RUN_DIR / f"{tag}.net"
    raw_path = RUN_DIR / f"{tag}.raw"
    log_path = RUN_DIR / f"{tag}.log"
    netlist_path.write_text(netlist_text, encoding="utf-8")
    command = [
        str(NGSPICE),
        "-b",
        "-D",
        "ngbehavior=ltpsa",
        "-r",
        str(raw_path),
        "-o",
        str(log_path),
        str(netlist_path),
    ]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(
            f"ngspice failed with exit code {completed.returncode}; see {log_path}"
        )
    return raw_path, log_path


def ac_arguments(rack_uh: float) -> SimpleNamespace:
    return SimpleNamespace(
        s4_pos=1,
        l_rack=f"{rack_uh:g}u",
        points_per_decade=10000,
        start="3Meg",
        stop="4.2Meg",
        set_component=["C19=36p"],
        c99_node=None,
        c99_value="10n",
    )


def read_ac_csv(path: Path) -> list[dict[str, float]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        return [
            {key: float(value) for key, value in row.items() if key}
            for row in reader
        ]


def interpolate_at(
    rows: list[dict[str, float]], column: str, target_hz: float
) -> float:
    for left, right in zip(rows, rows[1:]):
        if left["frequency"] <= target_hz <= right["frequency"]:
            fraction = (target_hz - left["frequency"]) / (
                right["frequency"] - left["frequency"]
            )
            return left[column] + fraction * (right[column] - left[column])
    return min(rows, key=lambda row: abs(row["frequency"] - target_hz))[column]


def run_ac_study() -> list[dict[str, float]]:
    AC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, float]] = []
    for rack_uh in RACK_SWEEP_UH:
        tag = f"ac-rack-{str(rack_uh).replace('.', 'p')}u"
        netlist = core.build_netlist(ac_arguments(rack_uh), BASE_NETLIST)
        raw_path, _ = run_ngspice(tag, netlist)
        generated_csv = RUN_DIR / f"{tag}.csv"
        result = core.write_csv_and_summary(raw_path, generated_csv)
        rows = read_ac_csv(generated_csv)
        summary.append(
            {
                "l_rack_uH": rack_uh,
                "gain_at_3p5_db": interpolate_at(
                    rows, "user0 (gain)", TARGET_HZ
                ),
                "input_gain_at_3p5_db": interpolate_at(
                    rows, "user3 (gain)", TARGET_HZ
                ),
                "output_peak_hz": float(result["output_peak_hz"]),
                "output_peak_db": float(result["output_peak_db"]),
            }
        )
        if rack_uh in SELECTED_RACKS_UH:
            destination = AC_DATA_DIR / (
                f"rack-{str(rack_uh).replace('.', 'p')}u.csv"
            )
            shutil.copyfile(generated_csv, destination)

    summary_path = AC_DATA_DIR / "rack-gain-at-3p5.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=summary[0].keys())
        writer.writeheader()
        writer.writerows(summary)
    return summary


def build_transient_netlist() -> str:
    text = core.build_netlist(ac_arguments(ALIGNED_RACK_UH), BASE_NETLIST)
    text, count = re.subn(
        r"(?m)^\.ac\s+.*$",
        ".tran 2n 60u",
        text,
    )
    if count != 1:
        raise ValueError(f"Expected one AC directive; found {count}")
    text, count = re.subn(
        r"(?m)^(V3\s+\S+\s+\S+\s+).*$",
        rf"\g<1>SIN(0 {SOURCE_PEAK_V:g} 3.5Meg)",
        text,
    )
    if count != 1:
        raise ValueError(f"Expected one V3 source; found {count}")
    return text


def half_peak_to_peak(values: list[float]) -> float:
    return 0.5 * (max(values) - min(values))


def write_transient_data(raw_path: Path) -> list[dict[str, float | str]]:
    TRANSIENT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    names, raw_rows = ngspice_raw.parse_ascii_raw(raw_path)
    indices = {name: index for index, name in enumerate(names)}
    vectors = {
        "ant": "v(/rf_amp_80166/ant)",
        "gate1": "v(/rf_amp_80166/q1_gate1)",
        "drain": "v(/rf_amp_80166/q1_drain)",
        "out": "v(/rf_amp_80166/out)",
    }
    required = {"time", *vectors.values()}
    missing = required - indices.keys()
    if missing:
        raise ValueError(f"Transient raw file is missing: {sorted(missing)}")

    rows: list[dict[str, float]] = []
    for raw_row in raw_rows:
        rows.append(
            {
                "time_s": raw_row[indices["time"]].real,
                **{
                    label: raw_row[indices[vector]].real
                    for label, vector in vectors.items()
                },
            }
        )

    period = 1.0 / TARGET_HZ
    steady_start = rows[-1]["time_s"] - 6.0 * period
    steady = [row for row in rows if row["time_s"] >= steady_start]
    dc_levels = {
        label: sum(row[label] for row in steady) / len(steady)
        for label in vectors
    }
    amplitudes = {
        label: half_peak_to_peak([row[label] for row in steady])
        for label in vectors
    }

    steady_path = TRANSIENT_DATA_DIR / "steady-state.csv"
    with steady_path.open("w", newline="", encoding="utf-8") as stream:
        fieldnames = [
            "time_us",
            "ant_ac_uV",
            "gate1_ac_uV",
            "drain_ac_uV",
            "out_ac_uV",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in steady:
            writer.writerow(
                {
                    "time_us": (row["time_s"] - steady_start) * 1e6,
                    **{
                        f"{label}_ac_uV": (row[label] - dc_levels[label]) * 1e6
                        for label in vectors
                    },
                }
            )

    cycles: dict[int, list[dict[str, float]]] = {}
    for row in rows:
        cycle = int(row["time_s"] / period)
        cycles.setdefault(cycle, []).append(row)
    envelope_path = TRANSIENT_DATA_DIR / "envelope.csv"
    with envelope_path.open("w", newline="", encoding="utf-8") as stream:
        fieldnames = [
            "time_us",
            "ant_peak_uV",
            "gate1_peak_uV",
            "drain_peak_uV",
            "out_peak_uV",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for cycle, cycle_rows in sorted(cycles.items()):
            if len(cycle_rows) < 10:
                continue
            writer.writerow(
                {
                    "time_us": (cycle + 0.5) * period * 1e6,
                    **{
                        f"{label}_peak_uV": half_peak_to_peak(
                            [row[label] for row in cycle_rows]
                        )
                        * 1e6
                        for label in vectors
                    },
                }
            )

    measurements: list[dict[str, float | str]] = []
    ant_amplitude = amplitudes["ant"]
    for label in vectors:
        ratio = amplitudes[label] / ant_amplitude
        measurements.append(
            {
                "node": label,
                "dc_v": dc_levels[label],
                "peak_uV": amplitudes[label] * 1e6,
                "voltage_ratio_from_ant": ratio,
                "gain_from_ant_db": 20.0 * math.log10(ratio),
            }
        )
    measurements_path = TRANSIENT_DATA_DIR / "measurements.csv"
    with measurements_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=measurements[0].keys())
        writer.writeheader()
        writer.writerows(measurements)
    return measurements


def read_csv(path: Path) -> list[dict[str, float]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return [
            {key: float(value) for key, value in row.items()}
            for row in csv.DictReader(stream)
        ]


def read_measurements(path: Path) -> dict[str, dict[str, float | str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return {
            row["node"]: {
                key: value if key == "node" else float(value)
                for key, value in row.items()
            }
            for row in csv.DictReader(stream)
        }


def plot_study() -> None:
    os.environ.setdefault(
        "MPLCONFIGDIR", str(SPICE_DIR / "generated" / "matplotlib")
    )
    import matplotlib.pyplot as plt

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    colors = {15.4: "#2980b9", 17.2: "#c0392b", 19.4: "#8e44ad"}
    figure, (responses, rack_gain) = plt.subplots(
        2,
        1,
        figsize=(10.5, 8.2),
        gridspec_kw={"height_ratios": (1.35, 1)},
        constrained_layout=True,
    )
    for rack_uh in SELECTED_RACKS_UH:
        path = AC_DATA_DIR / f"rack-{str(rack_uh).replace('.', 'p')}u.csv"
        rows = read_ac_csv(path)
        responses.plot(
            [row["frequency"] / 1e6 for row in rows],
            [row["user0 (gain)"] for row in rows],
            color=colors[rack_uh],
            linewidth=2,
            label=f"L_RACK = {rack_uh:g} µH",
        )
    responses.axvline(3.5, color="#222222", linestyle="--", linewidth=1.2)
    responses.set_xlim(3.0, 4.2)
    responses.set_ylabel("ANT-to-OUT voltage gain (dB)")
    responses.set_title("Turning RESONATE Moves the 3.5 MHz Passband")
    responses.grid(True, alpha=0.25)
    responses.legend()

    summary = read_csv(AC_DATA_DIR / "rack-gain-at-3p5.csv")
    rack_gain.plot(
        [row["l_rack_uH"] for row in summary],
        [row["gain_at_3p5_db"] for row in summary],
        color="#16a085",
        marker="o",
        markersize=4.5,
        linewidth=1.8,
    )
    rack_gain.axvline(
        ALIGNED_RACK_UH,
        color="#c0392b",
        linestyle="--",
        linewidth=1.2,
        label="Manual-aligned rack setting",
    )
    rack_gain.set_xlabel("Fitted L_RACK parameter (µH)")
    rack_gain.set_ylabel("Gain at 3.500 MHz (dB)")
    rack_gain.grid(True, alpha=0.25)
    rack_gain.legend()
    figure.savefig(FIGURE_DIR / "rack-tuning.png", dpi=180)
    plt.close(figure)

    envelope = read_csv(TRANSIENT_DATA_DIR / "envelope.csv")
    steady = read_csv(TRANSIENT_DATA_DIR / "steady-state.csv")
    measurements = read_measurements(TRANSIENT_DATA_DIR / "measurements.csv")
    figure = plt.figure(figsize=(10.5, 10.5), constrained_layout=True)
    grid = figure.add_gridspec(5, 1, height_ratios=(1.5, 1, 1, 1, 1))
    envelope_axis = figure.add_subplot(grid[0])
    waveform_axes = [figure.add_subplot(grid[index]) for index in range(1, 5)]
    node_style = (
        ("ant", "ANT", "#2c3e50"),
        ("gate1", "Q1 gate 1", "#8e44ad"),
        ("drain", "Q1 drain", "#2980b9"),
        ("out", "OUT", "#c0392b"),
    )

    for node, label, color in node_style:
        envelope_axis.plot(
            [row["time_us"] for row in envelope],
            [row[f"{node}_peak_uV"] for row in envelope],
            color=color,
            linewidth=1.7,
            label=label,
        )
    envelope_axis.set_title("Aligned 3.5 MHz Response Building to Steady State")
    envelope_axis.set_xlabel("Time (µs)")
    envelope_axis.set_ylabel("RF peak amplitude (µV)")
    envelope_axis.grid(True, alpha=0.25)
    envelope_axis.legend(ncol=2)

    for axis, (node, label, color) in zip(waveform_axes, node_style):
        axis.plot(
            [row["time_us"] for row in steady],
            [row[f"{node}_ac_uV"] for row in steady],
            color=color,
            linewidth=1.4,
        )
        peak_uv = measurements[node]["peak_uV"]
        axis.set_ylabel(f"{label}\n(µV)")
        axis.text(
            0.99,
            0.84,
            f"peak ≈ {peak_uv:.2f} µV",
            transform=axis.transAxes,
            ha="right",
            va="top",
            color=color,
        )
        axis.grid(True, alpha=0.25)
    waveform_axes[0].set_title("Final Six RF Cycles, with DC Bias Removed")
    waveform_axes[-1].set_xlabel("Time within retained window (µs)")
    figure.savefig(FIGURE_DIR / "signal-walk.png", dpi=180)
    plt.close(figure)


def main() -> int:
    export_netlist()
    ac_summary = run_ac_study()
    transient_raw, _ = run_ngspice("transient-aligned-3p5mhz", build_transient_netlist())
    measurements = write_transient_data(transient_raw)
    plot_study()

    best = max(ac_summary, key=lambda row: row["gain_at_3p5_db"])
    print(
        f"Best sampled rack: {best['l_rack_uH']:.4g} uH, "
        f"{best['gain_at_3p5_db']:.3f} dB at 3.5 MHz"
    )
    for row in measurements:
        print(
            f"{row['node']}: {row['peak_uV']:.4f} uV peak, "
            f"{row['gain_from_ant_db']:.3f} dB from ANT"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
