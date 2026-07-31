#!/usr/bin/env python3
"""Generate the 80289 switched-output-filter response study.

The saved KiCad schematic is exported afresh. The behavioral PTO frequency is
then stepped in generated netlist copies while the wanted component is measured
at the MC1496 output, selected-filter output, and 50 ohm loaded VFO output.
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
STUDY_DIR = SPICE_DIR / "studies" / "80289" / "filter-response"
DATA_DIR = STUDY_DIR / "data"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = SPICE_DIR / "generated" / "80289-filter-response"
RUN_DIR = GENERATED_DIR / "runs"
BASE_NETLIST = GENERATED_DIR / "80289-vfo-filter-response-base.cir"
OUTPUT_CSV = DATA_DIR / "80289-vfo-switched-filter-response.csv"
OUTPUT_PNG = FIGURE_DIR / "80289-vfo-switched-filter-response.png"

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")
SCHEMATIC = ROOT / "triton_540.kicad_sch"

VECTORS = {
    "mixer_positive_v": "v(net-_s89-1c-c-com_)",
    "mixer_negative_v": "v(net-_r89-13-pad2_)",
    "filter_output_v": "v(net-_q89-1-g_)",
    "vfo_out_v": "v(/vfo-80289/out)",
}


@dataclass(frozen=True)
class FilterPath:
    name: str
    components: str
    s4_pos: int
    manual_low_mhz: float
    manual_high_mhz: float
    sweep_low_mhz: float
    sweep_high_mhz: float
    points: int


FILTERS = (
    FilterPath(
        "80 m",
        "C89-9 / C89-12",
        1,
        12.50,
        13.00,
        12.35,
        13.15,
        17,
    ),
    FilterPath(
        "40 m",
        "C89-8 / C89-11",
        2,
        16.00,
        16.50,
        15.85,
        16.65,
        17,
    ),
    FilterPath(
        "15 m",
        "C89-7 / C89-10",
        4,
        12.00,
        12.50,
        11.85,
        12.65,
        17,
    ),
    FilterPath(
        "10 m",
        "T1",
        5,
        19.00,
        21.00,
        18.80,
        21.20,
        25,
    ),
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


def crystal_selection(
    path: FilterPath, wanted_mhz: float
) -> tuple[int, float]:
    if path.s4_pos == 1:
        return 1, 7.50
    if path.s4_pos == 2:
        return 1, 11.00
    if path.s4_pos == 4:
        return 1, 6.99
    if wanted_mhz < 19.50:
        return 1, 13.99
    if wanted_mhz < 20.00:
        return 2, 14.49
    if wanted_mhz < 20.50:
        return 3, 14.99
    return 4, 15.49


def make_netlist(
    base_text: str,
    path: FilterPath,
    s5_pos: int,
    pto_mhz: float,
) -> str:
    text, s4_count = re.subn(
        r"(?m)^\.param S4_POS=\S+\s*$",
        f".param S4_POS={path.s4_pos}",
        base_text,
    )
    if s4_count != 1:
        raise ValueError(f"Expected one S4_POS parameter; found {s4_count}")
    text, s5_count = re.subn(
        r"(?m)^\.param S5_POS=\S+\s*$",
        f".param S5_POS={s5_pos}",
        text,
    )
    if s5_count != 1:
        raise ValueError(f"Expected one S5_POS parameter; found {s5_count}")

    pto_line = (
        "V_PTO_IDEAL net-_Q89-5-E_ 0 DC 1.7 "
        f"SIN(1.7 300m {pto_mhz:.9g}Meg)"
    )
    text, pto_count = re.subn(
        r"(?m)^V_PTO_IDEAL\s+.*$",
        pto_line,
        text,
    )
    if pto_count != 1:
        raise ValueError(f"Expected one PTO source; found {pto_count}")

    fixture = ".save " + " ".join(VECTORS.values()) + "\n"
    text, end_count = re.subn(
        r"(?m)^\.end\s*$",
        fixture + ".end",
        text,
    )
    if end_count != 1:
        raise ValueError(f"Expected one .end directive; found {end_count}")
    return text


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
    row_match = re.search(r"No\. of Data Rows\s*:\s*(\d+)", log_text)
    if not row_match or int(row_match.group(1)) < 20_000:
        raise ValueError(f"{tag} did not produce at least 20,000 saved rows")
    if "error" in log_text.lower():
        raise ValueError(f"{tag} reported an error; see {log_path}")

    names, rows = core.parse_ascii_raw(raw_path)
    indices = {name: index for index, name in enumerate(names)}
    missing = {"time", *VECTORS.values()} - indices.keys()
    if missing:
        raise ValueError(f"{tag} is missing vectors: {sorted(missing)}")
    time_s = np.asarray([row[indices["time"]].real for row in rows])
    uniform_time_s = 60e-6 + np.arange(20_000) * 2e-9
    traces = {
        label: np.interp(
            uniform_time_s,
            time_s,
            np.asarray([row[indices[vector]].real for row in rows]),
        )
        for label, vector in VECTORS.items()
    }
    traces["mixer_raw_v"] = (
        traces["mixer_positive_v"] - traces["mixer_negative_v"]
    )
    return uniform_time_s, traces


def safe_gain_db(output_vpp: float, input_vpp: float) -> float:
    return float(20.0 * np.log10(max(output_vpp, 1e-15) / max(input_vpp, 1e-15)))


def run_sweep(base_text: str) -> list[dict[str, float | int | str]]:
    rows: list[dict[str, float | int | str]] = []
    total_cases = sum(path.points for path in FILTERS)
    case_number = 0
    for path in FILTERS:
        frequencies_mhz = np.linspace(
            path.sweep_low_mhz, path.sweep_high_mhz, path.points
        )
        for wanted_mhz in frequencies_mhz:
            case_number += 1
            s5_pos, crystal_mhz = crystal_selection(path, float(wanted_mhz))
            pto_mhz = float(wanted_mhz) - crystal_mhz
            tag = (
                f"{path.name.replace(' ', '').lower()}_"
                f"{wanted_mhz:.3f}".replace(".", "p")
            )
            netlist_text = make_netlist(
                base_text, path, s5_pos, pto_mhz
            )
            time_s, traces = run_case(tag, netlist_text)
            raw_vpp = coverage.fitted_tone_vpp(
                time_s, traces["mixer_raw_v"], float(wanted_mhz) * 1e6
            )
            filter_input_vpp = coverage.fitted_tone_vpp(
                time_s,
                traces["mixer_positive_v"],
                float(wanted_mhz) * 1e6,
            )
            filter_vpp = coverage.fitted_tone_vpp(
                time_s,
                traces["filter_output_v"],
                float(wanted_mhz) * 1e6,
            )
            out_vpp = coverage.fitted_tone_vpp(
                time_s, traces["vfo_out_v"], float(wanted_mhz) * 1e6
            )
            rows.append(
                {
                    "filter_path": path.name,
                    "filter_components": path.components,
                    "s4_pos": path.s4_pos,
                    "s5_pos": s5_pos if path.s4_pos == 5 else "",
                    "wanted_frequency_mhz": float(wanted_mhz),
                    "pto_mhz": pto_mhz,
                    "crystal_mhz": crystal_mhz,
                    "inside_manual_range": (
                        "yes"
                        if path.manual_low_mhz
                        <= wanted_mhz
                        <= path.manual_high_mhz
                        else "no"
                    ),
                    "raw_mixer_mvpp": 1e3 * raw_vpp,
                    "filter_input_mvpp": 1e3 * filter_input_vpp,
                    "filter_output_mvpp": 1e3 * filter_vpp,
                    "loaded_out_mvpp": 1e3 * out_vpp,
                    "filter_gain_db": safe_gain_db(
                        filter_vpp, filter_input_vpp
                    ),
                    "buffer_load_gain_db": safe_gain_db(out_vpp, filter_vpp),
                }
            )
            print(
                f"[{case_number:02d}/{total_cases}] {path.name} "
                f"{wanted_mhz:.3f} MHz: OUT={1e3 * out_vpp:.2f} mVpp",
                flush=True,
            )

    for path in FILTERS:
        selected = [row for row in rows if row["filter_path"] == path.name]
        peak_gain_db = max(float(row["filter_gain_db"]) for row in selected)
        for row in selected:
            row["filter_gain_normalized_db"] = (
                float(row["filter_gain_db"]) - peak_gain_db
            )
    return rows


def write_csv(rows: list[dict[str, float | int | str]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    frequency_columns = {
        "wanted_frequency_mhz",
        "pto_mhz",
        "crystal_mhz",
    }
    amplitude_columns = {
        "raw_mixer_mvpp",
        "filter_input_mvpp",
        "filter_output_mvpp",
        "loaded_out_mvpp",
    }
    gain_columns = {
        "filter_gain_db",
        "buffer_load_gain_db",
        "filter_gain_normalized_db",
    }
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            formatted = dict(row)
            for column in frequency_columns:
                formatted[column] = f"{float(row[column]):.6f}"
            for column in amplitude_columns:
                formatted[column] = f"{float(row[column]):.6f}"
            for column in gain_columns:
                formatted[column] = f"{float(row[column]):.6f}"
            writer.writerow(formatted)


def plot_response(rows: list[dict[str, float | int | str]]) -> None:
    os.environ.setdefault(
        "MPLCONFIGDIR", str(GENERATED_DIR / "matplotlib")
    )
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(
        2,
        2,
        figsize=(12.5, 8.2),
        constrained_layout=True,
    )
    for axis, path in zip(axes.flat, FILTERS):
        selected = [row for row in rows if row["filter_path"] == path.name]
        frequency_mhz = np.asarray(
            [float(row["wanted_frequency_mhz"]) for row in selected]
        )
        normalized_gain_db = np.asarray(
            [float(row["filter_gain_normalized_db"]) for row in selected]
        )
        loaded_out_mvpp = np.asarray(
            [float(row["loaded_out_mvpp"]) for row in selected]
        )

        axis.axvspan(
            path.manual_low_mhz,
            path.manual_high_mhz,
            color="#2ca02c",
            alpha=0.09,
            label="Documented operating range",
        )
        gain_line = axis.plot(
            frequency_mhz,
            normalized_gain_db,
            color="#1f77b4",
            marker="o",
            markersize=3.2,
            linewidth=1.4,
            label="Selected-filter transmission",
        )[0]
        axis.set_ylabel("Normalized filter transmission (dB)")
        axis.set_ylim(min(-12.0, float(np.min(normalized_gain_db)) - 1.0), 1.0)
        axis.grid(True, alpha=0.3)
        axis.set_xlabel("Wanted VFO frequency (MHz)")
        axis.set_title(
            f"{path.name}: {path.components}, S4={path.s4_pos}",
            loc="left",
        )

        amplitude_axis = axis.twinx()
        amplitude_line = amplitude_axis.plot(
            frequency_mhz,
            loaded_out_mvpp,
            color="#d62728",
            marker="s",
            markersize=2.8,
            linewidth=1.1,
            label="Loaded OUT wanted component",
        )[0]
        amplitude_axis.set_ylabel("Loaded OUT wanted component (mVpp)")
        amplitude_axis.set_ylim(
            0.0, max(200.0, 1.12 * float(np.max(loaded_out_mvpp)))
        )
        axis.legend(
            [gain_line, amplitude_line],
            [
                "Normalized selected-filter transmission",
                "Loaded OUT wanted component",
            ],
            loc="lower left",
            fontsize=8,
        )

    figure.suptitle(
        "80289 VFO switched-filter response\n"
        "Wanted-tone fits over 60–100 µs; shaded region is documented coverage"
    )
    OUTPUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT_PNG, dpi=180)
    plt.close(figure)


def summarize(rows: list[dict[str, float | int | str]]) -> None:
    for path in FILTERS:
        in_band = [
            row
            for row in rows
            if row["filter_path"] == path.name
            and row["inside_manual_range"] == "yes"
        ]
        min_out = min(float(row["loaded_out_mvpp"]) for row in in_band)
        max_out = max(float(row["loaded_out_mvpp"]) for row in in_band)
        ripple_db = 20.0 * np.log10(max_out / min_out)
        peak_rows = sorted(
            in_band,
            key=lambda row: float(row["filter_gain_normalized_db"]),
            reverse=True,
        )[:2]
        peak_text = ", ".join(
            f"{float(row['wanted_frequency_mhz']):.3f} MHz"
            for row in peak_rows
        )
        print(
            f"{path.name}: OUT {min_out:.2f}-{max_out:.2f} mVpp, "
            f"{ripple_db:.2f} dB span, strongest response at {peak_text}"
        )


def main() -> None:
    base_text = export_netlist()
    rows = run_sweep(base_text)
    write_csv(rows)
    plot_response(rows)
    summarize(rows)
    print(f"CSV: {OUTPUT_CSV.relative_to(ROOT)}")
    print(f"Figure: {OUTPUT_PNG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
