#!/usr/bin/env python3
"""Reproduce the 80282 crystal-filter and carrier-alignment study.

The KiCad sheet remains the component/topology source.  This runner exports a
fresh SPICE netlist, asserts the filter parts and board-pin connections, then
builds a pin-level AC fixture around that same lattice.  The eight undocumented
crystals use explicitly fitted engineering parameters from 80282_crystals.lib.
"""

from __future__ import annotations

import csv
import math
import re
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

import ngspice_raw


ROOT = Path(__file__).resolve().parents[2]
KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")
SCHEMATIC = ROOT / "80282_ssb_generator.kicad_sch"
GENERATED = ROOT / "spice" / "generated" / "80282-operation"
STUDY = ROOT / "spice" / "studies" / "80282" / "operation"
DATA = STUDY / "data"
FIGURES = STUDY / "figures"

F_START = 8.996e6
F_STOP = 9.007e6
POINTS = 2201
GRID_HZ = (F_STOP - F_START) / (POINTS - 1)


def run_checked(command: list[str], description: str) -> None:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        print(result.stdout, end="")
        print(result.stderr, end="")
        raise SystemExit(f"{description} failed with exit code {result.returncode}")


def export_and_check() -> None:
    GENERATED.mkdir(parents=True, exist_ok=True)
    exported = GENERATED / "80282-export.cir"
    run_checked(
        [
            str(KICAD_CLI), "sch", "export", "netlist", "--format", "spice",
            "-o", str(exported), str(SCHEMATIC),
        ],
        "KiCad SPICE export",
    )
    text = exported.read_text(encoding="utf-8")
    required = (
        "C82-27 Net-_C82-27-Pad1_ /RX_IF 68pF N220",
        "C82-28 Net-_C82-28-Pad1_ GND 220p",
        "C82-29 Net-_C82-29-Pad1_ Net-_C82-29-Pad2_ 68pF N220",
        "XL2 Net-_C82-29-Pad2_ Net-_C82-29-Pad1_ GND SSB80282_FILTER_L_CT",
        "XL3 /RX_IF Net-_C82-27-Pad1_ GND SSB80282_FILTER_L_CT",
        "R82-26 /Out GND 220",
    )
    missing = [line for line in required if line not in text]
    if missing:
        raise ValueError(f"Fresh KiCad export does not match the filter: {missing}")


def make_netlist(name: str, shift_hz: float = 0.0) -> Path:
    """Write the two-section lattice exactly as connected on the KiCad sheet."""
    low = 9.00095e6 + shift_hz
    high = 9.00245e6 + shift_hz
    model = (ROOT / "spice" / "models" / "80282_crystals.lib").as_posix()
    magnetics = (
        ROOT / "spice" / "models" / "80282_ssb_generator_magnetics.lib"
    ).as_posix()
    netlist = GENERATED / f"80282-filter-{name}.cir"
    raw = GENERATED / f"80282-filter-{name}.raw"
    lines = [
        "80282 eight-crystal lattice at accessible board pins",
        f'.include "{model}"',
        f'.include "{magnetics}"',
        "VTEST SRC 0 AC 1",
        "RSRC SRC OUT 50",
        "R82_26 OUT 0 220",
        "RLOAD RXIF 0 1000",
        "* First balanced lattice section and its center-tapped tuned coil",
        "XL3 RXIF N29 0 SSB80282_FILTER_L_CT",
        "C82_27 RXIF N29 68p",
        f"XY2 N29 0 SSB80282_XTAL PARAMS: FS={low:g}",
        f"XY3 RXIF 0 SSB80282_XTAL PARAMS: FS={high:g}",
        f"XY4 N30 N29 SSB80282_XTAL PARAMS: FS={high:g}",
        f"XY5 N30 RXIF SSB80282_XTAL PARAMS: FS={low:g}",
        "C82_28 N30 0 220p",
        "* Second balanced lattice section and output tuned coil",
        f"XY6 N31 N30 SSB80282_XTAL PARAMS: FS={low:g}",
        f"XY7 N32 N30 SSB80282_XTAL PARAMS: FS={high:g}",
        f"XY8 OUT N31 SSB80282_XTAL PARAMS: FS={high:g}",
        f"XY9 OUT N32 SSB80282_XTAL PARAMS: FS={low:g}",
        "XL2 N32 N31 0 SSB80282_FILTER_L_CT",
        "C82_29 N32 N31 68p",
        f".ac lin {POINTS} {F_START:g} {F_STOP:g}",
        ".options filetype=ascii",
        ".end",
    ]
    netlist.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run_checked(
        [
            str(NGSPICE), "-b", "-D", "ngbehavior=ltpsa",
            "-r", str(raw), "-o", str(GENERATED / f"{name}.log"), str(netlist),
        ],
        f"ngspice {name}",
    )
    return raw


def read_response(raw: Path) -> tuple[np.ndarray, np.ndarray]:
    names, rows = ngspice_raw.parse_ascii_raw(raw)
    indices = {name: index for index, name in enumerate(names)}
    frequency = np.asarray([row[indices["frequency"]].real for row in rows])
    source = np.asarray([row[indices["v(src)"]] for row in rows])
    output = np.asarray([row[indices["v(rxif)"]] for row in rows])
    gain = 20 * np.log10(np.maximum(np.abs(output / source), 1e-15))
    return frequency, gain


def crossing(frequency: np.ndarray, relative: np.ndarray, level: float, side: str) -> float:
    peak = int(np.argmax(relative))
    indexes = range(peak, 0, -1) if side == "low" else range(peak, len(relative) - 1)
    step = -1 if side == "low" else 1
    for index in indexes:
        other = index + step
        if relative[other] <= level < relative[index]:
            x1, x2 = frequency[index], frequency[other]
            y1, y2 = relative[index], relative[other]
            return float(x1 + (level - y1) * (x2 - x1) / (y2 - y1))
    raise ValueError(f"No {side} crossing at {level} dB")


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    export_and_check()
    f, gain = read_response(make_netlist("nominal"))
    shifted_f, shifted_gain = read_response(make_netlist("crystals-plus-250hz", 250.0))
    peak_index = int(np.argmax(gain))
    peak_hz = float(f[peak_index])
    peak_db = float(gain[peak_index])
    relative = gain - peak_db
    low_3 = crossing(f, relative, -3.0, "low")
    high_3 = crossing(f, relative, -3.0, "high")
    low_26 = crossing(f, relative, -26.0, "low")
    high_26 = crossing(f, relative, -26.0, "high")
    cw_hz = low_26 + 750.0
    cw_db = float(np.interp(cw_hz, f, relative))

    with (DATA / "filter-response.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("frequency_hz", "rx_if_db", "relative_db", "shifted_plus_250hz_db"))
        for row in zip(f, gain, relative, shifted_gain):
            writer.writerow(row)

    metrics = [
        ("sweep_grid_hz", GRID_HZ, "calculated from linear sweep"),
        ("peak_frequency_hz", peak_hz, "grid-limited simulated value"),
        ("peak_gain_db", peak_db, "RX IF relative to 1 V source"),
        ("minus3_low_hz", low_3, "interpolated crossing"),
        ("minus3_high_hz", high_3, "interpolated crossing"),
        ("minus3_bandwidth_hz", high_3 - low_3, "model result"),
        ("minus26_low_hz", low_26, "manual alignment skirt level"),
        ("minus26_high_hz", high_26, "manual alignment skirt level"),
        ("cw_marker_hz", cw_hz, "750 Hz above modeled low skirt"),
        ("cw_marker_relative_db", cw_db, "expected to return near passband"),
    ]
    with (DATA / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("measurement", "value", "evidence"))
        writer.writerows(metrics)

    fig, axis = plt.subplots(figsize=(10, 5.8))
    axis.plot((f - 9e6) / 1e3, relative, color="#245c8a", linewidth=1.7)
    axis.axhline(-26, color="#777777", linestyle="--", linewidth=1, label="manual skirt level")
    axis.axvline((low_26 - 9e6) / 1e3, color="#b24a3b", linestyle=":", label="SB-N carrier")
    axis.axvline((cw_hz - 9e6) / 1e3, color="#357a38", linestyle=":", label="CW carrier (+750 Hz)")
    axis.axvline((high_26 - 9e6) / 1e3, color="#7b3f98", linestyle=":", label="SB-R carrier")
    axis.set(xlabel="Frequency offset from 9.000 MHz (kHz)", ylabel="RX IF response relative to peak (dB)", ylim=(-50, 2), title="80282 crystal-filter response and carrier alignment points")
    axis.grid(True, alpha=0.25)
    axis.legend(loc="best")
    fig.tight_layout()
    fig.savefig(FIGURES / "filter-and-carrier-alignment.png", dpi=180)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(10, 5.8))
    axis.plot((f - 9e6) / 1e3, relative, label="fitted nominal crystals")
    axis.plot((shifted_f - 9e6) / 1e3, shifted_gain - np.max(shifted_gain), label="all crystal resonances +250 Hz")
    axis.set(xlabel="Frequency offset from 9.000 MHz (kHz)", ylabel="Response relative to each peak (dB)", ylim=(-45, 2), title="Filter sensitivity to a common crystal-frequency shift")
    axis.grid(True, alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(FIGURES / "crystal-frequency-sensitivity.png", dpi=180)
    plt.close(fig)

    print(f"peak {peak_hz:.0f} Hz; -3 dB bandwidth {high_3-low_3:.0f} Hz")
    print(f"-26 dB skirts {low_26:.0f} Hz to {high_26:.0f} Hz")
    print(f"CW point {cw_hz:.0f} Hz is {cw_db:.2f} dB relative")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
