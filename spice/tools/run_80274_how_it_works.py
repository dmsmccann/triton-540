#!/usr/bin/env python3
"""Run the 80274 receive, transmit-mute, and CW-sidetone study.

The runner exports the assembly schematic afresh.  It takes the DC supply
value from V1 on the root sheet, represents the closed J8 speaker contact by
one 8 ohm load at the board OUTPUT pin, and supplies documented T/SIDETONE
control voltages in disposable netlists.
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
SCHEMATIC = ROOT / "80274_audio_power_amp.kicad_sch"
ROOT_SCHEMATIC = ROOT / "triton_540.kicad_sch"
STUDY_DIR = ROOT / "spice" / "studies" / "80274" / "how-it-works"
DATA_DIR = STUDY_DIR / "data"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = ROOT / "spice" / "generated" / "80274-how-it-works"
BASE_NETLIST = GENERATED_DIR / "80274-base.cir"

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")

SPEAKER_OHM = 8.0
INPUT_HZ = 1_000.0
INPUT_V_PEAK = 10e-3
T_RX_V = 0.2
T_TX_V = 10.4
MAIN_STOP_S = 0.250
RX_END_S = 0.050
CW_START_S = 0.100
TX_END_S = 0.175
TIME_STEP_S = 2e-6

TRACES = (
    ("input", "/input"),
    ("output", "/output"),
    ("t", "/t"),
    ("sidetone", "/sidetone"),
    ("mute_node", "net-_q74-1-c_"),
    ("lm380_input", "net-_u74-1-+_"),
    ("lm380_output", "net-_c74-6-pad1_"),
    ("ujt_emitter", "net-_q74-2-e_"),
    ("q3_collector", "net-_q74-3-c_"),
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
    required = (
        "R74-5 __R74-5",
        "R74-7 __R74-7",
        "D74-1 /T Net-_D74-1-K_ 1N4154",
        "C74-6 Net-_C74-6-Pad1_ /OUTPUT 220u",
        "XU74-1 ",
        "LM380_FITTED",
        "XQ74-2 ",
        "UN4870",
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise ValueError(f"Fresh KiCad export is missing expected content: {missing}")
    return text


def replace_line(text: str, reference: str, replacement: str) -> str:
    text, count = re.subn(
        rf"(?m)^{re.escape(reference)}\s+.*$", replacement, text, count=1
    )
    if count != 1:
        raise ValueError(f"Expected one {reference} line; found {count}")
    return text


def fixture_netlist(
    base: str,
    supply_v: float,
    r5_position: float,
    r7_position: float,
    main_sequence: bool,
) -> str:
    if not 0.0 < r5_position < 1.0 or not 0.0 < r7_position < 1.0:
        raise ValueError("Pot positions must remain inside the open interval (0, 1)")

    # R74-5 is a divider from the UJT timing node to ground; its wiper feeds
    # R74-14. R74-7 has pins 1 and 2 tied, so it is a rheostat in series with
    # R74-8. Small endpoint guards avoid zero-ohm branches.
    r5_upper = max(1.0, 10_000.0 * (1.0 - r5_position))
    r5_lower = max(1.0, 10_000.0 * r5_position)
    r7_value = max(1.0, 10_000.0 * r7_position)
    text = base.replace("Net-_R74-14-Pad2_", "R74_5_WIPER")
    text = replace_line(
        text,
        "R74-5",
        f"R74-5A Net-_C74-3-Pad1_ R74_5_WIPER {r5_upper:.9g}\n"
        f"R74-5B R74_5_WIPER GND {r5_lower:.9g}",
    )
    text = replace_line(
        text,
        "R74-7",
        f"R74-7R Net-_Q74-2-B2_ Net-_R74-7-Pad3_ {r7_value:.9g}",
    )

    if main_sequence:
        t_source = (
            f"PWL(0 {T_RX_V} {RX_END_S - 10e-6:g} {T_RX_V} "
            f"{RX_END_S:g} {T_TX_V} {TX_END_S - 10e-6:g} {T_TX_V} "
            f"{TX_END_S:g} {T_RX_V})"
        )
        sidetone_source = (
            f"PWL(0 {T_RX_V} {CW_START_S - 10e-6:g} {T_RX_V} "
            f"{CW_START_S:g} {T_TX_V} {TX_END_S - 10e-6:g} {T_TX_V} "
            f"{TX_END_S:g} {T_RX_V})"
        )
        stop = MAIN_STOP_S
    else:
        t_source = f"PWL(0 {T_RX_V} 0.00999 {T_RX_V} 0.010 {T_TX_V})"
        sidetone_source = f"PWL(0 {T_RX_V} 0.00999 {T_RX_V} 0.010 {T_TX_V})"
        stop = 0.120

    fixture = "\n".join(
        (
            "* 80274 assembly-specific external fixture",
            f"V80274SUPPLY /+12 GND DC {supply_v:.9g}",
            f"V80274T /T GND {t_source}",
            f"V80274SIDETONE /SIDETONE GND {sidetone_source}",
            f"V80274INPUT /INPUT GND SIN(0 {INPUT_V_PEAK:.9g} {INPUT_HZ:.9g})",
            f"R80274SPEAKER /OUTPUT GND {SPEAKER_OHM:g}",
            f".ic v(Net-_U74-1-BYPASS_)={supply_v / 2:.9g} "
            f"v(Net-_C74-6-Pad1_)={supply_v / 2:.9g}",
        )
    )
    text, count = re.subn(r"(?m)^\.end\s*$", fixture + "\n.end", text, count=1)
    if count != 1:
        raise ValueError("Expected one .end directive")
    return text, stop


def append_control(text: str, stop: float, dat_name: str, path: Path) -> Path:
    commands = [
        ".control",
        "set wr_singlescale",
        "set wr_vecnames",
        f"tran {TIME_STEP_S:g} {stop:g} 0 {TIME_STEP_S:g}",
        "linearize",
        "wrdata " + dat_name + " " + " ".join(f"v({node})" for _, node in TRACES),
        "quit",
        ".endc",
        ".end",
    ]
    text, count = re.subn(r"(?m)^\.end\s*$", "\n".join(commands), text, count=1)
    if count != 1:
        raise ValueError("Expected one .end directive while adding control block")
    path.write_text(text, encoding="utf-8")
    return path


def run_case(
    base: str,
    supply_v: float,
    stem: str,
    r5_position: float,
    r7_position: float,
    main_sequence: bool,
) -> np.ndarray:
    text, stop = fixture_netlist(
        base, supply_v, r5_position, r7_position, main_sequence
    )
    dat_name = stem + "-result.dat"
    dat_path = GENERATED_DIR / dat_name
    log = GENERATED_DIR / (stem + ".log")
    dat_path.unlink(missing_ok=True)
    log.unlink(missing_ok=True)
    netlist = append_control(
        text, stop, dat_name, GENERATED_DIR / (stem + ".cir")
    )
    run(
        [str(NGSPICE), "-b", "-D", "ngbehavior=ltpsa", "-o", str(log), str(netlist)],
        GENERATED_DIR,
        f"ngspice {stem}",
    )
    log_text = log.read_text(encoding="utf-8", errors="replace").lower()
    if (
        "fatal error" in log_text
        or "simulation(s) aborted" in log_text
        or "error:" in log_text
        or "ngspice-46 done" not in log_text
    ):
        raise ValueError(f"{stem} did not complete normally; see {log}")
    data = np.loadtxt(dat_path, skiprows=1)
    if data.ndim == 1:
        data = data.reshape(1, -1)
    if data.shape[1] != len(TRACES) + 1:
        raise ValueError(f"{stem} has {data.shape[1]} columns")
    return data


def rms(values: np.ndarray) -> float:
    centered = values - np.mean(values)
    return float(np.sqrt(np.mean(centered * centered)))


def frequency_from_rising_crossings(time: np.ndarray, values: np.ndarray) -> float:
    centered = values - np.mean(values)
    indices = np.flatnonzero((centered[:-1] <= 0) & (centered[1:] > 0))
    if indices.size < 3:
        return math.nan
    crossings = []
    for index in indices:
        fraction = -centered[index] / (centered[index + 1] - centered[index])
        crossings.append(time[index] + fraction * (time[index + 1] - time[index]))
    periods = np.diff(crossings)
    return float(1.0 / np.mean(periods))


def window(data: np.ndarray, start: float, stop: float) -> np.ndarray:
    return data[(data[:, 0] >= start) & (data[:, 0] < stop)]


def main_metrics(data: np.ndarray, supply_v: float) -> dict[str, float]:
    idx = {name: number + 1 for number, (name, _) in enumerate(TRACES)}
    rx = window(data, 0.030, 0.045)
    muted = window(data, 0.080, 0.095)
    cw = window(data, 0.135, 0.170)
    recovered = window(data, 0.225, 0.245)
    rx_in = rms(rx[:, idx["input"]])
    rx_out = rms(rx[:, idx["output"]])
    mute_out = rms(muted[:, idx["output"]])
    cw_out = rms(cw[:, idx["output"]])
    recovered_out = rms(recovered[:, idx["output"]])

    # One-cycle sliding RMS provides an easily interpreted recovery threshold.
    time = data[:, 0]
    output = data[:, idx["output"]]
    samples = max(3, int(round((1.0 / INPUT_HZ) / np.median(np.diff(time)))))
    kernel = np.ones(samples) / samples
    mean = np.convolve(output, kernel, mode="same")
    mean_sq = np.convolve(output * output, kernel, mode="same")
    envelope = np.sqrt(np.maximum(mean_sq - mean * mean, 0))
    after_edge = np.flatnonzero(time >= TX_END_S)
    below = after_edge[envelope[after_edge] <= 0.5 * rx_out]
    if below.size:
        # The CW waveform first decays through the receive-audio level.  Only
        # after that decay do we look for the received 1 kHz signal returning.
        eligible = np.flatnonzero(
            (np.arange(time.size) > below[0]) & (envelope >= 0.9 * rx_out)
        )
    else:
        eligible = np.array([], dtype=int)
    recovery_delay = float(time[eligible[0]] - TX_END_S) if eligible.size else math.nan

    return {
        "supply_v": supply_v,
        "speaker_ohm": SPEAKER_OHM,
        "input_frequency_hz": INPUT_HZ,
        "input_v_peak": INPUT_V_PEAK,
        "receive_input_v_rms": rx_in,
        "receive_output_v_rms": rx_out,
        "receive_voltage_gain": rx_out / rx_in,
        "receive_speaker_power_w": rx_out * rx_out / SPEAKER_OHM,
        "receive_lm380_output_dc_v": float(np.mean(rx[:, idx["lm380_output"]])),
        "muted_output_v_rms": mute_out,
        "mute_attenuation_db": 20 * math.log10(rx_out / max(mute_out, 1e-30)),
        "cw_sidetone_output_v_rms": cw_out,
        "cw_sidetone_power_w": cw_out * cw_out / SPEAKER_OHM,
        "cw_sidetone_frequency_hz": frequency_from_rising_crossings(
            cw[:, 0], cw[:, idx["output"]]
        ),
        "cw_lm380_output_dc_v": float(np.mean(cw[:, idx["lm380_output"]])),
        "recovered_output_v_rms": recovered_out,
        "audio_recovery_90_percent_s": recovery_delay,
        "time_step_s": TIME_STEP_S,
    }


def control_sweeps(base: str, supply_v: float) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    idx = {name: number + 1 for number, (name, _) in enumerate(TRACES)}
    for position in (0.10, 0.50, 0.90):
        data = run_case(base, supply_v, f"pitch-{position:.2f}".replace(".", "p"), 0.5, position, False)
        settled = window(data, 0.060, 0.110)
        rows.append({
            "sweep": "pitch",
            "position": position,
            "frequency_hz": frequency_from_rising_crossings(
                settled[:, 0], settled[:, idx["output"]]
            ),
            "output_v_rms": rms(settled[:, idx["output"]]),
            "speaker_power_w": rms(settled[:, idx["output"]]) ** 2 / SPEAKER_OHM,
        })
    for position in (0.10, 0.50, 0.90):
        data = run_case(base, supply_v, f"level-{position:.2f}".replace(".", "p"), position, 0.5, False)
        settled = window(data, 0.060, 0.110)
        rows.append({
            "sweep": "level",
            "position": position,
            "frequency_hz": frequency_from_rising_crossings(
                settled[:, 0], settled[:, idx["output"]]
            ),
            "output_v_rms": rms(settled[:, idx["output"]]),
            "speaker_power_w": rms(settled[:, idx["output"]]) ** 2 / SPEAKER_OHM,
        })
    return rows


def write_main_csv(data: np.ndarray) -> None:
    names = ["time_s", *(name for name, _ in TRACES)]
    stride = max(1, int(round(20e-6 / np.median(np.diff(data[:, 0])))))
    with (DATA_DIR / "80274-operation-timeline.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(names)
        writer.writerows(data[::stride])


def write_dict_csv(path: Path, rows: list[dict[str, float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_plots(data: np.ndarray, sweep_rows: list[dict[str, float]]) -> None:
    idx = {name: number + 1 for number, (name, _) in enumerate(TRACES)}
    time_ms = data[:, 0] * 1e3
    fig, axes = plt.subplots(4, 1, figsize=(11, 9), sharex=True)
    axes[0].plot(time_ms, data[:, idx["input"]] * 1e3, label="Board INPUT")
    axes[0].set_ylabel("Input (mV)")
    axes[1].plot(time_ms, data[:, idx["t"]], label="T")
    axes[1].plot(time_ms, data[:, idx["sidetone"]], label="SIDETONE")
    axes[1].set_ylabel("Control (V)")
    axes[1].legend(loc="upper right")
    axes[2].plot(time_ms, data[:, idx["mute_node"]], label="Q74-1 collector / mute node")
    axes[2].plot(time_ms, data[:, idx["lm380_input"]], label="LM380 input")
    axes[2].set_ylabel("Internal (V)")
    axes[2].legend(loc="upper right")
    axes[3].plot(time_ms, data[:, idx["output"]], label="Board OUTPUT into 8 ohms")
    axes[3].set_ylabel("Output (V)")
    axes[3].set_xlabel("Time (ms)")
    for boundary, label in ((RX_END_S, "voice TX"), (CW_START_S, "CW sidetone"), (TX_END_S, "receive")):
        for axis in axes:
            axis.axvline(boundary * 1e3, color="black", linestyle="--", linewidth=0.8)
        axes[3].text(boundary * 1e3 + 1, 0.92, label, transform=axes[3].get_xaxis_transform(), fontsize=8)
    for axis in axes:
        axis.grid(True, alpha=0.25)
    fig.suptitle("80274 receive audio, transmit muting, and CW sidetone")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "80274-operating-states.png", dpi=180)
    plt.close(fig)

    pitch = [row for row in sweep_rows if row["sweep"] == "pitch"]
    level = [row for row in sweep_rows if row["sweep"] == "level"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    axes[0].plot([row["position"] for row in pitch], [row["frequency_hz"] for row in pitch], marker="o")
    axes[0].set_xlabel("R74-7 normalized position")
    axes[0].set_ylabel("Sidetone frequency (Hz)")
    axes[0].set_title("PITCH control")
    axes[1].plot([row["position"] for row in level], [row["output_v_rms"] for row in level], marker="o")
    axes[1].set_xlabel("R74-5 normalized position")
    axes[1].set_ylabel("8 ohm load voltage (V RMS)")
    axes[1].set_title("LEVEL control")
    for axis in axes:
        axis.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "80274-sidetone-controls.png", dpi=180)
    plt.close(fig)


def write_manifest() -> None:
    rows = (
        ("README.md", "Method, results, assessment, limitations, and bench proposal"),
        ("data/80274-operation-timeline.csv", "Downsampled receive/mute/sidetone timeline"),
        ("data/80274-operation-summary.csv", "Principal numerical results"),
        ("data/80274-sidetone-controls.csv", "R74-5 level and R74-7 pitch checks"),
        ("figures/80274-operating-states.png", "Board operating-state waveform plot"),
        ("figures/80274-sidetone-controls.png", "Sidetone control trends"),
    )
    with (STUDY_DIR / "manifest.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("path", "description"))
        writer.writerows(rows)


def main() -> None:
    supply_v = live_supply_voltage()
    base = export_netlist()
    main_data = run_case(base, supply_v, "80274-operating-states", 0.5, 0.5, True)
    metrics = main_metrics(main_data, supply_v)
    sweep_rows = control_sweeps(base, supply_v)
    write_main_csv(main_data)
    write_dict_csv(
        DATA_DIR / "80274-operation-summary.csv",
        [{"metric": key, "value": value} for key, value in metrics.items()],
    )
    write_dict_csv(DATA_DIR / "80274-sidetone-controls.csv", sweep_rows)
    make_plots(main_data, sweep_rows)
    write_manifest()
    for key, value in metrics.items():
        print(f"{key}={value}")
    for row in sweep_rows:
        print(row)


if __name__ == "__main__":
    main()
