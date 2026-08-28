#!/usr/bin/env python3
"""Run the 80279 product-detector and audio-recovery study (Simulation 4).

Q79-3 receives a 9.001 MHz IF signal on gate 1 and a 9.000 MHz BFO on gate 2.
The wanted difference product is 1 kHz.  The runner exports a fresh KiCad
netlist, changes only the two fixture source definitions in generated copies,
and sweeps the BFO RF amplitude, which the manual does not document.

Two transient analyses run per case:

  * a short 9 MHz window used to measure carrier-frequency amplitudes, and
  * a long window linearized to a 5 MHz grid, used for recovered-audio
    measurements and the audio spectrum.

The 1 ns maximum timestep is a requirement, not a comfort margin.  The two IF
transformers give the modeled 9 MHz path a loaded Q near 108, and a coarser
step numerically damps it: 5 ns understates the IF amplitude reaching Q79-3
gate 1 by 38 percent and 2 ns by 3.6 percent.  Every run is therefore checked
against the Simulation 2 AC transfer before its measurements are reported.

Disposable netlists, logs, and raw data stay below spice/generated.  Curated
CSVs and figures are written to the 80279 study directory.
"""

from __future__ import annotations

import csv
import math
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SCHEMATIC = ROOT / "if-agc_80279.kicad_sch"
STUDY_DIR = ROOT / "spice" / "studies" / "80279" / "product-detector"
DATA_DIR = STUDY_DIR / "data"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = ROOT / "spice" / "generated" / "80279-detector"
BASE_NETLIST = GENERATED_DIR / "80279-detector-base.cir"

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")

IF_HZ = 9.001e6
BFO_HZ = 9.000e6
AUDIO_HZ = IF_HZ - BFO_HZ          # 1 kHz wanted difference product
SUM_HZ = IF_HZ + BFO_HZ            # 18.001 MHz unwanted sum product

IF_AMPLITUDE_V = 100e-6            # estimated board-input level, not a manual value

# Simulation 2 measured 55.066 dB from board IN to Q79-3 gate 1 at 9 MHz.  The
# AC result is exact for the linear IF chain, so it is the convergence anchor
# for these transient runs.
SIM2_IN_TO_G1_DB = 55.066
CONVERGENCE_TOLERANCE = 0.03       # transient must land within 3 percent of it

# Short 9 MHz observation window.
RF_START_S = 90e-6
RF_STOP_S = 110e-6
RF_MAX_STEP_S = 1e-9

# Long recovered-audio window: four complete 1 kHz cycles on a 5 MHz grid.
AUDIO_START_S = 1.1e-3
AUDIO_STOP_S = 5.1e-3
AUDIO_SAMPLE_S = 0.2e-6

RF_TRACES = (
    ("board_in", "/in", "Board IN (9.001 MHz)"),
    ("t79_2_secondary", "net-_c79-11-pad1_", "T79-2 secondary"),
    ("q79_3_g1", "net-_q79-3-g1_", "Q79-3 gate 1 (IF)"),
    ("q79_3_g2", "net-_q79-3-g2_", "Q79-3 gate 2 (BFO)"),
    ("q79_3_drain", "net-_q79-3-d_", "Q79-3 drain"),
    ("q79_3_source", "net-_q79-3-s_", "Q79-3 source"),
)

AUDIO_TRACES = (
    ("q79_3_drain", "net-_q79-3-d_", "Q79-3 drain (detector output)"),
    ("c79_17_node", "net-_c79-17-pad1_", "After R79-14/C79-17 low-pass"),
    ("filt_loop", "/filt_in", "FILT IN / FILT OUT (jumpered)"),
    ("audio_terminal", "/audio", "AUDIO terminal"),
    ("pin_bias", "/pin_bias", "PIN-diode bias bus"),
    ("agc_store", "net-_d79-6-k_", "C79-22 AGC storage"),
)

# Case name, BFO RF amplitude (V peak), IF RF amplitude (V peak).
CASES = (
    ("bfo-0mv", 0.0, IF_AMPLITUDE_V),
    ("bfo-25mv", 25e-3, IF_AMPLITUDE_V),
    ("bfo-50mv", 50e-3, IF_AMPLITUDE_V),
    ("bfo-100mv", 100e-3, IF_AMPLITUDE_V),
    ("bfo-200mv", 200e-3, IF_AMPLITUDE_V),
    ("bfo-400mv", 400e-3, IF_AMPLITUDE_V),
    ("bfo-800mv", 800e-3, IF_AMPLITUDE_V),
    ("bfo-1500mv", 1.5, IF_AMPLITUDE_V),
    ("if-off", 400e-3, 0.0),
)
NOMINAL_CASE = "bfo-400mv"


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
        "K79_T1 L79-3 L79-4 0.25",
        "K79_T2 L79-5 L79-6 0.25",
        "L79-6 GND Net-_C79-11-Pad1_ 2.63u",
        "XQ79-3 Net-_Q79-3-D_ Net-_Q79-3-G2_ Net-_Q79-3-G1_ Net-_Q79-3-S_ RCA40823",
        "C79-19 Net-_Q79-3-G2_ /BFO 22p",
        "C79-27 Net-_IC1-+B_ /FILT_IN 4.7u",
        "V79-SIM1 /+12 GND DC 13.8",
        "V79-SIM2 /+REG GND DC 8.0",
        "V79-SIM3 /R GND DC 12.1",
        "V79-SIM4 /T GND DC 0.2",
        "R79-SIM1 /AUDIO GND 25k",
        "R79-SIM2 /S_MTR GND 1k",
        ".options rshunt=1e12",
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise ValueError(f"Fresh KiCad export is missing expected content: {missing}")
    return text


def set_sine(text: str, reference: str, offset: float, amplitude: float,
             frequency: float, tail: str) -> str:
    """Replace one fixture source definition, preserving its node and DC value."""
    pattern = rf"(?m)^({reference}\s+\S+\s+GND\s+DC\s+)(\S+)\s+SIN\([^)]*\)(.*)$"
    replacement = (
        rf"\g<1>\g<2> SIN( {offset:g} {amplitude:g} {frequency:g} 0 0 0 ) {tail}"
    )
    updated, count = re.subn(pattern, replacement, text)
    if count != 1:
        raise ValueError(f"Expected one {reference} sine source; found {count}")
    return updated


def build_case_netlist(base: str, name: str, bfo_amplitude: float,
                       if_amplitude: float) -> Path:
    text = set_sine(base, "V79-SIM5", 0.0, if_amplitude, IF_HZ, "AC 1")
    text = set_sine(text, "V79-SIM6", 6.5, bfo_amplitude, BFO_HZ, "AC 0")
    commands = [
        ".control",
        "set wr_singlescale",
        "set wr_vecnames",
        f"tran {RF_MAX_STEP_S:g} {RF_STOP_S:g} {RF_START_S:g} {RF_MAX_STEP_S:g}",
        f"wrdata {name}-rf.dat "
        + " ".join(f"v({node})" for _, node, _ in RF_TRACES),
        f"tran {AUDIO_SAMPLE_S:g} {AUDIO_STOP_S:g} {AUDIO_START_S:g} {RF_MAX_STEP_S:g}",
        "linearize",
        f"wrdata {name}-audio.dat "
        + " ".join(f"v({node})" for _, node, _ in AUDIO_TRACES),
        "quit",
        ".endc",
        ".end",
    ]
    text, count = re.subn(r"(?m)^\.end\s*$", "\n".join(commands), text, count=1)
    if count != 1:
        raise ValueError(f"Expected one .end directive; found {count}")
    path = GENERATED_DIR / f"{name}.cir"
    path.write_text(text, encoding="utf-8")
    return path


def load_dat(path: Path, trace_count: int) -> np.ndarray:
    if not path.exists():
        raise ValueError(f"ngspice did not create {path}")
    data = np.loadtxt(path, skiprows=1)
    if data.shape[1] != trace_count + 1:
        raise ValueError(
            f"{path.name} has {data.shape[1]} columns; expected {trace_count + 1}"
        )
    return data


def run_case(base: str, name: str, bfo_amplitude: float, if_amplitude: float):
    netlist = build_case_netlist(base, name, bfo_amplitude, if_amplitude)
    log = GENERATED_DIR / f"{name}.log"
    if not NGSPICE.exists():
        raise SystemExit(f"ngspice was not found: {NGSPICE}")
    run(
        [str(NGSPICE), "-b", "-D", "ngbehavior=ltpsa", "-o", str(log), str(netlist)],
        GENERATED_DIR,
        f"ngspice {name} run",
    )
    log_text = log.read_text(encoding="utf-8", errors="replace")
    if "fatal error" in log_text.lower():
        raise ValueError(f"{name} reported a fatal error; see {log}")
    rf = load_dat(GENERATED_DIR / f"{name}-rf.dat", len(RF_TRACES))
    audio = load_dat(GENERATED_DIR / f"{name}-audio.dat", len(AUDIO_TRACES))
    expected_rows = round((AUDIO_STOP_S - AUDIO_START_S) / AUDIO_SAMPLE_S) + 1
    if abs(audio.shape[0] - expected_rows) > 2:
        raise ValueError(
            f"{name} audio window has {audio.shape[0]} rows; expected {expected_rows}"
        )
    return rf, audio


def fit_tone_vpp(time: np.ndarray, values: np.ndarray, frequency: float) -> float:
    """Least-squares amplitude of one tone against a DC offset.

    No drift term is included on purpose.  A ramp is not orthogonal to a sine
    over a whole number of cycles, so fitting one alongside the tone borrows
    amplitude from it.  With a coherent window this fit equals the DFT bin,
    which keeps the reported harmonics consistent with the spectrum figure.
    Slow settling appears in the sub-fundamental bins instead.
    """
    phase = 2 * np.pi * frequency * time
    design = np.column_stack((np.sin(phase), np.cos(phase), np.ones(time.size)))
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    return float(2 * math.hypot(coefficients[0], coefficients[1]))


def rf_band_residual_vpp(time: np.ndarray, values: np.ndarray) -> float:
    """Peak-to-peak left after removing the slow audio variation.

    The 20 microsecond window cannot resolve the 1 kHz spacing between the IF
    and BFO carriers, so the remainder is reported as a combined 9 MHz-band
    residual rather than as separate feedthrough components.  Over that window
    the 1 kHz product advances only about 7 degrees, so a quadratic baseline
    removes it without the ill-conditioning of fitting a 1 kHz tone there.
    """
    baseline = np.polyval(np.polyfit(time, values, 2), time)
    residual = values - baseline
    return float(residual.max() - residual.min())


def expected_g1_vpp(if_amplitude: float) -> float:
    """Gate-1 amplitude the Simulation 2 AC transfer predicts for this drive."""
    return 2.0 * if_amplitude * 10 ** (SIM2_IN_TO_G1_DB / 20.0)


def measure(name: str, bfo_amplitude: float, if_amplitude: float,
            rf: np.ndarray, audio: np.ndarray) -> dict[str, float]:
    rf_time = rf[:, 0]
    rf_columns = {key: rf[:, index + 1] for index, (key, _, _) in enumerate(RF_TRACES)}
    audio_time = audio[:, 0]
    audio_columns = {
        key: audio[:, index + 1] for index, (key, _, _) in enumerate(AUDIO_TRACES)
    }

    fundamental = fit_tone_vpp(audio_time, audio_columns["filt_loop"], AUDIO_HZ)
    harmonics = [
        fit_tone_vpp(audio_time, audio_columns["filt_loop"], AUDIO_HZ * order)
        for order in range(2, 6)
    ]
    thd = (
        math.sqrt(sum(value**2 for value in harmonics)) / fundamental
        if fundamental
        else float("nan")
    )

    g1_if_vpp = fit_tone_vpp(rf_time, rf_columns["q79_3_g1"], IF_HZ)
    return {
        "case": name,
        "bfo_amplitude_v_peak": bfo_amplitude,
        "if_amplitude_v_peak": if_amplitude,
        "board_in_9p001mhz_vpp": fit_tone_vpp(rf_time, rf_columns["board_in"], IF_HZ),
        "t79_2_secondary_9p001mhz_vpp": fit_tone_vpp(
            rf_time, rf_columns["t79_2_secondary"], IF_HZ
        ),
        "q79_3_g1_9p001mhz_vpp": g1_if_vpp,
        "q79_3_g2_9mhz_vpp": fit_tone_vpp(rf_time, rf_columns["q79_3_g2"], BFO_HZ),
        "q79_3_g2_dc_v": float(rf_columns["q79_3_g2"].mean()),
        "q79_3_drain_dc_v": float(rf_columns["q79_3_drain"].mean()),
        "q79_3_source_dc_v": float(rf_columns["q79_3_source"].mean()),
        "drain_9mhz_band_residual_vpp": rf_band_residual_vpp(
            rf_time, rf_columns["q79_3_drain"]
        ),
        "drain_18p001mhz_sum_vpp": fit_tone_vpp(
            rf_time, rf_columns["q79_3_drain"], SUM_HZ
        ),
        "drain_1khz_vpp": fit_tone_vpp(
            audio_time, audio_columns["q79_3_drain"], AUDIO_HZ
        ),
        "c79_17_1khz_vpp": fit_tone_vpp(
            audio_time, audio_columns["c79_17_node"], AUDIO_HZ
        ),
        "filt_loop_1khz_vpp": fundamental,
        "audio_terminal_1khz_vpp": fit_tone_vpp(
            audio_time, audio_columns["audio_terminal"], AUDIO_HZ
        ),
        "filt_loop_2khz_vpp": harmonics[0],
        "filt_loop_3khz_vpp": harmonics[1],
        "filt_loop_thd_percent": 100.0 * thd,
        "detector_transfer_filt_per_g1": (
            fundamental / g1_if_vpp if g1_if_vpp else float("nan")
        ),
        "detector_transfer_drain_per_g1": (
            fit_tone_vpp(audio_time, audio_columns["q79_3_drain"], AUDIO_HZ) / g1_if_vpp
            if g1_if_vpp
            else float("nan")
        ),
        "g1_vs_sim2_ac_percent": (
            100.0 * (g1_if_vpp / expected_g1_vpp(if_amplitude) - 1.0)
            if if_amplitude
            else float("nan")
        ),
        "pin_bias_dc_v": float(audio_columns["pin_bias"].mean()),
        "agc_store_dc_v": float(audio_columns["agc_store"].mean()),
    }


def audio_spectrum(audio: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Coherent single-sided spectrum of the recovered audio at FILT IN/OUT."""
    index = [key for key, _, _ in AUDIO_TRACES].index("filt_loop") + 1
    samples = audio[:-1, index]          # drop the duplicate end point
    samples = samples - samples.mean()
    spectrum = np.fft.rfft(samples) * 2.0 / samples.size
    frequencies = np.fft.rfftfreq(samples.size, AUDIO_SAMPLE_S)
    return frequencies, np.abs(spectrum)


def write_sweep_csv(rows: list[dict[str, float]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with (DATA_DIR / "80279-detector-sweep.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_waveform_csv(rf: np.ndarray, audio: np.ndarray) -> None:
    window = rf[:, 0] <= rf[0, 0] + 2e-6
    with (DATA_DIR / "80279-detector-rf-window.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(["time_s"] + [key for key, _, _ in RF_TRACES])
        writer.writerows(rf[window].tolist())
    step = 4                              # 1.25 MHz curated audio grid
    with (DATA_DIR / "80279-detector-audio-window.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(["time_s"] + [key for key, _, _ in AUDIO_TRACES])
        writer.writerows(audio[::step].tolist())


def write_spectrum_csv(frequencies: np.ndarray, magnitudes: np.ndarray) -> None:
    keep = frequencies <= 10e3
    reference = magnitudes[keep].max()
    with (DATA_DIR / "80279-detector-spectrum.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(("frequency_hz", "amplitude_v_peak", "db_relative_to_peak"))
        for frequency, magnitude in zip(frequencies[keep], magnitudes[keep]):
            writer.writerow(
                (
                    f"{frequency:.6g}",
                    f"{magnitude:.6g}",
                    f"{20 * math.log10(max(magnitude, 1e-18) / reference):.4f}",
                )
            )


def plot_waveforms(rf: np.ndarray, audio: np.ndarray) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    rf_window = rf[:, 0] <= rf[0, 0] + 1e-6
    rf_time_us = (rf[rf_window, 0] - rf[0, 0]) * 1e6
    audio_time_ms = audio[:, 0] * 1e3

    fig, axes = plt.subplots(4, 1, figsize=(9.6, 9.6))
    axes[0].plot(rf_time_us, rf[rf_window, 3] * 1e3, linewidth=1.2, color="#1f77b4")
    axes[0].set_ylabel("Gate 1 (mV)")
    axes[0].set_title("Q79-3 gate 1: 9.001 MHz IF signal")
    axes[0].set_xlabel("Time in the settled 9 MHz window (µs)")

    axes[1].plot(rf_time_us, rf[rf_window, 4], linewidth=1.2, color="#d62728")
    axes[1].set_ylabel("Gate 2 (V)")
    axes[1].set_title("Q79-3 gate 2: 9.000 MHz BFO injection")
    axes[1].set_xlabel("Time in the settled 9 MHz window (µs)")

    drain_index = [key for key, _, _ in AUDIO_TRACES].index("q79_3_drain") + 1
    filt_index = [key for key, _, _ in AUDIO_TRACES].index("filt_loop") + 1
    drain = audio[:, drain_index]
    filt = audio[:, filt_index]
    axes[2].plot(audio_time_ms, (drain - drain.mean()) * 1e3, linewidth=1.2,
                 color="#2f7d32")
    axes[2].set_ylabel("Drain (mV)")
    axes[2].set_title("Q79-3 drain: recovered 1 kHz difference product, DC removed")
    axes[2].set_xlabel("Time (ms)")

    axes[3].plot(audio_time_ms, (filt - filt.mean()) * 1e3, linewidth=1.2,
                 color="#7b3fa0")
    axes[3].set_ylabel("FILT IN/OUT (mV)")
    axes[3].set_title("FILT IN / FILT OUT loop, DC removed")
    axes[3].set_xlabel("Time (ms)")

    for axis in axes:
        axis.grid(True, alpha=0.28)
    fig.suptitle(
        "Ten-Tec 80279 product detector: 9.001 MHz IF against a 9.000 MHz BFO"
    )
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "80279-detector-waveforms.png", dpi=180)
    plt.close(fig)


def plot_spectrum(frequencies: np.ndarray, magnitudes: np.ndarray) -> None:
    keep = frequencies <= 10e3
    reference = magnitudes[keep].max()
    decibels = 20 * np.log10(np.maximum(magnitudes[keep], 1e-18) / reference)
    floor = float(np.median(decibels[frequencies[keep] > 1.5e3]))
    fig, axis = plt.subplots(figsize=(9.2, 5.2))
    # Discrete 250 Hz bins: draw them as lines from the baseline, not as a
    # continuous curve, so the coherent FFT resolution stays visible.
    axis.vlines(frequencies[keep] / 1e3, -100, decibels, linewidth=1.6,
                color="#7b3fa0")
    axis.plot(frequencies[keep] / 1e3, decibels, linestyle="none", marker="o",
              markersize=3.4, color="#7b3fa0")
    axis.axhline(floor, color="#999999", linestyle=":", linewidth=1.4,
                 label=f"Numerical floor, median {floor:.0f} dBc")
    axis.set_xlabel("Audio frequency (kHz)")
    axis.set_ylabel("Level relative to the 1 kHz product (dB)")
    axis.set_title(
        "Recovered audio spectrum at FILT IN / FILT OUT "
        "(9.001 MHz IF minus 9.000 MHz BFO)"
    )
    axis.set_ylim(-100, 5)
    axis.grid(True, alpha=0.28)
    axis.axvline(1.0, color="black", linestyle="--", linewidth=1.0,
                 label="1 kHz wanted product")
    axis.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "80279-detector-spectrum.png", dpi=180)
    plt.close(fig)


def plot_bfo_sensitivity(rows: list[dict[str, float]]) -> None:
    sweep = [row for row in rows if row["case"] != "if-off"]
    amplitudes = [row["bfo_amplitude_v_peak"] * 1e3 for row in sweep]
    recovered = [row["filt_loop_1khz_vpp"] * 1e3 for row in sweep]
    drain_dc = [row["q79_3_drain_dc_v"] for row in sweep]
    control = next(row for row in rows if row["case"] == "if-off")
    # Distortion is only meaningful once a real product exists; the zero-BFO
    # case measures the numerical floor against itself.
    driven = [row for row in sweep if row["bfo_amplitude_v_peak"] > 0]

    fig, axes = plt.subplots(2, 1, figsize=(9.4, 8.2), sharex=True)

    axes[0].plot(amplitudes, recovered, marker="o", linewidth=1.6,
                 color="#1f77b4", label="Recovered 1 kHz at FILT IN/OUT")
    axes[0].axhline(control["filt_loop_1khz_vpp"] * 1e3, color="#999999",
                    linestyle=":", linewidth=1.4,
                    label="Control: BFO on, no IF signal")
    axes[0].set_ylabel("Recovered 1 kHz product (mV p-p)")
    axes[0].grid(True, alpha=0.28)

    twin = axes[0].twinx()
    twin.plot([row["bfo_amplitude_v_peak"] * 1e3 for row in driven],
              [row["filt_loop_thd_percent"] for row in driven],
              marker="s", linewidth=1.3, linestyle="--", color="#d62728",
              label="Total harmonic distortion")
    twin.set_ylabel("Harmonic distortion at FILT IN/OUT (%)")
    twin.set_ylim(0, 8)

    handles, labels = axes[0].get_legend_handles_labels()
    extra_handles, extra_labels = twin.get_legend_handles_labels()
    axes[0].legend(handles + extra_handles, labels + extra_labels,
                   loc="upper left", fontsize=9)

    axes[1].plot(amplitudes, drain_dc, marker="o", linewidth=1.6,
                 color="#2f7d32", label="Simulated Q79-3 drain")
    axes[1].axhline(3.0, color="black", linestyle="--", linewidth=1.1,
                    label="Manual receive/no-signal value, 3.0 V")
    axes[1].axhspan(3.0 * 0.85, 3.0 * 1.15, color="#cccccc", alpha=0.45,
                    label="15 percent service tolerance")
    axes[1].set_xlabel("BFO RF amplitude at the board terminal (mV peak)")
    axes[1].set_ylabel("Q79-3 drain DC (V)")
    axes[1].grid(True, alpha=0.28)
    axes[1].legend(loc="upper left", fontsize=9)

    fig.suptitle(
        "80279 product-detector response to BFO injection level\n"
        f"(IF input held at {IF_AMPLITUDE_V * 1e6:g} µV peak, 9.001 MHz)"
    )
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "80279-detector-bfo-sensitivity.png", dpi=180)
    plt.close(fig)


def write_manifest() -> None:
    rows = (
        ("data/80279-detector-sweep.csv",
         "Per-case detector measurements across the BFO amplitude sweep"),
        ("data/80279-detector-rf-window.csv",
         f"{NOMINAL_CASE}: 2 microseconds of settled 9 MHz waveforms"),
        ("data/80279-detector-audio-window.csv",
         f"{NOMINAL_CASE}: 4 ms recovered-audio window on a 1.25 MHz grid"),
        ("data/80279-detector-spectrum.csv",
         f"{NOMINAL_CASE}: recovered-audio spectrum at FILT IN/OUT to 10 kHz"),
        ("figures/80279-detector-waveforms.png",
         "Gate 1, gate 2, drain, and FILT IN/OUT waveforms"),
        ("figures/80279-detector-spectrum.png",
         "Recovered-audio spectrum showing the 1 kHz product and its harmonics"),
        ("figures/80279-detector-bfo-sensitivity.png",
         "Recovered audio and distortion versus BFO injection amplitude"),
    )
    STUDY_DIR.mkdir(parents=True, exist_ok=True)
    with (STUDY_DIR / "manifest.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("path", "purpose"))
        writer.writerows(rows)


def run_all_cases(base: str) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    results: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(run_case, base, name, bfo, rf_in): name
            for name, bfo, rf_in in CASES
        }
        for future in as_completed(futures):
            name = futures[future]
            results[name] = future.result()
            print(f"finished {name} ({len(results)}/{len(CASES)})", flush=True)
    return results


def check_convergence(rows: list[dict[str, float]]) -> None:
    """Reject the run if the 1 ns transient failed to reproduce Simulation 2."""
    bad = [
        row for row in rows
        if row["if_amplitude_v_peak"]
        and abs(row["g1_vs_sim2_ac_percent"]) > 100.0 * CONVERGENCE_TOLERANCE
    ]
    if bad:
        detail = ", ".join(
            f"{row['case']} {row['g1_vs_sim2_ac_percent']:+.2f}%" for row in bad
        )
        raise ValueError(
            "Gate-1 IF amplitude disagrees with the Simulation 2 AC transfer by "
            f"more than {100 * CONVERGENCE_TOLERANCE:g} percent ({detail}). "
            "Reduce the maximum timestep before trusting these results."
        )


def load_existing() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Reuse the raw data of a previous run, for figure and CSV changes only."""
    return {
        name: (
            load_dat(GENERATED_DIR / f"{name}-rf.dat", len(RF_TRACES)),
            load_dat(GENERATED_DIR / f"{name}-audio.dat", len(AUDIO_TRACES)),
        )
        for name, _, _ in CASES
    }


def main() -> int:
    if "--figures-only" in sys.argv:
        print(f"reusing raw data below {GENERATED_DIR}")
        results = load_existing()
    else:
        results = run_all_cases(export_netlist())

    rows = [
        measure(name, bfo, rf_in, *results[name]) for name, bfo, rf_in in CASES
    ]
    check_convergence(rows)
    nominal = results.get(NOMINAL_CASE)
    if nominal is None:
        raise ValueError(f"Nominal case {NOMINAL_CASE} was not run")

    rf, audio = nominal
    frequencies, magnitudes = audio_spectrum(audio)
    write_sweep_csv(rows)
    write_waveform_csv(rf, audio)
    write_spectrum_csv(frequencies, magnitudes)
    plot_waveforms(rf, audio)
    plot_spectrum(frequencies, magnitudes)
    plot_bfo_sensitivity(rows)
    write_manifest()

    print()
    print(f"{'case':12s} {'BFO Vpk':>8s} {'G1 IF mVpp':>11s} {'vs AC':>8s} "
          f"{'FILT 1k mVpp':>13s} {'THD %':>8s}")
    for row in rows:
        print(
            f"{row['case']:12s} {row['bfo_amplitude_v_peak']:8.3f} "
            f"{row['q79_3_g1_9p001mhz_vpp'] * 1e3:11.4f} "
            f"{row['g1_vs_sim2_ac_percent']:+7.2f}% "
            f"{row['filt_loop_1khz_vpp'] * 1e3:13.5f} "
            f"{row['filt_loop_thd_percent']:8.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
