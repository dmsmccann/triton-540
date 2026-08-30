#!/usr/bin/env python3
"""Run 80166 AC sweeps from a freshly exported KiCad SPICE netlist.

The KiCad schematic remains the circuit source.  This script only changes
simulation parameters and selected component values in a generated copy.

Everything here is specific to the 80166 RF amplifier: the S4_POS and L_RACK
parameters, the C99 bypass fixture, the coil and trap model parameters, and
the board's net names read back from the raw file.  Board-independent helpers
live in ngspice_raw.

The four study runners named run_80166_<study>.py import this module for the
shared work of exporting a netlist, editing it, and running ngspice.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path
from typing import Iterable

from ngspice_raw import db_ratio, parse_ascii_raw


ROOT = Path(__file__).resolve().parents[2]
SPICE_DIR = ROOT / "spice"
GENERATED_DIR = SPICE_DIR / "generated" / "80166"
DEFAULT_NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")
DEFAULT_KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
DEFAULT_SCHEMATIC = ROOT / "triton_540.kicad_sch"
OUTPUT_DIR = GENERATED_DIR / "runs"

# Where each 80166 observation point appears in an exported netlist.
#
# The board pins ANT and OUT are wired on the root sheet to the chassis nets
# RCV2 and RCV3, and a root-sheet label outranks the sub-sheet one, so those
# two pins now export under their chassis names.  Earlier retained studies
# were run before those labels existed and carry the sheet-derived names, so
# both spellings are accepted and whichever the raw file holds is used.
PIN_NET_ALIASES: dict[str, tuple[str, ...]] = {
    "ant": ("/rf_amp_80166/ant", "/rcv2"),
    "out": ("/rf_amp_80166/out", "/rcv3"),
    "q1_gate1": ("/rf_amp_80166/q1_gate1",),
    "q1_drain": ("/rf_amp_80166/q1_drain",),
    "q1_source": ("/rf_amp_80166/q1_source",),
    "defeat": ("/rf_amp_80166/defeat",),
    "r": ("/rf_amp_80166/r",),
}

# The C13/C14 junction on bandswitch position 5 touches nothing but two
# capacitors, and the root sheet carries other assemblies' switch wafers whose
# commons float while their sheets are excluded from simulation.  Both are
# simulation artifacts rather than board faults: a 1 GOhm tie and ngspice's
# own rshunt give the solver a DC reference without loading anything
# measurably.
FLOATING_NODE_TIE = "R99 Net-_C13-Pad2_ GND 1Gig"
SOLVER_OPTIONS = ".option rshunt=1e12"
ANALYSIS_DIRECTIVES = (".ac", ".tran", ".op", ".dc", ".noise", ".disto")


def replace_directive(text: str, name: str, value: str) -> str:
    pattern = rf"(?m)^\.param\s+{re.escape(name)}\s*=.*$"
    replacement = f".param {name}={value}"
    updated, count = re.subn(pattern, replacement, text)
    if count != 1:
        raise ValueError(f"Expected one .param {name}; found {count}")
    return updated


def replace_component_value(text: str, reference: str, value: str) -> str:
    pattern = rf"(?m)^({re.escape(reference)}\s+\S+\s+\S+\s+)\S+\s*$"
    updated, count = re.subn(pattern, rf"\g<1>{value}", text)
    if count != 1:
        raise ValueError(f"Expected one {reference} line; found {count}")
    return updated


def replace_source_dc(text: str, reference: str, value: str) -> str:
    """Set the DC value of an independent source, leaving its AC card alone.

    replace_component_value cannot do this.  A source line reads
    ``V66-2 /RF_Amp_80166/R GND DC 12`` or
    ``V7 Net-_R66-99-Pad1_ GND DC 0 AC 1``, so the value is neither the last
    field nor necessarily the only one after it.  The 80166 studies that step
    the RF GAIN supply or the DEFEAT control voltage need exactly this edit.
    """

    pattern = rf"(?mi)^({re.escape(reference)}\s+\S+\s+\S+\s+DC\s+)\S+(\s*.*)$"
    updated, count = re.subn(pattern, rf"\g<1>{value}\g<2>", text)
    if count != 1:
        raise ValueError(f"Expected one {reference} DC source line; found {count}")
    return updated


def append_subckt_params(text: str, reference: str, params: str) -> str:
    """Append parameter overrides to a subcircuit instance line.

    The coil and trap models take their Q, parasitic capacitance and tap
    fractions as subcircuit parameters, and KiCad emits only the ones the
    schematic sets.  Appending ``QREF=30`` to the exported ``XL66-1`` line
    overrides a model default without editing the shared model library.
    """

    pattern = rf"(?m)^({re.escape(reference)}\s+.*?)\s*$"
    updated, count = re.subn(pattern, rf"\g<1> {params}", text)
    if count != 1:
        raise ValueError(f"Expected one {reference} line; found {count}")
    return updated


def rename_element(text: str, reference: str, new_reference: str) -> str:
    """Rename one element in the netlist.

    ngspice's ``.dc`` card will not accept a source whose name contains a
    hyphen: it reads ``V66-2`` as an expression and rejects the line.  Every
    Ten-Tec reference on this board is hyphenated, so a DC sweep has to rename
    the source it steps in its own generated copy of the netlist.
    """

    pattern = rf"(?m)^{re.escape(reference)}(?=\s)"
    updated, count = re.subn(pattern, new_reference, text)
    if count != 1:
        raise ValueError(f"Expected one {reference} element; found {count}")
    return updated


def is_analysis_card(line: str) -> bool:
    """True for an analysis directive, but not for .option or .options.

    The test is on the whole first word.  Matching a prefix would treat
    ".option rshunt=1e12" as a ".op" card and silently delete it.
    """

    words = line.split(None, 1)
    return bool(words) and words[0].lower() in ANALYSIS_DIRECTIVES


def set_analysis(text: str, directive: str) -> str:
    """Replace whatever analysis card the schematic carries with this one.

    The root schematic stores a single analysis directive and which kind it is
    depends on whichever study was set up last.  Studies that need an
    operating point, a DC sweep or an AC sweep therefore state the analysis
    they want rather than assuming the saved card is the right kind.
    """

    kept = [line for line in text.splitlines() if not is_analysis_card(line)]
    text = "\n".join(kept) + "\n"
    text, count = re.subn(r"(?m)^\.end\s*$", directive + "\n.end", text)
    if count != 1:
        raise ValueError(f"Expected one .end directive; found {count}")
    return text


def add_solver_aids(text: str) -> str:
    """Give the solver a DC reference for nodes that no component grounds."""

    if FLOATING_NODE_TIE.split()[0] + " " in text:
        return text
    addition = f"{FLOATING_NODE_TIE}\n{SOLVER_OPTIONS}\n"
    text, count = re.subn(r"(?m)^\.end\s*$", addition + ".end", text)
    if count != 1:
        raise ValueError(f"Expected one .end directive; found {count}")
    return text


def resolve_vector(available: Iterable[str], pin: str) -> str:
    """Return the raw-file vector name for one 80166 observation point."""

    names = set(available)
    for candidate in PIN_NET_ALIASES[pin]:
        if f"v({candidate})" in names:
            return f"v({candidate})"
    raise ValueError(
        f"Raw file has no vector for the 80166 {pin} node; "
        f"tried {PIN_NET_ALIASES[pin]}"
    )


def export_base_netlist(
    destination: Path,
    schematic: Path = DEFAULT_SCHEMATIC,
    kicad_cli: Path = DEFAULT_KICAD_CLI,
    require: str | None = "/RF_Amp_80166/Q1_DRAIN",
) -> Path:
    """Export a fresh SPICE netlist from the KiCad schematic.

    ``require`` is a string the exported netlist must contain.  It defaults to
    an 80166 node so that a root export made while the RF_Amp_80166 sheet is
    excluded from simulation fails loudly instead of producing an empty study.
    Pass ``None`` when exporting a different sheet on its own.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            str(kicad_cli),
            "sch",
            "export",
            "netlist",
            "--format",
            "spice",
            "-o",
            str(destination),
            str(schematic),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        print(completed.stdout, end="")
        print(completed.stderr, end="")
        raise SystemExit(
            f"KiCad netlist export failed with exit code {completed.returncode}"
        )
    if require and require not in destination.read_text(encoding="utf-8"):
        raise SystemExit(
            f"{destination} does not contain {require}. The sheet under test "
            "and its fixture symbols must be included in simulation."
        )
    return destination


def run_ngspice(
    netlist_text: str,
    tag: str,
    run_dir: Path,
    ngspice: Path = DEFAULT_NGSPICE,
) -> Path:
    """Write one netlist, run it in batch mode, and return its raw file."""

    run_dir.mkdir(parents=True, exist_ok=True)
    netlist_path = run_dir / f"{tag}.net"
    raw_path = run_dir / f"{tag}.raw"
    log_path = run_dir / f"{tag}.log"
    netlist_path.write_text(netlist_text, encoding="utf-8")
    completed = subprocess.run(
        [
            str(ngspice),
            "-b",
            "-D",
            "ngbehavior=ltpsa",
            "-r",
            str(raw_path),
            "-o",
            str(log_path),
            str(netlist_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise SystemExit(
            f"ngspice failed with exit code {completed.returncode}; see {log_path}"
        )
    return raw_path


def build_netlist(args: argparse.Namespace, base_netlist: Path) -> str:
    text = base_netlist.read_text(encoding="utf-8")
    text = replace_directive(text, "S4_POS", str(args.s4_pos))
    text = replace_directive(text, "L_RACK", args.l_rack)
    text = set_analysis(
        text, f".ac dec {args.points_per_decade} {args.start} {args.stop}"
    )

    for item in args.set_component:
        reference, value = item.split("=", 1)
        text = replace_component_value(text, reference, value)

    for item in getattr(args, "set_source", []) or []:
        reference, value = item.split("=", 1)
        text = replace_source_dc(text, reference, value)

    for item in getattr(args, "set_subckt_param", []) or []:
        reference, params = item.split("=", 1)
        text = append_subckt_params(text, reference, params)

    text = re.sub(r"(?m)^C99\s+.*\r?\n?", "", text)
    if args.c99_node:
        c99_line = f"C99 {args.c99_node} GND {args.c99_value}\n"
        text, count = re.subn(r"(?m)^\.end\s*$", c99_line + ".end", text)
        if count != 1:
            raise ValueError(f"Expected one .end directive; found {count}")
    return add_solver_aids(text)


def write_csv_and_summary(raw_path: Path, csv_path: Path) -> dict[str, float | int]:
    names, rows = parse_ascii_raw(raw_path)
    indices = {name: index for index, name in enumerate(names)}
    if "frequency" not in indices:
        raise ValueError("Raw file has no frequency vector")
    vectors = {
        pin: resolve_vector(names, pin)
        for pin in ("ant", "out", "q1_gate1", "q1_drain")
    }

    data: list[tuple[float, float, float, float, float]] = []
    for row in rows:
        frequency = row[indices["frequency"]].real
        antenna = row[indices[vectors["ant"]]]
        output = row[indices[vectors["out"]]]
        gate = row[indices[vectors["q1_gate1"]]]
        drain = row[indices[vectors["q1_drain"]]]
        data.append(
            (
                frequency,
                db_ratio(output, antenna),
                db_ratio(drain, gate),
                db_ratio(output, drain),
                db_ratio(gate, antenna),
            )
        )

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(
            [
                "frequency",
                "user0 (gain)",
                "user1 (gain)",
                "user2 (gain)",
                "user3 (gain)",
            ]
        )
        writer.writerows(data)

    output_peak = max(data, key=lambda row: row[1])
    gate_peak = max(data, key=lambda row: row[4])
    return {
        "rows": len(data),
        "output_peak_hz": output_peak[0],
        "output_peak_db": output_peak[1],
        "gate_peak_hz": gate_peak[0],
        "gate_peak_db": gate_peak[4],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument(
        "--base-netlist",
        type=Path,
        help="Use an existing exported netlist instead of exporting the schematic",
    )
    parser.add_argument("--ngspice", type=Path, default=DEFAULT_NGSPICE)
    parser.add_argument("--kicad-cli", type=Path, default=DEFAULT_KICAD_CLI)
    parser.add_argument("--schematic", type=Path, default=DEFAULT_SCHEMATIC)
    parser.add_argument("--s4-pos", type=int, required=True)
    parser.add_argument("--l-rack", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--stop", required=True)
    parser.add_argument("--points-per-decade", type=int, default=4000)
    parser.add_argument(
        "--set-component",
        action="append",
        default=[],
        metavar="REF=VALUE",
    )
    parser.add_argument(
        "--set-source",
        action="append",
        default=[],
        metavar="REF=VOLTS",
        help="Set an independent source's DC value, e.g. V66-2=6",
    )
    parser.add_argument(
        "--set-subckt-param",
        action="append",
        default=[],
        metavar="REF=PARAMS",
        help="Append model parameters to a subcircuit line, e.g. XL66-1=QREF=30",
    )
    parser.add_argument("--c99-node")
    parser.add_argument("--c99-value", default="10n")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    base_netlist = args.base_netlist
    if base_netlist is None:
        base_netlist = export_base_netlist(
            GENERATED_DIR / "80166_base.net", args.schematic, args.kicad_cli
        )
    else:
        base_netlist = base_netlist.resolve()

    netlist_path = OUTPUT_DIR / f"{args.tag}.net"
    raw_path = OUTPUT_DIR / f"{args.tag}.raw"
    log_path = OUTPUT_DIR / f"{args.tag}.log"
    csv_path = OUTPUT_DIR / f"{args.tag}.csv"

    netlist_path.write_text(build_netlist(args, base_netlist), encoding="utf-8")
    command = [
        str(args.ngspice),
        "-b",
        "-D",
        "ngbehavior=ltpsa",
        "-r",
        str(raw_path),
        "-o",
        str(log_path),
        str(netlist_path),
    ]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(
            f"ngspice failed with exit code {completed.returncode}; see {log_path}"
        )

    summary = write_csv_and_summary(raw_path, csv_path)
    summary.update(
        {
            "tag": args.tag,
            "base_netlist": str(base_netlist),
            "netlist": str(netlist_path),
            "csv": str(csv_path),
            "log": str(log_path),
        }
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
