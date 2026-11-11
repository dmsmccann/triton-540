#!/usr/bin/env python3
"""Run the Model 249 normal-signal and impulse-blanking study.

The runner exports mod_249.kicad_sch afresh, adds only the two supplies,
source/load, documented model-fit fixture, and analysis commands, then retains
pin-level waveforms and figures under spice/studies/249/how-it-works/.
"""

from __future__ import annotations

import csv
import math
import re
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SCHEMATIC = ROOT / "mod_249.kicad_sch"
ROOT_SCHEMATIC = ROOT / "triton_540.kicad_sch"
STUDY_DIR = ROOT / "spice" / "studies" / "249" / "how-it-works"
DATA_DIR = STUDY_DIR / "data"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = ROOT / "spice" / "generated" / "249-how-it-works"
BASE_NETLIST = GENERATED_DIR / "249-base.cir"

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")

IF_HZ = 9_000_000.0
NORMAL_V_PEAK = 50e-6
IMPULSE_V_PEAK = 5.0
IMPULSE_START_S = 60e-6
IMPULSE_STOP_S = 70e-6
STOP_S = 80e-6
TIME_STEP_S = 2e-9
SOURCE_OHM = 50.0
LOAD_OHM = 10e3
LOAD_PF = 15.0
MC1350_AGC_MODEL_SHUNT_OHM = 5.1e3
C18_MODEL_PF = 40.0

TRACES = (
    ("input", "/in"),
    ("output", "/out"),
    ("q3_base", "net-_q49-3-b_"),
    ("gate_ct", "/vct"),
    ("gate_cathode_a", "net-_d49-1-k_"),
    ("gate_cathode_b", "net-_d49-2-k_"),
    ("detector_q4_base", "/1350_out"),
    ("agc", "net-_ic49-1-agc_"),
    ("mc_out_minus", "net-_ic49-1-out-_"),
    ("mc_out_plus", "net-_ic49-1-out+_"),
    ("mc_vplus", "net-_ic49-1-v+_"),
    ("mc_tank_ct", "net-_l49-2-ct_"),
    ("mc_input_minus", "net-_ic49-1-in-_"),
    ("mc_input_plus", "net-_ic49-1-in+_"),
)


def run(command: list[str], cwd: Path, description: str) -> None:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if completed.returncode:
        print(completed.stdout, end="")
        print(completed.stderr, end="")
        raise SystemExit(f"{description} failed with exit code {completed.returncode}")


def live_supply_voltage() -> float:
    text = ROOT_SCHEMATIC.read_text(encoding="utf-8")
    match = re.search(
        r'\(property "Reference" "V1".*?\(property "Value" "([0-9.]+)"',
        text,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("Could not find root-sheet V1 value")
    return float(match.group(1))


def export_netlist() -> str:
    for directory in (DATA_DIR, FIGURE_DIR, GENERATED_DIR):
        directory.mkdir(parents=True, exist_ok=True)
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
    text = text.replace(
        '.include "spice/models/',
        f'.include "{ROOT.as_posix()}/spice/models/',
    )
    text, count = re.subn(
        r"(?m)^C49-18 (.+?) [0-9.]+p$",
        rf"C49-18 \1 {C18_MODEL_PF:g}p",
        text,
        count=1,
    )
    if count != 1:
        raise ValueError("Could not set the C49-18 model value")
    required = (
        "Q49-1 ", "Q49-2 ", "Q49-3 ", "Q49-4 ", "Q49-5 ", "Q49-6 ",
        "XIC49-1 ", "XD49-1 ", "XD49-2 ", "XL49-1 ", "XL49-2 ", "XT49-1 ",
        "MPN3404", "MC1350", "NB249_L1_CT", "NB249_L2_CT", "NB249_T1",
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise ValueError(f"Fresh KiCad export is missing expected content: {missing}")
    return text


def fixture_netlist(base: str, supply_v: float, enabled: bool, stem: str) -> Path:
    switched_v = supply_v if enabled else 0.0
    # The short 9 MHz burst is a deterministic stand-in for the IF ringing
    # produced by a broadband impulse upstream.  It is not a calibrated
    # automotive-noise waveform or a fitted threshold test.
    waveform = (
        f"{NORMAL_V_PEAK:.9g}*sin(2*pi*{IF_HZ:.9g}*time) + "
        f"{IMPULSE_V_PEAK:.9g}*(u(time-{IMPULSE_START_S:.9g})-"
        f"u(time-{IMPULSE_STOP_S:.9g}))*sin(2*pi*{IF_HZ:.9g}*time)"
    )
    fixture = "\n".join(
        (
            "* Model 249 assembly-specific external fixture",
            f"V249MAIN /+12 GND PWL(0 0 5u 0 10u {supply_v:.9g})",
            f"V249SW /+12_SW GND PWL(0 0 5u 0 10u {switched_v:.9g})",
            f"B249SOURCE 249_SOURCE GND V={{{waveform}}}",
            f"R249SOURCE 249_SOURCE /In {SOURCE_OHM:g}",
            f"R249LOAD /Out GND {LOAD_OHM:g}",
            f"C249SCOPE /Out GND {LOAD_PF:g}p",
            # The archived transistor macro-model sources too much quiescent
            # current from pin 5 for the board's 4.7 k + 10 k return.  This
            # model-only shunt restores the datasheet's roughly 5 V,
            # maximum-gain AGC operating region; it is not a board component.
            f"R249AGCFIT net-_IC49-1-AGC_ GND {MC1350_AGC_MODEL_SHUNT_OHM:g}",
            "R249GROUND GND 0 1m",
            ".options method=gear reltol=0.003 chgtol=1e-14 trtol=7",
        )
    )
    text, count = re.subn(r"(?m)^\.end\s*$", fixture + "\n.end", base, count=1)
    if count != 1:
        raise ValueError("Expected one .end directive")
    dat_name = stem + "-result.dat"
    control = "\n".join(
        (
            ".control",
            "set wr_singlescale",
            "set wr_vecnames",
            f"tran {TIME_STEP_S:g} {STOP_S:g} 0 {TIME_STEP_S:g}",
            "wrdata " + dat_name + " " + " ".join(f"v({node})" for _, node in TRACES),
            "quit",
            ".endc",
            ".end",
        )
    )
    text, count = re.subn(r"(?m)^\.end\s*$", control, text, count=1)
    if count != 1:
        raise ValueError("Expected one .end directive while adding control block")
    path = GENERATED_DIR / (stem + ".cir")
    path.write_text(text, encoding="utf-8")
    return path


def run_case(base: str, supply_v: float, enabled: bool, stem: str) -> np.ndarray:
    netlist = fixture_netlist(base, supply_v, enabled, stem)
    dat_path = GENERATED_DIR / (stem + "-result.dat")
    log_path = GENERATED_DIR / (stem + ".log")
    dat_path.unlink(missing_ok=True)
    log_path.unlink(missing_ok=True)
    run(
        [str(NGSPICE), "-b", "-D", "ngbehavior=ltpsa", "-o", str(log_path), str(netlist)],
        GENERATED_DIR,
        f"ngspice {stem}",
    )
    log = log_path.read_text(encoding="utf-8", errors="replace").lower()
    if "fatal error" in log or "simulation(s) aborted" in log or "error:" in log:
        raise ValueError(f"{stem} did not complete normally; see {log_path}")
    data = np.loadtxt(dat_path, skiprows=1)
    if data.ndim == 1:
        data = data.reshape(1, -1)
    if data.shape[1] != len(TRACES) + 1:
        raise ValueError(f"{stem} has {data.shape[1]} columns")
    return data


def window(data: np.ndarray, start: float, stop: float) -> np.ndarray:
    return data[(data[:, 0] >= start) & (data[:, 0] < stop)]


def resample(data: np.ndarray, times: np.ndarray) -> np.ndarray:
    columns = [times]
    columns.extend(np.interp(times, data[:, 0], data[:, column]) for column in range(1, data.shape[1]))
    return np.column_stack(columns)


def rms_ac(values: np.ndarray) -> float:
    centered = values - np.mean(values)
    return float(np.sqrt(np.mean(centered * centered)))


def carrier_envelope(data: np.ndarray, column: int) -> np.ndarray:
    samples = max(5, int(round((1.0 / IF_HZ) / np.median(np.diff(data[:, 0])))))
    kernel = np.ones(samples) / samples
    values = data[:, column]
    mean = np.convolve(values, kernel, mode="same")
    mean_sq = np.convolve(values * values, kernel, mode="same")
    return np.sqrt(np.maximum(mean_sq - mean * mean, 0)) * math.sqrt(2.0)


def median_carrier_peak(data: np.ndarray, column: int) -> float:
    envelope = carrier_envelope(data, column)
    trim = max(1, int(0.05 * envelope.size))
    return float(np.median(envelope[trim:-trim]))


def metrics(disabled: np.ndarray, enabled: np.ndarray, supply_v: float) -> dict[str, float]:
    idx = {name: number + 1 for number, (name, _) in enumerate(TRACES)}
    quiet_start, quiet_stop = 48e-6, 58e-6
    pulse_start, pulse_stop = 59.8e-6, 63e-6
    off_quiet = window(disabled, quiet_start, quiet_stop)
    on_quiet = window(enabled, quiet_start, quiet_stop)
    off_pulse = window(disabled, pulse_start, pulse_stop)
    on_pulse = window(enabled, pulse_start, pulse_stop)
    off_late = window(disabled, 66e-6, 69e-6)
    on_late = window(enabled, 66e-6, 69e-6)
    off_in_peak = median_carrier_peak(off_quiet, idx["input"])
    off_out_peak = median_carrier_peak(off_quiet, idx["output"])
    on_in_peak = median_carrier_peak(on_quiet, idx["input"])
    on_out_peak = median_carrier_peak(on_quiet, idx["output"])
    off_in = off_in_peak / math.sqrt(2.0)
    off_out = off_out_peak / math.sqrt(2.0)
    on_in = on_in_peak / math.sqrt(2.0)
    on_out = on_out_peak / math.sqrt(2.0)
    off_env = carrier_envelope(off_pulse, idx["output"])
    on_env = carrier_envelope(on_pulse, idx["output"])
    off_peak = float(np.max(off_env))
    on_peak = float(np.max(on_env))
    off_late_rms = median_carrier_peak(off_late, idx["output"]) / math.sqrt(2.0)
    on_late_rms = median_carrier_peak(on_late, idx["output"]) / math.sqrt(2.0)
    gate_low = on_pulse[:, idx["q3_base"]] < 0.7
    gate_low_times = on_pulse[gate_low, 0]
    return {
        "supply_v": supply_v,
        "if_hz": IF_HZ,
        "normal_source_v_peak": NORMAL_V_PEAK,
        "impulse_source_v_peak": IMPULSE_V_PEAK,
        "impulse_width_s": IMPULSE_STOP_S - IMPULSE_START_S,
        "source_ohm": SOURCE_OHM,
        "load_ohm": LOAD_OHM,
        "load_pf": LOAD_PF,
        "mc1350_agc_model_shunt_ohm": MC1350_AGC_MODEL_SHUNT_OHM,
        "c49_18_model_pf": C18_MODEL_PF,
        "disabled_input_v_rms": off_in,
        "disabled_output_v_rms": off_out,
        "disabled_gain_v_per_v": off_out / off_in,
        "disabled_gain_db": 20 * math.log10(off_out / off_in),
        "enabled_input_v_rms": on_in,
        "enabled_output_v_rms": on_out,
        "enabled_gain_v_per_v": on_out / on_in,
        "enabled_gain_db": 20 * math.log10(on_out / on_in),
        "normal_signal_change_db": 20 * math.log10(on_out / off_out),
        "disabled_impulse_output_v_peak": off_peak,
        "enabled_impulse_output_v_peak": on_peak,
        "impulse_suppression_db": 20 * math.log10(off_peak / max(on_peak, 1e-30)),
        "late_burst_disabled_output_v_rms": off_late_rms,
        "late_burst_enabled_output_v_rms": on_late_rms,
        "late_burst_suppression_db": 20 * math.log10(off_late_rms / max(on_late_rms, 1e-30)),
        "gate_trigger_delay_s": float(gate_low_times[0] - IMPULSE_START_S) if gate_low_times.size else math.nan,
        "enabled_detector_q4_base_peak_v": float(np.max(on_pulse[:, idx["detector_q4_base"]])),
        "enabled_q3_base_pulse_min_v": float(np.min(on_pulse[:, idx["q3_base"]])),
        "enabled_gate_ct_pulse_min_v": float(np.min(on_pulse[:, idx["gate_ct"]])),
        "enabled_mc_differential_peak_v": float(np.max(np.abs(
            on_pulse[:, idx["mc_out_plus"]] - on_pulse[:, idx["mc_out_minus"]]
        ))),
        "enabled_q3_base_quiet_v": float(np.mean(on_quiet[:, idx["q3_base"]])),
        "enabled_gate_ct_quiet_v": float(np.mean(on_quiet[:, idx["gate_ct"]])),
        "enabled_agc_quiet_v": float(np.mean(on_quiet[:, idx["agc"]])),
        "enabled_mc_out_minus_quiet_v": float(np.mean(on_quiet[:, idx["mc_out_minus"]])),
        "enabled_mc_out_plus_quiet_v": float(np.mean(on_quiet[:, idx["mc_out_plus"]])),
        "enabled_mc_vplus_quiet_v": float(np.mean(on_quiet[:, idx["mc_vplus"]])),
        "enabled_mc_tank_ct_quiet_v": float(np.mean(on_quiet[:, idx["mc_tank_ct"]])),
        "enabled_mc_input_minus_rms_v": rms_ac(on_quiet[:, idx["mc_input_minus"]]),
        "enabled_mc_input_plus_rms_v": rms_ac(on_quiet[:, idx["mc_input_plus"]]),
        "time_step_s": TIME_STEP_S,
    }


def write_timeline(path: Path, disabled: np.ndarray, enabled: np.ndarray) -> None:
    names = ["time_s"]
    for prefix in ("disabled", "enabled"):
        names.extend(prefix + "_" + name for name, _ in TRACES)
    stride = max(1, int(round(10e-9 / TIME_STEP_S)))
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(names)
        for off_row, on_row in zip(disabled[::stride], enabled[::stride]):
            writer.writerow([off_row[0], *off_row[1:], *on_row[1:]])


def write_summary(path: Path, values: dict[str, float]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("metric", "value"))
        writer.writerows(values.items())


def make_plots(disabled: np.ndarray, enabled: np.ndarray) -> None:
    idx = {name: number + 1 for number, (name, _) in enumerate(TRACES)}
    mask = (enabled[:, 0] >= 57e-6) & (enabled[:, 0] <= 70e-6)
    time_us = enabled[mask, 0] * 1e6
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    on_segment = enabled[mask]
    axes[0].plot(time_us, carrier_envelope(on_segment, idx["input"]) * 1e3, color="black")
    axes[0].set_ylabel("249_IN envelope (mV peak)")
    axes[0].set_title("Model 249 response to a strong 9 MHz IF burst")
    off_segment = disabled[mask]
    axes[1].plot(time_us, carrier_envelope(off_segment, idx["output"]) * 1e3, label="Blanker disabled")
    axes[1].plot(time_us, carrier_envelope(on_segment, idx["output"]) * 1e3, label="Blanker enabled", alpha=0.85)
    axes[1].set_ylabel("249_OUT envelope (mV peak)")
    axes[1].legend(loc="upper right")
    axes[2].plot(time_us, enabled[mask, idx["q3_base"]], label="Q49-3 base")
    axes[2].plot(time_us, enabled[mask, idx["gate_ct"]], label="T49-1 secondary CT")
    axes[2].set_ylabel("Gate control (V)")
    axes[2].set_xlabel("Time (us)")
    axes[2].legend(loc="upper right")
    for axis in axes:
        axis.axvspan(IMPULSE_START_S * 1e6, IMPULSE_STOP_S * 1e6, color="orange", alpha=0.18)
        axis.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "249-impulse-blanking.png", dpi=180)
    plt.close(fig)

    mask = (enabled[:, 0] >= 45e-6) & (enabled[:, 0] <= 58e-6)
    time_us = enabled[mask, 0] * 1e6
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    normal_segment = enabled[mask]
    axes[0].plot(time_us, carrier_envelope(normal_segment, idx["input"]) * 1e3)
    axes[0].set_ylabel("249_IN envelope (mV peak)")
    axes[0].set_title("Normal 9 MHz signal with the blanker enabled")
    axes[1].plot(time_us, carrier_envelope(normal_segment, idx["output"]) * 1e3)
    axes[1].set_ylabel("249_OUT envelope (mV peak)")
    axes[2].plot(time_us, enabled[mask, idx["agc"]], label="MC1350 AGC pin")
    axes[2].plot(time_us, enabled[mask, idx["gate_ct"]], label="Gate center tap")
    axes[2].set_ylabel("Control (V)")
    axes[2].set_xlabel("Time (us)")
    axes[2].legend(loc="upper right")
    for axis in axes:
        axis.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "249-normal-signal.png", dpi=180)
    plt.close(fig)


def write_manifest() -> None:
    rows = (
        ("README.md", "Method, results, assessment, limitations, and bench proposal"),
        ("data/249-operation-summary.csv", "Principal numerical results"),
        ("data/249-operation-timeline.csv", "Disabled/enabled pin and control waveforms"),
        ("figures/249-normal-signal.png", "Normal 9 MHz pin waveforms and control voltages"),
        ("figures/249-impulse-blanking.png", "Enabled/disabled response to the IF burst"),
    )
    with (STUDY_DIR / "manifest.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("path", "description"))
        writer.writerows(rows)


def main() -> None:
    supply_v = live_supply_voltage()
    base = export_netlist()
    disabled = run_case(base, supply_v, False, "249-disabled")
    enabled = run_case(base, supply_v, True, "249-enabled")
    disabled = resample(disabled, enabled[:, 0])
    values = metrics(disabled, enabled, supply_v)
    write_timeline(DATA_DIR / "249-operation-timeline.csv", disabled, enabled)
    write_summary(DATA_DIR / "249-operation-summary.csv", values)
    make_plots(disabled, enabled)
    write_manifest()
    for key, value in values.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
