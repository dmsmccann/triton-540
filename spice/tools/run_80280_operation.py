#!/usr/bin/env python3
"""Run the manual-transcribed 80280 study and retain pin-level evidence."""

import csv
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "spice/studies/80280/operation"
WORK = ROOT / "spice/generated/80280-operation"
PINS = "tcmd r t td supply reg ot ot_switch pot_top pot_w pot_bottom".split()
TRANSISTORS = [
    ("td", "q1b", "0"), ("t_drive", "q2b", "0"),
    ("0", "t_drive", "q3e"), ("supply", "t_drive", "q4e"),
    ("r_drive", "q5b", "0"), ("0", "r_drive", "r"),
    ("supply", "r_drive", "q7e"), ("zero", "q8b", "0"),
    ("pot_w", "q9b", "0"),
]
FACTORY = {
    "rx": [(0.2,0,0), (0.1,0.7,0), (0,0.1,0.2), (13.8,0.1,0.2),
           (13.6,0.2,0), (0,13.6,12.8), (13.8,13.6,13), (0.1,0.6,0), (3.5,0.1,0)],
    "tx": [(4.4,0,0), (12.5,0,0), (0,12.5,10.4), (13.8,12.5,11.9),
           (0.05,0.7,0), (0,0.05,0.6), (13.8,0.05,0.6), (3.5,0,0), (0,0.7,0)],
}
KEY_TRAIN = "PWL(0 0 10m 0 10.001m 1 90m 1 90.001m 0 " \
    "120m 0 120.001m 1 140m 1 140.001m 0 160m 0 160.001m 1 180m 1 180.001m 0)"


def write_csv(name, header, rows):
    with (STUDY / f"data/{name}.csv").open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def run(name, analysis, nodes, *, key="0", enabled=1, knob=0.5, trim=0.5,
        scale=1, cap="0.1u", relay_cap="32u", regulator=False, load="0.03", supply="13.8"):
    base = (STUDY / "fixtures/control-board.cir").read_text()
    regulation = ((STUDY / "fixtures/mc1723cl-envelope.cir").read_text()
                  if regulator else "Videal reg 0 8\nVref ref 0 7.15\n"
                  "Rpark1 pass 0 1Meg\nRpark2 comp 0 1Meg\n")
    models = "\n".join(f'.include "{(ROOT / "spice/models" / model).as_posix()}"'
                       for model in ("1N4154.lib", "2N5087.lib", "MPS6514.lib", "MPSU01_fitted.lib"))
    vectors = " ".join(f"v({node})" for node in nodes)
    deck = WORK / f"{name}.cir"
    deck.write_text(f"""{base}
{models}
.param timing_cap={cap} load_scale={scale} relay_cap={relay_cap}
Vinput supply 0 {supply}
Vkey key 0 {key}
Venable enabled 0 {enabled}
Vknob knob 0 {knob}
Vtrim trim 0 {trim}
Iexternal reg 0 {load}
{regulation}
.control
set wr_singlescale
set numdgt=9
{analysis}
wrdata {name}.dat {vectors}
quit
.endc
.end
""")
    exe = Path(os.environ.get("NGSPICE_EXE", r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe"))
    result = subprocess.run([str(exe), "-b", deck.name], cwd=WORK, capture_output=True, text=True)
    (WORK / f"{name}.log").write_text(result.stdout + result.stderr)
    result.check_returncode()
    if "error" in result.stderr.lower():
        raise RuntimeError(result.stderr)
    rows = [tuple(map(float, line.split()))
            for line in (WORK / f"{name}.dat").read_text().splitlines()]
    if not rows or any(len(row) != len(nodes) + 1 for row in rows):
        raise ValueError(f"Unexpected data shape for {name}")
    manifest.append((name, analysis.replace("\n", " / "), key, enabled, knob, trim, scale,
                     cap, relay_cap, "MC1723CL envelope" if regulator else "ideal 8 V", load, supply))
    return rows


def crossing(rows, column, level, start, stop, rising):
    for before, after in zip(rows, rows[1:]):
        if not start <= after[0] <= stop:
            continue
        y1, y2 = before[column], after[column]
        if (rising and y1 < level <= y2) or (not rising and y1 > level >= y2):
            return before[0] + (after[0] - before[0]) * (level - y1) / (y2 - y1)
    raise ValueError(f"Missing crossing at {level} V")


def main():
    os.environ.setdefault("MPLCONFIGDIR", str(WORK / "matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for folder in (WORK, STUDY / "data", STUDY / "figures"):
        folder.mkdir(parents=True, exist_ok=True)
    manifest.clear()
    nodes = list(dict.fromkeys(PINS + [node for triple in TRANSISTORS for node in triple if node != "0"]))
    pin_targets = {"rx": (2.1, 12.8, 0.2, 0.2, 13.8, 8, 3.1, 0.2, 4.8, 3.5, 2.4),
                   "tx": (0, 0.6, 10.4, 4.4, 13.8, None, 3.1, 10, 3.1, 0, 0)}
    dc = []
    states = {}
    for mode, key in (("rx", "0"), ("tx", "1")):
        values = dict(zip(nodes, run(f"dc-{mode}", "op", nodes, key=key)[0][1:]))
        states[mode] = values
        values["0"] = 0
        dc.extend((mode, pin, target, values[pin]) for pin, target in zip(PINS, pin_targets[mode]))
        for index, (pins, targets) in enumerate(zip(TRANSISTORS, FACTORY[mode]), 1):
            dc.extend((mode, f"Q80-{index} {terminal}", target, values[pin])
                      for terminal, pin, target in zip("CBE", pins, targets))
    write_csv("dc", ("mode", "point", "manual_V", "model_V"), dc)

    key_nodes = ["tcmd", "r", "t", "td", "ot"]
    timing = []
    for name, scale, cap, relay_cap in (
        ("keying", 1, "0.1u", "32u"), ("light-load", 1.5, "0.1u", "32u"),
        ("heavy-load", 0.75, "0.1u", "32u"), ("kicad-c2", 1, "0.01u", "32u"),
        ("driver-only-td", 1, "0.1u", "1a"), ("driver-only-kicad-c2", 1, "0.01u", "1a"),
    ):
        wave = run(name, "tran 2u 205m 0 2u\nlinearize", key_nodes,
                   key=KEY_TRAIN, scale=scale, cap=cap, relay_cap=relay_cap)
        if name in ("keying", "driver-only-td"):
            write_csv(name, ["time_s"] + key_nodes, (row for index, row in enumerate(wave)
                      if index % 10 == 0 or 9.5 <= row[0]*1000 <= 15))
        if name == "keying":
            nominal = wave
        if name == "driver-only-td":
            driver_only = wave
        levels = [(a + b) / 2 for a, b in zip(wave[0][1:], wave[40000][1:])]
        down = [crossing(wave, c, levels[c-1], .010, .049, c > 2) for c in range(1, 5)]
        up = [crossing(wave, c, levels[c-1], .090, .119, c < 3) for c in range(1, 5)]
        timing.append((name, *[1000*(value-.010) for value in down],
                       *[1000*(value-.090) for value in up], 1000*(down[3]-down[2])))
    write_csv("timing", ("case", "key_down_ms", "R_down_ms", "T_up_ms", "tD_up_ms",
                         "key_up_ms", "R_up_ms", "T_down_ms", "tD_down_ms", "tD_after_T_ms"), timing)
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), layout="constrained")
    for axis, window in zip(axes, [(0, 205), (9.5, 20)]):
        for index, label in enumerate(("T/R", "R", "T", "tD"), 1):
            axis.plot([row[0]*1000 for row in nominal], [row[index] for row in nominal], label=label)
        axis.set(xlim=window, xlabel="Time (ms)", ylabel="Board pin (V)")
        axis.grid(alpha=.25)
    axes[0].legend(ncol=4)
    axes[1].plot([row[0]*1000 for row in driver_only], [row[4] for row in driver_only],
                 "--", color="black", label="tD with driver load only")
    axes[1].legend(loc="upper right")
    axes[0].set_title("80280 keying sequence with chassis loads")
    axes[1].set_title("First key closure, expanded")
    fig.savefig(STUDY / "figures/keying.png", dpi=150)
    plt.close(fig)

    offset_nodes = ["ot", "ot_switch", "pot_w", "zero"]
    active_center = states["rx"]["ot"]
    sweep = run("offset-zero", "dc Vtrim 0 1 0.01", offset_nodes, enabled=0)
    trim = min(sweep, key=lambda row: abs(row[1] - active_center))[0]
    write_csv("offset-zero", ["trim_position"] + offset_nodes, sweep)
    fig, axis = plt.subplots(figsize=(9, 5), layout="constrained")
    for name, key, engaged, position in (
        ("Receive engaged", "0", 1, trim),
        ("Receive disengaged before", "0", 0, .25),
        ("Receive disengaged aligned", "0", 0, trim),
        ("Transmit aligned", "1", 1, trim),
    ):
        rows = run(name.lower().replace(" ", "-"), "dc Vknob 0 1 0.01", offset_nodes,
                   key=key, enabled=engaged, trim=position)
        write_csv(name.lower().replace(" ", "-"), ["knob_position"] + offset_nodes, rows)
        axis.plot([row[0] for row in rows], [row[1] for row in rows], label=name,
                  linestyle=":" if key == "1" else "-")
    axis.axvline(.5, color="gray", alpha=.35)
    axis.set(xlabel="Front-panel OFFSET position (fraction)", ylabel="OT (V)",
             title=f"OFFSET ZERO alignment, R80-16 at {trim:.2f} of travel")
    axis.legend()
    axis.grid(alpha=.25)
    fig.savefig(STUDY / "figures/offset.png", dpi=150)
    plt.close(fig)

    reg_nodes = ["supply", "reg", "pass", "plus", "feedback", "comp"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
    for current in (10, 30, 60):
        name = f"reg-line-{current}ma"
        rows = run(name, "dc Vinput 9.5 15 0.05", reg_nodes, regulator=True, load=f"{current}m")
        write_csv(name, ["input_sweep_V"] + reg_nodes, rows)
        axes[0].plot([row[0] for row in rows], [row[2] for row in rows], label=f"{current} mA")
    rows = run("reg-load", "dc Iexternal 0.001 0.15 0.001", reg_nodes, regulator=True)
    write_csv("reg-load", ["load_sweep_A"] + reg_nodes, rows)
    axes[1].plot([row[0]*1000 for row in rows], [row[2] for row in rows])
    axes[0].set(xlabel="Input (V)", ylabel="+REG (V)")
    axes[1].set(xlabel="External load (mA)", ylabel="+REG (V)")
    axes[0].legend()
    for axis in axes:
        axis.grid(alpha=.25)
    fig.suptitle("MC1723CL functional model with 80280 feedback network")
    fig.savefig(STUDY / "figures/regulation.png", dpi=150)
    plt.close(fig)
    rows = run("reg-keying", "tran 10u 105m 0 10u\nlinearize", ["supply", "reg", "t", "ot"],
               regulator=True, key=KEY_TRAIN, load="PWL(0 30m 10m 30m 10.001m 60m 90m 60m 90.001m 30m)")
    write_csv("reg-keying", ["time_s", "supply", "reg", "t", "ot"], rows)
    with (STUDY / "manifest.csv").open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("run", "analysis", "contact", "offset_enabled", "knob_position",
                         "trim_position", "rail_load_scale", "C80-2", "relay_C3", "regulator",
                         "external_load", "supply"))
        writer.writerows(manifest)


manifest = []

if __name__ == "__main__":
    main()
