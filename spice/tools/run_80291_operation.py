#!/usr/bin/env python3
"""Reproduce the 80291 band-filter operation study.

The KiCad sheet is the component and topology source.  This runner exports a
fresh SPICE netlist from bandpass_80291.kicad_sch, asserts that every filter
part and board-pin connection matches the manual (PDF page 41, printed page
3-25), and then places pin-level test fixtures around that exported circuit:

* bench      - 50 ohm generator into each -I pin, 50 ohm load on each -O pin.
               This is what a restorer can reproduce with the board unplugged.
* load-200 / load-1k
             - the same generator with 200 ohm and 1 kohm loads, because the
               80285 driver input impedance is not documented.
* mixer-drive
             - a 1 kohm Norton source (a high-impedance current source, like
               the MC1496 collector behind L87-2) with a 50 ohm load.
* detune-plus / detune-minus
             - bench fixture with the mixer-side winding of every transformer
               (unit A) changed by +/-3 % inductance, roughly what a slug turned
               a fraction of a turn does.  It tests the manual's claim that
               the filters need no field alignment.
* dc         - 1 mA into every pin at once to reproduce the manual's
               resistance-to-chassis check.

Retained evidence is written under spice/studies/80291/operation/.
"""

from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

import ngspice_raw


ROOT = Path(__file__).resolve().parents[2]
KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")
SCHEMATIC = ROOT / "bandpass_80291.kicad_sch"
MAGNETICS = ROOT / "spice" / "models" / "80291_bandpass_magnetics.lib"
GENERATED = ROOT / "spice" / "generated" / "80291-operation"
STUDY = ROOT / "spice" / "studies" / "80291" / "operation"
DATA = STUDY / "data"
FIGURES = STUDY / "figures"

F_START = 0.5e6
F_STOP = 40.0e6
GRID_HZ = 10e3
POINTS = int(round((F_STOP - F_START) / GRID_HZ)) + 1

# Board pin label prefix, short name, manual band edges (MHz), legend text.
BANDS = (
    ("3_5", "b80", 3.5, 4.0, "80 m low-pass"),
    ("7.0", "b40", 7.0, 7.5, "40 m T91-1"),
    ("14_0", "b20", 14.0, 14.5, "20 m T91-2"),
    ("21_0", "b15", 21.0, 21.5, "15 m T91-3"),
    ("28_0", "b10", 28.0, 30.0, "10 m T91-4"),
)
COLORS = {"b80": "#257de0", "b40": "#f47230", "b20": "#00b894",
          "b15": "#f2a600", "b10": "#ee7fac"}

# Transmit-mixer products at the 80291 input for each band, from the VFO
# table on PDF page 26 / printed page 3-10 and the 9 MHz IF.  The 10 m band
# is checked at its lowest (28.0) and highest (29.5) VFO segment.
SPURS = {
    "b80": (("wanted (VFO - 9)", 3.75), ("sum (VFO + 9)", 21.75),
            ("VFO leak", 12.75), ("9 MHz IF leak", 9.0)),
    "b40": (("wanted (VFO - 9)", 7.25), ("sum (VFO + 9)", 25.25),
            ("VFO leak", 16.25), ("9 MHz IF leak", 9.0)),
    "b20": (("wanted (VFO + 9)", 14.25), ("difference (9 - VFO)", 3.75),
            ("VFO leak", 5.25), ("9 MHz IF leak", 9.0)),
    "b15": (("wanted (VFO + 9)", 21.25), ("difference (VFO - 9)", 3.25),
            ("VFO leak", 12.25), ("9 MHz IF leak", 9.0)),
    "b10": (("wanted, 28.0 segment", 28.25), ("difference, 28.0 segment", 10.25),
            ("VFO leak, 28.0 segment", 19.25), ("wanted, 29.5 segment", 29.75),
            ("difference, 29.5 segment", 11.75), ("VFO leak, 29.5 segment", 20.75),
            ("9 MHz IF leak", 9.0)),
}

REQUIRED = (
    ".param K_T1=0.08 K_T2=0.08 K_T3=0.08 K_T4=0.08",
    "XT91-1 Net-_C91-6-Pad1_ GND /7.0-I Net-_C91-5-Pad1_ GND /7.0-O BP80291_T1 K={K_T1}",
    "XT91-2 Net-_C91-7-Pad1_ GND /14_0-I Net-_C91-8-Pad1_ GND /14_0-O BP80291_T2 K={K_T2}",
    "XT91-3 Net-_C91-10-Pad1_ GND /21_0-I Net-_C91-9-Pad1_ GND /21_0-O BP80291_T3 K={K_T3}",
    "XT91-4 Net-_C91-11-Pad1_ GND /28_0-I Net-_C91-12-Pad1_ GND /28_0-O BP80291_T4 K={K_T4}",
    "C91-1 /3_5-I Net-_C91-1-Pad2_ 1500p",
    "R91-1 Net-_C91-1-Pad2_ GND 47",
    "C91-2 Net-_C91-1-Pad2_ GND 1500p",
    "L91-1 Net-_C91-1-Pad2_ Net-_C91-3-Pad1_ 2.7u",
    "C91-3 Net-_C91-3-Pad1_ GND 1500p",
    "L91-2 Net-_C91-3-Pad1_ /3_5-O 2.7u",
    "C91-4 /3_5-O GND 750p",
    "C91-5 Net-_C91-5-Pad1_ GND 82p",
    "C91-6 Net-_C91-6-Pad1_ GND 82p",
    "C91-7 Net-_C91-7-Pad1_ GND 56p",
    "C91-8 Net-_C91-8-Pad1_ GND 56p",
    "C91-9 Net-_C91-9-Pad1_ GND 22p",
    "C91-10 Net-_C91-10-Pad1_ GND 22p",
    "C91-11 Net-_C91-11-Pad1_ GND 10p",
    "C91-12 Net-_C91-12-Pad1_ GND 10p",
)


def run_checked(command: list[str], description: str) -> None:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        print(result.stdout, end="")
        print(result.stderr, end="")
        raise SystemExit(f"{description} failed with exit code {result.returncode}")


def export_board() -> str:
    """Export the sheet, verify it, and return the circuit with pin nets renamed."""
    GENERATED.mkdir(parents=True, exist_ok=True)
    exported = GENERATED / "80291-export.cir"
    run_checked(
        [str(KICAD_CLI), "sch", "export", "netlist", "--format", "spice",
         "-o", str(exported), str(SCHEMATIC)],
        "KiCad SPICE export",
    )
    text = exported.read_text(encoding="utf-8")
    missing = [line for line in REQUIRED if line not in text.splitlines()]
    if missing:
        raise ValueError(f"Fresh KiCad export does not match the manual: {missing}")
    body = [line for line in text.splitlines()
            if line and not line.startswith((".title", ".end"))]
    circuit = "\n".join(body)
    for label, short, *_ in BANDS:
        circuit = re.sub(rf"/{re.escape(label)}-I(?=\s|$)", f"in_{short}", circuit, flags=re.M)
        circuit = re.sub(rf"/{re.escape(label)}-O(?=\s|$)", f"out_{short}", circuit, flags=re.M)
    return circuit


def detuned_library(scale: float) -> Path:
    """Copy the magnetics model with every unit-A (mixer-side) winding scaled."""
    text = MAGNETICS.read_text(encoding="utf-8")

    def scale_line(match: re.Match[str]) -> str:
        return f"{match.group(1)}{float(match.group(2)) * scale:.6g}"

    text = re.sub(r"^(LA[TB] \S+ \S+ )(\S+)$", scale_line, text, flags=re.M)
    path = GENERATED / f"80291_bandpass_magnetics_x{scale:g}.lib"
    path.write_text(text, encoding="utf-8")
    return path


def fixture(case: str) -> list[str]:
    lines = []
    for _, short, *_ in BANDS:
        if case == "mixer-drive":
            lines += [f"I_{short} 0 in_{short} AC 2m",
                      f"RSRC_{short} in_{short} 0 1k",
                      f"RLOAD_{short} out_{short} 0 50"]
            continue
        load = {"load-200": "200", "load-1k": "1k"}.get(case, "50")
        lines += [f"V_{short} src_{short} 0 AC 2",
                  f"RGEN_{short} src_{short} in_{short} 50",
                  f"RLOAD_{short} out_{short} 0 {load}"]
    return lines


def run_ac(circuit: str, case: str) -> dict[str, np.ndarray]:
    if case.startswith("detune"):
        scale = 1.03 if case.endswith("plus") else 0.97
        lib = detuned_library(scale).as_posix()
        circuit = circuit.replace(MAGNETICS.as_posix(), lib)
        if lib not in circuit:
            raise ValueError("Magnetics include not found for detune run")
    netlist = GENERATED / f"80291-{case}.cir"
    raw = GENERATED / f"80291-{case}.raw"
    lines = [f"80291 band filters, {case} fixture at board pins", circuit,
             *fixture(case),
             f".ac lin {POINTS} {F_START:g} {F_STOP:g}",
             ".options filetype=ascii", ".end"]
    netlist.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run_checked([str(NGSPICE), "-b", "-r", str(raw), "-o",
                 str(GENERATED / f"{case}.log"), str(netlist)], f"ngspice {case}")
    names, rows = ngspice_raw.parse_ascii_raw(raw)
    index = {name: i for i, name in enumerate(names)}
    result = {"frequency": np.asarray([row[index["frequency"]].real for row in rows])}
    for _, short, *_ in BANDS:
        out = np.asarray([row[index[f"v(out_{short})"]] for row in rows])
        # 0 dB = 1 V at the output pin = the full available power of a 2 V EMF,
        # 50 ohm generator delivered into 50 ohms (transducer gain for "bench").
        result[short] = 20 * np.log10(np.maximum(np.abs(out), 1e-15))
    return result


def run_dc(circuit: str) -> list[tuple[str, float]]:
    netlist = GENERATED / "80291-dc.cir"
    raw = GENERATED / "80291-dc.raw"
    pins = [(f"{label}-{side}", f"{'in' if side == 'I' else 'out'}_{short}")
            for label, short, *_ in BANDS for side in ("I", "O")]
    lines = ["80291 resistance to chassis, 1 mA into every pin", circuit]
    lines += [f"IOHM_{node} 0 {node} DC 1m" for _, node in pins]
    lines += [".options rshunt=1e12", ".op", ".options filetype=ascii", ".end"]
    netlist.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run_checked([str(NGSPICE), "-b", "-r", str(raw), "-o",
                 str(GENERATED / "dc.log"), str(netlist)], "ngspice dc")
    names, rows = ngspice_raw.parse_ascii_raw(raw)
    index = {name: i for i, name in enumerate(names)}
    return [(pin, rows[0][index[f"v({node})"]].real / 1e-3) for pin, node in pins]


def band_metrics(f: np.ndarray, gain: np.ndarray, low: float, high: float) -> dict[str, float]:
    in_band = (f >= low * 1e6) & (f <= high * 1e6)
    peak_index = int(np.argmax(np.where(f < 35e6, gain, -999)))
    peak = float(gain[peak_index])
    above = np.where(gain >= peak - 3.0)[0]
    # contiguous -3 dB region around the peak
    lo_i = hi_i = peak_index
    while lo_i > 0 and gain[lo_i - 1] >= peak - 3.0:
        lo_i -= 1
    while hi_i < len(gain) - 1 and gain[hi_i + 1] >= peak - 3.0:
        hi_i += 1
    del above
    return {
        "peak_db": peak,
        "peak_mhz": float(f[peak_index]) / 1e6,
        "in_band_min_db": float(gain[in_band].min()),
        "in_band_max_db": float(gain[in_band].max()),
        "in_band_variation_db": float(gain[in_band].max() - gain[in_band].min()),
        "minus3_low_mhz": float(f[lo_i]) / 1e6,
        "minus3_high_mhz": float(f[hi_i]) / 1e6,
    }


def at(f: np.ndarray, gain: np.ndarray, mhz: float) -> float:
    return float(np.interp(mhz * 1e6, f, gain))


def plot_overview(bench: dict[str, np.ndarray]) -> None:
    f = bench["frequency"] / 1e6
    fig, axis = plt.subplots(figsize=(10, 5.6))
    for _, short, low, high, name in BANDS:
        axis.axvspan(low, high, color=COLORS[short], alpha=0.12, linewidth=0)
        axis.plot(f, bench[short], color=COLORS[short], linewidth=2, label=name)
        peak = int(np.argmax(np.where(f < 35, bench[short], -999)))
        axis.annotate(name.split()[0], (f[peak], bench[short][peak]),
                      textcoords="offset points", xytext=(0, 8), ha="center",
                      color="#333333", fontsize=9)
    axis.axvline(9.0, color="#777777", linestyle="--", linewidth=1)
    axis.text(9.1, -78, "9 MHz IF", color="#555555", fontsize=9)
    axis.set(xscale="log", xlim=(1, 40), ylim=(-80, 5),
             xlabel="Frequency (MHz, log scale)",
             ylabel="Output at -O pin (dB, 0 dB = matched 50 ohm transfer)",
             title="80291: each band filter passes its own band (shaded) and rejects the rest")
    axis.set_xticks([1, 2, 3.5, 5, 7, 9, 14, 21, 28, 40])
    axis.get_xaxis().set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}"))
    axis.grid(True, which="both", alpha=0.2)
    axis.legend(loc="lower left", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIGURES / "band-overview.png", dpi=170)
    plt.close(fig)


def plot_passbands(bench: dict[str, np.ndarray], minus: dict[str, np.ndarray],
                   plus: dict[str, np.ndarray]) -> None:
    f = bench["frequency"] / 1e6
    fig, axes = plt.subplots(1, 5, figsize=(14, 4.4), sharey=True)
    for axis, (_, short, low, high, name) in zip(axes, BANDS):
        span = max(high - low, 0.5)
        window = (f > low - 1.2 * span) & (f < high + 1.2 * span)
        axis.axvspan(low, high, color=COLORS[short], alpha=0.12, linewidth=0)
        axis.plot(f[window], bench[short][window], color=COLORS[short], linewidth=2,
                  label="as modeled")
        if short != "b80":
            axis.plot(f[window], minus[short][window], color="#555555", linewidth=1,
                      linestyle="--", label="input winding -3 % L")
            axis.plot(f[window], plus[short][window], color="#555555", linewidth=1,
                      linestyle=":", label="input winding +3 % L")
        axis.set(title=name, xlabel="MHz", ylim=(-12, 1))
        axis.grid(True, alpha=0.2)
    axes[0].set_ylabel("Output at -O pin (dB)")
    axes[1].legend(loc="lower center", fontsize=8)
    fig.suptitle("Passbands at the board pins, and what a slightly mistuned slug does "
                 "(shaded = amateur band)")
    fig.tight_layout()
    fig.savefig(FIGURES / "passbands-and-detune.png", dpi=170)
    plt.close(fig)


def plot_loading(cases: dict[str, dict[str, np.ndarray]]) -> None:
    styles = {"bench": ("50 ohm load (bench)", "-", 2.0),
              "load-200": ("200 ohm load", "--", 1.3),
              "load-1k": ("1 kohm load", ":", 1.3),
              "mixer-drive": ("1 kohm current-source drive, 50 ohm load", "-.", 1.3)}
    f = cases["bench"]["frequency"] / 1e6
    fig, axes = plt.subplots(1, 5, figsize=(14, 4.4), sharey=True)
    for axis, (_, short, low, high, name) in zip(axes, BANDS):
        span = max(high - low, 0.5)
        window = (f > max(0.5, low - 2.5 * span)) & (f < high + 2.5 * span)
        axis.axvspan(low, high, color=COLORS[short], alpha=0.12, linewidth=0)
        for case, (label, style, width) in styles.items():
            g = cases[case][short]
            peak = np.max(g[window])
            axis.plot(f[window], g[window] - peak, linestyle=style, linewidth=width,
                      color=COLORS[short] if case == "bench" else "#444444", label=label)
        axis.set(title=name, xlabel="MHz", ylim=(-25, 1))
        axis.grid(True, alpha=0.2)
    axes[0].set_ylabel("Response relative to its own peak (dB)")
    axes[0].legend(loc="lower center", fontsize=7)
    fig.suptitle("Passband shape depends on the impedances either side of the board "
                 "(neither is documented)")
    fig.tight_layout()
    fig.savefig(FIGURES / "termination-sensitivity.png", dpi=170)
    plt.close(fig)


def plot_spurs(bench: dict[str, np.ndarray], rows: list[dict]) -> None:
    fig, axes = plt.subplots(1, 5, figsize=(14, 4.6), sharey=True)
    f = bench["frequency"] / 1e6
    for axis, (_, short, low, high, name) in zip(axes, BANDS):
        axis.plot(f, bench[short], color=COLORS[short], linewidth=1.8)
        labelled: list[float] = []
        for row in sorted((r for r in rows if r["band"] == short),
                          key=lambda r: r["frequency_mhz"]):
            wanted = row["product"].startswith("wanted")
            axis.plot(row["frequency_mhz"], row["output_db"], marker="o",
                      markersize=7, color="#222222" if wanted else "#ffffff",
                      markeredgecolor="#222222")
            # label only points with room; every value is in mixer-products.csv
            if any(row["frequency_mhz"] / x < 1.15 for x in labelled):
                continue
            axis.annotate(f"{row['frequency_mhz']:g}", (row["frequency_mhz"], row["output_db"]),
                          textcoords="offset points", xytext=(5, 4), fontsize=8)
            labelled.append(row["frequency_mhz"])
        axis.set(title=name, xscale="log", xlim=(1, 40), ylim=(-90, 5), xlabel="MHz (log)")
        axis.set_xticks([2, 5, 10, 20, 40])
        axis.get_xaxis().set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}"))
        axis.grid(True, which="both", alpha=0.2)
    axes[0].set_ylabel("Output at -O pin (dB)")
    fig.suptitle("Mixer products at each band: filled dot = wanted signal, "
                 "open dots = products the filter must reject")
    fig.tight_layout()
    fig.savefig(FIGURES / "mixer-product-rejection.png", dpi=170)
    plt.close(fig)


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    circuit = export_board()
    cases = {case: run_ac(circuit, case) for case in
             ("bench", "load-200", "load-1k", "mixer-drive", "detune-minus", "detune-plus")}
    f = cases["bench"]["frequency"]

    with (DATA / "response.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        header = ["frequency_hz"] + [f"{case}_{short}_db" for case in cases for _, short, *_ in BANDS]
        writer.writerow(header)
        for i, freq in enumerate(f):
            writer.writerow([f"{freq:.0f}"] + [f"{cases[c][s][i]:.2f}" for c in cases
                                               for _, s, *_ in BANDS])

    metric_rows = []
    for case, result in cases.items():
        for _, short, low, high, name in BANDS:
            m = band_metrics(f, result[short], low, high)
            metric_rows.append({"case": case, "band": short, "filter": name, **m})
    with (DATA / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(metric_rows[0]))
        writer.writeheader()
        for row in metric_rows:
            writer.writerow({k: (f"{v:.3f}" if isinstance(v, float) else v) for k, v in row.items()})

    spur_rows = []
    bench = cases["bench"]
    for _, short, *_ in BANDS:
        wanted = at(f, bench[short], SPURS[short][0][1])
        for product, mhz in SPURS[short]:
            out = at(f, bench[short], mhz)
            spur_rows.append({"band": short, "product": product, "frequency_mhz": mhz,
                              "output_db": out, "relative_to_wanted_db": out - wanted})
    with (DATA / "mixer-products.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(spur_rows[0]))
        writer.writeheader()
        for row in spur_rows:
            writer.writerow({k: (f"{v:.2f}" if isinstance(v, float) else v) for k, v in row.items()})

    dc = run_dc(circuit)
    documented = {"3_5-I": "infinite (blocking capacitors)", "3_5-O": "47 ohms"}
    with (DATA / "dc-resistance.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("pin", "simulated_ohms", "manual_expectation"))
        for pin, ohms in dc:
            writer.writerow((pin, f"{ohms:.4g}", documented.get(pin, "zero")))

    plot_overview(bench)
    plot_passbands(bench, cases["detune-minus"], cases["detune-plus"])
    plot_loading(cases)
    plot_spurs(bench, spur_rows)

    for row in metric_rows:
        if row["case"] == "bench":
            print(f"{row['filter']:14s} peak {row['peak_db']:6.2f} dB at {row['peak_mhz']:.2f} MHz; "
                  f"in band {row['in_band_min_db']:.2f}..{row['in_band_max_db']:.2f} dB; "
                  f"-3 dB {row['minus3_low_mhz']:.2f}-{row['minus3_high_mhz']:.2f} MHz")
    for pin, ohms in dc:
        print(f"{pin:7s} {ohms:.4g} ohm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
