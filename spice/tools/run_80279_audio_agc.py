#!/usr/bin/env python3
"""Run 80279 Simulation 5: MC1747 audio and AGC-detector study.

The KiCad schematic is exported afresh.  In disposable netlist copies only,
the existing red-box V79-SIM5 source is moved from board IN to the jumpered
FILT IN/FILT OUT node and changed to an audio source.  This avoids adding a
second physical test source while keeping the saved schematic as the circuit
source of truth.

Two studies are run:

* a 1 Hz to 100 kHz small-signal AC sweep of both MC1747 sections; and
* a 1 kHz transient amplitude sweep that measures AUDIO gain/distortion,
  clipping, D79-6 drive, C79-22 storage voltage, and the PIN-bias response.

Curated CSVs and plots are retained below spice/studies/80279/audio-agc.
Disposable netlists, logs, and raw data remain below spice/generated.
"""

from __future__ import annotations

import csv
import math
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SCHEMATIC = ROOT / "80279_if_agc.kicad_sch"
STUDY_DIR = ROOT / "spice" / "studies" / "80279" / "audio-agc"
DATA_DIR = STUDY_DIR / "data"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = ROOT / "spice" / "generated" / "80279-audio-agc"
BASE_NETLIST = GENERATED_DIR / "80279-audio-agc-base.cir"

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")

AC_START_HZ = 1.0
AC_STOP_HZ = 100e3
AC_POINTS_PER_DECADE = 100
TONE_HZ = 1e3
TRAN_START_S = 80e-3
TRAN_STOP_S = 120e-3
TRAN_SAMPLE_S = 5e-6
TRAN_MAX_STEP_S = 2e-6

# Peak voltage applied by the ideal audio fixture at the jumpered filter node.
AMPLITUDES_V_PEAK = (
    0.0,
    0.1e-3,
    0.3e-3,
    1e-3,
    3e-3,
    5e-3,
    10e-3,
    15e-3,
    20e-3,
    30e-3,
    50e-3,
    75e-3,
    100e-3,
)

AC_TRACES = (
    ("filt_input", "/filt_in", "FILT IN / FILT OUT"),
    ("ic1_audio_input", "net-_ic1-+b_", "IC1 section B non-inverting input"),
    ("bias_reference", "net-_c79-25-pad1_", "IC1 half-supply reference"),
    ("audio_opamp", "net-_ic1-output_b_", "IC1 section B output"),
    ("audio_terminal", "/audio", "AUDIO terminal"),
    ("agc_opamp", "net-_ic1-output_a_", "IC1 section A AGC output"),
)

TRAN_TRACES = (
    ("filt_input", "/filt_in", "FILT IN / FILT OUT"),
    ("audio_opamp", "net-_ic1-output_b_", "IC1 section B output"),
    ("audio_terminal", "/audio", "AUDIO terminal"),
    ("agc_opamp", "net-_ic1-output_a_", "IC1 section A AGC output"),
    ("d79_6_anode", "net-_d79-6-a_", "D79-6 anode"),
    ("agc_store", "net-_d79-6-k_", "C79-22 AGC storage"),
    ("pin_bias", "/pin_bias", "PIN-diode bias bus"),
    ("d79_1_feed", "net-_d79-1-a_", "D79-1 feed-resistor output"),
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
        "XIC1 Net-_IC1--A_ Net-_IC1-+A_",
        "C79-27 Net-_IC1-+B_ /FILT_IN 4.7u",
        "R79-32 Net-_IC1-Output_B_ Net-_IC1--B_ 100k",
        "C79-26 Net-_IC1-Output_B_ Net-_IC1--B_ 430p",
        "C79-21 Net-_IC1-Output_B_ /AUDIO 1u",
        "C79-24 Net-_IC1-Output_B_ Net-_IC1-+A_ 0.1u",
        "R79-28 Net-_IC1-Output_A_ Net-_IC1--A_ 10k",
        "C79-23 Net-_IC1-Output_A_ Net-_D79-6-A_ 0.01u",
        "D79-6 Net-_D79-6-A_ Net-_D79-6-K_ 1N4154",
        "C79-22 Net-_D79-6-K_ GND 4.7u",
        "R79-24 Net-_D79-6-K_ GND 680k",
        "R79-SIM1 /AUDIO GND 25k",
        "V79-SIM5 /IN GND DC 0",
        "V79-SIM6 /BFO GND DC 6.5",
        ".options rshunt=1e12",
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise ValueError(f"Fresh KiCad export is missing expected content: {missing}")
    return text


def configure_audio_source(text: str, amplitude: float, ac: float) -> str:
    replacement = (
        f"V79-SIM5 /FILT_IN GND DC 0 "
        f"SIN( 0 {amplitude:g} {TONE_HZ:g} 0 0 0 ) AC {ac:g}"
    )
    text, count = re.subn(r"(?m)^V79-SIM5\s+.*$", replacement, text, count=1)
    if count != 1:
        raise ValueError(f"Expected one V79-SIM5 source; found {count}")
    # Retain the documented 6.5 V BFO DC condition but remove RF injection so
    # the product detector does not contribute audio during this isolated test.
    text, count = re.subn(
        r"(?m)^V79-SIM6\s+.*$",
        "V79-SIM6 /BFO GND DC 6.5 SIN( 6.5 0 9Meg 0 0 0 ) AC 0",
        text,
        count=1,
    )
    if count != 1:
        raise ValueError(f"Expected one V79-SIM6 source; found {count}")
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


def run_ac(base: str) -> np.ndarray:
    text = configure_audio_source(base, 0.0, 1.0)
    data_name = "80279-audio-response.dat"
    netlist = append_control(
        text,
        [
            f"ac dec {AC_POINTS_PER_DECADE} {AC_START_HZ:g} {AC_STOP_HZ:g}",
            "wrdata " + data_name + " "
            + " ".join(f"mag(v({node}))" for _, node, _ in AC_TRACES),
        ],
        GENERATED_DIR / "80279-audio-response.cir",
    )
    run_ngspice(netlist, GENERATED_DIR / "80279-audio-response.log")
    return load_dat(GENERATED_DIR / data_name, len(AC_TRACES))


def case_name(amplitude: float) -> str:
    return f"input-{amplitude * 1e3:07.3f}mv".replace(".", "p")


def run_transient_case(base: str, amplitude: float) -> tuple[str, np.ndarray]:
    name = case_name(amplitude)
    text = configure_audio_source(base, amplitude, 0.0)
    data_name = f"{name}.dat"
    netlist = append_control(
        text,
        [
            f"tran {TRAN_SAMPLE_S:g} {TRAN_STOP_S:g} {TRAN_START_S:g} {TRAN_MAX_STEP_S:g}",
            "linearize",
            "wrdata " + data_name + " "
            + " ".join(f"v({node})" for _, node, _ in TRAN_TRACES),
        ],
        GENERATED_DIR / f"{name}.cir",
    )
    run_ngspice(netlist, GENERATED_DIR / f"{name}.log")
    return name, load_dat(GENERATED_DIR / data_name, len(TRAN_TRACES))


def tone_vpp(time: np.ndarray, values: np.ndarray, order: int = 1) -> float:
    phase = 2.0 * np.pi * TONE_HZ * order * time
    design = np.column_stack((np.sin(phase), np.cos(phase), np.ones(time.size)))
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    return float(2.0 * math.hypot(coefficients[0], coefficients[1]))


def measure_transient(amplitude: float, data: np.ndarray) -> dict[str, float]:
    time = data[:, 0]
    columns = {
        key: data[:, index + 1]
        for index, (key, _, _) in enumerate(TRAN_TRACES)
    }
    input_vpp = tone_vpp(time, columns["filt_input"])
    audio_vpp = tone_vpp(time, columns["audio_terminal"])
    harmonics = [tone_vpp(time, columns["audio_terminal"], order) for order in range(2, 6)]
    audio_thd = (
        math.sqrt(sum(value * value for value in harmonics)) / audio_vpp
        if audio_vpp > 1e-15 else float("nan")
    )
    tail = max(1, round(5e-3 / TRAN_SAMPLE_S))
    return {
        "input_v_peak": amplitude,
        "input_1khz_vpp": input_vpp,
        "audio_opamp_1khz_vpp": tone_vpp(time, columns["audio_opamp"]),
        "audio_terminal_1khz_vpp": audio_vpp,
        "audio_gain_v_per_v": audio_vpp / input_vpp if input_vpp > 1e-15 else float("nan"),
        "audio_thd_percent": 100.0 * audio_thd,
        "audio_terminal_min_v": float(columns["audio_terminal"].min()),
        "audio_terminal_max_v": float(columns["audio_terminal"].max()),
        "agc_opamp_1khz_vpp": tone_vpp(time, columns["agc_opamp"]),
        "agc_opamp_min_v": float(columns["agc_opamp"].min()),
        "agc_opamp_max_v": float(columns["agc_opamp"].max()),
        "d79_6_anode_min_v": float(columns["d79_6_anode"].min()),
        "d79_6_anode_max_v": float(columns["d79_6_anode"].max()),
        "agc_store_final_v": float(columns["agc_store"][-tail:].mean()),
        "agc_store_peak_v": float(columns["agc_store"].max()),
        "pin_bias_final_v": float(columns["pin_bias"][-tail:].mean()),
        "pin_bias_peak_v": float(columns["pin_bias"].max()),
        "pin_diode_branch_final_a": float(
            ((columns["pin_bias"][-tail:] - columns["d79_1_feed"][-tail:]) / 1000.0).mean()
        ),
    }


def ac_rows(data: np.ndarray) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for values in data:
        row = {"frequency_hz": float(values[0])}
        input_magnitude = float(values[1])
        for index, (key, _, _) in enumerate(AC_TRACES):
            magnitude = float(values[index + 1])
            ratio = magnitude / input_magnitude if input_magnitude else float("nan")
            row[f"{key}_v_per_v"] = ratio
            row[f"{key}_db"] = 20.0 * math.log10(max(ratio, 1e-300))
        rows.append(row)
    return rows


def interpolate(rows: list[dict[str, float]], key: str, frequency: float) -> float:
    for left, right in zip(rows, rows[1:]):
        if left["frequency_hz"] <= frequency <= right["frequency_hz"]:
            fraction = ((frequency - left["frequency_hz"])
                        / (right["frequency_hz"] - left["frequency_hz"]))
            return left[key] + fraction * (right[key] - left[key])
    return min(rows, key=lambda row: abs(row["frequency_hz"] - frequency))[key]


def threshold_crossings(rows: list[dict[str, float]], key: str) -> tuple[float, float, float]:
    peak_index = max(range(len(rows)), key=lambda index: rows[index][key])
    peak = rows[peak_index][key]
    threshold = peak - 3.0

    def find(segment: list[dict[str, float]], rising: bool) -> float:
        for left, right in zip(segment, segment[1:]):
            y1, y2 = left[key], right[key]
            crossed = y1 <= threshold <= y2 if rising else y1 >= threshold >= y2
            if crossed and y2 != y1:
                fraction = (threshold - y1) / (y2 - y1)
                return left["frequency_hz"] + fraction * (
                    right["frequency_hz"] - left["frequency_hz"]
                )
        return float("nan")

    return find(rows[: peak_index + 1], True), find(rows[peak_index:], False), peak


def write_csv(path: Path, rows: list[dict[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_results(ac: list[dict[str, float]], transient: list[dict[str, float]]) -> list[dict[str, str | float]]:
    write_csv(DATA_DIR / "80279-audio-frequency-response.csv", ac)
    write_csv(DATA_DIR / "80279-audio-level-sweep.csv", transient)

    audio_low, audio_high, audio_peak = threshold_crossings(ac, "audio_terminal_db")
    agc_low, agc_high, agc_peak = threshold_crossings(ac, "agc_opamp_db")
    summary: list[dict[str, str | float]] = [
        {"metric": "audio_gain_at_1khz", "value": interpolate(ac, "audio_terminal_v_per_v", 1e3), "unit": "V/V"},
        {"metric": "audio_gain_at_1khz_db", "value": interpolate(ac, "audio_terminal_db", 1e3), "unit": "dB"},
        {"metric": "audio_peak_gain_db", "value": audio_peak, "unit": "dB"},
        {"metric": "audio_lower_3db_hz", "value": audio_low, "unit": "Hz"},
        {"metric": "audio_upper_3db_hz", "value": audio_high, "unit": "Hz"},
        {"metric": "agc_gain_at_1khz", "value": interpolate(ac, "agc_opamp_v_per_v", 1e3), "unit": "V/V"},
        {"metric": "agc_gain_at_1khz_db", "value": interpolate(ac, "agc_opamp_db", 1e3), "unit": "dB"},
        {"metric": "agc_peak_gain_db", "value": agc_peak, "unit": "dB"},
        {"metric": "agc_lower_3db_hz", "value": agc_low, "unit": "Hz"},
        {"metric": "agc_upper_3db_hz", "value": agc_high, "unit": "Hz"},
    ]
    with (DATA_DIR / "80279-audio-agc-summary.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=("metric", "value", "unit"))
        writer.writeheader()
        writer.writerows(summary)
    return summary


def plot_frequency(ac: list[dict[str, float]]) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    frequency = np.array([row["frequency_hz"] for row in ac])
    fig, axis = plt.subplots(figsize=(9.4, 5.8))
    axis.semilogx(frequency, [row["audio_terminal_db"] for row in ac],
                  linewidth=1.8, label="AUDIO terminal")
    axis.semilogx(frequency, [row["agc_opamp_db"] for row in ac],
                  linewidth=1.8, label="IC1 AGC-section output")
    axis.axvline(1e3, color="black", linestyle="--", linewidth=1.0,
                 label="1 kHz reference")
    axis.set_title("80279 audio and AGC-amplifier small-signal response")
    axis.set_xlabel("Audio frequency (Hz, logarithmic scale)")
    axis.set_ylabel("Voltage gain from FILT IN / FILT OUT (dB)")
    axis.grid(True, which="both", alpha=0.28)
    axis.legend(loc="best")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "80279-audio-frequency-response.png", dpi=180)
    plt.close(fig)


def plot_level(transient: list[dict[str, float]]) -> None:
    driven = [row for row in transient if row["input_v_peak"] > 0]
    input_mv_peak = np.array([row["input_v_peak"] * 1e3 for row in driven])
    fig, axes = plt.subplots(2, 1, figsize=(9.4, 8.2), sharex=True)

    axes[0].plot(input_mv_peak,
                 [row["audio_terminal_1khz_vpp"] for row in driven],
                 marker="o", linewidth=1.6, label="AUDIO 1 kHz output")
    axes[0].set_ylabel("AUDIO output (V p-p)")
    axes[0].grid(True, alpha=0.28)
    twin = axes[0].twinx()
    twin.plot(input_mv_peak, [row["audio_thd_percent"] for row in driven],
              marker="s", linestyle="--", linewidth=1.4, color="#d62728",
              label="AUDIO harmonic distortion")
    twin.set_ylabel("Modeled AUDIO THD (%)")
    handles, labels = axes[0].get_legend_handles_labels()
    h2, l2 = twin.get_legend_handles_labels()
    axes[0].legend(handles + h2, labels + l2, loc="best")

    baseline = transient[0]["agc_store_final_v"]
    axes[1].plot(input_mv_peak,
                 [row["agc_store_final_v"] for row in driven],
                 marker="o", linewidth=1.6, label="C79-22 AGC storage")
    axes[1].plot(input_mv_peak,
                 [row["pin_bias_final_v"] for row in driven],
                 marker="s", linewidth=1.6, label="PIN-bias bus")
    axes[1].axhline(baseline, color="#999999", linestyle=":", linewidth=1.2,
                    label="No-audio storage level")
    axes[1].set_xlabel("Applied 1 kHz level at FILT IN / FILT OUT (mV peak)")
    axes[1].set_ylabel("End-of-120 ms control voltage (V)")
    axes[1].grid(True, alpha=0.28)
    axes[1].legend(loc="best")

    fig.suptitle("80279 audio output and AGC-detector response to 1 kHz input")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "80279-audio-level-agc-response.png", dpi=180)
    plt.close(fig)


def write_nominal_waveform(amplitude: float, data: np.ndarray) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "80279-audio-nominal-waveform.csv"
    step = 4
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["time_s"] + [key for key, _, _ in TRAN_TRACES])
        writer.writerows(data[::step].tolist())

    time_ms = (data[:, 0] - data[0, 0]) * 1e3
    fig, axes = plt.subplots(3, 1, figsize=(9.4, 8.4), sharex=True)
    indexes = {key: index + 1 for index, (key, _, _) in enumerate(TRAN_TRACES)}
    axes[0].plot(time_ms, data[:, indexes["filt_input"]] * 1e3, linewidth=1.3)
    axes[0].set_ylabel("Filter input (mV)")
    axes[0].set_title(f"Applied 1 kHz signal ({amplitude * 1e3:g} mV peak)")
    axes[1].plot(time_ms, data[:, indexes["audio_terminal"]], linewidth=1.3,
                 color="#2f7d32")
    axes[1].set_ylabel("AUDIO (V)")
    axes[1].set_title("Amplified AUDIO terminal waveform")
    axes[2].plot(time_ms, data[:, indexes["agc_store"]], linewidth=1.3,
                 label="C79-22 storage")
    axes[2].plot(time_ms, data[:, indexes["pin_bias"]], linewidth=1.3,
                 label="PIN-bias bus")
    axes[2].set_ylabel("Control voltage (V)")
    axes[2].set_xlabel("Time in retained window (ms)")
    axes[2].set_title("Rectified AGC control")
    axes[2].legend(loc="best")
    for axis in axes:
        axis.grid(True, alpha=0.28)
    fig.suptitle("Ten-Tec 80279 audio amplifier and AGC detector")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "80279-audio-agc-waveforms.png", dpi=180)
    plt.close(fig)


def write_manifest() -> None:
    rows = (
        ("data/80279-audio-frequency-response.csv", "Small-signal response of both MC1747 paths"),
        ("data/80279-audio-level-sweep.csv", "1 kHz level, clipping, and AGC-control measurements"),
        ("data/80279-audio-agc-summary.csv", "Principal gain and bandwidth measurements"),
        ("data/80279-audio-nominal-waveform.csv", "Retained 10 mV-peak transient waveform"),
        ("figures/80279-audio-frequency-response.png", "Audio and AGC-section frequency response"),
        ("figures/80279-audio-level-agc-response.png", "Output, distortion, and AGC control versus input"),
        ("figures/80279-audio-agc-waveforms.png", "Nominal audio and control waveforms"),
    )
    STUDY_DIR.mkdir(parents=True, exist_ok=True)
    with (STUDY_DIR / "manifest.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("path", "purpose"))
        writer.writerows(rows)


def main() -> int:
    base = export_netlist()
    ac = ac_rows(run_ac(base))

    transient_data: dict[float, np.ndarray] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(run_transient_case, base, amplitude): amplitude
            for amplitude in AMPLITUDES_V_PEAK
        }
        for future in as_completed(futures):
            amplitude = futures[future]
            _, data = future.result()
            transient_data[amplitude] = data
            print(f"finished {amplitude * 1e3:g} mV peak "
                  f"({len(transient_data)}/{len(AMPLITUDES_V_PEAK)})", flush=True)

    transient = [
        measure_transient(amplitude, transient_data[amplitude])
        for amplitude in AMPLITUDES_V_PEAK
    ]
    summary = write_results(ac, transient)
    plot_frequency(ac)
    plot_level(transient)
    nominal_amplitude = 10e-3
    write_nominal_waveform(nominal_amplitude, transient_data[nominal_amplitude])
    write_manifest()

    print()
    for item in summary:
        print(f"{item['metric']}={item['value']} {item['unit']}")
    print()
    print(f"{'input mVpk':>10s} {'AUDIO Vpp':>10s} {'gain':>9s} {'THD %':>9s} "
          f"{'store V':>9s} {'PIN V':>9s} {'branch uA':>10s}")
    for row in transient:
        print(
            f"{row['input_v_peak'] * 1e3:10.3f} "
            f"{row['audio_terminal_1khz_vpp']:10.4f} "
            f"{row['audio_gain_v_per_v']:9.2f} "
            f"{row['audio_thd_percent']:9.3f} "
            f"{row['agc_store_final_v']:9.4f} "
            f"{row['pin_bias_final_v']:9.4f} "
            f"{row['pin_diode_branch_final_a'] * 1e6:10.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
