#!/usr/bin/env python3
"""Run the 80279 open-loop PIN-diode AGC attenuation study.

The board schematic is exported afresh for every invocation. The saved
I79-SIM1 fixture is disabled for normal simulations; disposable netlist copies
open D79-5 and enable that same named source on the labeled PIN_BIAS bus.
Curated CSVs and figures are retained below spice/studies/80279.
"""

from __future__ import annotations

import csv
import math
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMATIC = ROOT / "if-agc_80279.kicad_sch"
STUDY_DIR = ROOT / "spice" / "studies" / "80279" / "pin-agc-sweep"
DATA_DIR = STUDY_DIR / "data"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = ROOT / "spice" / "generated" / "80279-pin-agc-sweep"
BASE_NETLIST = GENERATED_DIR / "80279-pin-agc-sweep-base.cir"

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")

START_HZ = 8.8e6
STOP_HZ = 9.2e6
POINTS = 2001
TARGET_HZ = 9.0e6
FEED_RESISTANCE_OHM = 1000.0
PIN_R_NUMERATOR = 8e-3
PIN_R_FLOOR_OHM = 0.4
PIN_CURRENT_FLOOR_A = 1e-9

PIN_CURRENTS_A = (
    0.0,
    1e-6,
    3e-6,
    10e-6,
    30e-6,
    100e-6,
    300e-6,
    1e-3,
    3e-3,
    10e-3,
    12e-3,
    20e-3,
)

PIN_ANODES = (
    ("d79_1", "Net-_D79-1-A_"),
    ("d79_2", "Net-_D79-2-A_"),
    ("d79_3", "Net-_D79-3-A_"),
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


def export_netlist() -> str:
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
    text = BASE_NETLIST.read_text(encoding="utf-8")
    required = (
        "D79-5 Net-_D79-5-A_ /PIN_BIAS 1N4154",
        "R79-17 Net-_D79-3-A_ /PIN_BIAS 1k",
        "R79-18 Net-_D79-2-A_ /PIN_BIAS 1k",
        "R79-19 Net-_D79-1-A_ /PIN_BIAS 1k",
        "XD79-1 GND Net-_D79-1-A_ HP5082_3379",
        "XD79-2 GND Net-_D79-2-A_ HP5082_3379",
        "XD79-3 GND Net-_D79-3-A_ HP5082_3379",
    )
    for line in required:
        if line not in text:
            raise ValueError(f"Fresh KiCad export is missing required topology: {line}")
    if "I79-SIM1" in text:
        raise ValueError("I79-SIM1 must remain disabled in the normal saved schematic")
    return text


def current_slug(current_a: float) -> str:
    return f"{current_a * 1e3:08.4f}".replace(".", "p")


def build_case(base_text: str, pin_current_a: float) -> tuple[Path, Path, Path, Path]:
    slug = current_slug(pin_current_a)
    case_dir = GENERATED_DIR / "cases-current" / f"pin-current-{slug}ma"
    case_dir.mkdir(parents=True, exist_ok=True)
    netlist = case_dir / "case.cir"
    bias_data = case_dir / "bias.dat"
    response_data = case_dir / "response.dat"
    log_path = case_dir / "ngspice.log"

    text, count = re.subn(
        r"(?m)^D79-5\s+.*$",
        "* Simulation 3: D79-5 open; I79-SIM1 controls PIN_BIAS",
        base_text,
        count=1,
    )
    if count != 1:
        raise ValueError(f"Expected one D79-5 line; found {count}")

    total_current_a = 3.0 * pin_current_a
    commands = [
        f"I79-SIM1 GND /PIN_BIAS DC {total_current_a:.12g}",
        ".control",
        "set wr_singlescale",
        "set wr_vecnames",
        "op",
        "wrdata bias.dat v(/PIN_BIAS) "
        + " ".join(f"v({node})" for _, node in PIN_ANODES),
        f"ac lin {POINTS} {START_HZ:g} {STOP_HZ:g}",
        "wrdata response.dat mag(v(Net-_Q79-3-G1_))",
        "quit",
        ".endc",
        ".end",
    ]
    text, end_count = re.subn(
        r"(?m)^\.end\s*$",
        "\n".join(commands),
        text,
        count=1,
    )
    if end_count != 1:
        raise ValueError(f"Expected one .end directive; found {end_count}")
    netlist.write_text(text, encoding="utf-8")
    return netlist, bias_data, response_data, log_path


def run_case(netlist: Path, log_path: Path) -> None:
    if not NGSPICE.exists():
        raise SystemExit(f"ngspice was not found: {NGSPICE}")
    run(
        [
            str(NGSPICE),
            "-b",
            "-D",
            "ngbehavior=ltpsa",
            "-o",
            str(log_path),
            str(netlist),
        ],
        netlist.parent,
    )


def read_numeric_rows(path: Path) -> tuple[list[str], list[list[float]]]:
    if not path.exists():
        raise ValueError(f"ngspice did not create {path}")
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError(f"No numerical rows in {path}")
    header = lines[0].split()
    rows = [[float(value) for value in line.split()] for line in lines[1:]]
    return header, rows


def interpolate(rows: list[tuple[float, float]], frequency: float) -> float:
    for left, right in zip(rows, rows[1:]):
        if left[0] <= frequency <= right[0]:
            fraction = (frequency - left[0]) / (right[0] - left[0])
            return left[1] + fraction * (right[1] - left[1])
    return min(rows, key=lambda row: abs(row[0] - frequency))[1]


def pin_resistance(current_a: float) -> float:
    return max(
        PIN_R_FLOOR_OHM,
        PIN_R_NUMERATOR / max(abs(current_a), PIN_CURRENT_FLOOR_A),
    )


def parse_case(
    target_pin_current_a: float, bias_path: Path, response_path: Path
) -> tuple[dict[str, float], list[tuple[float, float]]]:
    _, bias_rows = read_numeric_rows(bias_path)
    if len(bias_rows) != 1 or len(bias_rows[0]) != len(PIN_ANODES) + 2:
        raise ValueError(f"Unexpected operating-point shape in {bias_path}: {bias_rows}")
    _, bus_voltage, *anode_voltages = bias_rows[0]

    _, response_rows = read_numeric_rows(response_path)
    response: list[tuple[float, float]] = []
    for row in response_rows:
        if len(row) != 2:
            raise ValueError(f"Unexpected AC row in {response_path}: {row}")
        response.append((row[0], 20.0 * math.log10(max(row[1], 1e-300))))
    if len(response) != POINTS:
        raise ValueError(f"Expected {POINTS} AC rows, found {len(response)}")

    currents = [
        max(0.0, (bus_voltage - anode_voltage) / FEED_RESISTANCE_OHM)
        for anode_voltage in anode_voltages
    ]
    result: dict[str, float] = {
        "target_per_diode_current_a": target_pin_current_a,
        "forced_total_bus_current_a": 3.0 * target_pin_current_a,
        "pin_bias_bus_v": bus_voltage,
        "gain_at_9mhz_db": interpolate(response, TARGET_HZ),
        "peak_gain_db": max(value for _, value in response),
        "peak_frequency_hz": max(response, key=lambda row: row[1])[0],
    }
    for (key, _), current in zip(PIN_ANODES, currents):
        result[f"{key}_current_a"] = current
        result[f"{key}_modeled_rf_resistance_ohm"] = pin_resistance(current)
    return result, response


def write_results(
    summaries: list[dict[str, float]],
    responses: dict[float, list[tuple[float, float]]],
) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    reference_gain = summaries[0]["gain_at_9mhz_db"]
    for row in summaries:
        row["attenuation_at_9mhz_db"] = reference_gain - row["gain_at_9mhz_db"]

    summary_path = DATA_DIR / "80279-pin-agc-sweep-summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summaries[0].keys()))
        writer.writeheader()
        writer.writerows(summaries)

    family_path = DATA_DIR / "80279-pin-agc-response-family.csv"
    family_rows: list[dict[str, float]] = []
    for current_a, rows in responses.items():
        for frequency, gain_db in rows:
            family_rows.append(
                {
                    "target_per_diode_current_a": current_a,
                    "frequency_hz": frequency,
                    "q79_3_gate1_gain_db": gain_db,
                }
            )
    with family_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(family_rows[0].keys()))
        writer.writeheader()
        writer.writerows(family_rows)


def validate_results(summaries: list[dict[str, float]]) -> None:
    reference_gain = summaries[0]["gain_at_9mhz_db"]
    previous_attenuation = -1e-9
    for row in summaries:
        target = row["target_per_diode_current_a"]
        for key in ("d79_1_current_a", "d79_2_current_a", "d79_3_current_a"):
            actual = row[key]
            tolerance = max(1e-12, abs(target) * 1e-6)
            if abs(actual - target) > tolerance:
                raise ValueError(f"{key}={actual} A does not match target {target} A")
        attenuation = reference_gain - row["gain_at_9mhz_db"]
        if attenuation + 1e-6 < previous_attenuation:
            raise ValueError("9 MHz attenuation is not monotonic with PIN current")
        previous_attenuation = attenuation


def write_figures(
    summaries: list[dict[str, float]],
    responses: dict[float, list[tuple[float, float]]],
) -> None:
    import matplotlib.pyplot as plt

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    family_currents = (0.0, 10e-6, 100e-6, 1e-3, 10e-3, 12e-3)
    fig, axis = plt.subplots(figsize=(9.2, 5.7))
    for current_a in family_currents:
        rows = responses[current_a]
        axis.plot(
            [frequency / 1e6 for frequency, _ in rows],
            [gain for _, gain in rows],
            linewidth=1.6,
            label=f"{current_a * 1e3:g} mA per PIN diode",
        )
    axis.axvline(9.0, color="black", linestyle="--", linewidth=1.0)
    axis.set_title("Ten-Tec 80279 open-loop PIN-diode IF attenuation")
    axis.set_xlabel("Frequency (MHz)")
    axis.set_ylabel("Transfer from IN to Q79-3 G1 (dB)")
    axis.grid(True, alpha=0.28)
    axis.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "80279-pin-agc-response-family.png", dpi=180)
    plt.close(fig)

    pin_currents_ma = [row["target_per_diode_current_a"] * 1e3 for row in summaries]
    fig, (gain_axis, device_axis) = plt.subplots(2, 1, figsize=(9.2, 7.6), sharex=True)
    gain_axis.plot(
        pin_currents_ma,
        [row["attenuation_at_9mhz_db"] for row in summaries],
        marker="o",
        linewidth=1.8,
        color="#b11f24",
    )
    gain_axis.set_ylabel("Attenuation at 9 MHz (dB)")
    gain_axis.set_title("80279 open-loop PIN-bias control characteristic")
    gain_axis.grid(True, alpha=0.28)
    gain_axis.set_xscale("symlog", linthresh=0.001)

    device_axis.semilogy(
        pin_currents_ma,
        [max(row["d79_1_current_a"] * 1e3, 1e-9) for row in summaries],
        marker="o",
        linewidth=1.6,
        label="D79-1 forward current (mA)",
    )
    device_axis.semilogy(
        pin_currents_ma,
        [row["d79_1_modeled_rf_resistance_ohm"] for row in summaries],
        marker="s",
        linewidth=1.6,
        label="D79-1 modeled RF resistance (ohm)",
    )
    device_axis.set_xlabel("Forced forward current per PIN diode (mA)")
    device_axis.set_ylabel("Log scale")
    device_axis.grid(True, which="both", alpha=0.28)
    device_axis.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "80279-pin-agc-control-characteristic.png", dpi=180)
    plt.close(fig)


def write_manifest() -> None:
    rows = [
        ("data/80279-pin-agc-sweep-summary.csv", "9 MHz gain, attenuation, PIN currents, and modeled RF resistances"),
        ("data/80279-pin-agc-response-family.csv", "Complete 8.8-9.2 MHz response at every forced control voltage"),
        ("figures/80279-pin-agc-response-family.png", "Representative IF-response family"),
        ("figures/80279-pin-agc-control-characteristic.png", "9 MHz attenuation and D79-1 model characteristic"),
    ]
    STUDY_DIR.mkdir(parents=True, exist_ok=True)
    with (STUDY_DIR / "manifest.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("path", "purpose"))
        writer.writerows(rows)


def main() -> None:
    base_text = export_netlist()
    summaries: list[dict[str, float]] = []
    responses: dict[float, list[tuple[float, float]]] = {}
    for pin_current_a in PIN_CURRENTS_A:
        netlist, bias_path, response_path, log_path = build_case(base_text, pin_current_a)
        run_case(netlist, log_path)
        summary, response = parse_case(pin_current_a, bias_path, response_path)
        summaries.append(summary)
        responses[pin_current_a] = response
        print(
            f"target={pin_current_a * 1e3:8.4f} mA/PIN  "
            f"PIN_BIAS={summary['pin_bias_bus_v']:8.4f} V  "
            f"I(D79-1)={summary['d79_1_current_a'] * 1e3:9.5f} mA  "
            f"gain@9MHz={summary['gain_at_9mhz_db']:8.3f} dB"
        )
    validate_results(summaries)
    write_results(summaries, responses)
    write_figures(summaries, responses)
    write_manifest()
    reference = summaries[0]["gain_at_9mhz_db"]
    maximum_attenuation = reference - summaries[-1]["gain_at_9mhz_db"]
    print(f"reference_gain_at_9mhz_db={reference:.6f}")
    print(f"maximum_modeled_attenuation_db={maximum_attenuation:.6f}")


if __name__ == "__main__":
    main()
