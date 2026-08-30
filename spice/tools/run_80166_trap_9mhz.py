#!/usr/bin/env python3
"""Generate the 80166 9 MHz trap study.

T1 and C7 sit in the antenna lead and remove signals on the receiver's own
9 MHz intermediate frequency, which would otherwise walk into the IF strip
without ever being mixed.  Nothing in the board document has modelled them.
This runner sweeps 1-30 MHz on the 7 MHz band state, moves C7 across its
documented 5-60 pF range to show the null moving, and degrades the trap
secondary's Q to show what a lossy T1 looks like.

Every notch measurement is referenced to a companion run with the transformer
coupling removed, so "depth" means depth below the response the same board
would have with no trap action at all, rather than depth below an eyeballed
neighbouring point.

The KiCad schematic stays the circuit source; this script only changes
simulation parameters and component values in a generated copy of its netlist.
"""

from __future__ import annotations

import csv
import math
import os
from pathlib import Path
from types import SimpleNamespace

import ngspice_raw
import run_80166_headless as core


ROOT = Path(__file__).resolve().parents[2]
SPICE_DIR = ROOT / "spice"
STUDY_DIR = SPICE_DIR / "studies" / "80166" / "trap-9mhz"
DATA_DIR = STUDY_DIR / "data"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = SPICE_DIR / "generated" / "80166-trap"
RUN_DIR = GENERATED_DIR / "runs"
BASE_NETLIST = GENERATED_DIR / "80166_base.net"

TRAP = "XT66-1"
TRIMMER = "C66-7"
IF_HZ = 9.0e6

# The manual aligns the trap on the 7 MHz band position, so that is the state
# the study runs in.  Values come from the retained alignment study.
S4_POS = 2
L_RACK = "3.43u"
TRIMMER_L2 = "C17=68p"
# Wide enough to hold every null the 5-60 pF trimmer can produce, the peak that
# sits beside each one, and half a megahertz of plain response either side for
# the depth comparison.  Widening it further only makes the retained CSVs larger.
SWEEP_START = "3Meg"
SWEEP_STOP = "20Meg"
# The band-position comparison only needs the value at 9.000 MHz.
BAND_SWEEP_START = "8Meg"
BAND_SWEEP_STOP = "10Meg"
POINTS_PER_DECADE = 20000

# C7 is a 5-60 pF trimmer.  20 pF is the model's own starting value and puts
# the null on 9 MHz.
C7_PICOFARADS = (5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0)
ALIGNED_C7_PF = 20.0

# QS is the trap secondary's unloaded Q.  80 is the model default; 5 is a trap
# whose coil has gone lossy.
TRAP_Q = (80.0, 40.0, 20.0, 10.0, 5.0)
DEFAULT_TRAP_Q = 80.0

# From the 80166_T1_9MHZ model: secondary inductance and the stray
# capacitance that sits across it beside C7.
TRAP_SECONDARY_H = 12.5e-6
TRAP_STRAY_PF = 5.0
# Half-width of the window the null is looked for in, as a frequency ratio.
NULL_SEARCH_SPAN = 1.15
# How far either side of the null a bench sweep would read the response.
NEIGHBOUR_OFFSET_HZ = 500e3
# Below this, a null is too shallow to find by ear on a real receiver.
USABLE_NULL_DB = 6.0

# Coupling low enough that the trap does nothing, while the primary winding
# stays in the antenna path exactly as before.  This is the baseline every
# notch depth is measured against.
NO_TRAP_COUPLING = "1e-9"

# Every band position, to show why the manual aligns the trap on 7 MHz.
BAND_STATES = (
    SimpleNamespace(key="3p5", label="3.5 MHz", s4_pos=1, l_rack="17.2u", trimmer="C19=36p"),
    SimpleNamespace(key="7p0", label="7 MHz", s4_pos=2, l_rack="3.43u", trimmer="C17=68p"),
    SimpleNamespace(key="14p2", label="14 MHz", s4_pos=3, l_rack="2.84u", trimmer="C16=47.2p"),
    SimpleNamespace(key="21p2", label="21 MHz", s4_pos=4, l_rack="2.06u", trimmer="C15=16.94p"),
    SimpleNamespace(key="29p0", label="28 MHz", s4_pos=5, l_rack="1.4253u", trimmer="C13=5.787p"),
)


def ac_arguments(
    c7_pf: float,
    trap_q: float,
    coupling: str | None = None,
    state: SimpleNamespace | None = None,
) -> SimpleNamespace:
    trap_params = [f"QS={trap_q:g}"]
    if coupling is not None:
        trap_params.append(f"KTRAP={coupling}")
    return SimpleNamespace(
        s4_pos=state.s4_pos if state else S4_POS,
        l_rack=state.l_rack if state else L_RACK,
        points_per_decade=POINTS_PER_DECADE,
        start=SWEEP_START,
        stop=SWEEP_STOP,
        set_component=[state.trimmer if state else TRIMMER_L2, f"{TRIMMER}={c7_pf:g}p"],
        set_source=["V66-2=12", "V66-1=3.9"],
        set_subckt_param=[f"{TRAP}=" + " ".join(trap_params)],
        c99_node=None,
        c99_value="10n",
    )


def sweep(tag: str, arguments: SimpleNamespace) -> tuple[list[float], list[float]]:
    raw_path = core.run_ngspice(
        core.build_netlist(arguments, BASE_NETLIST), tag, RUN_DIR
    )
    generated_csv = RUN_DIR / f"{tag}.csv"
    core.write_csv_and_summary(raw_path, generated_csv)
    with generated_csv.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream, delimiter=";"))
    return (
        [float(row["frequency"]) for row in rows],
        [float(row["user0 (gain)"]) for row in rows],
    )


def trap_resonance_hz(c7_pf: float) -> float:
    """Where the trap secondary resonates, from the model library's own values.

    ``80166_T1_9MHZ`` gives the secondary LS = 12.5 uH and a stray CPS = 5 pF
    across it, and C7 adds to that stray.
    """

    capacitance = (c7_pf + TRAP_STRAY_PF) * 1e-12
    return 1.0 / (2.0 * math.pi * math.sqrt(TRAP_SECONDARY_H * capacitance))


def notch_measurements(
    frequencies: list[float],
    with_trap: list[float],
    without_trap: list[float],
    c7_pf: float,
) -> dict[str, float]:
    """Locate the trap's null and measure how deep and how narrow it is.

    ``attenuation`` is what the trap alone takes out: the response with the
    transformer coupled, subtracted from a companion run with the coupling
    removed.  A null is a local maximum of that curve, and it is looked for
    only inside a window around where the trap can physically resonate.

    Both restrictions are needed.  On the 7 MHz band position the front end has
    a very sharp 40 dB peak of its own near 7.2 MHz; inserting the trap shifts
    that peak slightly, and the shift alone puts a 10 dB feature into the
    attenuation curve that is not a null.  Requiring a local maximum rejects
    the shoulder of that feature, and the window - more than a hundred times
    wider than the null itself - keeps it out of range in the first place.

    When there is no local maximum at all, the trap has stopped producing a
    null on this band position.  That is reported as such rather than as a
    frequency, and the attenuation at the trap's predicted frequency is given
    instead so the row still carries a number.
    """

    centre = trap_resonance_hz(c7_pf)
    low, high = centre / NULL_SEARCH_SPAN, centre * NULL_SEARCH_SPAN
    attenuation = [
        untrapped - trapped
        for trapped, untrapped in zip(with_trap, without_trap)
    ]

    candidates = [
        index
        for index in range(1, len(attenuation) - 1)
        if low <= frequencies[index] <= high
        and attenuation[index] >= attenuation[index - 1]
        and attenuation[index] > attenuation[index + 1]
    ]
    if not candidates:
        return {
            "predicted_null_hz": centre,
            "null_hz": float("nan"),
            "depth_vs_no_trap_db": ngspice_raw.interpolate_at(
                frequencies, attenuation, centre
            ),
            "depth_vs_neighbours_db": float("nan"),
            "width_3db_hz": float("nan"),
            "gain_at_null_db": float("nan"),
            "attenuation_at_9mhz_db": ngspice_raw.interpolate_at(
                frequencies, attenuation, IF_HZ
            ),
            "null_usable": 0.0,
            "grid_step_hz": ngspice_raw.grid_step_at(frequencies, centre),
        }

    null_index = max(candidates, key=lambda index: attenuation[index])
    null_hz = frequencies[null_index]
    depth_db = attenuation[null_index]

    lower = ngspice_raw.crossing_below(
        frequencies, attenuation, null_index, -1, depth_db - 3.0
    )
    upper = ngspice_raw.crossing_below(
        frequencies, attenuation, null_index, +1, depth_db - 3.0
    )
    width = None if lower is None or upper is None else upper - lower

    # What a bench sweep reads: the null against the response half a megahertz
    # either side of it, which is well outside a null this narrow.
    neighbours = [
        ngspice_raw.interpolate_at(frequencies, with_trap, null_hz + offset)
        for offset in (-NEIGHBOUR_OFFSET_HZ, NEIGHBOUR_OFFSET_HZ)
    ]
    return {
        "predicted_null_hz": centre,
        "null_hz": null_hz,
        "depth_vs_no_trap_db": depth_db,
        "depth_vs_neighbours_db": sum(neighbours) / len(neighbours)
        - with_trap[null_index],
        "width_3db_hz": width if width is not None else float("nan"),
        "gain_at_null_db": with_trap[null_index],
        "attenuation_at_9mhz_db": ngspice_raw.interpolate_at(
            frequencies, attenuation, IF_HZ
        ),
        "null_usable": 1.0 if depth_db >= USABLE_NULL_DB else 0.0,
        "grid_step_hz": ngspice_raw.grid_step_at(frequencies, null_hz),
    }


def write_curve(path: Path, frequencies: list[float], gains: list[float]) -> None:
    """Retain one response curve.

    Frequencies are written to the nearest hertz and gains to four decimal
    places.  The sweep grid is a kilohertz wide here and the gains are model
    outputs, so nothing below that is meaningful, and the rounding keeps the
    retained files a manageable size.
    """

    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["frequency_hz", "ant_to_out_db"])
        writer.writerows(
            (f"{frequency:.0f}", f"{gain:.4f}")
            for frequency, gain in zip(frequencies, gains)
        )


def run_study() -> None:
    """Produce every retained response curve.  Measurement is a separate step.

    Keeping the two apart means the numbers in the summary tables can be
    recomputed from the retained CSVs without re-running the simulator.
    """

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # One baseline per trap-Q setting, because the secondary's loss resistance
    # is present in the model whether or not the winding is coupled, and the
    # comparison has to isolate the coupling alone.
    for trap_q in TRAP_Q:
        write_curve(
            DATA_DIR / f"no-trap-q{trap_q:g}.csv",
            *sweep(
                f"baseline-q{trap_q:g}",
                ac_arguments(ALIGNED_C7_PF, trap_q, coupling=NO_TRAP_COUPLING),
            ),
        )

    for c7_pf in C7_PICOFARADS:
        write_curve(
            DATA_DIR / f"c7-{c7_pf:g}p.csv",
            *sweep(f"trap-c7-{c7_pf:g}p", ac_arguments(c7_pf, DEFAULT_TRAP_Q)),
        )

    for trap_q in TRAP_Q:
        if trap_q == DEFAULT_TRAP_Q:
            # Identical to the aligned C7 run; copy rather than repeat it.
            source = DATA_DIR / f"c7-{ALIGNED_C7_PF:g}p.csv"
            (DATA_DIR / f"trap-q{trap_q:g}.csv").write_bytes(source.read_bytes())
            continue
        write_curve(
            DATA_DIR / f"trap-q{trap_q:g}.csv",
            *sweep(f"trap-q{trap_q:g}", ac_arguments(ALIGNED_C7_PF, trap_q)),
        )

    # Why the manual aligns the trap on the 7 MHz band position: only there does
    # the front end still pass enough 9 MHz for the null to be audible.  A
    # narrow sweep is enough, because only the value at 9.000 MHz is wanted.
    for state in BAND_STATES:
        for suffix, coupling in (("", NO_TRAP_COUPLING), ("-trapped", None)):
            arguments = ac_arguments(
                ALIGNED_C7_PF, DEFAULT_TRAP_Q, coupling=coupling, state=state
            )
            arguments.start, arguments.stop = BAND_SWEEP_START, BAND_SWEEP_STOP
            write_curve(
                DATA_DIR / f"band-{state.key}{suffix}.csv",
                *sweep(f"band-{state.key}{suffix}", arguments),
            )


def measure_study() -> tuple[
    list[dict[str, float]], list[dict[str, float]], list[dict[str, object]]
]:
    """Measure every retained curve and write the three summary tables."""

    baseline_frequencies, default_baseline = read_curve(
        DATA_DIR / f"no-trap-q{DEFAULT_TRAP_Q:g}.csv"
    )

    c7_rows: list[dict[str, float]] = []
    for c7_pf in C7_PICOFARADS:
        frequencies, gains = read_curve(DATA_DIR / f"c7-{c7_pf:g}p.csv")
        c7_rows.append(
            {
                "c7_pf": c7_pf,
                **notch_measurements(
                    frequencies, gains, default_baseline, c7_pf
                ),
            }
        )

    q_rows: list[dict[str, float]] = []
    for trap_q in TRAP_Q:
        frequencies, gains = read_curve(DATA_DIR / f"trap-q{trap_q:g}.csv")
        _, baseline = read_curve(DATA_DIR / f"no-trap-q{trap_q:g}.csv")
        q_rows.append(
            {
                "trap_q": trap_q,
                **notch_measurements(
                    frequencies, gains, baseline, ALIGNED_C7_PF
                ),
            }
        )

    band_rows: list[dict[str, object]] = []
    for state in BAND_STATES:
        frequencies, untrapped = read_curve(DATA_DIR / f"band-{state.key}.csv")
        _, trapped = read_curve(DATA_DIR / f"band-{state.key}-trapped.csv")
        no_trap_db = ngspice_raw.interpolate_at(frequencies, untrapped, IF_HZ)
        with_trap_db = ngspice_raw.interpolate_at(frequencies, trapped, IF_HZ)
        band_rows.append(
            {
                "band": state.label,
                "gain_at_9mhz_no_trap_db": no_trap_db,
                "gain_at_9mhz_with_trap_db": with_trap_db,
                "attenuation_at_9mhz_db": no_trap_db - with_trap_db,
            }
        )

    for rows, name in (
        (c7_rows, "notch-vs-c7.csv"),
        (q_rows, "notch-vs-trap-q.csv"),
        (band_rows, "band-response-at-9mhz.csv"),
    ):
        path = DATA_DIR / name
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return c7_rows, q_rows, band_rows


def read_curve(path: Path) -> tuple[list[float], list[float]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    return (
        [float(row["frequency_hz"]) for row in rows],
        [float(row["ant_to_out_db"]) for row in rows],
    )


def read_summary(name: str) -> list[dict[str, object]]:
    with (DATA_DIR / name).open(newline="", encoding="utf-8-sig") as stream:
        rows: list[dict[str, object]] = []
        for row in csv.DictReader(stream):
            rows.append(
                {
                    key: value if key == "band" else float(value)
                    for key, value in row.items()
                }
            )
        return rows


def plot_study() -> None:
    os.environ.setdefault(
        "MPLCONFIGDIR", str(SPICE_DIR / "generated" / "matplotlib")
    )
    import matplotlib.pyplot as plt

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    # Figure 66-9: the null moves with C7.
    figure, (curves, centres) = plt.subplots(
        2, 1, figsize=(10.5, 8.8), constrained_layout=True
    )
    colormap = plt.get_cmap("viridis")
    for index, c7_pf in enumerate(C7_PICOFARADS):
        frequencies, gains = read_curve(DATA_DIR / f"c7-{c7_pf:g}p.csv")
        curves.plot(
            [value / 1e6 for value in frequencies],
            gains,
            color=colormap(index / max(len(C7_PICOFARADS) - 1, 1)),
            linewidth=1.7,
            label=f"C7 = {c7_pf:g} pF",
        )
    frequencies, baseline = read_curve(DATA_DIR / f"no-trap-q{DEFAULT_TRAP_Q:g}.csv")
    curves.plot(
        [value / 1e6 for value in frequencies],
        baseline,
        color="#888888",
        linewidth=1.4,
        linestyle="--",
        label="Trap coupling removed",
    )
    curves.axvline(9.0, color="#c0392b", linestyle=":", linewidth=1.6)
    curves.set_xlim(4.0, 18.0)
    curves.set_xlabel("Frequency (MHz)")
    curves.set_ylabel("ANT-to-OUT voltage gain (dB)")
    curves.set_title("Tuning C7 Moves the Trap Null, 7 MHz Band Position")
    curves.grid(True, alpha=0.25)
    curves.legend(ncol=2, fontsize=8)

    c7_rows = read_summary("notch-vs-c7.csv")
    centres.plot(
        [row["c7_pf"] for row in c7_rows],
        [row["null_hz"] / 1e6 for row in c7_rows],
        color="#2980b9",
        marker="o",
        markersize=5,
        linewidth=1.8,
    )
    centres.axhline(
        9.0, color="#c0392b", linestyle=":", linewidth=1.6, label="9 MHz IF"
    )
    centres.set_xlabel("C7 setting (pF)")
    centres.set_ylabel("Null centre frequency (MHz)")
    centres.grid(True, alpha=0.25)
    centres.legend()
    figure.savefig(FIGURE_DIR / "notch-vs-c7.png", dpi=180)
    plt.close(figure)

    # Figure 66-10: a lossy trap keeps its frequency and loses its depth.
    figure, (curves, depths) = plt.subplots(
        2, 1, figsize=(10.5, 8.8), constrained_layout=True
    )
    colormap = plt.get_cmap("plasma")
    for index, trap_q in enumerate(TRAP_Q):
        frequencies, gains = read_curve(DATA_DIR / f"trap-q{trap_q:g}.csv")
        curves.plot(
            [value / 1e6 for value in frequencies],
            gains,
            color=colormap(index / max(len(TRAP_Q) - 1, 1) * 0.85),
            linewidth=1.7,
            label=f"Trap secondary Q = {trap_q:g}",
        )
    curves.axvline(9.0, color="#2c3e50", linestyle=":", linewidth=1.6)
    curves.set_xlim(6.0, 13.0)
    curves.set_xlabel("Frequency (MHz)")
    curves.set_ylabel("ANT-to-OUT voltage gain (dB)")
    curves.set_title("A Lossy T1 Loses Its Depth Long Before It Loses Its Frequency")
    curves.grid(True, alpha=0.25)
    curves.legend(fontsize=8)

    q_rows = read_summary("notch-vs-trap-q.csv")
    depths.plot(
        [row["trap_q"] for row in q_rows],
        [row["depth_vs_no_trap_db"] for row in q_rows],
        color="#c0392b",
        marker="o",
        markersize=5,
        linewidth=1.8,
        label="Null depth below the no-trap response",
    )
    depths.axhline(
        USABLE_NULL_DB,
        color="#888888",
        linestyle=":",
        linewidth=1.4,
        label=f"{USABLE_NULL_DB:g} dB — below this the null is hard to find",
    )
    depths.set_xlabel("Trap secondary unloaded Q (QS)")
    depths.set_ylabel("Null depth (dB)")
    depths.grid(True, alpha=0.25)
    depths.legend()
    twin = depths.twinx()
    twin.plot(
        [row["trap_q"] for row in q_rows],
        [row["null_hz"] / 1e6 for row in q_rows],
        color="#2980b9",
        marker="s",
        markersize=4,
        linewidth=1.4,
        linestyle="--",
        label="Null centre frequency",
    )
    twin.set_ylabel("Null centre (MHz)")
    twin.legend(loc="lower right")
    figure.savefig(FIGURE_DIR / "notch-vs-trap-q.png", dpi=180)
    plt.close(figure)


def main() -> int:
    core.export_base_netlist(BASE_NETLIST)
    run_study()
    c7_rows, q_rows, band_rows = measure_study()
    plot_study()

    print("C7 sweep, trap secondary Q = 80")
    for row in c7_rows:
        print(
            f"  C7 {row['c7_pf']:5.1f} pF  null {row['null_hz'] / 1e6:7.4f} MHz  "
            f"depth {row['depth_vs_no_trap_db']:6.2f} dB  "
            f"width {row['width_3db_hz'] / 1e3:7.1f} kHz  "
            f"attenuation at 9.000 MHz {row['attenuation_at_9mhz_db']:7.2f} dB  "
            f"{'usable' if row['null_usable'] else 'TOO SHALLOW TO FIND'}"
        )
    print("\nTrap Q sweep, C7 = 20 pF")
    for row in q_rows:
        print(
            f"  QS {row['trap_q']:5.1f}  null {row['null_hz'] / 1e6:7.4f} MHz  "
            f"depth {row['depth_vs_no_trap_db']:6.2f} dB  "
            f"width {row['width_3db_hz'] / 1e3:7.1f} kHz"
        )
    print("\nResponse at 9.000 MHz by band position")
    for row in band_rows:
        print(
            f"  {row['band']:>8}  no trap {row['gain_at_9mhz_no_trap_db']:8.2f} dB  "
            f"with trap {row['gain_at_9mhz_with_trap_db']:8.2f} dB  "
            f"attenuation {row['attenuation_at_9mhz_db']:6.2f} dB"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
