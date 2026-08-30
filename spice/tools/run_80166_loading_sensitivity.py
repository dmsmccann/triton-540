#!/usr/bin/env python3
"""Generate the 80166 output-loading and coil-Q sensitivity study.

The schematic carries a provisional `1 MOhm || 5 pF` load on the OUT pin and
the coil models default to an unloaded Q of 70.  Together those produce peak
gains above 70 dB on the high bands, which is useful for finding resonance and
worthless as a gain prediction.  This runner sweeps the load resistance against
the coil Q on two band states and records peak gain and -3 dB bandwidth for
every combination, so the document can show how much of the modelled gain is an
artifact of the assumed load rather than a property of the board.

It also measures what the next stage actually presents, by exporting the 80287
mixer sub-sheet on its own and reading the impedance looking into its `Rx In`
pin.  That number is a property of the 80166's load, not infrastructure for the
80287 study, and it is what makes one corner of the map the realistic one.

The KiCad schematic stays the circuit source; this script only changes
simulation parameters and component values in a generated copy of its netlist.
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
STUDY_DIR = SPICE_DIR / "studies" / "80166" / "loading-sensitivity"
DATA_DIR = STUDY_DIR / "data"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = SPICE_DIR / "generated" / "80166-loading"
RUN_DIR = GENERATED_DIR / "runs"
BASE_NETLIST = GENERATED_DIR / "80166_base.net"
MIXER_SCHEMATIC = ROOT / "80287_tx_rx_mixer.kicad_sch"
MIXER_NETLIST = GENERATED_DIR / "80287_base.net"

OUT_LOAD = "R66-100"
INPUT_COIL = "XL66-1"
OUTPUT_COIL = "XL66-2"

# Two band states from the retained alignment study: the lowest band, where
# the modelled gain is already plausible, and 21 MHz, where it is not.
BAND_STATES = (
    SimpleNamespace(
        key="3p5",
        label="3.5 MHz",
        s4_pos=1,
        l_rack="17.2u",
        trimmer="C19=36p",
        target_hz=3.5e6,
        start="2Meg",
        stop="6Meg",
    ),
    SimpleNamespace(
        key="21p2",
        label="21.2 MHz",
        s4_pos=4,
        l_rack="2.06u",
        trimmer="C15=16.94p",
        target_hz=21.2e6,
        start="12Meg",
        stop="32Meg",
    ),
)

POINTS_PER_DECADE = 20000

# Load resistances spanning the schematic's provisional value down past the
# modelled mixer input.  Values are ohms; the label is what appears on the map.
LOAD_OHMS = (1_000_000.0, 100_000.0, 22_000.0, 10_000.0, 4_700.0, 2_200.0, 1_000.0, 470.0)

# Unloaded-Q settings applied to both coil models at once.  70 is the model
# default; 10 is a tired 1970s slug-tuned coil.
COIL_Q = (70.0, 50.0, 30.0, 20.0, 10.0)

MIXER_PROBE_HZ = (3.5e6, 7.0e6, 14.2e6, 21.2e6, 29.0e6)


def format_ohms(ohms: float) -> str:
    if ohms >= 1e6:
        return f"{ohms / 1e6:g}Meg"
    if ohms >= 1e3:
        return f"{ohms / 1e3:g}k"
    return f"{ohms:g}"


def tag_for(state: SimpleNamespace, ohms: float, coil_q: float) -> str:
    return f"{state.key}-load{format_ohms(ohms)}-q{coil_q:g}"


def ac_arguments(
    state: SimpleNamespace, ohms: float, coil_q: float
) -> SimpleNamespace:
    return SimpleNamespace(
        s4_pos=state.s4_pos,
        l_rack=state.l_rack,
        points_per_decade=POINTS_PER_DECADE,
        start=state.start,
        stop=state.stop,
        set_component=[state.trimmer, f"{OUT_LOAD}={format_ohms(ohms)}"],
        set_source=["V66-2=12", "V66-1=3.9"],
        set_subckt_param=[
            f"{INPUT_COIL}=QREF={coil_q:g}",
            f"{OUTPUT_COIL}=QREF={coil_q:g}",
        ],
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


def measure_mixer_input() -> list[dict[str, float]]:
    """Impedance looking into the 80287 `Rx In` pin, which is the 80166's load.

    The mixer sub-sheet already carries an `AC 1` source on that pin for its own
    studies, so the impedance is simply the applied volt divided by the current
    the source delivers.
    """

    core.export_base_netlist(MIXER_NETLIST, MIXER_SCHEMATIC, require="/Rx_In")
    text = MIXER_NETLIST.read_text(encoding="utf-8")
    text = core.set_analysis(text, ".ac lin 581 1Meg 30Meg")
    text = text.replace(".end", f"{core.SOLVER_OPTIONS}\n.end")
    raw_path = core.run_ngspice(text, "mixer-input-impedance", RUN_DIR)

    names, rows = ngspice_raw.parse_ascii_raw(raw_path)
    indices = {name: index for index, name in enumerate(names)}
    if "v(/rx_in)" not in indices or "i(v87-3)" not in indices:
        raise ValueError("80287 raw file has no Rx In drive to measure")

    frequencies = [row[indices["frequency"]].real for row in rows]
    resistance: list[float] = []
    reactance: list[float] = []
    magnitude: list[float] = []
    for row in rows:
        impedance = row[indices["v(/rx_in)"]] / -row[indices["i(v87-3)"]]
        resistance.append(impedance.real)
        reactance.append(impedance.imag)
        magnitude.append(abs(impedance))

    results = [
        {
            "frequency_hz": probe_hz,
            "resistance_ohm": ngspice_raw.interpolate_at(
                frequencies, resistance, probe_hz
            ),
            "reactance_ohm": ngspice_raw.interpolate_at(
                frequencies, reactance, probe_hz
            ),
            "magnitude_ohm": ngspice_raw.interpolate_at(
                frequencies, magnitude, probe_hz
            ),
        }
        for probe_hz in MIXER_PROBE_HZ
    ]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "mixer-input-impedance.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    return results


def run_map() -> list[dict[str, float | str]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, float | str]] = []
    for state in BAND_STATES:
        for ohms in LOAD_OHMS:
            for coil_q in COIL_Q:
                tag = tag_for(state, ohms, coil_q)
                raw_path = core.run_ngspice(
                    core.build_netlist(
                        ac_arguments(state, ohms, coil_q), BASE_NETLIST
                    ),
                    tag,
                    RUN_DIR,
                )
                generated_csv = RUN_DIR / f"{tag}.csv"
                core.write_csv_and_summary(raw_path, generated_csv)
                frequencies, gains = read_response(generated_csv)

                peak_hz, peak_db = ngspice_raw.peak_of(frequencies, gains)
                lower, upper, width = ngspice_raw.minus_3db_bandwidth(
                    frequencies, gains
                )
                loaded_q = (
                    peak_hz / width if width not in (None, 0.0) else float("nan")
                )
                summary.append(
                    {
                        "band": state.label,
                        "band_key": state.key,
                        "load_ohm": ohms,
                        "coil_q": coil_q,
                        "peak_hz": peak_hz,
                        "peak_db": peak_db,
                        "gain_at_target_db": ngspice_raw.interpolate_at(
                            frequencies, gains, state.target_hz
                        ),
                        "bandwidth_3db_hz": (
                            width if width is not None else float("nan")
                        ),
                        "loaded_q": loaded_q,
                        "grid_step_hz": ngspice_raw.grid_step_at(
                            frequencies, state.target_hz
                        ),
                    }
                )

    path = DATA_DIR / "loading-map.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    return summary


def read_map() -> list[dict[str, float | str]]:
    with (DATA_DIR / "loading-map.csv").open(
        newline="", encoding="utf-8-sig"
    ) as stream:
        rows: list[dict[str, float | str]] = []
        for row in csv.DictReader(stream):
            converted: dict[str, float | str] = {}
            for key, value in row.items():
                converted[key] = value if key in ("band", "band_key") else float(value)
            rows.append(converted)
        return rows


def grid_for(
    rows: list[dict[str, float | str]], band_key: str, column: str
) -> list[list[float]]:
    lookup = {
        (row["load_ohm"], row["coil_q"]): row[column]
        for row in rows
        if row["band_key"] == band_key
    }
    return [[lookup[(ohms, coil_q)] for coil_q in COIL_Q] for ohms in LOAD_OHMS]


def plot_study(mixer_ohm: float) -> None:
    os.environ.setdefault(
        "MPLCONFIGDIR", str(SPICE_DIR / "generated" / "matplotlib")
    )
    import matplotlib.pyplot as plt

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_map()

    figure, axes = plt.subplots(2, 2, figsize=(12.5, 9.6), constrained_layout=True)
    panels = (
        ("peak_db", "Peak ANT-to-OUT gain (dB)", "magma", "{:.0f}"),
        ("loaded_q", "Loaded Q of the whole stage", "viridis", "{:.0f}"),
    )
    load_labels = [format_ohms(ohms).replace("Meg", " M").replace("k", " k") for ohms in LOAD_OHMS]

    for column_index, (column, title, cmap, fmt) in enumerate(panels):
        for row_index, state in enumerate(BAND_STATES):
            axis = axes[row_index][column_index]
            values = grid_for(rows, state.key, column)
            image = axis.imshow(values, cmap=cmap, aspect="auto", origin="upper")
            axis.set_xticks(range(len(COIL_Q)))
            axis.set_xticklabels([f"{value:g}" for value in COIL_Q])
            axis.set_yticks(range(len(LOAD_OHMS)))
            axis.set_yticklabels(load_labels)
            axis.set_xlabel("Coil unloaded Q (QREF on L1 and L2)")
            axis.set_ylabel("OUT load resistance (ohms)")
            axis.set_title(f"{title}\n{state.label} band state")
            for y, load_row in enumerate(values):
                for x, value in enumerate(load_row):
                    # Without this, a gain of -0.17 dB prints as "-0".
                    label = fmt.format(value)
                    if set(label) <= {"-", "0"}:
                        label = label.lstrip("-")
                    axis.text(
                        x,
                        y,
                        label,
                        ha="center",
                        va="center",
                        fontsize=8,
                        color="white" if value < max(map(max, values)) * 0.6 else "black",
                    )
            figure.colorbar(image, ax=axis, shrink=0.85)

            nearest_load = min(
                range(len(LOAD_OHMS)),
                key=lambda index: abs(LOAD_OHMS[index] - mixer_ohm),
            )
            axis.add_patch(
                plt.Rectangle(
                    (-0.5, nearest_load - 0.5),
                    len(COIL_Q),
                    1,
                    fill=False,
                    edgecolor="#00d0ff",
                    linewidth=2.5,
                )
            )

    figure.suptitle(
        "How much of the modelled gain is the assumed load?  "
        f"(outlined row = the modelled 80287 mixer input, about {mixer_ohm:.0f} ohms)"
    )
    figure.savefig(FIGURE_DIR / "loading-map.png", dpi=170)
    plt.close(figure)


def main() -> int:
    core.export_base_netlist(BASE_NETLIST)
    mixer = measure_mixer_input()
    for row in mixer:
        print(
            f"80287 Rx In at {row['frequency_hz'] / 1e6:5.2f} MHz: "
            f"{row['resistance_ohm']:7.1f} {row['reactance_ohm']:+7.1f}j ohm"
        )

    summary = run_map()
    mixer_ohm = mixer[0]["magnitude_ohm"]
    plot_study(mixer_ohm)

    for state in BAND_STATES:
        print(f"\n{state.label}")
        for row in summary:
            if row["band_key"] != state.key:
                continue
            print(
                f"  load {format_ohms(float(row['load_ohm'])):>6} "
                f"Q {row['coil_q']:4.0f}  "
                f"peak {row['peak_db']:7.2f} dB at "
                f"{float(row['peak_hz']) / 1e6:8.4f} MHz  "
                f"BW {float(row['bandwidth_3db_hz']) / 1e3:8.1f} kHz  "
                f"loaded Q {row['loaded_q']:6.1f}"
            )
    print(f"\nModelled 80287 input magnitude at 3.5 MHz: {mixer_ohm:.1f} ohm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
