#!/usr/bin/env python3
"""Reproduce the 80287 3.5 MHz receive/transmit operation study.

The KiCad hierarchy is the circuit source of truth.  This runner exports a
fresh netlist, changes only R/T control voltages in generated copies, runs
ngspice, and writes curated measurements and figures.
"""

from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

import run_80166_headless as core


ROOT = Path(__file__).resolve().parents[2]
KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")
SCHEMATIC = ROOT / "triton_540.kicad_sch"
GENERATED = ROOT / "spice" / "generated" / "80287-operation"
STUDY = ROOT / "spice" / "studies" / "80287" / "operation-3p5mhz"
DATA = STUDY / "data"
FIGURES = STUDY / "figures"
BASE = GENERATED / "80287-base.cir"

RX_INPUT_HZ = 3.499e6
IF_HZ = 9.001e6
VFO_HZ = 12.5e6

VECTORS = {
    "rx_input": "v(/rcv3)",
    "rx_vfo": "v(/tx_rx_mixer_80287/rx_vfo)",
    "rx_if": "v(/tx_rx_mixer_80287/rx_9mhz)",
    "tx_if": "v(/tx_rx_mixer_80287/tx_9mhz)",
    "tx_vfo": "v(/tx_rx_mixer_80287/tx_vfo)",
    "tx_out": "v(/tx_rx_mixer_80287/out)",
    "tx_signal_pin1": "v(net-_c87-14-pad2_)",
    "tx_signal_pin4": "v(net-_c87-12-pad1_)",
    "tx_carrier_pin8": "v(net-_u87-2-input_carrier_)",
    "tx_carrier_pin10": "v(net-_u87-2-carrier_input_)",
    "tx_output_pin6": "v(net-_c87-9-pad1_)",
    "tx_output_pin12": "v(net-_l87-2-pad1_)",
    "supply": "v(/+12)",
    "r_control": "v(/tx_rx_mixer_80287/r)",
    "t_control": "v(/tx_rx_mixer_80287/t)",
    "u1_pin1": "v(net-_c87-1-pad2_)",
    "u1_pin2": "v(net-_c87-2-pad1_)",
    "u1_pin3": "v(net-_c87-2-pad2_)",
    "u1_pin4": "v(net-_c87-19-pad1_)",
    "u1_pin5": "v(net-_u87-1-bias_)",
    "u1_pin6": "v(net-_d87-1-k_)",
    "u1_pin8": "v(net-_u87-1-input_carrier_)",
    "u1_pin10": "v(net-_u87-1-carrier_input_)",
    "u1_pin12": "v(net-_c87-5-pad2_)",
    "u1_signal_bias_tap": "v(net-_r87-1-pad2_)",
    "u2_pin1": "v(net-_c87-14-pad2_)",
    "u2_pin2": "v(net-_r87-18-pad1_)",
    "u2_pin3": "v(net-_r87-18-pad2_)",
    "u2_pin4": "v(net-_c87-12-pad1_)",
    "u2_pin5": "v(net-_u87-2-bias_)",
    "u2_pin6": "v(net-_c87-9-pad1_)",
    "u2_pin8": "v(net-_u87-2-input_carrier_)",
    "u2_pin10": "v(net-_u87-2-carrier_input_)",
    "u2_pin12": "v(net-_l87-2-pad1_)",
}


def run_checked(command: list[str], description: str) -> None:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        print(result.stdout, end="")
        print(result.stderr, end="")
        raise SystemExit(f"{description} failed with exit code {result.returncode}")


def export_netlist() -> str:
    GENERATED.mkdir(parents=True, exist_ok=True)
    run_checked(
        [
            str(KICAD_CLI), "sch", "export", "netlist", "--format", "spice",
            "-o", str(BASE), str(SCHEMATIC),
        ],
        "KiCad netlist export",
    )
    text = BASE.read_text(encoding="utf-8")
    required = (
        "V87-3 /RCV3 GND DC 0 SIN( 0 10u 3.499Meg",
        "V87-4 /TX_RX_Mixer_80287/Rx_VFO GND DC 0 SIN( 0 100m 12.5Meg",
        "V87-5 /TX_RX_Mixer_80287/Tx_9MHz GND DC 0 SIN( 0 100m 9.001Meg",
        "V87-6 /TX_RX_Mixer_80287/Tx_VFO GND DC 0 SIN( 0 100m 12.5Meg",
        "XL87-2 ",
        "R87-90 /TX_RX_Mixer_80287/Rx_9MHz GND 10k",
        "R87-91 /TX_RX_Mixer_80287/OUT GND 50",
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise ValueError(f"Fresh KiCad export is missing fixtures: {missing}")
    return text


def set_control(text: str, reference: str, volts: float) -> str:
    pattern = rf"(?m)^({reference}\s+\S+\s+GND\s+DC\s+)\S+\s*$"
    updated, count = re.subn(pattern, rf"\g<1>{volts:g} ", text)
    if count != 1:
        raise ValueError(f"Expected one {reference} control source; found {count}")
    return updated


def run_state(name: str, base: str, r_volts: float, t_volts: float):
    text = set_control(base, "V87-1", r_volts)
    text = set_control(text, "V87-2", t_volts)
    netlist = GENERATED / f"80287-{name}.cir"
    raw = GENERATED / f"80287-{name}.raw"
    log = GENERATED / f"80287-{name}.log"
    netlist.write_text(text, encoding="utf-8")
    run_checked(
        [
            str(NGSPICE), "-b", "-D", "ngbehavior=ltpsa",
            "-r", str(raw), "-o", str(log), str(netlist),
        ],
        f"ngspice {name} run",
    )
    log_text = log.read_text(encoding="utf-8", errors="replace")
    rows = re.search(r"No\. of Data Rows\s*:\s*(\d+)", log_text)
    if not rows or int(rows.group(1)) < 10_000 or "fatal error" in log_text.lower():
        raise ValueError(f"{name} did not complete; see {log}")
    names, values = core.parse_ascii_raw(raw)
    indices = {vector: index for index, vector in enumerate(names)}
    missing = set(VECTORS.values()) - indices.keys()
    if missing:
        raise ValueError(f"{name} raw file lacks vectors: {sorted(missing)}")
    time = np.asarray([row[indices["time"]].real for row in values])
    traces = {
        key: np.asarray([row[indices[vector]].real for row in values])
        for key, vector in VECTORS.items()
    }
    return time, traces


def fit_vpp(time: np.ndarray, values: np.ndarray, frequency_hz: float) -> float:
    selected = time >= time[-1] - 20e-6
    t = time[selected]
    y = values[selected]
    phase = 2 * np.pi * frequency_hz * t
    design = np.column_stack((np.sin(phase), np.cos(phase), np.ones(t.size)))
    coeff, *_ = np.linalg.lstsq(design, y, rcond=None)
    return float(2 * np.hypot(coeff[0], coeff[1]))


def fit_tones_vpp(
    time: np.ndarray, values: np.ndarray, frequencies_hz: tuple[float, ...]
) -> dict[float, float]:
    """Fit several nearby mixer products at once to reduce spectral leakage."""
    selected = time >= time[-1] - 20e-6
    t = time[selected]
    columns = []
    for frequency_hz in frequencies_hz:
        phase = 2 * np.pi * frequency_hz * t
        columns.extend((np.sin(phase), np.cos(phase)))
    columns.append(np.ones(t.size))
    coeff, *_ = np.linalg.lstsq(np.column_stack(columns), values[selected], rcond=None)
    return {
        frequency_hz: float(2 * np.hypot(coeff[2 * index], coeff[2 * index + 1]))
        for index, frequency_hz in enumerate(frequencies_hz)
    }


def dc_mean(time: np.ndarray, values: np.ndarray) -> float:
    return float(np.mean(values[time >= time[-1] - 20e-6]))


def plot_state(name: str, time: np.ndarray, traces: dict[str, np.ndarray]) -> None:
    selected = time >= time[-1] - 2e-6
    t_us = (time[selected] - time[selected][0]) * 1e6
    if name == "receive":
        panels = (("rx_input", "Rx In (V)"), ("rx_vfo", "Rx VFO (V)"), ("rx_if", "Rx 9 MHz output (V)"))
        title = "80287 receive conversion: 3.499 MHz to 9.001 MHz"
    else:
        panels = (("tx_if", "Tx 9 MHz input (V)"), ("tx_vfo", "Tx VFO (V)"), ("tx_out", "OUT into 50 ohms (V)"))
        title = "80287 transmit conversion: 9.001 MHz to 3.499 MHz"
    fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
    for axis, (key, label) in zip(axes, panels):
        axis.plot(t_us, traces[key][selected], linewidth=1)
        axis.set_ylabel(label)
        axis.grid(True, alpha=0.25)
    axes[-1].set_xlabel("Time in final 2 microseconds (µs)")
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(FIGURES / f"80287-{name}-3p5mhz.png", dpi=180)
    plt.close(fig)


def plot_mixing_products(
    name: str, time: np.ndarray, traces: dict[str, np.ndarray]
) -> dict[float, float]:
    if name == "receive":
        frequencies = (RX_INPUT_HZ, IF_HZ, VFO_HZ, VFO_HZ + RX_INPUT_HZ)
        labels = ("RF\n3.499", "diff.\n9.001", "VFO\n12.500", "sum\n15.999")
        products = fit_tones_vpp(time, traces["rx_if"], frequencies)
        title = "Receive mixer output: 12.500 − 3.499 = 9.001 MHz"
        ylabel = "Rx 9 MHz node component (V p-p)"
    else:
        frequencies = (VFO_HZ - IF_HZ, IF_HZ, VFO_HZ, VFO_HZ + IF_HZ)
        labels = ("diff.\n3.499", "IF\n9.001", "VFO\n12.500", "sum\n21.501")
        products = fit_tones_vpp(time, traces["tx_out"], frequencies)
        title = "Transmit mixer output: 12.500 − 9.001 = 3.499 MHz"
        ylabel = "OUT component into 50 ohms (V p-p)"

    values = [max(products[frequency], 1e-12) for frequency in frequencies]
    colors = ["#2f7d32" if index == (1 if name == "receive" else 0) else "#777777"
              for index in range(len(values))]
    fig, axis = plt.subplots(figsize=(9, 5.5))
    bars = axis.bar(labels, values, color=colors)
    axis.set_yscale("log")
    axis.set_ylabel(ylabel)
    axis.set_xlabel("Fitted frequency component (MHz)")
    axis.set_title(title)
    axis.grid(True, axis="y", which="both", alpha=0.25)
    axis.set_ylim(min(values) / 1.5, max(values) * 1.7)
    axis.tick_params(axis="x", labelsize=9)
    for bar, value in zip(bars, values):
        axis.annotate(
            f"{value:.3g} V",
            xy=(bar.get_x() + bar.get_width() / 2, value),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    fig.tight_layout()
    fig.savefig(FIGURES / f"80287-{name}-mixing-products.png", dpi=180)
    plt.close(fig)
    return products


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    base = export_netlist()
    rx_time, rx = run_state("receive", base, 12.8, 0.2)
    tx_time, tx = run_state("transmit", base, 0.6, 10.4)

    rows = [
        ("receive", "supply_dc_v", dc_mean(rx_time, rx["supply"]), 13.28, "saved top-sheet ideal source"),
        ("receive", "r_control_dc_v", dc_mean(rx_time, rx["r_control"]), 12.8, "manual receive state"),
        ("receive", "t_control_dc_v", dc_mean(rx_time, rx["t_control"]), 0.2, "manual receive state"),
        ("receive", "rx_vfo_dc_v", dc_mean(rx_time, rx["rx_vfo"]), 0.05, "manual board terminal"),
        ("receive", "rx_9mhz_dc_v", dc_mean(rx_time, rx["rx_if"]), 0.0, "manual board terminal"),
        ("receive", "tx_9mhz_dc_v", dc_mean(rx_time, rx["tx_if"]), 0.0, "manual board terminal"),
        ("receive", "tx_vfo_dc_v", dc_mean(rx_time, rx["tx_vfo"]), 0.1, "manual board terminal"),
        ("receive", "out_dc_v", dc_mean(rx_time, rx["tx_out"]), 0.0, "manual board terminal"),
        ("receive", "rx_input_vpp", fit_vpp(rx_time, rx["rx_input"], RX_INPUT_HZ), 20e-6, "3.499 MHz"),
        ("receive", "rx_if_9p001mhz_vpp", fit_vpp(rx_time, rx["rx_if"], IF_HZ), float("nan"), "wanted difference product"),
        ("transmit", "supply_dc_v", dc_mean(tx_time, tx["supply"]), 13.28, "saved top-sheet ideal source"),
        ("transmit", "r_control_dc_v", dc_mean(tx_time, tx["r_control"]), 0.6, "manual transmit state"),
        ("transmit", "t_control_dc_v", dc_mean(tx_time, tx["t_control"]), 10.4, "manual transmit state"),
        ("transmit", "rx_vfo_dc_v", dc_mean(tx_time, tx["rx_vfo"]), 0.05, "manual board terminal"),
        ("transmit", "rx_9mhz_dc_v", dc_mean(tx_time, tx["rx_if"]), 0.0, "manual board terminal"),
        ("transmit", "tx_9mhz_dc_v", dc_mean(tx_time, tx["tx_if"]), 0.0, "manual board terminal"),
        ("transmit", "tx_vfo_dc_v", dc_mean(tx_time, tx["tx_vfo"]), 0.1, "manual board terminal"),
        ("transmit", "out_dc_v", dc_mean(tx_time, tx["tx_out"]), 0.0, "manual board terminal"),
        ("transmit", "tx_if_vpp", fit_vpp(tx_time, tx["tx_if"], IF_HZ), 0.2, "9.001 MHz"),
        ("transmit", "tx_signal_pin1_vpp", fit_vpp(tx_time, tx["tx_signal_pin1"], IF_HZ), float("nan"), "MC1496 pin 1 at 9.001 MHz"),
        ("transmit", "tx_signal_pin4_vpp", fit_vpp(tx_time, tx["tx_signal_pin4"], IF_HZ), float("nan"), "MC1496 pin 4 at 9.001 MHz"),
        ("transmit", "tx_carrier_pin8_vpp", fit_vpp(tx_time, tx["tx_carrier_pin8"], VFO_HZ), float("nan"), "MC1496 pin 8 at 12.5 MHz"),
        ("transmit", "tx_carrier_pin10_vpp", fit_vpp(tx_time, tx["tx_carrier_pin10"], VFO_HZ), float("nan"), "MC1496 pin 10 at 12.5 MHz"),
        ("transmit", "tx_output_differential_3p499mhz_vpp", fit_vpp(tx_time, tx["tx_output_pin6"] - tx["tx_output_pin12"], RX_INPUT_HZ), float("nan"), "MC1496 differential collectors"),
        ("transmit", "tx_out_3p499mhz_vpp", fit_vpp(tx_time, tx["tx_out"], RX_INPUT_HZ), float("nan"), "wanted difference product into 50 ohms"),
    ]
    plot_state("receive", rx_time, rx)
    plot_state("transmit", tx_time, tx)
    rx_products = plot_mixing_products("receive", rx_time, rx)
    tx_products = plot_mixing_products("transmit", tx_time, tx)
    for frequency, value in rx_products.items():
        rows.append(("receive", f"rx_if_{frequency / 1e6:.3f}mhz_vpp", value, float("nan"), "simultaneous product fit"))
    for frequency, value in tx_products.items():
        rows.append(("transmit", f"tx_out_{frequency / 1e6:.3f}mhz_vpp", value, float("nan"), "simultaneous product fit"))

    # Rewrite after appending the product-fit rows used by the new figures.
    with (DATA / "80287-3p5mhz-measurements.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("state", "measurement", "simulated_value", "applied_or_expected", "note"))
        writer.writerows(rows)
    for state, measurement, value, *_ in rows:
        print(f"{state:8s} {measurement:30s} {value:.9g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
