#!/usr/bin/env python3
"""Generate the 80166 RF GAIN supply study.

The `R` pin is not a rail.  It is a variable DC supply taken from the
front-panel RF GAIN control, and because R4 hangs off the same decoupled node
as the drain feed, turning the knob down lowers the drain supply and gate-1
bias together.  This runner sweeps that supply from 12 V to 0 V and records the
bias the stage settles at and the gain it delivers, so the document can show
both mechanisms working at once on one axis.

The KiCad schematic stays the circuit source; this script only changes
simulation parameters and source values in a generated copy of its netlist.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from types import SimpleNamespace

import ngspice_raw
import run_80166_headless as core


ROOT = Path(__file__).resolve().parents[2]
SPICE_DIR = ROOT / "spice"
STUDY_DIR = SPICE_DIR / "studies" / "80166" / "rf-gain-supply"
DATA_DIR = STUDY_DIR / "data"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = SPICE_DIR / "generated" / "80166-rf-gain"
RUN_DIR = GENERATED_DIR / "runs"
BASE_NETLIST = GENERATED_DIR / "80166_base.net"

# The manual-aligned 3.5 MHz state, from the retained alignment study.
S4_POS = 1
L_RACK = "17.2u"
C19 = "36p"
TARGET_HZ = 3.5e6
SWEEP_START = "3Meg"
SWEEP_STOP = "4.2Meg"
POINTS_PER_DECADE = 10000

RF_GAIN_SUPPLY = "V66-2"
# ngspice cannot name a hyphenated source on a .dc card, so the sweep renames it.
DC_SWEEP_NAME = "VRFGAIN"
DEFEAT_SUPPLY = "V66-1"
NORMAL_DEFEAT_V = "3.9"
FULL_SUPPLY_V = 12.0
SOURCE_RESISTOR_OHM = 470.0

# The DC sweep resolves the bias curves; the AC runs are one per point, so they
# are sampled more coarsely and chosen to bracket the knee.
DC_SWEEP_STEP_V = 0.05
AC_SUPPLY_VOLTS = (
    12.0,
    10.0,
    8.0,
    6.0,
    5.0,
    4.0,
    3.0,
    2.5,
    2.0,
    1.5,
    1.0,
    0.75,
    0.5,
    0.25,
    0.0,
)

# The curves the document overlays.
RETAINED_RESPONSES = (12.0, 6.0, 2.0)


def tag_for(supply_v: float) -> str:
    return f"supply-{supply_v:.2f}".replace(".", "p")


def ac_arguments(supply_v: float) -> SimpleNamespace:
    return SimpleNamespace(
        s4_pos=S4_POS,
        l_rack=L_RACK,
        points_per_decade=POINTS_PER_DECADE,
        start=SWEEP_START,
        stop=SWEEP_STOP,
        set_component=[f"C19={C19}"],
        set_source=[
            f"{RF_GAIN_SUPPLY}={supply_v:g}",
            f"{DEFEAT_SUPPLY}={NORMAL_DEFEAT_V}",
        ],
        set_subckt_param=[],
        c99_node=None,
        c99_value="10n",
    )


def read_response(path: Path) -> tuple[list[float], list[float]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream, delimiter=";"))
    return (
        [float(row["frequency"]) for row in rows],
        [float(row["user0 (gain)"]) for row in rows],
    )


def run_dc_sweep() -> list[dict[str, float]]:
    """One .dc run gives the bias at every supply voltage on a fine grid."""

    text = core.build_netlist(ac_arguments(FULL_SUPPLY_V), BASE_NETLIST)
    text = core.rename_element(text, RF_GAIN_SUPPLY, DC_SWEEP_NAME)
    text = core.set_analysis(
        text, f".dc {DC_SWEEP_NAME} 0 {FULL_SUPPLY_V:g} {DC_SWEEP_STEP_V:g}"
    )
    raw_path = core.run_ngspice(text, "bias-sweep", RUN_DIR)

    names, rows = ngspice_raw.parse_ascii_raw(raw_path)
    indices = {name: index for index, name in enumerate(names)}
    sweep = next(
        (name for name in names if "sweep" in name), names[0]
    )
    supply = core.resolve_vector(names, "r")
    gate1 = core.resolve_vector(names, "q1_gate1")
    source = core.resolve_vector(names, "q1_source")
    drain = core.resolve_vector(names, "q1_drain")

    results: list[dict[str, float]] = []
    for row in rows:
        source_v = row[indices[source]].real
        results.append(
            {
                "supply_v": row[indices[supply]].real
                if supply in indices
                else row[indices[sweep]].real,
                "q1_gate1_v": row[indices[gate1]].real,
                "q1_source_v": source_v,
                "q1_drain_v": row[indices[drain]].real,
                "v_gs_v": row[indices[gate1]].real - source_v,
                # R66-6 carries the entire drain current, so the voltage across
                # it is the only current the board offers without breaking a
                # connection.
                "drain_current_ma": 1000.0 * source_v / SOURCE_RESISTOR_OHM,
            }
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "bias-vs-supply.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    return results


def run_ac_sweep() -> list[dict[str, float]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, float]] = []
    for supply_v in AC_SUPPLY_VOLTS:
        tag = tag_for(supply_v)
        raw_path = core.run_ngspice(
            core.build_netlist(ac_arguments(supply_v), BASE_NETLIST), tag, RUN_DIR
        )
        generated_csv = RUN_DIR / f"{tag}.csv"
        core.write_csv_and_summary(raw_path, generated_csv)
        frequencies, gains = read_response(generated_csv)

        peak_hz, peak_db = ngspice_raw.peak_of(frequencies, gains)
        lower, upper, width = ngspice_raw.minus_3db_bandwidth(frequencies, gains)
        summary.append(
            {
                "supply_v": supply_v,
                "gain_at_3p5_db": ngspice_raw.interpolate_at(
                    frequencies, gains, TARGET_HZ
                ),
                "peak_hz": peak_hz,
                "peak_db": peak_db,
                "bandwidth_3db_hz": width if width is not None else float("nan"),
                "grid_step_hz": ngspice_raw.grid_step_at(frequencies, TARGET_HZ),
            }
        )
        if supply_v in RETAINED_RESPONSES:
            (DATA_DIR / f"response-{tag}.csv").write_bytes(
                generated_csv.read_bytes()
            )

    path = DATA_DIR / "gain-vs-supply.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    return summary


def read_csv(path: Path) -> list[dict[str, float]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return [
            {key: float(value) for key, value in row.items()}
            for row in csv.DictReader(stream)
        ]


def plot_study() -> None:
    os.environ.setdefault(
        "MPLCONFIGDIR", str(SPICE_DIR / "generated" / "matplotlib")
    )
    import matplotlib.pyplot as plt

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    bias = read_csv(DATA_DIR / "bias-vs-supply.csv")
    gain = read_csv(DATA_DIR / "gain-vs-supply.csv")

    figure, (current, bias_axis, gain_axis) = plt.subplots(
        3, 1, figsize=(10.5, 10.0), sharex=True, constrained_layout=True
    )

    current.plot(
        [row["supply_v"] for row in bias],
        [row["drain_current_ma"] for row in bias],
        color="#c0392b",
        linewidth=2,
    )
    current.set_ylabel("Drain current\nthrough R6 (mA)")
    current.set_title("Turning RF GAIN Down Lowers Supply, Bias and Gain Together")
    current.grid(True, alpha=0.25)

    bias_axis.plot(
        [row["supply_v"] for row in bias],
        [row["v_gs_v"] for row in bias],
        color="#8e44ad",
        linewidth=2,
        label="V_GS (gate 1 minus source)",
    )
    bias_axis.plot(
        [row["supply_v"] for row in bias],
        [row["q1_gate1_v"] for row in bias],
        color="#16a085",
        linewidth=1.6,
        linestyle="--",
        label="Gate-1 voltage",
    )
    bias_axis.axhline(0.0, color="#888888", linewidth=0.8)
    bias_axis.set_ylabel("Volts")
    bias_axis.grid(True, alpha=0.25)
    bias_axis.legend(loc="lower right")

    gain_axis.plot(
        [row["supply_v"] for row in gain],
        [row["gain_at_3p5_db"] for row in gain],
        color="#2980b9",
        marker="o",
        markersize=4.5,
        linewidth=1.8,
    )
    gain_axis.axhline(0.0, color="#888888", linewidth=0.8)
    gain_axis.set_xlabel("`R` pin voltage — the stage's supply (V)")
    gain_axis.set_ylabel("ANT-to-OUT gain\nat 3.500 MHz (dB)")
    gain_axis.grid(True, alpha=0.25)

    figure.savefig(FIGURE_DIR / "rf-gain-supply.png", dpi=180)
    plt.close(figure)


def main() -> int:
    core.export_base_netlist(BASE_NETLIST)
    run_dc_sweep()
    summary = run_ac_sweep()
    plot_study()

    reference = summary[0]["gain_at_3p5_db"]
    for row in summary:
        print(
            f"R = {row['supply_v']:5.2f} V  "
            f"gain {row['gain_at_3p5_db']:8.3f} dB  "
            f"change {row['gain_at_3p5_db'] - reference:8.3f} dB  "
            f"peak {row['peak_hz'] / 1e6:.5f} MHz  "
            f"BW {row['bandwidth_3db_hz'] / 1e3:7.1f} kHz"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
