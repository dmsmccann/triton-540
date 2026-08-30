#!/usr/bin/env python3
"""Run the manual-order 80289 ten-meter alignment study.

The study uses a fresh KiCad netlist, nulls crystal feedthrough with R89-2
while the PTO is suppressed, then sweeps T1 and R89-27 with the PTO restored.
All source edits are made only in generated netlists.
"""

from __future__ import annotations

import csv
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import ngspice_raw


ROOT = Path(__file__).resolve().parents[2]
SPICE_DIR = ROOT / "spice"
STUDY_DIR = SPICE_DIR / "studies" / "80289" / "ten-meter-alignment"
DATA_DIR = STUDY_DIR / "data"
GENERATED_DIR = SPICE_DIR / "generated" / "80289-ten-meter-alignment"
RUN_DIR = GENERATED_DIR / "runs"
BASE_NETLIST = GENERATED_DIR / "80289-ten-meter-alignment-base.cir"

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")
SCHEMATIC = ROOT / "triton_540.kicad_sch"
OUT_VECTOR = "v(/vfo-80289/out)"


@dataclass(frozen=True)
class TestPoint:
    name: str
    s5_pos: int
    pto_mhz: float
    crystal_mhz: float
    wanted_mhz: float


TEST_POINTS = (
    TestPoint("19p00", 1, 5.01, 13.99, 19.00),
    TestPoint("19p25", 1, 5.26, 13.99, 19.25),
    TestPoint("19p50", 1, 5.51, 13.99, 19.50),
    TestPoint("19p50b", 2, 5.01, 14.49, 19.50),
    TestPoint("19p75", 2, 5.26, 14.49, 19.75),
    TestPoint("20p00", 2, 5.51, 14.49, 20.00),
    TestPoint("20p00b", 3, 5.01, 14.99, 20.00),
    TestPoint("20p25", 3, 5.26, 14.99, 20.25),
    TestPoint("20p50", 3, 5.51, 14.99, 20.50),
    TestPoint("20p50b", 4, 5.01, 15.49, 20.50),
    TestPoint("20p75", 4, 5.26, 15.49, 20.75),
    TestPoint("21p00", 4, 5.51, 15.49, 21.00),
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


def replace_one(text: str, pattern: str, replacement: str, label: str) -> str:
    changed, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"Expected one {label}; found {count}")
    return changed


def make_netlist(
    base_text: str,
    point: TestPoint,
    r2_position: float,
    r27_position: float,
    t1_l_uh: float,
    t1_k: float,
    pto_enabled: bool = True,
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
        r"^\.param VFO_T1_L1=\S+\s*$",
        f".param VFO_T1_L1={t1_l_uh:.6g}u",
        "VFO_T1_L1",
    )
    text = replace_one(
        text,
        r"^\.param VFO_T1_L2=\S+\s*$",
        f".param VFO_T1_L2={t1_l_uh:.6g}u",
        "VFO_T1_L2",
    )
    text = replace_one(
        text,
        r"^\.param VFO_T1_K=\S+\s*$",
        f".param VFO_T1_K={t1_k:.6g}",
        "VFO_T1_K",
    )
    pto_amplitude = "300m" if pto_enabled else "0"
    text = replace_one(
        text,
        r"^V_PTO_IDEAL\s+.*$",
        "V_PTO_IDEAL net-_Q89-5-E_ 0 DC 1.7 "
        f"SIN(1.7 {pto_amplitude} {point.pto_mhz:.6g}Meg)",
        "PTO source",
    )
    text = replace_one(
        text,
        r"^(XR89-2\s+.*?\s+POT_POSITION)\s+.*$",
        rf"\1 R=1k POS={r2_position:.6g}",
        "R89-2 instance",
    )
    text = replace_one(
        text,
        r"^(XR89-27\s+.*?\s+POT_POSITION)\s+.*$",
        rf"\1 R=1k POS={r27_position:.6g}",
        "R89-27 instance",
    )
    return replace_one(
        text, r"^\.end\s*$", f".save {OUT_VECTOR}\n.end", ".end directive"
    )


def run_case(tag: str, netlist_text: str) -> tuple[np.ndarray, np.ndarray]:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    netlist_path = RUN_DIR / f"{tag}.cir"
    raw_path = RUN_DIR / f"{tag}.raw"
    log_path = RUN_DIR / f"{tag}.log"
    netlist_path.write_text(netlist_text, encoding="utf-8")
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
    names, rows = ngspice_raw.parse_ascii_raw(raw_path)
    indices = {name: index for index, name in enumerate(names)}
    time_s = np.asarray([row[indices["time"]].real for row in rows])
    output_v = np.asarray([row[indices[OUT_VECTOR]].real for row in rows])
    uniform_time_s = 60e-6 + np.arange(20_000) * 2e-9
    return uniform_time_s, np.interp(uniform_time_s, time_s, output_v)


def tone_vpp(time_s: np.ndarray, values: np.ndarray, frequency_mhz: float) -> float:
    angle = 2.0 * np.pi * frequency_mhz * 1e6 * time_s
    design = np.column_stack(
        (np.sin(angle), np.cos(angle), np.ones(time_s.size))
    )
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    return float(2.0 * np.hypot(coefficients[0], coefficients[1]))


def dominant_frequency_mhz(time_s: np.ndarray, values: np.ndarray) -> float:
    selected = values - np.mean(values)
    spectrum = np.abs(np.fft.rfft(selected * np.hanning(selected.size)))
    frequencies = np.fft.rfftfreq(selected.size, 2e-9)
    valid = (frequencies >= 10e6) & (frequencies <= 25e6)
    valid_indices = np.flatnonzero(valid)
    return float(
        frequencies[valid_indices[int(np.argmax(spectrum[valid]))]] / 1e6
    )


def measure(
    base_text: str,
    tag: str,
    point: TestPoint,
    r2_position: float,
    r27_position: float,
    t1_l_uh: float,
    t1_k: float,
    pto_enabled: bool = True,
) -> dict[str, float | str | int]:
    netlist = make_netlist(
        base_text,
        point,
        r2_position,
        r27_position,
        t1_l_uh,
        t1_k,
        pto_enabled,
    )
    time_s, output_v = run_case(tag, netlist)
    wanted_vpp = tone_vpp(time_s, output_v, point.wanted_mhz)
    crystal_vpp = tone_vpp(time_s, output_v, point.crystal_mhz)
    return {
        "test_point": point.name,
        "s5_pos": point.s5_pos,
        "pto_mhz": point.pto_mhz,
        "crystal_mhz": point.crystal_mhz,
        "wanted_mhz": point.wanted_mhz,
        "r2_position": r2_position,
        "r27_position": r27_position,
        "t1_l_uh": t1_l_uh,
        "t1_k": t1_k,
        "pto_enabled": int(pto_enabled),
        "wanted_mvpp": wanted_vpp * 1e3,
        "crystal_mvpp": crystal_vpp * 1e3,
        "wanted_to_crystal_ratio": wanted_vpp / max(crystal_vpp, 1e-15),
        "total_mvpp": float(np.ptp(output_v) * 1e3),
        "dominant_mhz": dominant_frequency_mhz(time_s, output_v),
    }


def write_csv(path: Path, rows: list[dict[str, float | str | int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def aggregate_sweep(
    base_text: str,
    prefix: str,
    values: list[float],
    value_name: str,
    points: tuple[TestPoint, ...],
    r2_position: float,
    r27_position: float,
    t1_l_uh: float,
    t1_k: float,
) -> tuple[float, list[dict[str, float | str]]]:
    aggregates: list[dict[str, float | str]] = []
    for value in values:
        settings = {
            "r2_position": r2_position,
            "r27_position": r27_position,
            "t1_l_uh": t1_l_uh,
            "t1_k": t1_k,
        }
        settings[value_name] = value
        measurements = [
            measure(
                base_text,
                f"{prefix}_{value:.6g}_{point.name}".replace(".", "p"),
                point,
                **settings,
            )
            for point in points
        ]
        minimum_wanted = min(float(row["wanted_mvpp"]) for row in measurements)
        maximum_crystal = max(float(row["crystal_mvpp"]) for row in measurements)
        minimum_ratio = min(
            float(row["wanted_to_crystal_ratio"]) for row in measurements
        )
        score = minimum_wanted * min(minimum_ratio, 20.0)
        aggregates.append(
            {
                value_name: value,
                "minimum_wanted_mvpp": minimum_wanted,
                "maximum_crystal_mvpp": maximum_crystal,
                "minimum_wanted_to_crystal_ratio": minimum_ratio,
                "score": score,
            }
        )
    best = max(aggregates, key=lambda row: float(row["score"]))
    return float(best[value_name]), aggregates


def main() -> None:
    base_text = export_netlist()
    balance_point = TEST_POINTS[1]

    balance_rows: list[dict[str, float | str | int]] = []
    coarse_positions = [float(value) for value in np.linspace(0.05, 0.95, 10)]
    for position in coarse_positions:
        balance_rows.append(
            measure(
                base_text,
                f"balance_coarse_{position:.3f}".replace(".", "p"),
                balance_point,
                position,
                0.5,
                5.3,
                0.08,
                pto_enabled=False,
            )
        )
    coarse_best = min(
        balance_rows, key=lambda row: float(row["crystal_mvpp"])
    )
    center = float(coarse_best["r2_position"])
    refine_positions = sorted(
        {
            round(float(np.clip(center + offset, 0.001, 0.999)), 6)
            for offset in np.linspace(-0.08, 0.08, 17)
        }
    )
    for position in refine_positions:
        balance_rows.append(
            measure(
                base_text,
                f"balance_refine_{position:.3f}".replace(".", "p"),
                balance_point,
                position,
                0.5,
                5.3,
                0.08,
                pto_enabled=False,
            )
        )
    balance_best = min(
        balance_rows, key=lambda row: float(row["crystal_mvpp"])
    )
    r2_best = float(balance_best["r2_position"])
    write_csv(DATA_DIR / "80289-r89-2-balance-sweep.csv", balance_rows)

    edge_points = (TEST_POINTS[0], TEST_POINTS[-1])
    l_best, l_rows = aggregate_sweep(
        base_text,
        "t1_l",
        [4.5, 4.875, 5.25, 5.625, 6.0, 6.375, 6.75, 7.125, 7.5],
        "t1_l_uh",
        edge_points,
        r2_best,
        0.5,
        5.3,
        0.08,
    )
    write_csv(DATA_DIR / "80289-t1-inductance-sweep.csv", l_rows)

    three_points = (TEST_POINTS[0], TEST_POINTS[5], TEST_POINTS[-1])
    k_best, k_rows = aggregate_sweep(
        base_text,
        "t1_k",
        [0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.18],
        "t1_k",
        three_points,
        r2_best,
        0.5,
        l_best,
        0.08,
    )
    write_csv(DATA_DIR / "80289-t1-coupling-sweep.csv", k_rows)

    r27_best, injection_rows = aggregate_sweep(
        base_text,
        "r27",
        [0.10, 0.233, 0.367, 0.50, 0.633, 0.767, 0.90],
        "r27_position",
        three_points,
        r2_best,
        0.5,
        l_best,
        k_best,
    )
    write_csv(DATA_DIR / "80289-r89-27-injection-sweep.csv", injection_rows)

    coverage_rows = [
        measure(
            base_text,
            f"aligned_{point.name}",
            point,
            r2_best,
            r27_best,
            l_best,
            k_best,
        )
        for point in TEST_POINTS
    ]
    write_csv(DATA_DIR / "80289-ten-meter-aligned-coverage.csv", coverage_rows)

    minimum_ratio = min(
        float(row["wanted_to_crystal_ratio"]) for row in coverage_rows
    )
    minimum_wanted = min(float(row["wanted_mvpp"]) for row in coverage_rows)
    print(f"R89-2 position: {r2_best:.6f}")
    print(f"R89-27 position: {r27_best:.6f}")
    print(f"T1 inductance: {l_best:.6f} uH")
    print(f"T1 coupling: {k_best:.6f}")
    print(f"Minimum wanted output: {minimum_wanted:.3f} mVpp")
    print(f"Minimum wanted/crystal ratio: {minimum_ratio:.3f}")
    print(f"Data: {DATA_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
