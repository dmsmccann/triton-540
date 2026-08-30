#!/usr/bin/env python3
"""Generate the 80166 DEFEAT gain-reduction study.

The manual states that energizing the crystal calibrator drops this stage's
gain by about 25 dB.  That happens because a TTL gate on the calibrator board
pulls the DEFEAT line, and with it Q1's gate 2, toward ground.  This runner
steps the DEFEAT supply from its normal 3.9 V down to 0 V and records both the
gain at the alignment frequency and the shape of the whole passband, so the
documented figure can be checked and the mechanism can be seen.

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
STUDY_DIR = SPICE_DIR / "studies" / "80166" / "defeat-gain-control"
DATA_DIR = STUDY_DIR / "data"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = SPICE_DIR / "generated" / "80166-defeat-gain"
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

DEFEAT_SUPPLY = "V66-1"
RF_GAIN_SUPPLY = "V66-2"
NORMAL_DEFEAT_V = 3.9
NORMAL_SUPPLY_V = "12"

# Dense near the bottom, where the gate-2 channel is closing and the gain is
# expected to move fastest.
DEFEAT_VOLTS = (
    3.9,
    3.5,
    3.0,
    2.5,
    2.0,
    1.75,
    1.5,
    1.25,
    1.0,
    0.875,
    0.75,
    0.625,
    0.5,
    0.375,
    0.25,
    0.125,
    0.0,
)

# The two curves the document overlays, plus one midpoint that shows the
# transition is gradual rather than a step.
RETAINED_RESPONSES = (3.9, 1.0, 0.0)


def tag_for(defeat_v: float) -> str:
    return f"defeat-{defeat_v:.3f}".replace(".", "p")


def ac_arguments(defeat_v: float) -> SimpleNamespace:
    return SimpleNamespace(
        s4_pos=S4_POS,
        l_rack=L_RACK,
        points_per_decade=POINTS_PER_DECADE,
        start=SWEEP_START,
        stop=SWEEP_STOP,
        set_component=[f"C19={C19}"],
        set_source=[
            f"{RF_GAIN_SUPPLY}={NORMAL_SUPPLY_V}",
            f"{DEFEAT_SUPPLY}={defeat_v:g}",
        ],
        set_subckt_param=[],
        c99_node=None,
        c99_value="10n",
    )


def operating_point_netlist(defeat_v: float) -> str:
    """The same state, but asking for DC bias instead of a frequency sweep."""

    text = core.build_netlist(ac_arguments(defeat_v), BASE_NETLIST)
    return core.set_analysis(text, ".op")


def read_operating_point(raw_path: Path) -> dict[str, float]:
    names, rows = ngspice_raw.parse_ascii_raw(raw_path)
    indices = {name: index for index, name in enumerate(names)}
    gate1 = rows[0][indices[core.resolve_vector(names, "q1_gate1")]].real
    source = rows[0][indices[core.resolve_vector(names, "q1_source")]].real
    drain = rows[0][indices[core.resolve_vector(names, "q1_drain")]].real
    return {
        "q1_gate1_v": gate1,
        "q1_source_v": source,
        "q1_drain_v": drain,
        "v_gs_v": gate1 - source,
        # R66-6 carries the whole drain current, so the voltage across it is
        # the only current measurement the board offers without breaking a
        # connection.
        "drain_current_ma": 1000.0 * source / 470.0,
    }


def read_response(path: Path) -> tuple[list[float], list[float]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream, delimiter=";"))
    frequencies = [float(row["frequency"]) for row in rows]
    gains = [float(row["user0 (gain)"]) for row in rows]
    return frequencies, gains


def run_study() -> list[dict[str, float]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, float]] = []
    for defeat_v in DEFEAT_VOLTS:
        tag = tag_for(defeat_v)

        raw_path = core.run_ngspice(
            core.build_netlist(ac_arguments(defeat_v), BASE_NETLIST),
            tag,
            RUN_DIR,
        )
        generated_csv = RUN_DIR / f"{tag}.csv"
        core.write_csv_and_summary(raw_path, generated_csv)
        frequencies, gains = read_response(generated_csv)

        bias_raw = core.run_ngspice(
            operating_point_netlist(defeat_v), f"{tag}-op", RUN_DIR
        )
        bias = read_operating_point(bias_raw)

        peak_hz, peak_db = ngspice_raw.peak_of(frequencies, gains)
        lower, upper, width = ngspice_raw.minus_3db_bandwidth(frequencies, gains)
        summary.append(
            {
                "defeat_v": defeat_v,
                "gain_at_3p5_db": ngspice_raw.interpolate_at(
                    frequencies, gains, TARGET_HZ
                ),
                "peak_hz": peak_hz,
                "peak_db": peak_db,
                "bandwidth_3db_hz": width if width is not None else float("nan"),
                "lower_3db_hz": lower if lower is not None else float("nan"),
                "upper_3db_hz": upper if upper is not None else float("nan"),
                "grid_step_hz": ngspice_raw.grid_step_at(frequencies, TARGET_HZ),
                **bias,
            }
        )

        if defeat_v in RETAINED_RESPONSES:
            destination = DATA_DIR / f"response-{tag}.csv"
            destination.write_bytes(generated_csv.read_bytes())

    summary_path = DATA_DIR / "defeat-sweep.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    return summary


def read_summary() -> list[dict[str, float]]:
    with (DATA_DIR / "defeat-sweep.csv").open(
        newline="", encoding="utf-8-sig"
    ) as stream:
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
    summary = read_summary()
    reference = next(
        row for row in summary if abs(row["defeat_v"] - NORMAL_DEFEAT_V) < 1e-9
    )

    figure, (knee, overlay) = plt.subplots(
        2, 1, figsize=(10.5, 8.6), constrained_layout=True
    )

    knee.plot(
        [row["defeat_v"] for row in summary],
        [row["gain_at_3p5_db"] for row in summary],
        color="#c0392b",
        marker="o",
        markersize=4.5,
        linewidth=1.8,
        label="ANT-to-OUT gain at 3.500 MHz",
    )
    knee.axvline(
        NORMAL_DEFEAT_V,
        color="#2c3e50",
        linestyle="--",
        linewidth=1.2,
        label="Normal receive, DEFEAT = 3.9 V",
    )
    knee.axhline(
        reference["gain_at_3p5_db"] - 25.0,
        color="#16a085",
        linestyle=":",
        linewidth=1.6,
        label="25 dB below normal (the manual's figure)",
    )
    knee.set_xlabel("DEFEAT pin voltage (V)")
    knee.set_ylabel("Gain at 3.500 MHz (dB)")
    knee.set_title("Pulling DEFEAT Low Turns the Stage Down")
    knee.grid(True, alpha=0.25)
    knee.legend(loc="lower right")

    colors = {3.9: "#c0392b", 1.0: "#8e44ad", 0.0: "#2980b9"}
    for defeat_v in RETAINED_RESPONSES:
        frequencies, gains = read_response(
            DATA_DIR / f"response-{tag_for(defeat_v)}.csv"
        )
        overlay.plot(
            [value / 1e6 for value in frequencies],
            gains,
            color=colors[defeat_v],
            linewidth=2,
            label=f"DEFEAT = {defeat_v:g} V",
        )
    overlay.axvline(3.5, color="#222222", linestyle="--", linewidth=1.2)
    overlay.set_xlim(3.0, 4.2)
    overlay.set_xlabel("Frequency (MHz)")
    overlay.set_ylabel("ANT-to-OUT voltage gain (dB)")
    overlay.set_title("The Passband Keeps Its Shape and Only Changes Height")
    overlay.grid(True, alpha=0.25)
    overlay.legend()

    figure.savefig(FIGURE_DIR / "defeat-gain.png", dpi=180)
    plt.close(figure)


def main() -> int:
    core.export_base_netlist(BASE_NETLIST)
    summary = run_study()
    plot_study()

    reference = next(
        row for row in summary if abs(row["defeat_v"] - NORMAL_DEFEAT_V) < 1e-9
    )
    for row in summary:
        print(
            f"DEFEAT {row['defeat_v']:5.3f} V  "
            f"gain {row['gain_at_3p5_db']:8.3f} dB  "
            f"change {row['gain_at_3p5_db'] - reference['gain_at_3p5_db']:8.3f} dB  "
            f"Id {row['drain_current_ma']:6.3f} mA  "
            f"BW {row['bandwidth_3db_hz'] / 1e3:7.1f} kHz"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
