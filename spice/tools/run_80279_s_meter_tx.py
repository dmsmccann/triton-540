#!/usr/bin/env python3
"""Run 80279 Simulation 7: S-meter adjustment and transmit inhibit.

The saved KiCad schematic is exported afresh.  Existing sources inside the
red SIMULATION ONLY box are changed only in disposable netlist copies.

The long tests use the calibrated 1 kHz detector envelope established by
Simulations 3, 4, and 6.  The actual IC1, detector/storage, Q79-4/Q79-5,
Q79-6, PIN-bias, R79-20, D79-4, and S-meter-load circuits remain present.
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
STUDY_DIR = ROOT / "spice" / "studies" / "80279" / "s-meter-tx"
DATA_DIR = STUDY_DIR / "data"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = ROOT / "spice" / "generated" / "80279-s-meter-tx"
BASE_NETLIST = GENERATED_DIR / "80279-s-meter-tx-base.cir"

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

AUDIO_HZ = 1_000.0
METER_LOAD_OHM = 1_000.0
POT_POSITIONS = (0.05, 0.25, 0.50, 0.75, 0.95)
INPUT_LEVELS_UV_PEAK = (0.5, 1, 2, 5, 10, 20, 50, 100, 200)
LEVEL_DWELL_S = 0.35
LEVEL_SETTLE_S = 0.05
TX_STEP_S = 0.30
TX_STOP_S = 0.60
TX_INPUT_UV_PEAK = 100.0

TRACES = (
    ("filt_loop", "/filt_in"),
    ("audio", "/audio"),
    ("agc_store", "net-_d79-6-k_"),
    ("q79_6_base", "net-_q79-6-b_"),
    ("pin_bias", "/pin_bias"),
    ("d79_1_feed", "net-_d79-1-a_"),
    ("d79_5_anode", "net-_d79-5-a_"),
    ("d79_4_anode", "net-_d79-4-a_"),
    ("s_meter", "/s_mtr"),
    ("r_line", "/r"),
    ("t_line", "/t"),
)


def run(command: list[str], cwd: Path, description: str) -> None:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if completed.returncode:
        print(completed.stdout, end="")
        print(completed.stderr, end="")
        raise SystemExit(f"{description} failed with exit code {completed.returncode}")


def export_netlist() -> str:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    for executable in (KICAD_CLI, NGSPICE):
        if not executable.exists():
            raise SystemExit(f"Required executable was not found: {executable}")
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
        ".model __R79-20 potentiometer( r=10k position=.5 )",
        "AR79-20 Net-_D79-4-A_ Net-_D79-4-A_ Net-_D79-5-A_ __R79-20",
        "D79-4 Net-_D79-4-A_ /S_MTR 1N4154",
        "Q79-6 Net-_D79-6-K_ Net-_Q79-6-B_ GND MPS6514",
        "R79-22 /T Net-_Q79-6-B_ 22k",
        "V79-SIM3 /R GND DC 12.1",
        "V79-SIM4 /T GND DC 0.2",
        "R79-SIM2 /S_MTR GND 1k",
        "C79-22 Net-_D79-6-K_ GND 4.7u",
    )
    missing = [line for line in required if line not in text]
    if missing:
        raise ValueError(f"Fresh KiCad export is missing expected content: {missing}")
    return text


def replace_line(text: str, reference: str, replacement: str) -> str:
    text, count = re.subn(rf"(?m)^{re.escape(reference)}\s+.*$", replacement, text, count=1)
    if count != 1:
        raise ValueError(f"Expected one {reference} line; found {count}")
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
    log_text = log.read_text(encoding="utf-8", errors="replace").lower()
    if "fatal error" in log_text or "ngspice-46 done" not in log_text:
        raise ValueError(f"{netlist.name} did not complete normally; see {log}")


def load_dat(path: Path, trace_count: int = len(TRACES)) -> np.ndarray:
    data = np.loadtxt(path, skiprows=1)
    if data.ndim == 1:
        data = data.reshape(1, -1)
    if data.shape[1] != trace_count + 1:
        raise ValueError(f"{path.name} has {data.shape[1]} columns; expected {trace_count+1}")
    return data


def load_calibration() -> tuple[list[tuple[float, float]], float]:
    with PIN_SWEEP_CSV.open(newline="", encoding="utf-8") as stream:
        pin_rows = list(csv.DictReader(stream))
    points = [(0.45, 0.0)]
    points.extend(
        (float(row["pin_bias_bus_v"]), float(row["attenuation_at_9mhz_db"]))
        for row in pin_rows[1:]
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
    expression = f"{points[-1][1]:.12g}"
    for (x1, y1), (x2, y2) in reversed(list(zip(points, points[1:]))):
        slope = (y2 - y1) / (x2 - x1)
        segment = f"({y1:.12g}+({variable}-{x1:.12g})*{slope:.12g})"
        expression = f"if({variable}<{x2:.12g},{segment},{expression})"
    return f"if({variable}<{points[0][0]:.12g},0,{expression})"


def envelope_source(amplitude_expression: str, points: list[tuple[float, float]], detector_gain: float) -> str:
    attenuation_db = interpolation_expression("v(/PIN_BIAS)", points)
    ratio = f"exp(-{math.log(10.0)/20.0:.15g}*({attenuation_db}))"
    return (
        "B79SIM5 /FILT_IN GND V = "
        f"({amplitude_expression})*1e-6*{detector_gain:.15g}*({ratio})*"
        f"sin({2*math.pi*AUDIO_HZ:.15g}*time)"
    )


def common_envelope_netlist(base: str, source: str, pot_position: float) -> str:
    text = replace_line(base, "V79-SIM5", source)
    text = replace_line(
        text, "V79-SIM6",
        "V79-SIM6 /BFO GND DC 6.5 SIN( 6.5 0 9Meg 0 0 0 ) AC 0",
    )
    text, count = re.subn(
        r"(?m)^\.model __R79-20 potentiometer\([^\r\n]*$",
        f".model __R79-20 potentiometer( r=10k position={pot_position:g} )",
        text,
        count=1,
    )
    if count != 1:
        raise ValueError("Could not set R79-20 position")
    return text


def staircase_expression() -> str:
    expression = f"{INPUT_LEVELS_UV_PEAK[-1]:g}"
    for index in reversed(range(len(INPUT_LEVELS_UV_PEAK) - 1)):
        boundary = (index + 1) * LEVEL_DWELL_S
        expression = f"if(time<{boundary:g},{INPUT_LEVELS_UV_PEAK[index]:g},{expression})"
    return expression


def run_meter_sweep(base: str, points: list[tuple[float, float]], detector_gain: float) -> list[dict[str, float]]:
    results: list[dict[str, float]] = []
    source = envelope_source(staircase_expression(), points, detector_gain)
    stop = len(INPUT_LEVELS_UV_PEAK) * LEVEL_DWELL_S
    for position in POT_POSITIONS:
        print(f"running R79-20 position {position:.2f}")
        text = common_envelope_netlist(base, source, position)
        stem = f"80279-s-meter-pos-{position:.2f}".replace(".", "p")
        dat_name = stem + ".dat"
        netlist = append_control(
            text,
            [
                f"tran 50u {stop:g} 0 10u",
                "linearize",
                "wrdata " + dat_name + " " + " ".join(f"v({node})" for _, node in TRACES),
            ],
            GENERATED_DIR / (stem + ".cir"),
        )
        run_ngspice(netlist, GENERATED_DIR / (stem + ".log"))
        data = load_dat(GENERATED_DIR / dat_name)
        idx = {name: number + 1 for number, (name, _) in enumerate(TRACES)}
        for level_index, level_uv in enumerate(INPUT_LEVELS_UV_PEAK):
            right = (level_index + 1) * LEVEL_DWELL_S
            left = right - LEVEL_SETTLE_S
            mask = (data[:, 0] >= left) & (data[:, 0] < right)
            if mask.sum() < 10:
                raise ValueError(f"Insufficient settled rows at {position}, {level_uv} uV")
            meter_v = float(np.mean(data[mask, idx["s_meter"]]))
            pin_current = float(np.mean(
                (data[mask, idx["pin_bias"]] - data[mask, idx["d79_1_feed"]]) / 1000.0
            ))
            results.append({
                "r79_20_position": position,
                "board_input_uv_peak": level_uv,
                "meter_voltage_v": meter_v,
                "meter_current_a": meter_v / METER_LOAD_OHM,
                "agc_store_v": float(np.mean(data[mask, idx["agc_store"]])),
                "pin_bias_v": float(np.mean(data[mask, idx["pin_bias"]])),
                "pin_current_a_per_branch": pin_current,
            })
    return results


def run_transmit(base: str, points: list[tuple[float, float]], detector_gain: float) -> np.ndarray:
    source = envelope_source(f"{TX_INPUT_UV_PEAK:g}", points, detector_gain)
    text = common_envelope_netlist(base, source, 0.5)
    text = replace_line(text, "V79-SIM3", f"B79SIM3 /R GND V = if(time<{TX_STEP_S:g},12.1,0)")
    text = replace_line(text, "V79-SIM4", f"B79SIM4 /T GND V = if(time<{TX_STEP_S:g},0.2,10.4)")
    dat_name = "80279-receive-to-transmit.dat"
    netlist = append_control(
        text,
        [
            f"tran 2u {TX_STOP_S:g} 0 2u",
            "linearize",
            "wrdata " + dat_name + " " + " ".join(f"v({node})" for _, node in TRACES),
        ],
        GENERATED_DIR / "80279-receive-to-transmit.cir",
    )
    run_ngspice(netlist, GENERATED_DIR / "80279-receive-to-transmit.log")
    return load_dat(GENERATED_DIR / dat_name)


def run_d79_4_isolation(base: str) -> dict[str, float]:
    """Apply a transmit-side meter voltage and verify D79-4 reverse isolation."""
    text = common_envelope_netlist(
        base,
        "V79-SIM5 /S_MTR GND DC 1",
        0.5,
    )
    text = replace_line(text, "V79-SIM3", "V79-SIM3 /R GND DC 0")
    text = replace_line(text, "V79-SIM4", "V79-SIM4 /T GND DC 10.4")
    dat_name = "80279-d79-4-transmit-isolation.dat"
    netlist = append_control(
        text,
        [
            "op",
            "wrdata " + dat_name + " v(/S_MTR) v(Net-_D79-4-A_) "
            "v(Net-_D79-6-K_) v(/PIN_BIAS)",
        ],
        GENERATED_DIR / "80279-d79-4-transmit-isolation.cir",
    )
    run_ngspice(netlist, GENERATED_DIR / "80279-d79-4-transmit-isolation.log")
    data = load_dat(GENERATED_DIR / dat_name, 4)
    row = data[-1]
    return {
        "isolation_test_s_meter_v": float(row[1]),
        "isolation_test_d79_4_anode_v": float(row[2]),
        "isolation_test_d79_4_voltage_v": float(row[2] - row[1]),
        "isolation_test_agc_store_v": float(row[3]),
        "isolation_test_pin_bias_v": float(row[4]),
    }


def write_csv(path: Path, rows: list[dict[str, float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def crossing_time(time: np.ndarray, values: np.ndarray, start: float, threshold: float) -> float:
    mask = time >= start
    indices = np.flatnonzero(mask & (values <= threshold))
    return float(time[indices[0]]) if indices.size else math.nan


def process_transmit(data: np.ndarray) -> tuple[list[dict[str, float]], dict[str, float]]:
    idx = {name: number + 1 for number, (name, _) in enumerate(TRACES)}
    time = data[:, 0]
    pre = (time >= 0.25) & (time < 0.29)
    post = (time >= 0.50) & (time < 0.59)
    timeline: list[dict[str, float]] = []
    stride = max(1, int(round(50e-6 / np.median(np.diff(time)))))
    for row in data[::stride]:
        timeline.append({
            "time_s": float(row[0]),
            "r_line_v": float(row[idx["r_line"]]),
            "t_line_v": float(row[idx["t_line"]]),
            "q79_6_base_v": float(row[idx["q79_6_base"]]),
            "agc_store_v": float(row[idx["agc_store"]]),
            "pin_bias_v": float(row[idx["pin_bias"]]),
            "pin_current_a_per_branch": float(
                (row[idx["pin_bias"]] - row[idx["d79_1_feed"]]) / 1000.0
            ),
            "meter_current_a": float(row[idx["s_meter"]] / METER_LOAD_OHM),
            "d79_4_anode_v": float(row[idx["d79_4_anode"]]),
            "d79_4_cathode_v": float(row[idx["s_meter"]]),
        })
    pre_store = float(np.mean(data[pre, idx["agc_store"]]))
    post_store = float(np.mean(data[post, idx["agc_store"]]))
    pre_meter = float(np.mean(data[pre, idx["s_meter"]]) / METER_LOAD_OHM)
    post_meter = float(np.mean(data[post, idx["s_meter"]]) / METER_LOAD_OHM)
    threshold = post_store + 0.1 * (pre_store - post_store)
    reset_at = crossing_time(time, data[:, idx["agc_store"]], TX_STEP_S, threshold)
    summary = {
        "rx_agc_store_v": pre_store,
        "tx_agc_store_v": post_store,
        "rx_q79_6_base_v": float(np.mean(data[pre, idx["q79_6_base"]])),
        "tx_q79_6_base_v": float(np.mean(data[post, idx["q79_6_base"]])),
        "rx_pin_bias_v": float(np.mean(data[pre, idx["pin_bias"]])),
        "tx_pin_bias_v": float(np.mean(data[post, idx["pin_bias"]])),
        "rx_pin_current_a_per_branch": float(np.mean(
            (data[pre, idx["pin_bias"]] - data[pre, idx["d79_1_feed"]]) / 1000.0
        )),
        "tx_pin_current_a_per_branch": float(np.mean(
            (data[post, idx["pin_bias"]] - data[post, idx["d79_1_feed"]]) / 1000.0
        )),
        "rx_meter_current_a": pre_meter,
        "tx_meter_current_a": post_meter,
        "meter_reduction_db": 20 * math.log10(max(abs(pre_meter), 1e-30) / max(abs(post_meter), 1e-30)),
        "agc_reset_90_percent_s": reset_at - TX_STEP_S,
        "tx_d79_4_voltage_v": float(np.mean(
            data[post, idx["d79_4_anode"]] - data[post, idx["s_meter"]]
        )),
    }
    return timeline, summary


def make_plots(meter_rows: list[dict[str, float]], tx_rows: list[dict[str, float]]) -> None:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for position in POT_POSITIONS:
        rows = [row for row in meter_rows if row["r79_20_position"] == position]
        ax.semilogx(
            [row["board_input_uv_peak"] for row in rows],
            [row["meter_current_a"] * 1e6 for row in rows],
            marker="o", label=f"R79-20 = {position:.2f}",
        )
    ax.set_xlabel("Modeled 80279 IN level (uV peak; not antenna S units)")
    ax.set_ylabel("Current in 1 kOhm S-meter fixture (uA)")
    ax.set_title("80279 S-meter response and R79-20 adjustment range")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(ncol=2)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "80279-s-meter-sweep.png", dpi=180)
    plt.close(fig)

    time = np.array([row["time_s"] for row in tx_rows])
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    axes[0].plot(time, [row["r_line_v"] for row in tx_rows], label="R receive supply")
    axes[0].plot(time, [row["t_line_v"] for row in tx_rows], label="T transmit control")
    axes[0].plot(time, [row["q79_6_base_v"] for row in tx_rows], label="Q79-6 base")
    axes[0].set_ylabel("Voltage (V)")
    axes[0].legend(loc="best")
    axes[1].plot(time, [row["agc_store_v"] for row in tx_rows], label="C79-22 stored AGC")
    axes[1].plot(time, [row["pin_bias_v"] for row in tx_rows], label="PIN-bias bus")
    axes[1].set_ylabel("Voltage (V)")
    axes[1].legend(loc="best")
    axes[2].plot(time, [row["meter_current_a"] * 1e6 for row in tx_rows], label="S-meter current")
    axes[2].axvline(TX_STEP_S, color="black", linestyle="--", label="Transmit begins")
    axes[2].set_ylabel("Current (uA)")
    axes[2].set_xlabel("Time (s)")
    axes[2].legend(loc="best")
    for ax in axes:
        ax.grid(True, alpha=0.3)
    fig.suptitle("80279 receive-to-transmit AGC reset and meter inhibit")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "80279-receive-to-transmit.png", dpi=180)
    plt.close(fig)


def write_summary(
    meter_rows: list[dict[str, float]],
    tx_summary: dict[str, float],
    isolation_summary: dict[str, float],
) -> None:
    saved = [row for row in meter_rows if row["r79_20_position"] == 0.5]
    selected = {row["board_input_uv_peak"]: row for row in saved}
    at_100 = [row for row in meter_rows if row["board_input_uv_peak"] == 100]
    rows = [
        {"metric": "saved_position_meter_at_1uv", "value": selected[1]["meter_current_a"] * 1e6, "unit": "uA"},
        {"metric": "saved_position_meter_at_10uv", "value": selected[10]["meter_current_a"] * 1e6, "unit": "uA"},
        {"metric": "saved_position_meter_at_100uv", "value": selected[100]["meter_current_a"] * 1e6, "unit": "uA"},
        {"metric": "meter_adjustment_min_at_100uv", "value": min(row["meter_current_a"] for row in at_100) * 1e6, "unit": "uA"},
        {"metric": "meter_adjustment_max_at_100uv", "value": max(row["meter_current_a"] for row in at_100) * 1e6, "unit": "uA"},
    ]
    combined = {**tx_summary, **isolation_summary}
    rows.extend({
        "metric": key,
        "value": value,
        "unit": (
            "s" if key.endswith("_s") else
            "A" if "_current_a" in key else
            "dB" if key.endswith("_db") else
            "V"
        ),
    } for key, value in combined.items())
    with (DATA_DIR / "80279-sim7-summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("metric", "value", "unit"))
        writer.writeheader()
        writer.writerows(rows)


def write_manifest() -> None:
    rows = [
        ("README.md", "Hobbyist-level method, results, assessment, and limitations"),
        ("data/80279-s-meter-sweep.csv", "R79-20 and modeled board-input sweep"),
        ("data/80279-receive-to-transmit.csv", "Downsampled receive/transmit timeline"),
        ("data/80279-sim7-summary.csv", "Principal numerical results"),
        ("figures/80279-s-meter-sweep.png", "Meter response and adjustment plot"),
        ("figures/80279-receive-to-transmit.png", "AGC reset and meter-inhibit plot"),
    ]
    with (STUDY_DIR / "manifest.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("path", "description"))
        writer.writerows(rows)


def main() -> None:
    base = export_netlist()
    points, detector_gain = load_calibration()
    meter_path = DATA_DIR / "80279-s-meter-sweep.csv"
    tx_path = DATA_DIR / "80279-receive-to-transmit.csv"

    if "--figures-only" in sys.argv or "--transmit-only" in sys.argv:
        if not meter_path.exists():
            raise SystemExit("Meter sweep CSV is required for this mode")
        with meter_path.open(newline="", encoding="utf-8") as stream:
            meter_rows = [{key: float(value) for key, value in row.items()} for row in csv.DictReader(stream)]
    else:
        meter_rows = run_meter_sweep(base, points, detector_gain)
        write_csv(meter_path, meter_rows)

    if "--figures-only" in sys.argv or "--meter-only" in sys.argv:
        if not tx_path.exists():
            if "--meter-only" in sys.argv:
                print("meter sweep complete")
                return
            raise SystemExit("Transmit CSV is required for --figures-only")
        with tx_path.open(newline="", encoding="utf-8") as stream:
            tx_rows = [{key: float(value) for key, value in row.items()} for row in csv.DictReader(stream)]
        # Reconstruct summary from the retained raw transmit result.
        raw = load_dat(GENERATED_DIR / "80279-receive-to-transmit.dat")
        _, tx_summary = process_transmit(raw)
    else:
        tx_raw = run_transmit(base, points, detector_gain)
        tx_rows, tx_summary = process_transmit(tx_raw)
        write_csv(tx_path, tx_rows)

    if "--figures-only" in sys.argv:
        isolation_raw = GENERATED_DIR / "80279-d79-4-transmit-isolation.dat"
        if not isolation_raw.exists():
            raise SystemExit("D79-4 isolation raw result is required for --figures-only")
        data = load_dat(isolation_raw, 4)[-1]
        isolation_summary = {
            "isolation_test_s_meter_v": float(data[1]),
            "isolation_test_d79_4_anode_v": float(data[2]),
            "isolation_test_d79_4_voltage_v": float(data[2] - data[1]),
            "isolation_test_agc_store_v": float(data[3]),
            "isolation_test_pin_bias_v": float(data[4]),
        }
    else:
        isolation_summary = run_d79_4_isolation(base)

    write_summary(meter_rows, tx_summary, isolation_summary)
    make_plots(meter_rows, tx_rows)
    write_manifest()
    for key, value in tx_summary.items():
        print(f"{key}={value}")
    for key, value in isolation_summary.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
