#!/usr/bin/env python3
"""Read ngspice ASCII raw files, convert ratios to decibels, measure curves.

Board-independent helpers shared by every study runner under this directory.
Nothing here knows about a particular assembly, net name, or analysis; the
board-specific netlist edits and result summaries belong in each board's own
runner.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Sequence


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


def interpolate_at(
    x_values: Sequence[float], y_values: Sequence[float], x_target: float
) -> float:
    """Linearly interpolate y at x_target on a monotonically rising x grid.

    A swept analysis lands on grid points, not on the frequency a specification
    names, so reading "the gain at 3.500 MHz" off a sweep means interpolating
    between the two samples that straddle it.
    """

    for index in range(len(x_values) - 1):
        left, right = x_values[index], x_values[index + 1]
        if left <= x_target <= right:
            if right == left:
                return y_values[index]
            fraction = (x_target - left) / (right - left)
            return y_values[index] + fraction * (
                y_values[index + 1] - y_values[index]
            )
    nearest = min(
        range(len(x_values)), key=lambda index: abs(x_values[index] - x_target)
    )
    return y_values[nearest]


def peak_of(
    x_values: Sequence[float], y_values: Sequence[float]
) -> tuple[float, float]:
    """Return the largest sample as (x, y).

    The x it returns is a grid point, so its resolution is the sweep's own
    sample spacing.  Callers that quote a peak frequency must quote that
    spacing with it rather than the full printed precision.
    """

    index = max(range(len(y_values)), key=lambda i: y_values[i])
    return x_values[index], y_values[index]


def crossing_below(
    x_values: Sequence[float],
    y_values: Sequence[float],
    start_index: int,
    step: int,
    level: float,
) -> float | None:
    """Walk away from start_index until y drops through level; interpolate x."""

    index = start_index
    while 0 <= index + step < len(y_values):
        following = index + step
        if y_values[following] <= level:
            span = y_values[index] - y_values[following]
            if span == 0:
                return x_values[following]
            fraction = (y_values[index] - level) / span
            return x_values[index] + fraction * (
                x_values[following] - x_values[index]
            )
        index = following
    return None


def minus_3db_bandwidth(
    x_values: Sequence[float], y_values: Sequence[float]
) -> tuple[float | None, float | None, float | None]:
    """Return (lower edge, upper edge, width) 3 dB below the largest sample.

    Any edge that falls outside the swept window is returned as None rather
    than extrapolated, and the width is None unless both edges were found.
    """

    peak_index = max(range(len(y_values)), key=lambda i: y_values[i])
    level = y_values[peak_index] - 3.0
    lower = crossing_below(x_values, y_values, peak_index, -1, level)
    upper = crossing_below(x_values, y_values, peak_index, +1, level)
    width = None if lower is None or upper is None else upper - lower
    return lower, upper, width


def grid_step_at(x_values: Sequence[float], x_target: float) -> float:
    """The sweep's own sample spacing near x_target.

    This is the resolution limit of every frequency read off that sweep.
    """

    nearest = min(
        range(len(x_values) - 1),
        key=lambda index: abs(x_values[index] - x_target),
    )
    return abs(x_values[nearest + 1] - x_values[nearest])
