#!/usr/bin/env python3
"""Align the estimated 80289 switched-filter parameters.

This is a bounded coordinate search using fresh schematic-derived transient
netlists. It first centers T1, then adjusts coupling and independent winding
inductance, and finally centers each switched trimmer pair.
"""

from __future__ import annotations

import csv
import math
import re
import subprocess
from pathlib import Path

import numpy as np

import run_80289_filter_response as response
import run_80289_frequency_plan as coverage


ROOT = Path(__file__).resolve().parents[2]
SPICE_DIR = ROOT / "spice"
STUDY_DIR = SPICE_DIR / "studies" / "80289" / "filter-response"
DATA_DIR = STUDY_DIR / "data"
GENERATED_DIR = SPICE_DIR / "generated" / "80289-filter-alignment"
RUN_DIR = GENERATED_DIR / "runs"
BASE_NETLIST = GENERATED_DIR / "80289-vfo-filter-alignment-base.cir"
OUTPUT_CSV = DATA_DIR / "80289-vfo-filter-alignment-search.csv"

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
SCHEMATIC = ROOT / "triton_540.kicad_sch"

PARAMETER_ORDER = (
    "VFO_T1_L1",
    "VFO_T1_L2",
    "VFO_T1_K",
    "VFO_C7",
    "VFO_C8",
    "VFO_C9",
    "VFO_C10",
    "VFO_C11",
    "VFO_C12",
)


def export_netlist() -> str:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
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
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        print(completed.stdout, end="")
        print(completed.stderr, end="")
        raise SystemExit(
            f"KiCad netlist export failed with {completed.returncode}"
        )
    return BASE_NETLIST.read_text(encoding="utf-8")


def parameter_text(name: str, value: float) -> str:
    if name == "VFO_T1_K":
        return f"{value:.8g}"
    if name.startswith("VFO_T1_L"):
        return f"{value:.8g}u"
    return f"{value:.8g}p"


def apply_parameters(base_text: str, parameters: dict[str, float]) -> str:
    text = base_text
    for name in PARAMETER_ORDER:
        replacement = f".param {name}={parameter_text(name, parameters[name])}"
        text, count = re.subn(
            rf"(?m)^\.param {re.escape(name)}=\S+\s*$",
            replacement,
            text,
        )
        if count != 1:
            raise ValueError(f"Expected one {name} parameter; found {count}")
    return text


def path_by_name(name: str) -> response.FilterPath:
    return next(path for path in response.FILTERS if path.name == name)


def evaluate(
    base_text: str,
    parameters: dict[str, float],
    phase: str,
    candidate: str,
    path: response.FilterPath,
    frequencies_mhz: list[float],
    rows: list[dict[str, float | int | str]],
) -> list[dict[str, float]]:
    parameterized_text = apply_parameters(base_text, parameters)
    measurements: list[dict[str, float]] = []
    for frequency_mhz in frequencies_mhz:
        s5_pos, crystal_mhz = response.crystal_selection(
            path, frequency_mhz
        )
        pto_mhz = frequency_mhz - crystal_mhz
        tag = (
            f"{phase}_{candidate}_{path.name.replace(' ', '').lower()}_"
            f"{frequency_mhz:.3f}"
        ).replace(".", "p")
        netlist_text = response.make_netlist(
            parameterized_text, path, s5_pos, pto_mhz
        )
        time_s, traces = response.run_case(tag, netlist_text)
        raw_vpp = coverage.fitted_tone_vpp(
            time_s, traces["mixer_raw_v"], frequency_mhz * 1e6
        )
        filter_input_vpp = coverage.fitted_tone_vpp(
            time_s, traces["mixer_positive_v"], frequency_mhz * 1e6
        )
        filter_vpp = coverage.fitted_tone_vpp(
            time_s, traces["filter_output_v"], frequency_mhz * 1e6
        )
        out_vpp = coverage.fitted_tone_vpp(
            time_s, traces["vfo_out_v"], frequency_mhz * 1e6
        )
        measurement = {
            "frequency_mhz": frequency_mhz,
            "filter_gain_db": response.safe_gain_db(
                filter_vpp, filter_input_vpp
            ),
            "loaded_out_mvpp": 1e3 * out_vpp,
        }
        measurements.append(measurement)
        rows.append(
            {
                "phase": phase,
                "candidate": candidate,
                "filter_path": path.name,
                **{name: parameters[name] for name in PARAMETER_ORDER},
                "raw_mixer_mvpp": 1e3 * raw_vpp,
                "filter_input_mvpp": 1e3 * filter_input_vpp,
                "filter_output_mvpp": 1e3 * filter_vpp,
                **measurement,
            }
        )
    return measurements


def score(measurements: list[dict[str, float]]) -> float:
    gains = np.asarray([item["filter_gain_db"] for item in measurements])
    span = float(np.ptp(gains))
    edge_imbalance = float(abs(gains[0] - gains[-1]))
    center = float(gains[len(gains) // 2])
    lower_edge = float(min(gains[0], gains[-1]))
    center_above_edges = max(0.0, center - lower_edge)
    return span + edge_imbalance + 2.0 * center_above_edges


def select_candidate(
    base_text: str,
    candidates: list[tuple[str, dict[str, float]]],
    phase: str,
    path: response.FilterPath,
    frequencies_mhz: list[float],
    rows: list[dict[str, float | int | str]],
) -> dict[str, float]:
    scored: list[tuple[float, str, dict[str, float]]] = []
    for index, (label, parameters) in enumerate(candidates, start=1):
        measurements = evaluate(
            base_text,
            parameters,
            phase,
            label,
            path,
            frequencies_mhz,
            rows,
        )
        candidate_score = score(measurements)
        scored.append((candidate_score, label, parameters))
        print(
            f"{phase} {index}/{len(candidates)} {label}: "
            f"score={candidate_score:.3f} dB",
            flush=True,
        )
    best_score, best_label, best_parameters = min(
        scored, key=lambda item: item[0]
    )
    print(
        f"{phase} selected {best_label}, score={best_score:.3f} dB",
        flush=True,
    )
    return dict(best_parameters)


def calculated_capacitance_pf(
    frequency_mhz: float, inductance_uh: float
) -> float:
    total_f = 1.0 / (
        4.0
        * math.pi**2
        * (frequency_mhz * 1e6) ** 2
        * inductance_uh
        * 1e-6
    )
    return 1e12 * total_f - 10.0


def write_csv(rows: list[dict[str, float | int | str]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    response.RUN_DIR = RUN_DIR
    base_text = export_netlist()
    rows: list[dict[str, float | int | str]] = []
    parameters = {
        "VFO_T1_L1": 6.35,
        "VFO_T1_L2": 6.35,
        "VFO_T1_K": 0.10,
        "VFO_C7": 16.6,
        "VFO_C8": 5.1,
        "VFO_C9": 14.5,
        "VFO_C10": 16.6,
        "VFO_C11": 5.1,
        "VFO_C12": 14.5,
    }

    ten_meter = path_by_name("10 m")
    ten_meter_points = [19.0, 19.5, 20.0, 20.5, 21.0]
    l_candidates = []
    for inductance_uh in (5.0, 5.2, 5.4, 5.6, 5.8, 6.0):
        candidate = dict(parameters)
        candidate["VFO_T1_L1"] = inductance_uh
        candidate["VFO_T1_L2"] = inductance_uh
        l_candidates.append((f"l{inductance_uh:.2f}", candidate))
    parameters = select_candidate(
        base_text,
        l_candidates,
        "t1_inductance",
        ten_meter,
        ten_meter_points,
        rows,
    )

    k_candidates = []
    for coupling in (0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.18):
        candidate = dict(parameters)
        candidate["VFO_T1_K"] = coupling
        k_candidates.append((f"k{coupling:.2f}", candidate))
    parameters = select_candidate(
        base_text,
        k_candidates,
        "t1_coupling",
        ten_meter,
        ten_meter_points,
        rows,
    )

    mean_inductance = 0.5 * (
        parameters["VFO_T1_L1"] + parameters["VFO_T1_L2"]
    )
    split_candidates = []
    for split in (-0.10, -0.05, 0.0, 0.05, 0.10):
        candidate = dict(parameters)
        candidate["VFO_T1_L1"] = mean_inductance * (1.0 + split)
        candidate["VFO_T1_L2"] = mean_inductance * (1.0 - split)
        split_candidates.append((f"split{split:+.2f}", candidate))
    parameters = select_candidate(
        base_text,
        split_candidates,
        "t1_slug_split",
        ten_meter,
        ten_meter_points,
        rows,
    )

    capacitor_paths = (
        ("80 m", "VFO_C9", "VFO_C12"),
        ("40 m", "VFO_C8", "VFO_C11"),
        ("15 m", "VFO_C7", "VFO_C10"),
    )
    for path_name, primary_name, secondary_name in capacitor_paths:
        path = path_by_name(path_name)
        center_mhz = 0.5 * (path.manual_low_mhz + path.manual_high_mhz)
        base_primary_pf = calculated_capacitance_pf(
            center_mhz, parameters["VFO_T1_L1"]
        )
        base_secondary_pf = calculated_capacitance_pf(
            center_mhz, parameters["VFO_T1_L2"]
        )
        coarse_candidates = []
        for scale in (0.85, 0.925, 1.0, 1.075, 1.15):
            candidate = dict(parameters)
            candidate[primary_name] = max(5.0, base_primary_pf * scale)
            candidate[secondary_name] = max(5.0, base_secondary_pf * scale)
            coarse_candidates.append((f"scale{scale:.3f}", candidate))
        parameters = select_candidate(
            base_text,
            coarse_candidates,
            f"{path_name.replace(' ', '').lower()}_coarse",
            path,
            [
                path.manual_low_mhz,
                center_mhz,
                path.manual_high_mhz,
            ],
            rows,
        )

        coarse_primary = parameters[primary_name]
        coarse_secondary = parameters[secondary_name]
        fine_candidates = []
        for scale in (0.94, 0.97, 1.0, 1.03, 1.06):
            candidate = dict(parameters)
            candidate[primary_name] = max(5.0, coarse_primary * scale)
            candidate[secondary_name] = max(5.0, coarse_secondary * scale)
            fine_candidates.append((f"fine{scale:.3f}", candidate))
        parameters = select_candidate(
            base_text,
            fine_candidates,
            f"{path_name.replace(' ', '').lower()}_fine",
            path,
            [
                path.manual_low_mhz,
                center_mhz,
                path.manual_high_mhz,
            ],
            rows,
        )

    write_csv(rows)
    print("Selected parameters:")
    for name in PARAMETER_ORDER:
        print(f"  {name}={parameter_text(name, parameters[name])}")
    print(f"Search CSV: {OUTPUT_CSV.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
