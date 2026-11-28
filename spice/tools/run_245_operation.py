#!/usr/bin/env python3
"""Model 245 CW filter: DC operating point, CW-1/CW-2 response, stage-by-stage
response, and the R45-9 (manual R9) value question.

The circuit comes from a fresh KiCad export of 245_cw_filt.kicad_sch, so the
simulation is the schematic itself.  This runner only adds the drive source,
the +REG supply, the analyses, and the R45-9 substitution for the 120k case.

Every observation point is a Model 245 board pin:
    pin 1 INPUT (sheet IN)   pin 4 OUT 1 (sheet CW2)   pin 5 OUT 2
    pin 6 OUT 3              pin 7 OUT 4 (sheet CW1)   pin 3 +12V (sheet +REG)

Run from the repository root:
    python spice/tools/run_245_operation.py
"""

from __future__ import annotations

import csv
import math
import os
import re
import subprocess
from pathlib import Path

import ngspice_raw

ROOT = Path(__file__).resolve().parents[2]
KICAD_CLI = Path(os.environ.get("KICAD_CLI", r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"))
NGSPICE = Path(os.environ.get("NGSPICE_EXE", r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe"))
SCHEMATIC = ROOT / "245_cw_filt.kicad_sch"
GENERATED = ROOT / "spice" / "generated" / "245-operation"
STUDY = ROOT / "spice" / "studies" / "245" / "operation"
DATA = STUDY / "data"
FIGURES = STUDY / "figures"

REG_540 = 8.0      # 80280 +REG, about 8 V (80280.md); the supply in a Model 540
REG_MANUAL = 13.0  # the Model 245 sheet's own pin table reads 13 V on "+12"
SWEEP = "ac dec 2000 100 10k"   # 2000 points per decade: about 0.86 Hz apart at 750 Hz

# Board pins, in the Model 245 sheet's numbering, with the KiCad net names.
PINS = [
    ("1", "INPUT", "/in"), ("3", "+12V", "/+reg"),
    ("4", "OUT 1", "/cw2"), ("5", "OUT 2", "/out_2"),
    ("6", "OUT 3", "/out_3"), ("7", "OUT 4", "/cw1"),
]
# Model 245 manual, PDF p.2 / printed p.3-41, receive mode.
MANUAL_PIN_V = {"INPUT": 0, "+12V": 13, "OUT 1": 0, "OUT 2": 6.5, "OUT 3": 6.5, "OUT 4": 0}
MANUAL_IC_V = {1: 6.5, 2: 6.5, 4: 0, 6: 6.5, 7: 6.5, 9: 13, 10: 6.5, 12: 6.5, 13: 13}

# Model 245 manual specifications, PDF p.1.
SPEC = {
    "cw1_bw3": 150.0, "cw1_bw60": 1450.0, "cw1_shape_6_60": 7.2,
    "cw2_bw3": 260.0, "cw2_bw20": 2800.0, "center": 750.0, "insertion_gain_db": 2.5,
}

REQUIRED_EXPORT = (
    "C45-1 /IN Net-_C45-1-Pad2_ 0.01u",
    "R45-1 Net-_C45-1-Pad2_ Net-_C45-2-Pad2_ 220k",
    "R45-9 Net-_IC45-1A-__ Net-_C45-5-Pad2_ 220k",
    "C45-4 /CW2 Net-_IC45-1A-__ 0.1u",
    "C45-12 /CW1 Net-_IC45-2B-__ 0.1u",
    "C45-7 Net-_IC45-1A-+_ GND 32u",
    "R45-4 Net-_IC45-1A-+_ /+REG 15k",
)

manifest: list[tuple] = []


def run_checked(command: list[str], description: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        print(result.stdout, end="")
        print(result.stderr, end="")
        raise SystemExit(f"{description} failed with exit code {result.returncode}")
    return result


def export_and_check() -> str:
    """Export the sheet and confirm it is the circuit this study describes."""
    exported = GENERATED / "245-export.cir"
    run_checked([str(KICAD_CLI), "sch", "export", "netlist", "--format", "spice",
                 "-o", str(exported), str(SCHEMATIC)], "KiCad SPICE export")
    text = exported.read_text(encoding="utf-8")
    missing = [line for line in REQUIRED_EXPORT if line not in text.splitlines()]
    if missing:
        raise ValueError(f"Fresh KiCad export does not match the Model 245 drawing: {missing}")
    for ref in ("XIC45-1", "XIC45-2"):
        line = next((l for l in text.splitlines() if l.startswith(ref + " ")), "")
        if not line.endswith(" MC1747") or len(line.split()) != 16:
            raise ValueError(f"{ref} is not exported as a 14-pin MC1747 subcircuit: {line!r}")
    if ".include" not in text:
        raise ValueError("Export has no .include for the MC1747 model")
    return text


def ic_nodes(export: str) -> dict[str, list[str]]:
    """Map IC45-1 / IC45-2 package pin numbers (1..14) to exported net names."""
    nodes = {}
    for ref in ("IC45-1", "IC45-2"):
        line = next(l for l in export.splitlines() if l.startswith("X" + ref + " "))
        nodes[ref] = [n.lower() for n in line.split()[1:15]]
    return nodes


def make_deck(export: str, name: str, analysis: str, vectors: list[str], *,
              supply: float = REG_540, r9: str = "220k") -> Path:
    body = [l for l in export.splitlines() if l.strip().lower() != ".end"]
    if r9 != "220k":
        body = [re.sub(r"^(R45-9 \S+ \S+) 220k$", rf"\g<1> {r9}", l) for l in body]
        if not any(l.startswith("R45-9 ") and l.endswith(" " + r9) for l in body):
            raise ValueError("R45-9 substitution failed")
    raw = f"{name}.raw"
    body += [
        "* ---- study drive (added by run_245_operation.py) ----",
        f"VREG /+REG 0 DC {supply}",
        "VIN /IN 0 DC 0 AC 1",
        ".control",
        "set filetype=ascii",
        analysis,
        f"write {raw} {' '.join(vectors)}",
        "quit",
        ".endc",
        ".end",
    ]
    deck = GENERATED / f"{name}.cir"
    deck.write_text("\n".join(body) + "\n", encoding="utf-8")
    return deck


def simulate(export: str, name: str, analysis: str, vectors: list[str], *,
             supply: float = REG_540, r9: str = "220k", note: str = ""):
    deck = make_deck(export, name, analysis, vectors, supply=supply, r9=r9)
    result = run_checked([str(NGSPICE), "-b", deck.name], f"ngspice {name}", cwd=GENERATED)
    (GENERATED / f"{name}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if re.search(r"(?im)^\s*error", result.stdout + result.stderr):
        raise RuntimeError(f"ngspice reported an error in {name}; see {name}.log")
    names, rows = ngspice_raw.parse_ascii_raw(GENERATED / f"{name}.raw")
    manifest.append((name, analysis, f"{supply:g}", r9, "ideal 1 V AC at pin 1",
                     "pins 4-7 unloaded", note))
    return names, rows


def column(names, rows, vector):
    index = names.index(vector.lower())
    return [row[index] for row in rows]


def width_at(freqs, db, drop):
    """Total width (Hz) at `drop` dB below the peak, or None outside the sweep."""
    peak_index = max(range(len(db)), key=lambda i: db[i])
    level = db[peak_index] - drop
    lower = ngspice_raw.crossing_below(freqs, db, peak_index, -1, level)
    upper = ngspice_raw.crossing_below(freqs, db, peak_index, +1, level)
    if lower is None or upper is None:
        return None, lower, upper
    return upper - lower, lower, upper


def write_csv(name: str, header, rows) -> None:
    with (DATA / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def geometric_edges(center: float, width: float) -> tuple[float, float]:
    """Edges of a width centred geometrically on `center` (f_lo * f_hi = f0^2)."""
    lower = (-width + math.sqrt(width * width + 4 * center * center)) / 2
    return lower, lower + width


def main() -> None:
    for folder in (GENERATED, DATA, FIGURES):
        folder.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(GENERATED / "matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    export = export_and_check()
    ics = ic_nodes(export)

    # ---------------------------------------------------------------- DC
    dc_vectors = sorted({f"v({net})" for _, _, net in PINS if net != "/in"}
                        | {f"v({ics[r][p - 1]})" for r in ics for p in MANUAL_IC_V if ics[r][p - 1] != "gnd"}
                        | {"i(vreg)"})
    dc = {}
    for label, supply in (("540", REG_540), ("manual", REG_MANUAL)):
        names, rows = simulate(export, f"dc-{label}", "op", dc_vectors, supply=supply,
                               note="operating point")
        dc[label] = {n: v.real for n, v in zip(names, rows[0])}
    dc_rows = []
    for pin, name, net in PINS:
        vec = f"v({net})"
        model = [0.0 if net == "/in" else dc[k][vec] for k in ("manual", "540")]
        dc_rows.append((f"pin {pin} {name}", MANUAL_PIN_V[name], f"{model[0]:.3f}", f"{model[1]:.3f}"))
    for ref in ("IC45-1", "IC45-2"):
        for p, manual in MANUAL_IC_V.items():
            net = ics[ref][p - 1]
            model = [0.0 if net == "gnd" else dc[k][f"v({net})"] for k in ("manual", "540")]
            dc_rows.append((f"{ref} pin {p}", manual, f"{model[0]:.3f}", f"{model[1]:.3f}"))
    dc_rows.append(("supply current (mA)", 2,
                    f"{-1000 * dc['manual']['i(vreg)']:.3f}", f"{-1000 * dc['540']['i(vreg)']:.3f}"))
    write_csv("dc", ("point", "manual_V_at_13V", "model_V_at_13V", "model_V_at_8V"), dc_rows)

    # ---------------------------------------------------------------- AC
    ac_vectors = ["v(/in)", "v(/cw2)", "v(/out_2)", "v(/out_3)", "v(/cw1)"]

    def sweep(name, **kw):
        names, rows = simulate(export, name, SWEEP, ac_vectors, **kw)
        f = [v.real for v in column(names, rows, "frequency")]
        vin = column(names, rows, "v(/in)")
        out = {v: column(names, rows, v) for v in ac_vectors[1:]}
        db = {v: [ngspice_raw.db_ratio(a, b) for a, b in zip(out[v], vin)] for v in out}
        return f, out, db

    f, out, db = sweep("ac-nominal", note="nominal, +REG as in the 540")
    _, _, db13 = sweep("ac-13v", supply=REG_MANUAL, note="supply-dependence check")
    _, out120, db120 = sweep("ac-r9-120k", r9="120k", note="R45-9 alternative reading")

    write_csv("response", ("frequency_hz", "pin4_out1_cw2_db", "pin5_out2_db",
                           "pin6_out3_db", "pin7_out4_cw1_db"),
              ((f"{x:.4f}", *(f"{db[v][i]:.4f}" for v in ac_vectors[1:])) for i, x in enumerate(f)))

    stage2 = [ngspice_raw.db_ratio(a, b) for a, b in zip(out["v(/out_2)"], out["v(/cw2)"])]
    stage2_120 = [ngspice_raw.db_ratio(a, b) for a, b in zip(out120["v(/out_2)"], out120["v(/cw2)"])]
    write_csv("r9", ("frequency_hz", "out2_over_out1_db_r9_220k", "out2_over_out1_db_r9_120k",
                     "pin7_cw1_db_r9_220k", "pin7_cw1_db_r9_120k"),
              ((f"{x:.4f}", f"{stage2[i]:.4f}", f"{stage2_120[i]:.4f}",
                f"{db['v(/cw1)'][i]:.4f}", f"{db120['v(/cw1)'][i]:.4f}") for i, x in enumerate(f)))

    # ---------------------------------------------------------------- metrics
    step = ngspice_raw.grid_step_at(f, 750.0)
    metrics = [("sweep spacing near 750 Hz (Hz)", f"{step:.3f}", "resolution of every frequency below")]

    def describe(tag, curve, drops):
        fp, gp = ngspice_raw.peak_of(f, curve)
        metrics.append((f"{tag} peak frequency (Hz)", f"{fp:.1f}", "grid point"))
        metrics.append((f"{tag} peak gain from pin 1 (dB)", f"{gp:.3f}", "simulated"))
        widths = {}
        for d in drops:
            w, lo, hi = width_at(f, curve, d)
            widths[d] = w
            metrics.append((f"{tag} width at -{d:g} dB (Hz)",
                            "outside sweep" if w is None else f"{w:.1f}",
                            "" if w is None else f"edges {lo:.1f} / {hi:.1f} Hz"))
        return fp, gp, widths

    cw1 = describe("CW-1 (pin 7)", db["v(/cw1)"], (3, 6, 20, 60))
    cw2 = describe("CW-2 (pin 4)", db["v(/cw2)"], (3, 6, 20, 60))
    describe("OUT 2 (pin 5)", db["v(/out_2)"], (3,))
    describe("OUT 3 (pin 6)", db["v(/out_3)"], (3,))
    shape = cw1[2][60] / cw1[2][6]
    metrics.append(("CW-1 shape factor 60 dB / 6 dB", f"{shape:.2f}", "ratio of the two widths"))
    diff13 = max(abs(a - b) for v in ac_vectors[1:] for a, b in zip(db[v], db13[v]))
    metrics.append(("largest response change, 13 V vs 8 V supply (dB)", f"{diff13:.4f}", "any pin, any frequency"))
    s2_750 = ngspice_raw.interpolate_at(f, stage2, 750.0)
    s2_750_120 = ngspice_raw.interpolate_at(f, stage2_120, 750.0)
    s2p = ngspice_raw.peak_of(f, stage2)
    s2p120 = ngspice_raw.peak_of(f, stage2_120)
    metrics += [
        ("OUT 2 / OUT 1 at 750 Hz, R45-9 = 220k (dB)", f"{s2_750:.3f}", "pins 5 / 4"),
        ("OUT 2 / OUT 1 at 750 Hz, R45-9 = 120k (dB)", f"{s2_750_120:.3f}", "pins 5 / 4"),
        ("OUT 2 / OUT 1 peak, R45-9 = 220k (Hz, dB)", f"{s2p[0]:.1f}, {s2p[1]:.3f}", "grid point"),
        ("OUT 2 / OUT 1 peak, R45-9 = 120k (Hz, dB)", f"{s2p120[0]:.1f}, {s2p120[1]:.3f}", "grid point"),
    ]
    c120 = ngspice_raw.peak_of(f, db120["v(/cw1)"])
    w120, _, _ = width_at(f, db120["v(/cw1)"], 3)
    metrics += [
        ("CW-1 peak with R45-9 = 120k (Hz, dB)", f"{c120[0]:.1f}, {c120[1]:.3f}", "grid point"),
        ("CW-1 -3 dB width with R45-9 = 120k (Hz)", f"{w120:.1f}", ""),
    ]
    write_csv("metrics", ("measurement", "value", "note"), metrics)

    with (STUDY / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("run", "analysis", "+REG_V", "R45-9", "source", "load", "purpose"))
        writer.writerows(manifest)

    # ---------------------------------------------------------------- figures
    from matplotlib.ticker import FixedLocator, NullFormatter

    def hz_axis(axis, ticks=(200, 300, 500, 750, 1000, 2000, 3000, 5000)):
        """Plain frequency labels on a log axis, so a reader sees 750, not 7.5x10^2."""
        axis.xaxis.set_major_locator(FixedLocator(ticks))
        axis.set_xticklabels([f"{t / 1000:g}k" if t >= 1000 else f"{t}" for t in ticks])
        axis.xaxis.set_minor_formatter(NullFormatter())

    pin_style = {
        "v(/cw2)": ("pin 4  OUT 1 = CW-2 (1 stage)", "#4c78a8"),
        "v(/out_2)": ("pin 5  OUT 2 (2 stages)", "#72b7b2"),
        "v(/out_3)": ("pin 6  OUT 3 (3 stages)", "#f58518"),
        "v(/cw1)": ("pin 7  OUT 4 = CW-1 (4 stages)", "#e45756"),
    }

    # Figure 45-1: CW-1 and CW-2 against the manual's widths
    fig, ax = plt.subplots(figsize=(9, 5.2), layout="constrained")
    for v in ("v(/cw2)", "v(/cw1)"):
        ax.semilogx(f, db[v], color=pin_style[v][1], linewidth=1.8, label=pin_style[v][0])
    marks = [("v(/cw1)", 3, SPEC["cw1_bw3"]), ("v(/cw1)", 60, SPEC["cw1_bw60"]),
             ("v(/cw2)", 3, SPEC["cw2_bw3"]), ("v(/cw2)", 20, SPEC["cw2_bw20"])]
    for i, (v, drop, width) in enumerate(marks):
        peak = max(db[v])
        lo, hi = geometric_edges(SPEC["center"], width)
        ax.plot([lo, hi], [peak - drop] * 2, color=pin_style[v][1], linestyle=":", linewidth=2.2,
                marker="|", markersize=10,
                label="manual width, centred geometrically on 750 Hz" if i == 0 else None)
        ax.annotate(f"manual {width:g} Hz at -{drop} dB", (hi, peak - drop), xytext=(6, -3),
                    textcoords="offset points", fontsize=8, color=pin_style[v][1])
    ax.set_xlim(200, 5000)
    hz_axis(ax)
    ax.set_ylim(-80, 8)
    ax.set_xlabel("Audio frequency (Hz)")
    ax.set_ylabel("Gain from pin 1 INPUT (dB)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(loc="lower left", fontsize=9)
    ax.set_title("Model 245 CW-1 and CW-2 responses at the board pins (simulated, +REG = 8 V)")
    fig.savefig(FIGURES / "cw1-cw2-response.png", dpi=150)
    plt.close(fig)

    # Figure 45-2: each stage narrows the response
    fig, ax = plt.subplots(figsize=(9, 5.2), layout="constrained")
    for v, (label, colour) in pin_style.items():
        ax.semilogx(f, db[v], color=colour, linewidth=1.8, label=label)
    ax.set_xlim(200, 5000)
    hz_axis(ax)
    ax.set_ylim(-60, 8)
    ax.axhline(-3, color="grey", linewidth=0.8, linestyle="--")
    ax.text(210, -2.4, "-3 dB", fontsize=8, color="grey")
    ax.set_xlabel("Audio frequency (Hz)")
    ax.set_ylabel("Gain from pin 1 INPUT (dB)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(loc="lower left", fontsize=9)
    ax.set_title("Each identical stage narrows the response (simulated, all four output pins)")
    fig.savefig(FIGURES / "stage-by-stage.png", dpi=150)
    plt.close(fig)

    # Figure 45-3: R45-9 220k vs 120k, seen as OUT 2 relative to OUT 1
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), layout="constrained")
    axes[0].semilogx(f, stage2, color="#4c78a8", linewidth=1.8, label="R45-9 = 220k (drawn as inferred)")
    axes[0].semilogx(f, stage2_120, color="#e45756", linewidth=1.8, linestyle="--", label="R45-9 = 120k")
    axes[0].axvline(750, color="grey", linewidth=0.8)
    axes[0].set_xlim(200, 5000)
    hz_axis(axes[0])
    axes[0].set_ylim(-30, 12)
    axes[0].set_xlabel("Audio frequency (Hz)")
    axes[0].set_ylabel("Pin 5 OUT 2 relative to pin 4 OUT 1 (dB)")
    axes[0].set_title("Stage 2 alone: what the bench would compare")
    axes[1].semilogx(f, db["v(/cw1)"], color="#4c78a8", linewidth=1.8, label="R45-9 = 220k")
    axes[1].semilogx(f, db120["v(/cw1)"], color="#e45756", linewidth=1.8, linestyle="--", label="R45-9 = 120k")
    axes[1].set_xlim(400, 1400)
    hz_axis(axes[1], (400, 500, 600, 750, 900, 1000, 1200, 1400))
    axes[1].set_ylim(-30, 12)
    axes[1].set_xlabel("Audio frequency (Hz)")
    axes[1].set_ylabel("Pin 7 CW-1 gain from pin 1 (dB)")
    axes[1].set_title("Effect on the complete CW-1 response")
    for axis in axes:
        axis.grid(True, which="both", alpha=0.3)
        axis.legend(fontsize=9, loc="lower center")
    fig.savefig(FIGURES / "r9-value.png", dpi=150)
    plt.close(fig)

    for row in metrics:
        print(" | ".join(row))


if __name__ == "__main__":
    main()
