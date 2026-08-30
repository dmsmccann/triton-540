#!/usr/bin/env python3
"""Run the 80279 two-stage 9 MHz IF small-signal response study.

The KiCad schematic is exported afresh. Disposable netlists and ngspice logs
stay below spice/generated; curated CSVs and the response figure are written
to the 80279 study directory.
"""

from __future__ import annotations

import csv
import math
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMATIC = ROOT / "80279_if_agc.kicad_sch"
STUDY_DIR = ROOT / "spice" / "studies" / "80279" / "if-response-9mhz"
DATA_DIR = STUDY_DIR / "data"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = ROOT / "spice" / "generated" / "80279-if-response"
BASE_NETLIST = GENERATED_DIR / "80279-if-response-base.cir"
RUN_NETLIST = GENERATED_DIR / "80279-if-response-ac.cir"
RAW_DATA = GENERATED_DIR / "80279-if-response.dat"
LOG_PATH = GENERATED_DIR / "80279-if-response.log"

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")

START_HZ = 8.8e6
STOP_HZ = 9.2e6
POINTS = 4001
TARGET_HZ = 9.0e6

TRACES = (
    ("input", "/in", "80279 IN"),
    ("q79_1_collector", "net-_q79-1-c_", "Q79-1 collector"),
    ("q79_2_base", "net-_q79-2-b_", "T79-1 secondary / Q79-2 base"),
    ("q79_2_collector", "net-_q79-2-c_", "Q79-2 collector"),
    ("q79_3_gate1", "net-_q79-3-g1_", "T79-2 secondary / Q79-3 G1"),
)


def run(command: list[str], cwd: Path) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        print(completed.stdout, end="")
        print(completed.stderr, end="")
        raise SystemExit(
            f"Command failed with exit code {completed.returncode}: {command[0]}"
        )


def export_netlist() -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    if not KICAD_CLI.exists():
        raise SystemExit(f"KiCad CLI was not found: {KICAD_CLI}")
    run(
        [
            str(KICAD_CLI),
            "sch",
            "export",
            "netlist",
            "--format",
            "spice",
            "-o",
            str(BASE_NETLIST),
            str(SCHEMATIC),
        ],
        ROOT,
    )


def build_ac_netlist() -> None:
    text = BASE_NETLIST.read_text(encoding="utf-8")
    if "L79-3" not in text or "2.63u" not in text:
        raise ValueError("Fresh export does not contain the aligned 2.63 uH model")
    if "K79_T1 L79-3 L79-4 0.25" not in text:
        raise ValueError("Fresh export does not contain the T79-1 coupling model")
    if "K79_T2 L79-5 L79-6 0.25" not in text:
        raise ValueError("Fresh export does not contain the T79-2 coupling model")

    commands = [
        ".control",
        "set wr_singlescale",
        "set wr_vecnames",
        f"ac lin {POINTS} {START_HZ:g} {STOP_HZ:g}",
        "wrdata 80279-if-response.dat "
        + " ".join(f"mag(v({node}))" for _, node, _ in TRACES),
        "quit",
        ".endc",
        ".end",
    ]
    text, count = re.subn(
        r"(?m)^\.end\s*$",
        "\n".join(commands),
        text,
        count=1,
    )
    if count != 1:
        raise ValueError(f"Expected one .end directive; found {count}")
    RUN_NETLIST.write_text(text, encoding="utf-8")


def run_ngspice() -> None:
    if not NGSPICE.exists():
        raise SystemExit(f"ngspice was not found: {NGSPICE}")
    run(
        [
            str(NGSPICE),
            "-b",
            "-D",
            "ngbehavior=ltpsa",
            "-o",
            str(LOG_PATH),
            str(RUN_NETLIST),
        ],
        GENERATED_DIR,
    )
    if not RAW_DATA.exists():
        raise ValueError(f"ngspice did not create {RAW_DATA}")


def load_rows() -> list[dict[str, float]]:
    lines = RAW_DATA.read_text(encoding="utf-8").splitlines()
    rows: list[dict[str, float]] = []
    for line in lines[1:]:
        values = [float(value) for value in line.split()]
        if len(values) != len(TRACES) + 1:
            raise ValueError(
                f"Expected {len(TRACES) + 1} columns, found {len(values)}"
            )
        row = {"frequency_hz": values[0]}
        for (key, _, _), magnitude in zip(TRACES, values[1:]):
            row[f"{key}_v_per_v"] = magnitude
            row[f"{key}_db"] = 20.0 * math.log10(max(magnitude, 1e-300))
        rows.append(row)
    if len(rows) != POINTS:
        raise ValueError(f"Expected {POINTS} AC rows, found {len(rows)}")
    return rows


def interpolate(rows: list[dict[str, float]], key: str, frequency: float) -> float:
    for left, right in zip(rows, rows[1:]):
        if left["frequency_hz"] <= frequency <= right["frequency_hz"]:
            span = right["frequency_hz"] - left["frequency_hz"]
            fraction = (frequency - left["frequency_hz"]) / span
            return left[key] + fraction * (right[key] - left[key])
    return min(rows, key=lambda row: abs(row["frequency_hz"] - frequency))[key]


def crossing(
    rows: list[dict[str, float]], key: str, threshold: float, rising: bool
) -> float:
    pairs = zip(rows, rows[1:])
    for left, right in pairs:
        y1, y2 = left[key], right[key]
        crossed = y1 <= threshold <= y2 if rising else y1 >= threshold >= y2
        if crossed and y2 != y1:
            fraction = (threshold - y1) / (y2 - y1)
            return left["frequency_hz"] + fraction * (
                right["frequency_hz"] - left["frequency_hz"]
            )
    raise ValueError(f"No {'rising' if rising else 'falling'} threshold crossing")


def write_results(rows: list[dict[str, float]]) -> list[dict[str, str | float]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    response_path = DATA_DIR / "80279-if-response.csv"
    fieldnames = list(rows[0].keys())
    with response_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    final_key = "q79_3_gate1_db"
    peak_index = max(range(len(rows)), key=lambda index: rows[index][final_key])
    peak_row = rows[peak_index]
    threshold = peak_row[final_key] - 3.0
    lower = crossing(rows[: peak_index + 1], final_key, threshold, rising=True)
    upper = crossing(rows[peak_index:], final_key, threshold, rising=False)

    at_target = {
        key: interpolate(rows, f"{key}_db", TARGET_HZ)
        for key, _, _ in TRACES
    }
    stage_rows: list[dict[str, str | float]] = []
    previous_key = TRACES[0][0]
    for key, _, label in TRACES[1:]:
        stage_rows.append(
            {
                "measurement": label,
                "frequency_hz": TARGET_HZ,
                "node_gain_db": at_target[key],
                "incremental_gain_db": at_target[key] - at_target[previous_key],
            }
        )
        previous_key = key
    stage_rows.append(
        {
            "measurement": "Overall IN to Q79-3 G1",
            "frequency_hz": TARGET_HZ,
            "node_gain_db": at_target["q79_3_gate1"],
            "incremental_gain_db": at_target["q79_3_gate1"],
        }
    )

    with (DATA_DIR / "80279-if-signal-walk.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=stage_rows[0].keys())
        writer.writeheader()
        writer.writerows(stage_rows)

    summary = [
        {"metric": "peak_frequency_hz", "value": peak_row["frequency_hz"], "unit": "Hz"},
        {"metric": "peak_gain_db", "value": peak_row[final_key], "unit": "dB"},
        {"metric": "gain_at_9mhz_db", "value": at_target["q79_3_gate1"], "unit": "dB"},
        {"metric": "lower_3db_hz", "value": lower, "unit": "Hz"},
        {"metric": "upper_3db_hz", "value": upper, "unit": "Hz"},
        {"metric": "bandwidth_3db_hz", "value": upper - lower, "unit": "Hz"},
        {"metric": "loaded_q", "value": peak_row["frequency_hz"] / (upper - lower), "unit": "ratio"},
        {"metric": "winding_inductance", "value": 2.63, "unit": "uH estimated"},
        {"metric": "coupling_k", "value": 0.25, "unit": "estimated"},
    ]
    with (DATA_DIR / "80279-if-response-summary.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=summary[0].keys())
        writer.writeheader()
        writer.writerows(summary)
    return summary


def write_figure(rows: list[dict[str, float]]) -> None:
    import matplotlib.pyplot as plt

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    frequencies = [row["frequency_hz"] / 1e6 for row in rows]
    fig, axis = plt.subplots(figsize=(9.2, 5.6))
    for key, _, label in TRACES[1:]:
        axis.plot(
            frequencies,
            [row[f"{key}_db"] for row in rows],
            linewidth=1.8,
            label=label,
        )
    axis.axvline(9.0, color="black", linestyle="--", linewidth=1.1, label="9.000 MHz")
    axis.set_title("Ten-Tec 80279 estimated 9 MHz IF signal walk")
    axis.set_xlabel("Frequency (MHz)")
    axis.set_ylabel("Small-signal transfer from IN (dB)")
    axis.grid(True, alpha=0.28)
    axis.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "80279-if-response.png", dpi=180)
    plt.close(fig)


def write_manifest() -> None:
    rows = [
        ("data/80279-if-response.csv", "Curated 8.8-9.2 MHz AC response"),
        ("data/80279-if-signal-walk.csv", "9 MHz stage-by-stage gains"),
        ("data/80279-if-response-summary.csv", "Peak and bandwidth measurements"),
        ("figures/80279-if-response.png", "IF response and signal-walk figure"),
    ]
    STUDY_DIR.mkdir(parents=True, exist_ok=True)
    with (STUDY_DIR / "manifest.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(("path", "purpose"))
        writer.writerows(rows)


def main() -> None:
    export_netlist()
    build_ac_netlist()
    run_ngspice()
    rows = load_rows()
    summary = write_results(rows)
    write_figure(rows)
    write_manifest()
    for item in summary:
        print(f"{item['metric']}={item['value']} {item['unit']}")


if __name__ == "__main__":
    main()
