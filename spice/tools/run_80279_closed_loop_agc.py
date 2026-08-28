#!/usr/bin/env python3
"""Run 80279 Simulation 6: closed-loop AGC attack and release.

The study has two deliberately separate time scales:

1. A short full-RF transient uses the complete KiCad circuit, a 9.001 MHz
   weak/strong/weak IF sequence, and a 9.000 MHz BFO.  It validates the sign
   and onset of feedback through Q79-3, IC1, D79-6, Q79-4/Q79-5, and the three
   PIN diodes.
2. A long audio-envelope transient keeps the real audio/AGC/control circuit
   but replaces the expensive 9 MHz path with a behavioral source calibrated
   from Simulation 4 and attenuated by the Simulation 3 PIN-bus transfer.
   It measures multi-second release without integrating billions of RF steps.

The KiCad schematic is exported afresh.  All source substitutions occur only
in disposable netlist copies below spice/generated.
"""

from __future__ import annotations

import csv
import math
import re
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SCHEMATIC = ROOT / "if-agc_80279.kicad_sch"
STUDY_DIR = ROOT / "spice" / "studies" / "80279" / "closed-loop-agc"
DATA_DIR = STUDY_DIR / "data"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = ROOT / "spice" / "generated" / "80279-closed-loop-agc"
BASE_NETLIST = GENERATED_DIR / "80279-closed-loop-agc-base.cir"

PIN_SWEEP_CSV = (
    ROOT / "spice" / "studies" / "80279" / "pin-agc-sweep" / "data"
    / "80279-pin-agc-sweep-summary.csv"
)
DETECTOR_CSV = (
    ROOT / "spice" / "studies" / "80279" / "product-detector" / "data"
    / "80279-detector-sweep.csv"
)

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")

IF_HZ = 9.001e6
BFO_HZ = 9.000e6
AUDIO_HZ = IF_HZ - BFO_HZ
BFO_AMPLITUDE_V_PEAK = 0.4
WEAK_IF_V_PEAK = 1e-6
STRONG_IF_V_PEAK = 100e-6
RF_STRONG_IF_V_PEAK = STRONG_IF_V_PEAK
PRECHARGE_STORE_V = 2.32535121669

RF_PRE_END_S = 2e-3
RF_STRONG_END_S = 8e-3
RF_STOP_S = 10e-3
RF_OUTPUT_STEP_S = 20e-9
RF_MAX_STEP_S = 1e-9

ENV_PRE_END_S = 0.2
ENV_STRONG_END_S = 1.2
ENV_STOP_S = 12.0
ENV_OUTPUT_STEP_S = 50e-6
ENV_MAX_STEP_S = 10e-6

RF_TRACES = (
    ("board_in", "/in"),
    ("q79_3_g1", "net-_q79-3-g1_"),
    ("filt_loop", "/filt_in"),
    ("audio", "/audio"),
    ("agc_store", "net-_d79-6-k_"),
    ("pin_bias", "/pin_bias"),
    ("d79_1_feed", "net-_d79-1-a_"),
    ("s_meter", "/s_mtr"),
)

ENV_TRACES = (
    ("filt_loop", "/filt_in"),
    ("audio", "/audio"),
    ("agc_opamp", "net-_ic1-output_a_"),
    ("agc_store", "net-_d79-6-k_"),
    ("pin_bias", "/pin_bias"),
    ("d79_1_feed", "net-_d79-1-a_"),
    ("s_meter", "/s_mtr"),
)


def run(command: list[str], cwd: Path, description: str) -> None:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if completed.returncode:
        print(completed.stdout, end="")
        print(completed.stderr, end="")
        raise SystemExit(f"{description} failed with exit code {completed.returncode}")


def export_netlist() -> str:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    if not KICAD_CLI.exists():
        raise SystemExit(f"KiCad CLI was not found: {KICAD_CLI}")
    if not NGSPICE.exists():
        raise SystemExit(f"ngspice was not found: {NGSPICE}")
    run(
        [
            str(KICAD_CLI), "sch", "export", "netlist", "--format", "spice",
            "-o", str(BASE_NETLIST), str(SCHEMATIC),
        ],
        ROOT,
        "KiCad netlist export",
    )
    text = BASE_NETLIST.read_text(encoding="utf-8")
    required = (
        "V79-SIM5 /IN GND DC 0",
        "V79-SIM6 /BFO GND DC 6.5",
        "D79-5 Net-_D79-5-A_ /PIN_BIAS 1N4154",
        "D79-6 Net-_D79-6-A_ Net-_D79-6-K_ 1N4154",
        "C79-22 Net-_D79-6-K_ GND 4.7u",
        "R79-24 Net-_D79-6-K_ GND 680k",
        "R79-19 Net-_D79-1-A_ /PIN_BIAS 1k",
        "XD79-1 GND Net-_D79-1-A_ HP5082_3379",
        "R79-SIM1 /AUDIO GND 25k",
        "R79-SIM2 /S_MTR GND 1k",
        ".options rshunt=1e12",
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise ValueError(f"Fresh KiCad export is missing expected content: {missing}")
    return text


def replace_line(text: str, reference: str, replacement: str) -> str:
    text, count = re.subn(rf"(?m)^{re.escape(reference)}\s+.*$", replacement, text, count=1)
    if count != 1:
        raise ValueError(f"Expected one {reference} source; found {count}")
    return text


def append_control(text: str, commands: list[str], path: Path) -> Path:
    block = [".control", "set wr_singlescale", "set wr_vecnames", *commands,
             "quit", ".endc", ".end"]
    text, count = re.subn(r"(?m)^\.end\s*$", "\n".join(block), text, count=1)
    if count != 1:
        raise ValueError(f"Expected one .end directive; found {count}")
    path.write_text(text, encoding="utf-8")
    return path


def run_ngspice(netlist: Path, log: Path) -> None:
    run(
        [str(NGSPICE), "-b", "-D", "ngbehavior=ltpsa", "-o", str(log), str(netlist)],
        GENERATED_DIR,
        f"ngspice {netlist.stem}",
    )
    log_text = log.read_text(encoding="utf-8", errors="replace")
    if "fatal error" in log_text.lower():
        raise ValueError(f"{netlist.name} reported a fatal error; see {log}")


def load_dat(path: Path, trace_count: int) -> np.ndarray:
    if not path.exists():
        raise ValueError(f"ngspice did not create {path}")
    data = np.loadtxt(path, skiprows=1)
    if data.ndim == 1:
        data = data.reshape(1, -1)
    if data.shape[1] != trace_count + 1:
        raise ValueError(
            f"{path.name} has {data.shape[1]} columns; expected {trace_count + 1}"
        )
    return data


def run_full_rf(base: str) -> np.ndarray:
    amplitude = (
        f"if(time<{RF_PRE_END_S:g},{WEAK_IF_V_PEAK:g},"
        f"if(time<{RF_STRONG_END_S:g},{RF_STRONG_IF_V_PEAK:g},{WEAK_IF_V_PEAK:g}))"
    )
    source = (
        "B79SIM5 /IN GND V = "
        f"({amplitude})*sin({2 * math.pi * IF_HZ:.15g}*time)"
    )
    text = replace_line(base, "V79-SIM5", source)
    text = replace_line(
        text,
        "V79-SIM6",
        "V79-SIM6 /BFO GND DC 6.5 "
        f"SIN( 6.5 {BFO_AMPLITUDE_V_PEAK:g} {BFO_HZ:g} 0 0 0 ) AC 0",
    )
    data_name = "80279-full-rf-closed-loop.dat"
    netlist = append_control(
        text,
        [
            f"tran {RF_OUTPUT_STEP_S:g} {RF_STOP_S:g} 0 {RF_MAX_STEP_S:g}",
            "linearize",
            "wrdata " + data_name + " "
            + " ".join(f"v({node})" for _, node in RF_TRACES),
        ],
        GENERATED_DIR / "80279-full-rf-closed-loop.cir",
    )
    run_ngspice(netlist, GENERATED_DIR / "80279-full-rf-closed-loop.log")
    return load_dat(GENERATED_DIR / data_name, len(RF_TRACES))


def run_precharged_rf(base: str) -> np.ndarray:
    """Static RF cross-check with C79-22 held at a measured strong level.

    This is not an attack-time simulation.  It verifies that the actual
    Q79-4/Q79-5, D79-5, PIN-diode, and tuned-IF topology produces the
    attenuation predicted by the split envelope study.
    """
    text = replace_line(
        base,
        "V79-SIM5",
        "V79-SIM5 /IN GND DC 0 "
        f"SIN( 0 {STRONG_IF_V_PEAK:g} {IF_HZ:g} 0 0 0 ) AC 0",
    )
    text = replace_line(
        text,
        "V79-SIM6",
        "V79-SIM6 /BFO GND DC 6.5 "
        f"SIN( 6.5 {BFO_AMPLITUDE_V_PEAK:g} {BFO_HZ:g} 0 0 0 ) AC 0",
    )
    text, count = re.subn(
        r"(?m)^\.end\s*$",
        f"V79PRECHARGE Net-_D79-6-K_ GND DC {PRECHARGE_STORE_V:.15g}\n.end",
        text,
        count=1,
    )
    if count != 1:
        raise ValueError(f"Expected one .end directive before precharge; found {count}")
    data_name = "80279-full-rf-precharged.dat"
    netlist = append_control(
        text,
        [
            f"tran {RF_OUTPUT_STEP_S:g} 3m 0 {RF_MAX_STEP_S:g}",
            "linearize",
            "wrdata " + data_name + " "
            + " ".join(f"v({node})" for _, node in RF_TRACES),
        ],
        GENERATED_DIR / "80279-full-rf-precharged.cir",
    )
    run_ngspice(netlist, GENERATED_DIR / "80279-full-rf-precharged.log")
    return load_dat(GENERATED_DIR / data_name, len(RF_TRACES))


def load_calibration() -> tuple[list[tuple[float, float]], float]:
    with PIN_SWEEP_CSV.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    points = [(0.45, 0.0)]
    points.extend(
        (float(row["pin_bias_bus_v"]), float(row["attenuation_at_9mhz_db"]))
        for row in rows[1:]
    )
    points.sort()

    with DETECTOR_CSV.open(newline="", encoding="utf-8") as stream:
        detector_rows = list(csv.DictReader(stream))
    nominal = next(row for row in detector_rows if row["case"] == "bfo-400mv")
    detector_gain = (
        float(nominal["filt_loop_1khz_vpp"])
        / (2.0 * float(nominal["if_amplitude_v_peak"]))
    )
    return points, detector_gain


def interpolation_expression(variable: str, points: list[tuple[float, float]]) -> str:
    """Nested linear interpolation suitable for an ngspice behavioral source."""
    expression = f"{points[-1][1]:.12g}"
    for (x1, y1), (x2, y2) in reversed(list(zip(points, points[1:]))):
        slope = (y2 - y1) / (x2 - x1)
        segment = f"({y1:.12g}+({variable}-{x1:.12g})*{slope:.12g})"
        expression = f"if({variable}<{x2:.12g},{segment},{expression})"
    expression = f"if({variable}<{points[0][0]:.12g},0,{expression})"
    return expression


def run_envelope(base: str, points: list[tuple[float, float]], detector_gain: float) -> np.ndarray:
    incoming = (
        f"if(time<{ENV_PRE_END_S:g},{WEAK_IF_V_PEAK:g},"
        f"if(time<{ENV_STRONG_END_S:g},{STRONG_IF_V_PEAK:g},{WEAK_IF_V_PEAK:g}))"
    )
    attenuation_db = interpolation_expression("v(/PIN_BIAS)", points)
    voltage_ratio = f"exp(-{math.log(10.0) / 20.0:.15g}*({attenuation_db}))"
    source = (
        "B79SIM5 /FILT_IN GND V = "
        f"({incoming})*{detector_gain:.15g}*({voltage_ratio})*"
        f"sin({2 * math.pi * AUDIO_HZ:.15g}*time)"
    )
    text = replace_line(base, "V79-SIM5", source)
    text = replace_line(
        text,
        "V79-SIM6",
        "V79-SIM6 /BFO GND DC 6.5 SIN( 6.5 0 9Meg 0 0 0 ) AC 0",
    )
    data_name = "80279-envelope-closed-loop.dat"
    netlist = append_control(
        text,
        [
            f"tran {ENV_OUTPUT_STEP_S:g} {ENV_STOP_S:g} 0 {ENV_MAX_STEP_S:g}",
            "linearize",
            "wrdata " + data_name + " "
            + " ".join(f"v({node})" for _, node in ENV_TRACES),
        ],
        GENERATED_DIR / "80279-envelope-closed-loop.cir",
    )
    run_ngspice(netlist, GENERATED_DIR / "80279-envelope-closed-loop.log")
    return load_dat(GENERATED_DIR / data_name, len(ENV_TRACES))


def tone_vpp(time: np.ndarray, values: np.ndarray, frequency: float) -> float:
    phase = 2.0 * np.pi * frequency * time
    design = np.column_stack((np.sin(phase), np.cos(phase), np.ones(time.size)))
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    return float(2.0 * math.hypot(coefficients[0], coefficients[1]))


def binned_envelopes(
    data: np.ndarray,
    traces: tuple[tuple[str, str], ...],
    bin_s: float,
    include_rf: bool,
) -> list[dict[str, float]]:
    indexes = {key: index + 1 for index, (key, _) in enumerate(traces)}
    rows: list[dict[str, float]] = []
    start = float(data[0, 0])
    stop = float(data[-1, 0])
    left = start
    while left + bin_s <= stop + 1e-12:
        right = left + bin_s
        mask = (data[:, 0] >= left) & (data[:, 0] < right)
        if mask.sum() < 5:
            left = right
            continue
        time = data[mask, 0]
        row = {"time_s": 0.5 * (left + right)}
        if include_rf:
            row["board_in_vpp"] = tone_vpp(time, data[mask, indexes["board_in"]], IF_HZ)
            row["q79_3_g1_vpp"] = tone_vpp(time, data[mask, indexes["q79_3_g1"]], IF_HZ)
        row["filt_loop_vpp"] = tone_vpp(time, data[mask, indexes["filt_loop"]], AUDIO_HZ)
        row["audio_vpp"] = tone_vpp(time, data[mask, indexes["audio"]], AUDIO_HZ)
        row["agc_store_v"] = float(data[mask, indexes["agc_store"]].mean())
        row["pin_bias_v"] = float(data[mask, indexes["pin_bias"]].mean())
        row["pin_branch_a"] = float(
            ((data[mask, indexes["pin_bias"]] - data[mask, indexes["d79_1_feed"]]) / 1000.0).mean()
        )
        row["s_meter_a"] = float(data[mask, indexes["s_meter"]].mean() / 1000.0)
        rows.append(row)
        left = right
    return rows


def average_between(rows: list[dict[str, float]], key: str, start: float, stop: float) -> float:
    values = [row[key] for row in rows if start <= row["time_s"] <= stop]
    if not values:
        raise ValueError(f"No {key} rows between {start} and {stop}")
    return float(np.mean(values))


def crossing_time(
    data: np.ndarray,
    column: int,
    start: float,
    stop: float,
    threshold: float,
    rising: bool,
) -> float:
    mask = (data[:, 0] >= start) & (data[:, 0] <= stop)
    time = data[mask, 0]
    values = data[mask, column]
    for t1, t2, y1, y2 in zip(time, time[1:], values, values[1:]):
        crossed = y1 <= threshold <= y2 if rising else y1 >= threshold >= y2
        if crossed and y2 != y1:
            return float(t1 + (threshold - y1) * (t2 - t1) / (y2 - y1))
    return float("nan")


def write_csv(path: Path, rows: list[dict[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def measure(
    rf_rows: list[dict[str, float]],
    precharged_rows: list[dict[str, float]],
    env_rows: list[dict[str, float]],
    env_data: np.ndarray,
    detector_gain: float,
) -> list[dict[str, str | float]]:
    rf_first = average_between(rf_rows, "q79_3_g1_vpp", 2e-3, 3e-3)
    rf_last = average_between(rf_rows, "q79_3_g1_vpp", 7e-3, 8e-3)
    rf_pin_first = average_between(rf_rows, "pin_branch_a", 2e-3, 3e-3)
    rf_pin_last = average_between(rf_rows, "pin_branch_a", 7e-3, 8e-3)
    pre_g1 = average_between(precharged_rows, "q79_3_g1_vpp", 2e-3, 3e-3)
    pre_pin = average_between(precharged_rows, "pin_branch_a", 2e-3, 3e-3)
    pre_audio = average_between(precharged_rows, "audio_vpp", 2e-3, 3e-3)

    weak_audio = average_between(env_rows, "audio_vpp", 0.10, 0.19)
    strong_audio = average_between(env_rows, "audio_vpp", 1.10, 1.19)
    input_step_db = 20.0 * math.log10(STRONG_IF_V_PEAK / WEAK_IF_V_PEAK)
    output_step_db = 20.0 * math.log10(strong_audio / weak_audio)
    compression_db = input_step_db - output_step_db

    indexes = {key: index + 1 for index, (key, _) in enumerate(ENV_TRACES)}
    store_column = indexes["agc_store"]
    baseline = average_between(env_rows, "agc_store_v", 0.10, 0.19)
    strong_store = average_between(env_rows, "agc_store_v", 1.10, 1.19)
    rise10 = baseline + 0.1 * (strong_store - baseline)
    rise90 = baseline + 0.9 * (strong_store - baseline)
    t10 = crossing_time(env_data, store_column, ENV_PRE_END_S, ENV_STRONG_END_S, rise10, True)
    t90 = crossing_time(env_data, store_column, ENV_PRE_END_S, ENV_STRONG_END_S, rise90, True)
    fall90 = baseline + 0.9 * (strong_store - baseline)
    fall10 = baseline + 0.1 * (strong_store - baseline)
    tr90 = crossing_time(env_data, store_column, ENV_STRONG_END_S, ENV_STOP_S, fall90, False)
    tr10 = crossing_time(env_data, store_column, ENV_STRONG_END_S, ENV_STOP_S, fall10, False)

    post_audio = [row["audio_vpp"] for row in env_rows if row["time_s"] > ENV_STRONG_END_S]
    overshoot = (max(post_audio) / weak_audio - 1.0) * 100.0 if post_audio else float("nan")
    attack_audio = [
        row["audio_vpp"]
        for row in env_rows
        if ENV_PRE_END_S <= row["time_s"] < ENV_STRONG_END_S
    ]
    attack_peak = max(attack_audio)
    weak_pin = average_between(env_rows, "pin_branch_a", 0.10, 0.19)
    strong_pin = average_between(env_rows, "pin_branch_a", 1.10, 1.19)
    weak_meter = average_between(env_rows, "s_meter_a", 0.10, 0.19)
    strong_meter = average_between(env_rows, "s_meter_a", 1.10, 1.19)
    return [
        {"metric": "detector_calibration", "value": detector_gain, "unit": "FILT peak V per board-IN peak V"},
        {"metric": "if_input_step", "value": input_step_db, "unit": "dB"},
        {"metric": "full_rf_q79_3_g1_first_strong", "value": rf_first, "unit": "V p-p"},
        {"metric": "full_rf_q79_3_g1_last_strong", "value": rf_last, "unit": "V p-p"},
        {"metric": "full_rf_g1_reduction", "value": 20.0 * math.log10(rf_first / rf_last), "unit": "dB"},
        {"metric": "full_rf_pin_first_strong", "value": rf_pin_first, "unit": "A per branch"},
        {"metric": "full_rf_pin_last_strong", "value": rf_pin_last, "unit": "A per branch"},
        {"metric": "precharged_full_rf_q79_3_g1", "value": pre_g1, "unit": "V p-p"},
        {"metric": "precharged_full_rf_audio", "value": pre_audio, "unit": "V p-p"},
        {"metric": "precharged_full_rf_pin_current", "value": pre_pin, "unit": "A per branch"},
        {"metric": "precharged_full_rf_attenuation", "value": 20.0 * math.log10(rf_last / pre_g1), "unit": "dB relative to baseline full RF"},
        {"metric": "envelope_weak_audio", "value": weak_audio, "unit": "V p-p"},
        {"metric": "envelope_strong_audio", "value": strong_audio, "unit": "V p-p"},
        {"metric": "envelope_output_step", "value": output_step_db, "unit": "dB"},
        {"metric": "envelope_compression", "value": compression_db, "unit": "dB removed from 40 dB input step"},
        {"metric": "strong_attack_audio_peak", "value": attack_peak, "unit": "V p-p"},
        {"metric": "strong_attack_audio_overshoot", "value": (attack_peak / strong_audio - 1.0) * 100.0, "unit": "percent above regulated strong level"},
        {"metric": "agc_store_weak", "value": baseline, "unit": "V"},
        {"metric": "agc_store_strong", "value": strong_store, "unit": "V"},
        {"metric": "pin_current_weak", "value": weak_pin, "unit": "A per branch"},
        {"metric": "pin_current_strong", "value": strong_pin, "unit": "A per branch"},
        {"metric": "s_meter_current_weak", "value": weak_meter, "unit": "A"},
        {"metric": "s_meter_current_strong", "value": strong_meter, "unit": "A"},
        {"metric": "attack_10_90", "value": t90 - t10, "unit": "s"},
        {"metric": "release_90_10", "value": tr10 - tr90, "unit": "s"},
        {"metric": "post_release_audio_overshoot", "value": overshoot, "unit": "percent"},
    ]


def plot_full_rf(rows: list[dict[str, float]]) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    time_ms = np.array([row["time_s"] * 1e3 for row in rows])
    fig, axes = plt.subplots(4, 1, figsize=(9.6, 10.2), sharex=True)
    axes[0].plot(time_ms, [row["board_in_vpp"] * 1e6 for row in rows], marker="o")
    axes[0].set_ylabel("IN (uV p-p)")
    axes[0].set_title("Applied weak / strong / weak 9.001 MHz IF")
    axes[1].plot(time_ms, [row["q79_3_g1_vpp"] * 1e3 for row in rows], marker="o")
    axes[1].set_ylabel("Q79-3 G1 (mV p-p)")
    axes[1].set_title("IF reaching the product detector")
    axes[2].plot(time_ms, [row["audio_vpp"] for row in rows], marker="o",
                 label="AUDIO")
    axes[2].set_ylabel("AUDIO (V p-p)")
    axes[2].set_title("Recovered AUDIO envelope")
    axes[3].plot(time_ms, [row["pin_branch_a"] * 1e6 for row in rows], marker="o",
                 label="One PIN branch")
    axes[3].set_ylabel("PIN current (uA)")
    axes[3].set_xlabel("Time (ms)")
    axes[3].set_title("PIN control remains below turn-on in this 6 ms window")
    for axis in axes:
        axis.axvline(RF_PRE_END_S * 1e3, color="black", linestyle="--", linewidth=1.0)
        axis.axvline(RF_STRONG_END_S * 1e3, color="black", linestyle="--", linewidth=1.0)
        axis.grid(True, alpha=0.28)
    fig.suptitle("80279 short full-RF AGC onset window")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "80279-full-rf-agc-attack.png", dpi=180)
    plt.close(fig)


def plot_envelope(rows: list[dict[str, float]]) -> None:
    time = np.array([row["time_s"] for row in rows])
    fig, axes = plt.subplots(4, 1, figsize=(9.6, 10.2), sharex=True)
    axes[0].plot(time, [row["filt_loop_vpp"] * 1e3 for row in rows])
    axes[0].set_ylabel("Filter audio (mV p-p)")
    axes[0].set_title("Post-attenuation recovered-audio envelope")
    axes[1].plot(time, [row["audio_vpp"] for row in rows])
    axes[1].set_ylabel("AUDIO (V p-p)")
    axes[1].set_title("Receiver AUDIO response")
    axes[2].plot(time, [row["agc_store_v"] for row in rows], label="C79-22")
    axes[2].plot(time, [row["pin_bias_v"] for row in rows], label="PIN bus")
    axes[2].set_ylabel("Control voltage (V)")
    axes[2].set_title("AGC charge and release")
    axes[2].legend(loc="best")
    axes[3].plot(time, [row["pin_branch_a"] * 1e6 for row in rows], label="PIN current")
    axes[3].plot(time, [row["s_meter_a"] * 1e6 for row in rows], label="S-meter current")
    axes[3].set_ylabel("Current (uA)")
    axes[3].set_xlabel("Time (s)")
    axes[3].set_title("Gain-control and meter response")
    axes[3].legend(loc="best")
    for axis in axes:
        axis.axvline(ENV_PRE_END_S, color="black", linestyle="--", linewidth=1.0)
        axis.axvline(ENV_STRONG_END_S, color="black", linestyle="--", linewidth=1.0)
        axis.grid(True, alpha=0.28)
    fig.suptitle("80279 calibrated closed-loop AGC envelope: weak / strong / weak")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "80279-agc-attack-release.png", dpi=180)
    plt.close(fig)


def plot_precharge_crosscheck(
    baseline_rows: list[dict[str, float]], precharged_rows: list[dict[str, float]]
) -> None:
    baseline_g1 = average_between(baseline_rows, "q79_3_g1_vpp", 7e-3, 8e-3)
    precharged_g1 = average_between(precharged_rows, "q79_3_g1_vpp", 2e-3, 3e-3)
    baseline_pin = average_between(baseline_rows, "pin_branch_a", 7e-3, 8e-3)
    precharged_pin = average_between(precharged_rows, "pin_branch_a", 2e-3, 3e-3)
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 4.8))
    labels = ("Baseline store", f"C79-22 held at\n{PRECHARGE_STORE_V:.3f} V")
    axes[0].bar(labels, [baseline_g1 * 1e3, precharged_g1 * 1e3],
                color=("#1f77b4", "#d62728"))
    axes[0].set_ylabel("Q79-3 gate-1 IF (mV p-p)")
    axes[0].set_title("Actual 9 MHz path")
    axes[0].grid(True, axis="y", alpha=0.28)
    axes[1].bar(labels, [baseline_pin * 1e6, precharged_pin * 1e6],
                color=("#1f77b4", "#d62728"))
    axes[1].set_ylabel("One PIN branch (uA)")
    axes[1].set_title("Actual Q79-4/Q79-5 and PIN path")
    axes[1].grid(True, axis="y", alpha=0.28)
    fig.suptitle("80279 full-RF control-state cross-check at 100 uV peak IN")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "80279-full-rf-control-crosscheck.png", dpi=180)
    plt.close(fig)


def write_manifest() -> None:
    rows = (
        ("data/80279-full-rf-agc-envelope.csv", "One-millisecond envelopes from the complete 9 MHz circuit"),
        ("data/80279-full-rf-precharged-envelope.csv", "Full-RF response with C79-22 held at the Sim 5 strong-control level"),
        ("data/80279-agc-envelope-timeline.csv", "Ten-millisecond calibrated long-loop timeline"),
        ("data/80279-agc-summary.csv", "Attack, release, compression, and RF direction metrics"),
        ("figures/80279-full-rf-agc-attack.png", "Full-RF feedback direction and onset"),
        ("figures/80279-full-rf-control-crosscheck.png", "Actual IF and PIN paths at baseline and precharged control states"),
        ("figures/80279-agc-attack-release.png", "Calibrated multi-second AGC envelope"),
    )
    STUDY_DIR.mkdir(parents=True, exist_ok=True)
    with (STUDY_DIR / "manifest.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("path", "purpose"))
        writer.writerows(rows)


def main() -> int:
    base = export_netlist()
    points, detector_gain = load_calibration()
    envelope_raw = GENERATED_DIR / "80279-envelope-closed-loop.dat"
    if "--rf-only" in sys.argv or "--precharge-only" in sys.argv or "--figures-only" in sys.argv:
        print("reusing calibrated long-envelope raw data", flush=True)
        env_data = load_dat(envelope_raw, len(ENV_TRACES))
    else:
        print("running calibrated long envelope", flush=True)
        env_data = run_envelope(base, points, detector_gain)
    env_rows = binned_envelopes(env_data, ENV_TRACES, 10e-3, False)
    full_rf_raw = GENERATED_DIR / "80279-full-rf-closed-loop.dat"
    if "--envelope-only" in sys.argv or "--precharge-only" in sys.argv or "--figures-only" in sys.argv:
        print("reusing full-RF raw data", flush=True)
        rf_data = load_dat(full_rf_raw, len(RF_TRACES))
    else:
        print("running full-RF direction check", flush=True)
        rf_data = run_full_rf(base)
    rf_rows = binned_envelopes(rf_data, RF_TRACES, 1e-3, True)
    precharged_raw = GENERATED_DIR / "80279-full-rf-precharged.dat"
    if "--figures-only" in sys.argv:
        print("reusing precharged full-RF raw data", flush=True)
        precharged_data = load_dat(precharged_raw, len(RF_TRACES))
    else:
        print("running full-RF precharged-control cross-check", flush=True)
        precharged_data = run_precharged_rf(base)
    precharged_rows = binned_envelopes(precharged_data, RF_TRACES, 1e-3, True)

    summary = measure(rf_rows, precharged_rows, env_rows, env_data, detector_gain)
    write_csv(DATA_DIR / "80279-full-rf-agc-envelope.csv", rf_rows)
    write_csv(DATA_DIR / "80279-full-rf-precharged-envelope.csv", precharged_rows)
    write_csv(DATA_DIR / "80279-agc-envelope-timeline.csv", env_rows)
    with (DATA_DIR / "80279-agc-summary.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=("metric", "value", "unit"))
        writer.writeheader()
        writer.writerows(summary)
    plot_full_rf(rf_rows)
    plot_envelope(env_rows)
    plot_precharge_crosscheck(rf_rows, precharged_rows)
    write_manifest()

    print()
    for item in summary:
        print(f"{item['metric']}={item['value']} {item['unit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
