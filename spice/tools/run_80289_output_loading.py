#!/usr/bin/env python3
"""Compare the 80289 output under 50-ohm and light instrument loading."""

from __future__ import annotations

import csv
import re

import numpy as np

import run_80289_filter_response as study
import run_80289_frequency_plan as coverage


OUTPUT_CSV = study.DATA_DIR / "80289-vfo-output-loading-comparison.csv"
LOADS = (("50 ohm", 50.0), ("1 Mohm", 1e6))


def set_load(netlist_text: str, load_ohm: float) -> str:
    text, count = re.subn(
        r"(?m)^(R89-89\s+\S+\s+\S+)\s+\S+\s*$",
        rf"\1 {load_ohm:.9g}",
        netlist_text,
    )
    if count != 1:
        raise ValueError(f"Expected one R89-89 load; found {count}")
    return text


def main() -> None:
    base_text = study.export_netlist()
    rows: list[dict[str, float | int | str]] = []
    for path in study.FILTERS:
        test_frequencies = (
            path.manual_low_mhz,
            0.5 * (path.manual_low_mhz + path.manual_high_mhz),
            path.manual_high_mhz,
        )
        for wanted_mhz in test_frequencies:
            s5_pos, crystal_mhz = study.crystal_selection(path, wanted_mhz)
            pto_mhz = wanted_mhz - crystal_mhz
            base_case = study.make_netlist(
                base_text, path, s5_pos, pto_mhz
            )
            for load_name, load_ohm in LOADS:
                tag = (
                    f"load_{path.name.replace(' ', '').lower()}_"
                    f"{wanted_mhz:.3f}_{int(load_ohm)}"
                ).replace(".", "p")
                time_s, traces = study.run_case(
                    tag, set_load(base_case, load_ohm)
                )
                output_vpp = coverage.fitted_tone_vpp(
                    time_s,
                    traces["vfo_out_v"],
                    wanted_mhz * 1e6,
                )
                rows.append(
                    {
                        "filter_path": path.name,
                        "s4_pos": path.s4_pos,
                        "s5_pos": s5_pos if path.s4_pos == 5 else "",
                        "wanted_frequency_mhz": wanted_mhz,
                        "test_point": (
                            "low"
                            if wanted_mhz == path.manual_low_mhz
                            else "high"
                            if wanted_mhz == path.manual_high_mhz
                            else "center"
                        ),
                        "load": load_name,
                        "load_ohm": load_ohm,
                        "wanted_output_mvpp": 1e3 * output_vpp,
                    }
                )
                print(
                    f"{path.name} {wanted_mhz:.3f} MHz, {load_name}: "
                    f"{1e3 * output_vpp:.2f} mVpp",
                    flush=True,
                )

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            formatted = dict(row)
            formatted["wanted_frequency_mhz"] = (
                f"{float(row['wanted_frequency_mhz']):.6f}"
            )
            formatted["load_ohm"] = f"{float(row['load_ohm']):.6f}"
            formatted["wanted_output_mvpp"] = (
                f"{float(row['wanted_output_mvpp']):.6f}"
            )
            writer.writerow(formatted)

    for path in study.FILTERS:
        selected = [row for row in rows if row["filter_path"] == path.name]
        print(path.name + ":")
        for load_name, _ in LOADS:
            amplitudes = np.asarray(
                [
                    float(row["wanted_output_mvpp"])
                    for row in selected
                    if row["load"] == load_name
                ]
            )
            print(
                f"  {load_name}: {np.min(amplitudes):.2f}-"
                f"{np.max(amplitudes):.2f} mVpp"
            )
    print(f"CSV: {OUTPUT_CSV.relative_to(study.ROOT)}")


if __name__ == "__main__":
    main()
