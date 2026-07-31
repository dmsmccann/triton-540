#!/usr/bin/env python3
"""Run the 80289 manual mixer-balance sweep.

The saved KiCad schematic is exported afresh. Generated netlist copies select
the 28 MHz band and 13.99 MHz crystal, suppress the behavioral PTO source, and
sweep R89-2. The manual measurement is crystal feedthrough at VFO OUT.
"""

from __future__ import annotations

import csv
import os
import re
import subprocess
from pathlib import Path

import numpy as np

import run_80166_headless as core
import run_80289_frequency_plan as coverage


ROOT = Path(__file__).resolve().parents[2]
SPICE_DIR = ROOT / "spice"
STUDY_DIR = SPICE_DIR / "studies" / "80289" / "mixer-balance"
DATA_DIR = STUDY_DIR / "data"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = SPICE_DIR / "generated" / "80289-mixer-balance"
RUN_DIR = GENERATED_DIR / "runs"
BASE_NETLIST = GENERATED_DIR / "80289-vfo-mixer-balance-base.cir"
OUTPUT_CSV = DATA_DIR / "80289-vfo-r89-2-mixer-balance-sweep.csv"
OUTPUT_PNG = FIGURE_DIR / "80289-vfo-r89-2-mixer-balance-sweep.png"

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")
SCHEMATIC = ROOT / "triton_540.kicad_sch"
CRYSTAL_HZ = 13.99e6
SAVED_R2_POSITION = 0.760

VECTORS = {
    "pin1": "v(net-_r89-4-pad2_)",
    "pin4": "v(net-_c89-2-pad1_)",
    "pin6": "v(net-_s89-1c-c-com_)",
    "pin12": "v(net-_r89-13-pad2_)",
    "filter_output": "v(net-_q89-1-g_)",
    "out": "v(/vfo-80289/out)",
}


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


def make_netlist(base_text: str, r2_position: float) -> str:
    text = replace_one(
        base_text, r"^\.param S4_POS=\S+\s*$", ".param S4_POS=5", "S4_POS"
    )
    text = replace_one(
        text, r"^\.param S5_POS=\S+\s*$", ".param S5_POS=1", "S5_POS"
    )
    text = replace_one(
        text,
        r"^V_PTO_IDEAL\s+.*$",
        "V_PTO_IDEAL net-_Q89-5-E_ 0 DC 1.7 SIN(1.7 0 5.01Meg)",
        "PTO source",
    )
    text = replace_one(
        text,
        r"^\.param VFO_R2_POS=\S+\s*$",
        f".param VFO_R2_POS={r2_position:.6g}",
        "VFO_R2_POS",
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
    traces["mixer_differential"] = traces["pin6"] - traces["pin12"]
    return uniform_time_s, traces


def measure(base_text: str, position: float) -> dict[str, float]:
    tag = f"r2_{position:.4f}".replace(".", "p")
    time_s, traces = run_case(tag, make_netlist(base_text, position))
    tone = {
        label: 1e3
        * coverage.fitted_tone_vpp(time_s, trace, CRYSTAL_HZ)
        for label, trace in traces.items()
    }
    return {
        "r89_2_position": position,
        "r89_2_wiper_percent": 100.0 * position,
        "crystal_frequency_mhz": CRYSTAL_HZ / 1e6,
        "pto_enabled": 0.0,
        "out_crystal_mvpp": tone["out"],
        "filter_output_crystal_mvpp": tone["filter_output"],
        "mixer_differential_crystal_mvpp": tone["mixer_differential"],
        "pin6_crystal_mvpp": tone["pin6"],
        "pin12_crystal_mvpp": tone["pin12"],
        "out_total_mvpp": 1e3 * float(np.ptp(traces["out"])),
        "pin1_mean_v": float(np.mean(traces["pin1"])),
        "pin4_mean_v": float(np.mean(traces["pin4"])),
        "signal_input_dc_difference_v": float(
            np.mean(traces["pin1"] - traces["pin4"])
        ),
    }


def write_csv(rows: list[dict[str, float]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    name: f"{value:.9g}"
                    for name, value in row.items()
                }
            )


def plot(rows: list[dict[str, float]], best_position: float) -> None:
    os.environ.setdefault(
        "MPLCONFIGDIR", str(GENERATED_DIR / "matplotlib")
    )
    import matplotlib.pyplot as plt

    positions = np.asarray([row["r89_2_position"] for row in rows])
    out_mvpp = np.asarray([row["out_crystal_mvpp"] for row in rows])
    raw_mvpp = np.asarray(
        [row["mixer_differential_crystal_mvpp"] for row in rows]
    )
    pin1_v = np.asarray([row["pin1_mean_v"] for row in rows])
    pin4_v = np.asarray([row["pin4_mean_v"] for row in rows])

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    figure, (feedthrough_axis, dc_axis) = plt.subplots(
        2, 1, figsize=(10.5, 8.2), sharex=True, constrained_layout=True
    )
    feedthrough_axis.semilogy(
        positions,
        np.maximum(out_mvpp, 1e-6),
        color="#d62728",
        marker="o",
        markersize=3.2,
        linewidth=1.4,
        label="VFO OUT crystal feedthrough",
    )
    feedthrough_axis.semilogy(
        positions,
        np.maximum(raw_mvpp, 1e-6),
        color="#1f77b4",
        linewidth=1.2,
        label="MC1496 pin 6 - pin 12 feedthrough",
    )
    feedthrough_axis.set_ylabel("13.99 MHz component (mVpp)")
    feedthrough_axis.grid(True, which="both", alpha=0.3)
    feedthrough_axis.legend()

    dc_axis.plot(
        positions, pin1_v, color="#9467bd", label="U89-1 pin 1 mean"
    )
    dc_axis.plot(
        positions, pin4_v, color="#2ca02c", label="U89-1 pin 4 mean"
    )
    dc_axis.set(
        xlabel="R89-2 normalized wiper position",
        ylabel="Mean voltage (V)",
    )
    dc_axis.grid(True, alpha=0.3)
    dc_axis.legend()

    for axis in (feedthrough_axis, dc_axis):
        axis.axvline(
            SAVED_R2_POSITION,
            color="#555555",
            linestyle="--",
            linewidth=1.0,
            label="Saved position" if axis is dc_axis else None,
        )
        axis.axvline(
            best_position,
            color="#ff7f0e",
            linestyle=":",
            linewidth=1.4,
            label="Simulated minimum" if axis is dc_axis else None,
        )
    dc_axis.legend()
    figure.suptitle(
        "80289 VFO mixer balance (manual 28 MHz procedure)\n"
        "PTO suppressed; S4=5, S5=1; 13.99 MHz crystal feedthrough",
        fontsize=13,
    )
    figure.savefig(OUTPUT_PNG, dpi=170)
    plt.close(figure)


def main() -> None:
    base_text = export_netlist()
    coarse_positions = [
        round(float(value), 4) for value in np.linspace(0.0, 1.0, 21)
    ]
    measured: dict[float, dict[str, float]] = {}
    for index, position in enumerate(coarse_positions, start=1):
        measured[position] = measure(base_text, position)
        print(
            f"[coarse {index:02d}/{len(coarse_positions)}] "
            f"R89-2={position:.3f}: "
            f"OUT={measured[position]['out_crystal_mvpp']:.4f} mVpp",
            flush=True,
        )

    coarse_best = min(
        measured.values(), key=lambda row: row["out_crystal_mvpp"]
    )
    center = coarse_best["r89_2_position"]
    refine_positions = sorted(
        {
            round(float(np.clip(center + offset, 0.0, 1.0)), 4)
            for offset in np.linspace(-0.05, 0.05, 21)
        }
    )
    pending = [position for position in refine_positions if position not in measured]
    for index, position in enumerate(pending, start=1):
        measured[position] = measure(base_text, position)
        print(
            f"[refine {index:02d}/{len(pending)}] "
            f"R89-2={position:.4f}: "
            f"OUT={measured[position]['out_crystal_mvpp']:.4f} mVpp",
            flush=True,
        )

    rows = sorted(measured.values(), key=lambda row: row["r89_2_position"])
    best = min(rows, key=lambda row: row["out_crystal_mvpp"])
    write_csv(rows)
    plot(rows, best["r89_2_position"])
    saved = min(
        rows,
        key=lambda row: abs(
            row["r89_2_position"] - SAVED_R2_POSITION
        ),
    )
    print(
        f"Minimum: R89-2={best['r89_2_position']:.4f}, "
        f"OUT crystal={best['out_crystal_mvpp']:.6f} mVpp, "
        f"raw mixer={best['mixer_differential_crystal_mvpp']:.6f} mVpp"
    )
    print(
        f"Saved R89-2={SAVED_R2_POSITION:.3f}: "
        f"OUT crystal={saved['out_crystal_mvpp']:.6f} mVpp"
    )
    print(f"CSV: {OUTPUT_CSV.relative_to(ROOT)}")
    print(f"Figure: {OUTPUT_PNG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
