#!/usr/bin/env python3
"""Reproduce the staged operation study for crystal calibrator 80308.

The KiCad sheet is exported on every run and checked for the documented
component values and model assignments.  Purpose-built staged fixtures are
then used because the board combines a sub-hertz gate with a 100 kHz carrier;
one brute-force transient would obscure both behaviors and waste millions of
time steps.
"""

from __future__ import annotations

import csv
import math
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

import ngspice_raw


ROOT = Path(__file__).resolve().parents[2]
KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")
SCHEMATIC = ROOT / "80308_crystal_calibrator.kicad_sch"
GENERATED = ROOT / "spice" / "generated" / "80308-operation"
STUDY = ROOT / "spice" / "studies" / "80308" / "operation"
DATA = STUDY / "data"
FIGURES = STUDY / "figures"
BASE = GENERATED / "80308-export.cir"


def spice_path(path: Path) -> str:
    return path.resolve().as_posix()


def run_checked(command: list[str], description: str) -> None:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        print(result.stdout, end="")
        print(result.stderr, end="")
        raise SystemExit(f"{description} failed with exit code {result.returncode}")


def export_and_check() -> None:
    GENERATED.mkdir(parents=True, exist_ok=True)
    run_checked(
        [
            str(KICAD_CLI), "sch", "export", "netlist", "--format", "spice",
            "-o", str(BASE), str(SCHEMATIC),
        ],
        "KiCad 80308 netlist export",
    )
    text = BASE.read_text(encoding="utf-8")
    required = (
        "C08-6 Net-_IC08-1A-1Y_ Net-_IC08-1B-2A_ 200u",
        "C08-7 Net-_IC08-1A-1A_ Net-_IC08-1B-2Y_ 33u",
        "C08-1 Net-_C08-1-Pad1_ Net-_Q08-1-C_ 30p",
        "SN7400_80308",
        "SN7476_80308",
        "XTAL_100kHz_80308",
        "1N752A_80308",
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise ValueError(f"Fresh 80308 export is missing: {missing}")


def run_raw(name: str, circuit: str) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    netlist = GENERATED / f"{name}.cir"
    raw = GENERATED / f"{name}.raw"
    log = GENERATED / f"{name}.log"
    netlist.write_text(circuit, encoding="utf-8")
    run_checked(
        [str(NGSPICE), "-b", "-r", str(raw), "-o", str(log), str(netlist)],
        f"ngspice {name}",
    )
    log_text = log.read_text(encoding="utf-8", errors="replace")
    if "fatal error" in log_text.lower() or "error:" in log_text.lower():
        raise ValueError(f"{name} reported an error; see {log}")
    names, values = ngspice_raw.parse_ascii_raw(raw)
    index = {vector.lower(): i for i, vector in enumerate(names)}
    scale_name = names[0].lower()
    scale = np.asarray([row[index[scale_name]].real for row in values])
    traces = {
        vector: np.asarray([row[i].real for row in values])
        for vector, i in index.items()
        if vector != scale_name
    }
    return scale, traces


def include(name: str) -> str:
    return f'.include "{spice_path(ROOT / "spice" / "models" / name)}"'


def crossing_frequency(time: np.ndarray, signal: np.ndarray, start: float) -> float:
    selected = time >= start
    t = time[selected]
    y = signal[selected]
    threshold = 0.5 * (float(np.min(y)) + float(np.max(y)))
    crossings = []
    for i in np.flatnonzero((y[:-1] < threshold) & (y[1:] >= threshold)):
        fraction = (threshold - y[i]) / (y[i + 1] - y[i])
        crossings.append(t[i] + fraction * (t[i + 1] - t[i]))
    if len(crossings) < 3:
        return float("nan")
    return float(1 / np.mean(np.diff(crossings)))


def fit_vpp(time: np.ndarray, signal: np.ndarray, frequency: float, start: float) -> float:
    selected = time >= start
    t = time[selected]
    y = signal[selected]
    phase = 2 * np.pi * frequency * t
    design = np.column_stack((np.sin(phase), np.cos(phase), np.ones(t.size)))
    coefficient, *_ = np.linalg.lstsq(design, y, rcond=None)
    return float(2 * np.hypot(coefficient[0], coefficient[1]))


def write_csv(path: Path, header: tuple[str, ...], rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def oscillator_study() -> dict[str, float]:
    runs = []
    waveforms = {}
    for capacitance_pf in (5, 15, 30, 45, 60):
        circuit = f"""* 80308 Q1 crystal oscillator, C1={capacitance_pf} pF
{include('MPS6514.lib')}
{include('XTAL_100kHz_80308.sub')}
VMAIN vmain 0 13.8
R2 vmain collector 2.2k
C3 collector vmain 3n
Q1 collector base 0 MPS6514
R1 collector base 220k
C2 base 0 1n
XY base trim XTAL_100kHz_80308
C1 trim collector {capacitance_pf}p
C4 collector handoff 200p
R3 handoff 0 3.63k
.ic v(base)=20m v(collector)=5
.options filetype=ascii method=gear reltol=2e-4
.tran 100n 30m 0 100n uic
.save v(base) v(collector) v(handoff)
.end
"""
        time, traces = run_raw(f"oscillator-{capacitance_pf}p", circuit)
        collector = traces["v(collector)"]
        handoff = traces["v(handoff)"]
        runs.append(
            {
                "capacitance_pf": capacitance_pf,
                "frequency_hz": crossing_frequency(time, collector, 20e-3),
                "base_dc_v": float(np.mean(traces["v(base)"][time >= 20e-3])),
                "collector_dc_v": float(np.mean(collector[time >= 20e-3])),
                "collector_vpp": float(np.ptp(collector[time >= 20e-3])),
                "handoff_vpp": float(np.ptp(handoff[time >= 20e-3])),
            }
        )
        waveforms[capacitance_pf] = (time, traces)

    selected_run = min(runs, key=lambda row: abs(row["frequency_hz"] - 100e3))
    selected_capacitance = int(selected_run["capacitance_pf"])
    time, traces = waveforms[selected_capacitance]
    collector = traces["v(collector)"]
    handoff = traces["v(handoff)"]
    result = {
        "selected_capacitance_pf": selected_capacitance,
        "frequency_hz": selected_run["frequency_hz"],
        "base_dc_v": selected_run["base_dc_v"],
        "collector_dc_v": selected_run["collector_dc_v"],
        "collector_vpp": selected_run["collector_vpp"],
        "handoff_vpp": selected_run["handoff_vpp"],
    }
    write_csv(
        DATA / "oscillator-tuning.csv",
        ("c1_pf", "frequency_hz", "base_dc_v", "collector_dc_v", "collector_vpp", "handoff_vpp"),
        ((r["capacitance_pf"], r["frequency_hz"], r["base_dc_v"], r["collector_dc_v"], r["collector_vpp"], r["handoff_vpp"]) for r in runs),
    )
    selected = time >= 29.8e-3
    write_csv(
        DATA / "oscillator-waveform.csv",
        ("time_s", "base_v", "collector_v", "handoff_v"),
        zip(time[selected], traces["v(base)"][selected], collector[selected], handoff[selected]),
    )
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
    t_us = (time[selected] - time[selected][0]) * 1e6
    axes[0].plot(t_us, collector[selected], color="#2d6a9f")
    axes[0].set_ylabel("Q1 collector (V)")
    axes[1].plot(t_us, handoff[selected], color="#a04a22")
    axes[1].set_ylabel("After C4/R3 (V)")
    axes[1].set_xlabel("Time in final 200 µs (µs)")
    for axis in axes:
        axis.grid(True, alpha=0.25)
    fig.suptitle(f"80308 crystal oscillator with C1 = {selected_capacitance} pF")
    fig.tight_layout()
    fig.savefig(FIGURES / "oscillator-100khz.png", dpi=180)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(8.5, 5.2))
    axis.plot([r["capacitance_pf"] for r in runs], [r["frequency_hz"] / 1e3 for r in runs], marker="o")
    axis.axhline(100, color="black", linestyle="--", linewidth=0.8, label="documented 100 kHz")
    axis.set_xlabel("C1 setting (pF)")
    axis.set_ylabel("Simulated oscillator frequency (kHz)")
    axis.set_title("C1 trims the 80308 crystal oscillator through 100 kHz")
    axis.grid(True, alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(FIGURES / "c1-frequency-adjustment.png", dpi=180)
    plt.close(fig)
    return result


def slow_gate_study() -> tuple[list[dict[str, float]], tuple[np.ndarray, dict[str, np.ndarray]]]:
    positions = (0.02, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.75, 0.80, 0.90, 0.98)
    results = []
    middle = None
    for position in positions:
        r_top = max(1.0, 10_000 * position)
        r_bottom = max(1.0, 10_000 * (1 - position))
        circuit = f"""* 80308 IC1 slow multivibrator, R6 position {position:.2f}
{include('SN7400_80308.sub')}
VCC vcc 0 5.6
XIC1 a a y1 b b y2 0 y3 vcc vcc y4 vcc vcc vcc SN7400_80308
R6A y1 a {r_top:.9g}
R6B a 0 {r_bottom:.9g}
C7 a y2 33u
C6 y1 b 200u
R7 b 0 3.3k
.ic v(a)=0.2 v(b)=1.8
.options filetype=ascii method=gear reltol=1e-4
.tran 500u 6 0 500u uic
.save v(a) v(b) v(y1) v(y2)
.end
"""
        time, traces = run_raw(f"slow-gate-{position:.2f}", circuit)
        frequency = crossing_frequency(time, traces["v(y2)"], 2.0)
        selected = time >= 2.0
        high_fraction = float(np.mean(traces["v(y2)"][selected] > 1.4))
        transitions = int(np.count_nonzero(np.diff(traces["v(y2)"][selected] > 1.4)))
        results.append(
            {
                "position": position,
                "frequency_hz": frequency,
                "period_s": 1 / frequency if math.isfinite(frequency) else float("nan"),
                "high_fraction": high_fraction,
                "transitions": transitions,
            }
        )
        if position == 0.75:
            middle = (time, traces)
    assert middle is not None
    time, traces = middle
    selected = time >= 1.5
    stride = max(1, int(np.count_nonzero(selected) / 6000))
    indices = np.flatnonzero(selected)[::stride]
    write_csv(
        DATA / "slow-gate-waveform.csv",
        ("time_s", "gate1_input_v", "gate2_input_v", "gate1_output_v", "gate2_output_v"),
        zip(time[indices], traces["v(a)"][indices], traces["v(b)"][indices], traces["v(y1)"][indices], traces["v(y2)"][indices]),
    )
    write_csv(
        DATA / "slow-gate-summary.csv",
        ("r6_fraction_from_gate1_output", "frequency_hz", "period_s", "gate_high_fraction", "transitions_after_3s"),
        ((r["position"], r["frequency_hz"], r["period_s"], r["high_fraction"], r["transitions"]) for r in results),
    )
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
    axes[0].plot(time[selected], traces["v(a)"][selected], label="IC1 pin 1/2 input")
    axes[0].plot(time[selected], traces["v(b)"][selected], label="IC1 pin 4/5 input")
    axes[0].axhline(1.4, color="black", linestyle="--", linewidth=0.8, label="modeled TTL threshold")
    axes[0].set_ylabel("Timing-node voltage (V)")
    axes[0].legend(loc="upper right")
    axes[1].step(time[selected], traces["v(y2)"][selected], where="post", color="#a04a22")
    axes[1].set_ylabel("Gate-enable output (V)")
    axes[1].set_xlabel("Time (s), R6 at 0.75 model position")
    for axis in axes:
        axis.grid(True, alpha=0.25)
    fig.suptitle("80308 slow multivibrator creates the pulsed calibrator envelope")
    fig.tight_layout()
    fig.savefig(FIGURES / "slow-gate-envelope.png", dpi=180)
    plt.close(fig)
    return results, middle


def fast_output_circuit(mode_grounded: bool, powered: bool = True) -> str:
    mode = "RMODE mode 0 1m" if mode_grounded else "* mode terminal open"
    vcc = 5.6 if powered else 0
    carrier = "pulse(0 3.5 0 5n 5n 4.995u 10u)" if powered else "0"
    return f"""* 80308 gated carrier and divider; grounded={mode_grounded}, powered={powered}
{include('SN7400_80308.sub')}
{include('SN7476_80308.sub')}
VCC vcc 0 {vcc}
VCARRIER carrier 0 {carrier}
VEN enable 0 {3.5 if powered else 0}
XIC1 vcc vcc u1y vcc vcc u2y 0 gated carrier enable defeat vcc vcc vcc SN7400_80308
XIC2 ff2qb pre1 mode j1 vcc gated mode clr2 j2 ff2qb ff2q k2 0 ff1qb ff1q k1 SN7476_80308
{mode}
R9 gated out 2.2k
C8 ff1qb out 10n
R8 out 0 2.2k
RDEFEAT defeat_pull defeat 10k
VDEFEAT defeat_pull 0 3.9
.options filetype=ascii method=gear reltol=1e-4
.tran 20n 2m 0 20n
.save v(carrier) v(gated) v(ff2qb) v(ff1qb) v(out) v(defeat)
.end
"""


def fast_output_study() -> dict[str, dict[str, float]]:
    runs = {}
    traces_by_mode = {}
    for label, grounded in (("25_khz", False), ("100_khz", True)):
        time, traces = run_raw(label, fast_output_circuit(grounded))
        start = 1e-3
        runs[label] = {
            "out_25khz_vpp": fit_vpp(time, traces["v(out)"], 25e3, start),
            "out_100khz_vpp": fit_vpp(time, traces["v(out)"], 100e3, start),
            "defeat_dc_v": float(np.mean(traces["v(defeat)"][time >= start])),
        }
        traces_by_mode[label] = (time, traces)

    off_time, off = run_raw("powered-off", fast_output_circuit(False, powered=False))
    runs["powered_off"] = {
        "defeat_dc_v": float(np.mean(off["v(defeat)"][off_time >= 1e-3]))
    }

    rows = []
    for label, (time, traces) in traces_by_mode.items():
        selected = time >= 1.8e-3
        stride = max(1, int(np.count_nonzero(selected) / 4000))
        for i in np.flatnonzero(selected)[::stride]:
            rows.append((label, time[i], traces["v(gated)"][i], traces["v(ff2qb)"][i], traces["v(ff1qb)"][i], traces["v(out)"][i]))
    write_csv(
        DATA / "output-waveforms.csv",
        ("mode", "time_s", "gated_100khz_v", "divide_by_2_v", "divide_by_4_v", "out_pin_v"),
        rows,
    )
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
    colors = {"25_khz": "#2d6a9f", "100_khz": "#a04a22"}
    for label, (time, traces) in traces_by_mode.items():
        selected = time >= 1.8e-3
        t_us = (time[selected] - 1.8e-3) * 1e6
        axes[0].plot(t_us, traces["v(out)"][selected], label=label.replace("_", " "), color=colors[label])
        axes[1].plot(t_us, traces["v(ff1qb)"][selected], label=label.replace("_", " "), color=colors[label])
    axes[0].set_ylabel("OUT terminal (V)")
    axes[1].set_ylabel("IC2 pin 14 (V)")
    axes[1].set_xlabel("Time in final 200 µs (µs)")
    axes[0].legend()
    for axis in axes:
        axis.grid(True, alpha=0.25)
    fig.suptitle("80308 output in normal 25 kHz and grounded 25/100 modes")
    fig.tight_layout()
    fig.savefig(FIGURES / "output-modes.png", dpi=180)
    plt.close(fig)
    return runs


def regulator_study() -> dict[str, float]:
    circuit = f"""* 80308 5.6 V zener regulator with fitted 60 mA logic load
{include('1N752A_80308.lib')}
VMAIN main 0 9
R5 main logic 100
D1 0 logic 1N752A_80308
BLOAD logic 0 I=60m
.options filetype=ascii
.dc VMAIN 9 15 0.25
.save v(main) v(logic)
.end
"""
    supply, traces = run_raw("regulator", circuit)
    logic = traces["v(logic)"]
    resistor_current = (supply - logic) / 100
    zener_current = resistor_current - 0.060
    rows = zip(supply, logic, resistor_current, zener_current)
    write_csv(
        DATA / "regulator-sweep.csv",
        ("input_v", "logic_supply_v", "r5_current_a", "zener_current_a"),
        rows,
    )
    fig, axes = plt.subplots(2, 1, figsize=(9, 6.5), sharex=True)
    axes[0].plot(supply, logic, color="#2d6a9f")
    axes[0].axhline(5.6, color="black", linestyle="--", linewidth=0.8, label="nominal 5.6 V")
    axes[0].set_ylabel("Logic supply (V)")
    axes[0].legend()
    axes[1].plot(supply, zener_current * 1e3, color="#a04a22")
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_ylabel("D1 current (mA)")
    axes[1].set_xlabel("Calibrator +12 terminal voltage (V)")
    for axis in axes:
        axis.grid(True, alpha=0.25)
    fig.suptitle("80308 R5/D1 logic-supply regulation")
    fig.tight_layout()
    fig.savefig(FIGURES / "logic-regulator.png", dpi=180)
    plt.close(fig)
    at_13p8 = int(np.argmin(np.abs(supply - 13.75)))
    regulating = np.flatnonzero(logic >= 5.4)
    return {
        "logic_v_at_13p75": float(logic[at_13p8]),
        "zener_ma_at_13p75": float(zener_current[at_13p8] * 1e3),
        "regulation_start_v": float(supply[regulating[0]]) if regulating.size else float("nan"),
    }


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    export_and_check()
    oscillator = oscillator_study()
    slow, _ = slow_gate_study()
    output = fast_output_study()
    regulator = regulator_study()

    summary_rows = [
        ("oscillator", key, value, "calculated from staged transient")
        for key, value in oscillator.items()
    ]
    for row in slow:
        for key in ("frequency_hz", "period_s", "high_fraction", "transitions"):
            summary_rows.append((f"slow_gate_r6_{row['position']:.2f}", key, row[key], "calculated from staged transient"))
    for mode, values in output.items():
        for key, value in values.items():
            summary_rows.append((mode, key, value, "calculated from staged transient"))
    for key, value in regulator.items():
        summary_rows.append(("regulator", key, value, "calculated from DC sweep"))
    write_csv(
        DATA / "measurements.csv",
        ("study", "measurement", "simulated_value", "evidence_status"),
        summary_rows,
    )
    for study, measurement, value, _ in summary_rows:
        print(f"{study:24s} {measurement:24s} {value:.9g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
