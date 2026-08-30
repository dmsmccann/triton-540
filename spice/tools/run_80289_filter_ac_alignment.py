#!/usr/bin/env python3
"""Small-signal alignment of the 80289 coupled output filters.

A fresh KiCad netlist is used for every candidate. The saved transient command
is replaced in generated copies by an AC current excitation at the actual
single-ended filter input (U89-1 pin 6 / S89-1C common). This preserves the
loading of the mixer and buffer while exposing both coupled resonances.
"""

from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path

import numpy as np
from scipy.optimize import differential_evolution

import ngspice_raw


ROOT = Path(__file__).resolve().parents[2]
SPICE_DIR = ROOT / "spice"
STUDY_DIR = SPICE_DIR / "studies" / "80289" / "filter-response"
DATA_DIR = STUDY_DIR / "data"
GENERATED_DIR = SPICE_DIR / "generated" / "80289-filter-ac-alignment"
RUN_DIR = GENERATED_DIR / "runs"
BASE_NETLIST = GENERATED_DIR / "80289-filter-ac-base.cir"
SEARCH_CSV = DATA_DIR / "80289-vfo-filter-ac-alignment-search.csv"

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")
SCHEMATIC = ROOT / "triton_540.kicad_sch"
FILTER_INPUT = "Net-_S89-1C-C-COM_"
FILTER_OUTPUT_VECTOR = "v(net-_q89-1-g_)"

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
        return f"{value:.10g}"
    if name.startswith("VFO_T1_L"):
        return f"{value:.10g}u"
    return f"{value:.10g}p"


def make_ac_netlist(
    base_text: str,
    parameters: dict[str, float],
    s4_pos: int,
    start_mhz: float,
    stop_mhz: float,
) -> str:
    text = base_text
    for name in PARAMETER_ORDER:
        text, count = re.subn(
            rf"(?m)^\.param {re.escape(name)}=\S+\s*$",
            f".param {name}={parameter_text(name, parameters[name])}",
            text,
        )
        if count != 1:
            raise ValueError(f"Expected one {name}; found {count}")
    text, s4_count = re.subn(
        r"(?m)^\.param S4_POS=\S+\s*$",
        f".param S4_POS={s4_pos}",
        text,
    )
    if s4_count != 1:
        raise ValueError(f"Expected one S4_POS; found {s4_count}")
    text, tran_count = re.subn(r"(?m)^\.tran\s+.*$\n?", "", text)
    if tran_count != 1:
        raise ValueError(f"Expected one transient command; found {tran_count}")
    fixture = (
        f"I_FILTER_TEST GND {FILTER_INPUT} AC 1\n"
        f".ac lin 401 {start_mhz:.8g}Meg {stop_mhz:.8g}Meg\n"
        f".save {FILTER_OUTPUT_VECTOR}\n"
    )
    text, end_count = re.subn(
        r"(?m)^\.end\s*$", fixture + ".end", text
    )
    if end_count != 1:
        raise ValueError(f"Expected one .end; found {end_count}")
    return text


def run_ac(
    tag: str,
    netlist_text: str,
) -> tuple[np.ndarray, np.ndarray]:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    netlist_path = RUN_DIR / f"{tag}.cir"
    raw_path = RUN_DIR / f"{tag}.raw"
    log_path = RUN_DIR / f"{tag}.log"
    netlist_path.write_text(netlist_text, encoding="utf-8")
    completed = subprocess.run(
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
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise RuntimeError(
            f"ngspice failed for {tag}; see {log_path}"
        )
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    if "error" in log_text.lower():
        raise RuntimeError(f"ngspice error for {tag}; see {log_path}")
    names, rows = ngspice_raw.parse_ascii_raw(raw_path)
    indices = {name: index for index, name in enumerate(names)}
    required = {"frequency", FILTER_OUTPUT_VECTOR}
    missing = required - indices.keys()
    if missing:
        raise ValueError(f"{tag} is missing vectors: {sorted(missing)}")
    frequency_hz = np.asarray(
        [row[indices["frequency"]].real for row in rows]
    )
    output = np.asarray(
        [abs(row[indices[FILTER_OUTPUT_VECTOR]]) for row in rows]
    )
    return frequency_hz, output


def response_metrics(
    frequency_hz: np.ndarray,
    output: np.ndarray,
    low_mhz: float,
    high_mhz: float,
) -> dict[str, float]:
    frequency_mhz = frequency_hz / 1e6
    mask = (frequency_mhz >= low_mhz) & (frequency_mhz <= high_mhz)
    selected_frequency = frequency_mhz[mask]
    selected_db = 20.0 * np.log10(
        np.maximum(output[mask], 1e-30)
    )
    selected_db -= np.max(selected_db)
    center_mhz = 0.5 * (low_mhz + high_mhz)
    half_span = 0.5 * (high_mhz - low_mhz)
    target_db = -0.5 * (
        1.0 - ((selected_frequency - center_mhz) / half_span) ** 2
    )
    low_db = float(np.interp(low_mhz, selected_frequency, selected_db))
    center_db = float(
        np.interp(center_mhz, selected_frequency, selected_db)
    )
    high_db = float(np.interp(high_mhz, selected_frequency, selected_db))
    rms_error = float(np.sqrt(np.mean((selected_db - target_db) ** 2)))
    symmetry_error = abs(low_db - high_db)
    ripple_db = float(np.ptp(selected_db))
    score = rms_error + symmetry_error + 0.25 * ripple_db
    return {
        "score": score,
        "rms_error_db": rms_error,
        "symmetry_error_db": symmetry_error,
        "ripple_db": ripple_db,
        "low_db": low_db,
        "center_db": center_db,
        "high_db": high_db,
    }


def main() -> None:
    base_text = export_netlist()
    parameters = {
        "VFO_T1_L1": 5.4,
        "VFO_T1_L2": 5.4,
        "VFO_T1_K": 0.10,
        "VFO_C7": 19.664525,
        "VFO_C8": 6.2034036,
        "VFO_C9": 17.441186,
        "VFO_C10": 19.664525,
        "VFO_C11": 6.2034036,
        "VFO_C12": 17.441186,
    }
    search_rows: list[dict[str, float | str]] = []
    evaluation = 0

    def optimize_path(
        phase: str,
        s4_pos: int,
        low_mhz: float,
        high_mhz: float,
        variable_names: tuple[str, ...],
        bounds: list[tuple[float, float]],
        maxiter: int,
    ) -> None:
        nonlocal evaluation, parameters

        def objective(values: np.ndarray) -> float:
            nonlocal evaluation
            candidate = dict(parameters)
            for name, value in zip(variable_names, values):
                candidate[name] = float(value)
            evaluation += 1
            netlist = make_ac_netlist(
                base_text,
                candidate,
                s4_pos,
                low_mhz - 0.15 * (high_mhz - low_mhz),
                high_mhz + 0.15 * (high_mhz - low_mhz),
            )
            frequency_hz, output = run_ac(
                f"{phase}_{evaluation:04d}", netlist
            )
            metrics = response_metrics(
                frequency_hz, output, low_mhz, high_mhz
            )
            search_rows.append(
                {
                    "phase": phase,
                    "evaluation": evaluation,
                    **{name: candidate[name] for name in PARAMETER_ORDER},
                    **metrics,
                }
            )
            if evaluation % 10 == 0:
                print(
                    f"{phase}: evaluation {evaluation}, "
                    f"score={metrics['score']:.3f}",
                    flush=True,
                )
            return metrics["score"]

        result = differential_evolution(
            objective,
            bounds=bounds,
            seed=540,
            popsize=5,
            maxiter=maxiter,
            polish=True,
            updating="immediate",
            workers=1,
            tol=0.02,
        )
        for name, value in zip(variable_names, result.x):
            parameters[name] = float(value)
        print(
            f"{phase} selected score={result.fun:.3f}: "
            + ", ".join(
                f"{name}={parameters[name]:.6g}"
                for name in variable_names
            ),
            flush=True,
        )

    optimize_path(
        "t1",
        5,
        19.0,
        21.0,
        ("VFO_T1_L1", "VFO_T1_L2", "VFO_T1_K"),
        [(4.5, 8.0), (4.5, 8.0), (0.02, 0.40)],
        8,
    )
    optimize_path(
        "80m",
        1,
        12.50,
        13.00,
        ("VFO_C9", "VFO_C12"),
        [(5.0, 60.0), (5.0, 60.0)],
        6,
    )
    optimize_path(
        "40m",
        2,
        16.00,
        16.50,
        ("VFO_C8", "VFO_C11"),
        [(5.0, 60.0), (5.0, 60.0)],
        6,
    )
    optimize_path(
        "15m",
        4,
        12.00,
        12.50,
        ("VFO_C7", "VFO_C10"),
        [(5.0, 60.0), (5.0, 60.0)],
        6,
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with SEARCH_CSV.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(search_rows[0]))
        writer.writeheader()
        writer.writerows(search_rows)
    print("Selected parameters:")
    for name in PARAMETER_ORDER:
        print(f"  {name}={parameter_text(name, parameters[name])}")
    print(f"Search CSV: {SEARCH_CSV.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
