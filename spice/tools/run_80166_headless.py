#!/usr/bin/env python3
"""Run 80166 AC sweeps from a freshly exported KiCad SPICE netlist.

The KiCad schematic remains the circuit source.  This script only changes
simulation parameters and selected component values in a generated copy.

Everything here is specific to the 80166 RF amplifier: the S4_POS and L_RACK
parameters, the C99 bypass fixture, and the rf_amp_80166 net names read back
from the raw file.  Board-independent helpers live in ngspice_raw.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path

from ngspice_raw import db_ratio, parse_ascii_raw


ROOT = Path(__file__).resolve().parents[2]
SPICE_DIR = ROOT / "spice"
GENERATED_DIR = SPICE_DIR / "generated" / "80166"
DEFAULT_NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")
DEFAULT_KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
DEFAULT_SCHEMATIC = ROOT / "triton_540.kicad_sch"
OUTPUT_DIR = GENERATED_DIR / "runs"


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


def build_netlist(args: argparse.Namespace, base_netlist: Path) -> str:
    text = base_netlist.read_text(encoding="utf-8")
    text = replace_directive(text, "S4_POS", str(args.s4_pos))
    text = replace_directive(text, "L_RACK", args.l_rack)
    text, count = re.subn(
        r"(?m)^\.ac\s+.*$",
        f".ac dec {args.points_per_decade} {args.start} {args.stop}",
        text,
    )
    if count != 1:
        raise ValueError(f"Expected one .ac directive; found {count}")

    for item in args.set_component:
        reference, value = item.split("=", 1)
        text = replace_component_value(text, reference, value)

    text = re.sub(r"(?m)^C99\s+.*\r?\n?", "", text)
    if args.c99_node:
        c99_line = f"C99 {args.c99_node} GND {args.c99_value}\n"
        text, count = re.subn(r"(?m)^\.end\s*$", c99_line + ".end", text)
        if count != 1:
            raise ValueError(f"Expected one .end directive; found {count}")
    return text


def write_csv_and_summary(raw_path: Path, csv_path: Path) -> dict[str, float | int]:
    names, rows = parse_ascii_raw(raw_path)
    indices = {name: index for index, name in enumerate(names)}
    required = {
        "frequency",
        "v(/rf_amp_80166/out)",
        "v(/rf_amp_80166/ant)",
        "v(/rf_amp_80166/q1_gate1)",
        "v(/rf_amp_80166/q1_drain)",
    }
    missing = required - indices.keys()
    if missing:
        raise ValueError(f"Raw file is missing vectors: {sorted(missing)}")

    data: list[tuple[float, float, float, float, float]] = []
    for row in rows:
        frequency = row[indices["frequency"]].real
        antenna = row[indices["v(/rf_amp_80166/ant)"]]
        output = row[indices["v(/rf_amp_80166/out)"]]
        gate = row[indices["v(/rf_amp_80166/q1_gate1)"]]
        drain = row[indices["v(/rf_amp_80166/q1_drain)"]]
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
    parser.add_argument("--c99-node")
    parser.add_argument("--c99-value", default="10n")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    base_netlist = args.base_netlist
    if base_netlist is None:
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        base_netlist = GENERATED_DIR / "80166_base.net"
        export_command = [
            str(args.kicad_cli),
            "sch",
            "export",
            "netlist",
            "--format",
            "spice",
            "-o",
            str(base_netlist),
            str(args.schematic),
        ]
        exported = subprocess.run(
            export_command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if exported.returncode:
            print(exported.stdout, end="")
            print(exported.stderr, end="")
            raise SystemExit(
                f"KiCad netlist export failed with exit code {exported.returncode}"
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
