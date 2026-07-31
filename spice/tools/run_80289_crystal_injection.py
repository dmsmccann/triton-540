#!/usr/bin/env python3
"""Sweep the 80289 R89-27 crystal-injection control.

The runner exports a fresh KiCad netlist, retains the aligned T1/filter and
R89-2 settings, and measures wanted and unwanted mixer products at 19, 20,
and 21 MHz while sweeping the full R89-27 range.
"""

from __future__ import annotations

import csv
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import run_80166_headless as core
import run_80289_frequency_plan as coverage


ROOT = Path(__file__).resolve().parents[2]
SPICE_DIR = ROOT / "spice"
STUDY_DIR = SPICE_DIR / "studies" / "80289" / "crystal-injection"
DATA_DIR = STUDY_DIR / "data"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = SPICE_DIR / "generated" / "80289-crystal-injection"
RUN_DIR = GENERATED_DIR / "runs"
BASE_NETLIST = GENERATED_DIR / "80289-vfo-crystal-injection-base.cir"
DETAIL_CSV = DATA_DIR / "80289-vfo-r89-27-crystal-injection-detail.csv"
SUMMARY_CSV = DATA_DIR / "80289-vfo-r89-27-crystal-injection-sweep.csv"
INSTRUMENT_CSV = (
    DATA_DIR / "80289-vfo-r89-27-instrument-load-check.csv"
)
OUTPUT_PNG = (
    FIGURE_DIR / "80289-vfo-r89-27-crystal-injection-sweep.png"
)

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")
SCHEMATIC = ROOT / "triton_540.kicad_sch"
SAVED_POSITION = 0.100

VECTORS = {
    "q89_3_drain": "v(net-_q89-3-d_)",
    "pin6": "v(net-_s89-1c-c-com_)",
    "pin12": "v(net-_r89-13-pad2_)",
    "out": "v(/vfo-80289/out)",
}


@dataclass(frozen=True)
class TestPoint:
    name: str
    s5_pos: int
    pto_mhz: float
    crystal_mhz: float
    wanted_mhz: float

    @property
    def difference_mhz(self) -> float:
        return self.crystal_mhz - self.pto_mhz


TEST_POINTS = (
    TestPoint("19 MHz low edge", 1, 5.01, 13.99, 19.00),
    TestPoint("20 MHz center", 2, 5.51, 14.49, 20.00),
    TestPoint("21 MHz high edge", 4, 5.51, 15.49, 21.00),
)


def run_checked(command: list[str], description: str) -> None:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        print(completed.stdout, end="")
        print(completed.stderr, end="")
        raise SystemExit(
            f"{description} failed with exit code {completed.returncode}"
        )


def export_netlist() -> str:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    run_checked(
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
        "KiCad netlist export",
    )
    return BASE_NETLIST.read_text(encoding="utf-8")


def replace_one(
    text: str, pattern: str, replacement: str, label: str
) -> str:
    changed, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"Expected one {label}; found {count}")
    return changed


def make_netlist(
    base_text: str,
    point: TestPoint,
    r27_position: float,
    load_ohm: float = 50.0,
) -> str:
    text = replace_one(
        base_text, r"^\.param S4_POS=\S+\s*$", ".param S4_POS=5", "S4_POS"
    )
    text = replace_one(
        text,
        r"^\.param S5_POS=\S+\s*$",
        f".param S5_POS={point.s5_pos}",
        "S5_POS",
    )
    text = replace_one(
        text,
        r"^\.param VFO_R27_POS=\S+\s*$",
        f".param VFO_R27_POS={r27_position:.6g}",
        "VFO_R27_POS",
    )
    text = replace_one(
        text,
        r"^V_PTO_IDEAL\s+.*$",
        "V_PTO_IDEAL net-_Q89-5-E_ 0 DC 1.7 "
        f"SIN(1.7 300m {point.pto_mhz:.6g}Meg)",
        "PTO source",
    )
    text = replace_one(
        text,
        r"^(R89-89\s+\S+\s+\S+)\s+\S+\s*$",
        rf"\1 {load_ohm:.9g}",
        "R89-89 load",
    )
    fixture = ".save " + " ".join(VECTORS.values()) + "\n"
    return replace_one(
        text, r"^\.end\s*$", fixture + ".end", ".end directive"
    )


def run_case(
    tag: str, netlist_text: str
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    netlist_path = RUN_DIR / f"{tag}.cir"
    raw_path = RUN_DIR / f"{tag}.raw"
    log_path = RUN_DIR / f"{tag}.log"
    reusable = (
        netlist_path.exists()
        and raw_path.exists()
        and log_path.exists()
        and netlist_path.read_text(encoding="utf-8") == netlist_text
    )
    netlist_path.write_text(netlist_text, encoding="utf-8")
    if not reusable:
        run_checked(
            [
                str(NGSPICE),
                "-b",
                "-D",
                "ngbehavior=ltpsa",
                "-r",
                str(raw_path),
                "-o",
                str(log_path),
                str(netlist_path),
            ],
            f"ngspice run {tag}",
        )
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    if "error" in log_text.lower():
        raise ValueError(f"{tag} reported an error; see {log_path}")
    row_match = re.search(r"No\. of Data Rows\s*:\s*(\d+)", log_text)
    if not row_match or int(row_match.group(1)) < 20_000:
        raise ValueError(f"{tag} did not produce at least 20,000 rows")

    names, raw_rows = core.parse_ascii_raw(raw_path)
    indices = {name: index for index, name in enumerate(names)}
    required = {"time", *VECTORS.values()}
    missing = required - indices.keys()
    if missing:
        raise ValueError(f"{tag} is missing vectors: {sorted(missing)}")
    time_s = np.asarray([row[indices["time"]].real for row in raw_rows])
    uniform_time_s = 60e-6 + np.arange(20_000) * 2e-9
    traces = {
        label: np.interp(
            uniform_time_s,
            time_s,
            np.asarray(
                [row[indices[vector]].real for row in raw_rows]
            ),
        )
        for label, vector in VECTORS.items()
    }
    traces["raw_mixer"] = traces["pin6"] - traces["pin12"]
    return uniform_time_s, traces


def tone_mvpp(
    time_s: np.ndarray, values: np.ndarray, frequency_mhz: float
) -> float:
    return 1e3 * coverage.fitted_tone_vpp(
        time_s, values, frequency_mhz * 1e6
    )


def measure(
    base_text: str,
    point: TestPoint,
    position: float,
    load_ohm: float = 50.0,
) -> dict[str, float | int | str]:
    tag = (
        f"r27_{position:.3f}_{point.wanted_mhz:.2f}"
    ).replace(".", "p")
    if load_ohm != 50.0:
        tag += f"_load_{int(load_ohm)}"
    time_s, traces = run_case(
        tag, make_netlist(base_text, point, position, load_ohm)
    )
    row: dict[str, float | int | str] = {
        "r89_27_position": position,
        "r89_27_wiper_percent": 100.0 * position,
        "load_ohm": load_ohm,
        "test_point": point.name,
        "s5_pos": point.s5_pos,
        "pto_mhz": point.pto_mhz,
        "crystal_mhz": point.crystal_mhz,
        "difference_mhz": point.difference_mhz,
        "wanted_mhz": point.wanted_mhz,
        "crystal_source_mvpp": tone_mvpp(
            time_s, traces["q89_3_drain"], point.crystal_mhz
        ),
        "out_wanted_mvpp": tone_mvpp(
            time_s, traces["out"], point.wanted_mhz
        ),
        "out_crystal_mvpp": tone_mvpp(
            time_s, traces["out"], point.crystal_mhz
        ),
        "out_pto_mvpp": tone_mvpp(
            time_s, traces["out"], point.pto_mhz
        ),
        "out_difference_mvpp": tone_mvpp(
            time_s, traces["out"], point.difference_mhz
        ),
        "raw_wanted_mvpp": tone_mvpp(
            time_s, traces["raw_mixer"], point.wanted_mhz
        ),
        "raw_crystal_mvpp": tone_mvpp(
            time_s, traces["raw_mixer"], point.crystal_mhz
        ),
        "raw_pto_mvpp": tone_mvpp(
            time_s, traces["raw_mixer"], point.pto_mhz
        ),
        "raw_difference_mvpp": tone_mvpp(
            time_s, traces["raw_mixer"], point.difference_mhz
        ),
        "out_total_mvpp": 1e3 * float(np.ptp(traces["out"])),
    }
    out_unwanted = max(
        float(row["out_crystal_mvpp"]),
        float(row["out_pto_mvpp"]),
        float(row["out_difference_mvpp"]),
    )
    raw_unwanted = max(
        float(row["raw_crystal_mvpp"]),
        float(row["raw_pto_mvpp"]),
        float(row["raw_difference_mvpp"]),
    )
    row["out_wanted_to_largest_unwanted_db"] = 20.0 * np.log10(
        max(float(row["out_wanted_mvpp"]), 1e-15)
        / max(out_unwanted, 1e-15)
    )
    row["raw_wanted_to_largest_unwanted_db"] = 20.0 * np.log10(
        max(float(row["raw_wanted_mvpp"]), 1e-15)
        / max(raw_unwanted, 1e-15)
    )
    return row


def summarize(
    positions: list[float],
    detail_rows: list[dict[str, float | int | str]],
) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for position in positions:
        selected = [
            row
            for row in detail_rows
            if float(row["r89_27_position"]) == position
        ]
        rows.append(
            {
                "r89_27_position": position,
                "r89_27_wiper_percent": 100.0 * position,
                "minimum_wanted_output_mvpp": min(
                    float(row["out_wanted_mvpp"]) for row in selected
                ),
                "maximum_crystal_feedthrough_mvpp": max(
                    float(row["out_crystal_mvpp"]) for row in selected
                ),
                "maximum_pto_feedthrough_mvpp": max(
                    float(row["out_pto_mvpp"]) for row in selected
                ),
                "maximum_difference_product_mvpp": max(
                    float(row["out_difference_mvpp"]) for row in selected
                ),
                "minimum_wanted_to_largest_unwanted_db": min(
                    float(row["out_wanted_to_largest_unwanted_db"])
                    for row in selected
                ),
                "minimum_crystal_source_mvpp": min(
                    float(row["crystal_source_mvpp"]) for row in selected
                ),
                "maximum_crystal_source_mvpp": max(
                    float(row["crystal_source_mvpp"]) for row in selected
                ),
            }
        )
    return rows


def write_csv(
    path: Path,
    rows: list[dict[str, float | int | str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    name: (
                        f"{value:.9g}"
                        if isinstance(value, float)
                        else value
                    )
                    for name, value in row.items()
                }
            )


def plot(summary_rows: list[dict[str, float]]) -> None:
    os.environ.setdefault(
        "MPLCONFIGDIR", str(GENERATED_DIR / "matplotlib")
    )
    import matplotlib.pyplot as plt

    positions = np.asarray(
        [row["r89_27_position"] for row in summary_rows]
    )
    wanted = np.asarray(
        [row["minimum_wanted_output_mvpp"] for row in summary_rows]
    )
    crystal = np.asarray(
        [row["maximum_crystal_feedthrough_mvpp"] for row in summary_rows]
    )
    pto = np.asarray(
        [row["maximum_pto_feedthrough_mvpp"] for row in summary_rows]
    )
    difference = np.asarray(
        [row["maximum_difference_product_mvpp"] for row in summary_rows]
    )
    ratio = np.asarray(
        [
            row["minimum_wanted_to_largest_unwanted_db"]
            for row in summary_rows
        ]
    )
    source = np.asarray(
        [row["maximum_crystal_source_mvpp"] for row in summary_rows]
    )

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(
        3, 1, figsize=(10.5, 10.2), sharex=True, constrained_layout=True
    )
    axes[0].plot(
        positions,
        wanted,
        color="#d62728",
        marker="o",
        label="Minimum wanted output (19/20/21 MHz)",
    )
    axes[0].axhline(
        200.0,
        color="#555555",
        linestyle="--",
        label="Manual 200 mV minimum",
    )
    axes[0].set_ylabel("Wanted output (mVpp)")
    axes[0].legend()

    axes[1].semilogy(
        positions,
        np.maximum(crystal, 1e-6),
        marker="o",
        label="Maximum crystal feedthrough",
    )
    axes[1].semilogy(
        positions,
        np.maximum(pto, 1e-6),
        marker="s",
        label="Maximum PTO feedthrough",
    )
    axes[1].semilogy(
        positions,
        np.maximum(difference, 1e-6),
        marker="^",
        label="Maximum difference product",
    )
    axes[1].set_ylabel("Unwanted output (mVpp)")
    axes[1].legend()

    axes[2].plot(
        positions,
        ratio,
        color="#1f77b4",
        marker="o",
        label="Worst wanted / largest unwanted",
    )
    axes[2].set(
        xlabel="R89-27 normalized wiper position",
        ylabel="Ratio (dB)",
    )
    source_axis = axes[2].twinx()
    source_axis.plot(
        positions,
        source,
        color="#2ca02c",
        linestyle="--",
        label="Maximum Q89-3 drain crystal amplitude",
    )
    source_axis.set_ylabel("Crystal source (mVpp)")
    lines, labels = axes[2].get_legend_handles_labels()
    extra_lines, extra_labels = source_axis.get_legend_handles_labels()
    axes[2].legend(lines + extra_lines, labels + extra_labels)

    for axis in axes:
        axis.axvline(
            SAVED_POSITION,
            color="#ff7f0e",
            linestyle=":",
            linewidth=1.4,
        )
        axis.grid(True, which="both", alpha=0.3)
    figure.suptitle(
        "80289 VFO crystal-injection sweep\n"
        "Aligned 10 m filter; normal PTO; 19, 20, and 21 MHz checks",
        fontsize=13,
    )
    figure.savefig(OUTPUT_PNG, dpi=170)
    plt.close(figure)


def main() -> None:
    base_text = export_netlist()
    positions = [
        round(float(value), 3) for value in np.linspace(0.0, 1.0, 21)
    ]
    detail_rows: list[dict[str, float | int | str]] = []
    total = len(positions) * len(TEST_POINTS)
    case = 0
    for position in positions:
        for point in TEST_POINTS:
            case += 1
            row = measure(base_text, point, position)
            detail_rows.append(row)
            print(
                f"[{case:02d}/{total}] R89-27={position:.2f}, "
                f"{point.wanted_mhz:.0f} MHz: "
                f"wanted={float(row['out_wanted_mvpp']):.2f} mVpp",
                flush=True,
            )
    summary_rows = summarize(positions, detail_rows)
    write_csv(DETAIL_CSV, detail_rows)
    write_csv(SUMMARY_CSV, summary_rows)
    plot(summary_rows)

    instrument_rows = [
        measure(base_text, point, position, 1e6)
        for position in (0.0, SAVED_POSITION)
        for point in TEST_POINTS
    ]
    write_csv(INSTRUMENT_CSV, instrument_rows)

    saved = min(
        summary_rows,
        key=lambda row: abs(row["r89_27_position"] - SAVED_POSITION),
    )
    maximum_wanted = max(
        row["minimum_wanted_output_mvpp"] for row in summary_rows
    )
    best_ratio = max(
        row["minimum_wanted_to_largest_unwanted_db"]
        for row in summary_rows
    )
    print(
        f"Saved R89-27={SAVED_POSITION:.3f}: "
        f"minimum wanted={saved['minimum_wanted_output_mvpp']:.3f} mVpp, "
        f"worst ratio={saved['minimum_wanted_to_largest_unwanted_db']:.3f} dB"
    )
    print(
        f"Sweep maximum minimum-wanted={maximum_wanted:.3f} mVpp; "
        f"best worst-case wanted/unwanted={best_ratio:.3f} dB"
    )
    print(f"Detail CSV: {DETAIL_CSV.relative_to(ROOT)}")
    print(f"Summary CSV: {SUMMARY_CSV.relative_to(ROOT)}")
    print(f"Instrument-load CSV: {INSTRUMENT_CSV.relative_to(ROOT)}")
    print(f"Figure: {OUTPUT_PNG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
