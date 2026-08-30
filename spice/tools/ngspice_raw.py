#!/usr/bin/env python3
"""Read ngspice ASCII raw files and compute decibel ratios.

Board-independent helpers shared by every study runner under this directory.
Nothing here knows about a particular assembly, net name, or analysis; the
board-specific netlist edits and result summaries belong in each board's own
runner.
"""

from __future__ import annotations

import math
import re
from pathlib import Path


def parse_ascii_raw(raw_path: Path) -> tuple[list[str], list[list[complex]]]:
    text = raw_path.read_text(encoding="utf-8", errors="replace")
    header, body = text.split("Values:", 1)

    variable_match = re.search(
        r"Variables:\s*\n(?P<variables>.*?)(?=\nValues:|\Z)",
        text,
        flags=re.DOTALL,
    )
    if not variable_match:
        raise ValueError("Raw file has no Variables section")

    names: list[str] = []
    for line in variable_match.group("variables").splitlines():
        match = re.match(r"\s*\d+\s+(\S+)\s+", line)
        if match:
            names.append(match.group(1).lower())

    flags_match = re.search(r"(?m)^Flags:\s*(.*)$", header)
    flags = flags_match.group(1).lower() if flags_match else ""
    if "complex" in flags:
        pairs = re.findall(
            r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?),"
            r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)",
            body,
        )
        values = [complex(float(real), float(imag)) for real, imag in pairs]
    else:
        number = re.compile(
            r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
        )
        values = []
        for line in body.splitlines():
            tokens = number.findall(line)
            if not tokens:
                continue
            value_token = tokens[1] if not line[:1].isspace() else tokens[0]
            values.append(complex(float(value_token), 0.0))
    if not names or len(values) % len(names):
        raise ValueError(
            f"Raw value count {len(values)} is not divisible by {len(names)} variables"
        )
    rows = [
        values[index : index + len(names)]
        for index in range(0, len(values), len(names))
    ]
    return names, rows


def db_ratio(numerator: complex, denominator: complex) -> float:
    ratio = abs(numerator / denominator)
    return 20.0 * math.log10(ratio)
