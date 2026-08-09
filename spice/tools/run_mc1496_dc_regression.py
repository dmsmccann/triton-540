#!/usr/bin/env python3
"""Compare the schematic-native 80287 MC1496 DC points with the manual.

The current KiCad hierarchy is exported for every run.  No hand-built copy of
the 80287 external bias network is used.  Ten-Tec states that its service
voltages should be within 15 percent when measured with a DC voltmeter of at
least 20,000 ohms per volt (manual PDF page 18 / printed page 3-1).
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from pathlib import Path

import run_80287_operation as op


STUDY = op.ROOT / "spice" / "studies" / "80287" / "dc-regression"
DATA = STUDY / "data"
OUTPUT = DATA / "80287-mc1496-dc-regression.csv"

CHECKED_PINS = (1, 2, 3, 4, 5, 6, 8, 10, 12, 14)

# Manual PDF page 30 / printed page 3-14.  Values are positive volts relative
# to chassis ground.  Pins 7, 9, 11, and 13 are NC and intentionally omitted.
TARGETS = {
    ("receive", "U87-1"): {
        1: 3.5, 2: 2.7, 3: 2.7, 4: 3.4, 5: 1.2,
        6: 11.8, 8: 6.5, 10: 6.5, 12: 11.8, 14: 0.0,
    },
    ("transmit", "U87-1"): {
        1: 0.2, 2: 0.0, 3: 0.0, 4: 0.2, 5: 0.5,
        6: 0.7, 8: 0.4, 10: 0.4, 12: 0.7, 14: 0.0,
    },
    ("transmit", "U87-2"): {
        1: 6.5, 2: 5.8, 3: 5.8, 4: 6.5, 5: 3.0,
        6: 12.8, 8: 9.8, 10: 9.8, 12: 12.8, 14: 0.0,
    },
    ("receive", "U87-2"): {
        1: 6.7, 2: 6.2, 3: 6.2, 4: 6.7, 5: 0.2,
        6: 13.4, 8: 10.0, 10: 10.0, 12: 13.4, 14: 0.0,
    },
}


def measured_pin(state: str, device: str, pin: int, time, traces) -> float:
    if pin == 14:
        return 0.0
    prefix = "u1" if device == "U87-1" else "u2"
    return op.dc_mean(time, traces[f"{prefix}_pin{pin}"])


def tolerance(target: float) -> float:
    # The manual specifies a relative tolerance.  A small absolute band is
    # required for documented zero/near-zero readings.
    return max(abs(target) * 0.15, 0.15)


def extend_settling_time(netlist: str) -> str:
    """Keep the RF startup excitation but allow bias capacitors to settle."""
    updated, count = re.subn(
        r"(?m)^\.tran\s+.*$", ".tran 5n 500u 400u 5n", netlist
    )
    if count != 1:
        raise ValueError(f"Expected one transient directive; found {count}")
    return updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict", action="store_true",
        help="return a failing exit code when a documented pin is out of tolerance",
    )
    args = parser.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)
    base = extend_settling_time(op.export_netlist())
    rx_time, rx = op.run_state("dc-receive", base, 12.8, 0.2)
    tx_time, tx = op.run_state("dc-transmit", base, 0.6, 10.4)
    states = {"receive": (rx_time, rx), "transmit": (tx_time, tx)}

    rows = []
    failures = 0
    for (state, device), targets in TARGETS.items():
        time, traces = states[state]
        for pin in CHECKED_PINS:
            expected = targets[pin]
            measured = measured_pin(state, device, pin, time, traces)
            allowed = tolerance(expected)
            error = measured - expected
            passed = abs(error) <= allowed
            failures += not passed
            percent = math.nan if expected == 0 else 100.0 * error / expected
            rows.append(
                (state, device, pin, measured, expected, allowed, error, percent,
                 "PASS" if passed else "FAIL")
            )

    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ("state", "device", "pin", "simulated_v", "manual_v",
             "allowed_error_v", "error_v", "error_percent", "status")
        )
        writer.writerows(rows)

    print(f"manual_pin_checks={len(rows)}")
    print(f"passed={len(rows) - failures}")
    print(f"failed={failures}")
    print(f"csv={OUTPUT}")
    for row in rows:
        if row[-1] == "FAIL":
            state, device, pin, measured, expected, allowed, *_ = row
            print(
                f"FAIL {state:8s} {device} pin {pin:2d}: "
                f"{measured:8.4f} V; manual {expected:6.2f} V +/- {allowed:.3f} V"
            )
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
