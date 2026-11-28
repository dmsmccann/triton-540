#!/usr/bin/env python3
"""Export the 80285 schematic and exercise its bias, RF gain, and keying."""

from __future__ import annotations

import csv
import os
import shutil
import subprocess
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ngspice_raw import parse_ascii_raw


ROOT = Path(__file__).resolve().parents[2]
SCHEMATIC = ROOT / "80285_low_level_driver.kicad_sch"
STUDY = ROOT / "spice/studies/80285/operation"
GENERATED = ROOT / "spice/generated/80285-operation"
CONTROL_DATA = ROOT / "spice/studies/80280/operation/data"
KICAD = os.environ.get("KICAD_CLI") or shutil.which("kicad-cli") or r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
NGSPICE = os.environ.get("NGSPICE_EXE") or shutil.which("ngspice") or r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe"
FREQUENCIES = (3.5, 7.0, 14.0, 21.0, 28.0, 30.0)
AC = ".ac lin 266 3.5meg 30meg"
SOURCE_OHMS = 50
SUPPLY_V = 13.0
ALC_V = 4.3
KEY_CARRIER_HZ = 3_500_000
KEY_DRIVE_VPK = 10e-6
KEY_PRE_S = 0.0002
KEY_RISE_S = 1e-6
KEY_DELAY_S = 0.00173
KEY_WINDOW_S = {"down": 0.0040, "up": 0.0060}
SAMPLES_PER_CYCLE = 20
ENVELOPE_CYCLES = 32
LABELS = {
    "simultaneous": "Simultaneous T and tD",
    "delayed": "tD delayed by 1.73 ms",
    "80280-driver-only": "80280 replay, driver branch",
    "80280-with-80281": "80280 replay, with 80281 branch",
}
COLORS = ("#254a77", "#b54a27", "#21836c", "#895899", "#76621e", "#637889")


def write_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def run_checked(command, cwd=ROOT):
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"{result.args}:\n{result.stdout}\n{result.stderr}")


def export_circuit():
    export = GENERATED / "kicad-export.cir"
    run_checked([KICAD, "sch", "export", "netlist", "--format", "spice", "-o", str(export), str(SCHEMATIC)])
    lines = export.read_text(encoding="utf-8").splitlines()
    includes = [line for line in lines if line.startswith(".include ")]
    elements = {line.split()[0]: line.split()[1:] for line in lines if line and line[0] in "RCDQX"}
    if len(elements) != 36 or len(includes) != 3:
        raise ValueError("Expected all 36 driver elements and three model libraries in the export")
    transistor_terms = ("c", "b", "e")
    aliases = {"GND": "0", "/+12": "vcc", "/T": "t", "/tD": "td", "/ALC": "alc", "/IN": "rfin", "/OUT": "rfout"}
    for number in range(1, 6):
        collector, base, emitter, _ = elements[f"Q85-{number}"]
        for terminal, node in zip(transistor_terms, (collector, base, emitter)):
            aliases.setdefault(node, f"q{number}{terminal}")
    named = {ref: [aliases.get(token, token) for token in terms] for ref, terms in elements.items()}
    for ref, expected in {
        "R85-6": ["q5e", "0", "3.3"],
        "R85-8": ["q4e", "q1c", "10"],
        "R85-10": ["q3e", "q2c", "10"],
        "Q85-1": ["q1c", "q1b", "0", "MPS6514"],
        "Q85-2": ["q2c", "q2b", "0", "MPS6514"],
        "XT85-1": ["vcc", "q5c", "0", "rfout", "DRV80285_OUTPUT"],
    }.items():
        if named[ref] != expected:
            raise ValueError(f"Unexpected connectivity for {ref}: {named[ref]}")
    for ref, terms in named.items():
        if len(terms) != {"R": 3, "C": 3, "D": 3, "Q": 4, "X": 4 if ref.startswith("XL") else 5}[ref[0]]:
            raise ValueError(f"Invalid simulation instance: {ref} {terms}")
    return includes, named


def circuit_lines(elements, overrides):
    return [" ".join([ref, *terms, *overrides.get(ref, ())]) for ref, terms in elements.items()]


def run_spice(case, description, lines, *, raw=False):
    deck = GENERATED / f"{case}.cir"
    logfile = GENERATED / f"{case}.log"
    deck.write_text("\n".join([f"80285 {description}", *lines, ".end", ""]), encoding="utf-8")
    command = [NGSPICE, "-b", "-o", str(logfile)]
    if raw:
        rawfile = GENERATED / f"{case}.raw"
        command += ["-r", str(rawfile)]
    run_checked([*command, str(deck)], cwd=GENERATED)
    log = logfile.read_text(encoding="utf-8", errors="replace")
    if any(word in log.lower() for word in ("error:", "warning:", "failed", "aborted", "invalid argument")):
        raise RuntimeError(f"{case}:\n{log}")
    if raw:
        names, rows = parse_ascii_raw(rawfile)
        return dict(zip(names, np.asarray(rows).T))
    return None


def fixture(t=10.4, td=4.4, alc=ALC_V, load=50):
    return [f"V_supply vcc 0 {SUPPLY_V}", f"V_t t 0 {t}", f"V_td td 0 {td}",
            f"V_alc alc 0 {alc}", "V_rf source 0 DC 0 AC 1",
            f"R_source source rfin {SOURCE_OHMS}", f"R_load rfout 0 {load}"]


def db(voltage_ratio):
    return 20 * np.log10(np.maximum(np.abs(voltage_ratio), 1e-15))


def bias_run(includes, elements, case, t, td):
    data = run_spice(case, "DC bias", [*includes, *circuit_lines(elements, {}), *fixture(t=t, td=td),
                                      ".op", ".options filetype=ascii"], raw=True)
    return {name[2:-1]: float(values[0].real) for name, values in data.items() if name.startswith("v(")}


def ac_run(includes, elements, case, alc=ALC_V, load=50, overrides=None):
    data = run_spice(case, "small-signal RF response", [*includes, *circuit_lines(elements, overrides or {}),
                     *fixture(alc=alc, load=load), AC, ".options filetype=ascii"], raw=True)
    rfin, rfout = data["v(rfin)"], data["v(rfout)"]
    zin = rfin / ((data["v(source)"] - rfin) / SOURCE_OHMS)
    q3c, q4c = data["v(q3c)"], data["v(q4c)"]
    return {
        "frequency_hz": data["frequency"].real,
        "gain_db": db(rfout / rfin), "source_to_out_db": db(rfout / data["v(source)"]),
        "q3c_over_in_db": db(q3c / rfin), "q4c_over_q3c_db": db(q4c / q3c),
        "out_over_q4c_db": db(rfout / q4c),
        "zin_real_ohm": zin.real, "zin_imag_ohm": zin.imag, "zin_magnitude_ohm": np.abs(zin),
    }


def sampled_value(data, column, mhz):
    sample = np.argmin(np.abs(data["frequency_hz"] - mhz * 1e6))
    if abs(data["frequency_hz"][sample] - mhz * 1e6) > 1:
        raise ValueError(f"{mhz} MHz is off the AC sample grid")
    return data[column][sample]


def retained_drive(path, edge):
    # 80280's first long closure spans 10 to 90 ms. The steady interval between
    # edge windows can be skipped because the key-up trace starts from a DC solve.
    origin = 0.010 if edge == "down" else 0.090
    raw = np.genfromtxt(CONTROL_DATA / path, names=True, delimiter=",")
    start, stop = origin - KEY_PRE_S, origin + KEY_WINDOW_S[edge]
    # Exclude endpoints already inserted below, including roundoff from
    # subtracting the absolute origin of the retained trace.
    use = (raw["time_s"] > start + 1e-12) & (raw["time_s"] < stop - 1e-12)
    time = np.r_[start, raw["time_s"][use], stop]
    return time - start, np.interp(time, raw["time_s"], raw["t"]), np.interp(time, raw["time_s"], raw["td"])


def key_drive(case, edge):
    if case.startswith("80280"):
        return retained_drive("driver-only-td.csv" if case.endswith("driver-only") else "keying.csv", edge)
    delay = KEY_DELAY_S if case == "delayed" and edge == "down" else 0
    duration = KEY_PRE_S + KEY_WINDOW_S[edge]
    time = np.array(sorted({0., KEY_PRE_S, KEY_PRE_S + KEY_RISE_S,
                            KEY_PRE_S + delay, KEY_PRE_S + delay + KEY_RISE_S, duration}))
    t0, t1 = (0.2, 10.4) if edge == "down" else (10.4, 0.2)
    td0, td1 = (0.2, 4.4) if edge == "down" else (4.4, 0.2)
    t = np.interp(time, [KEY_PRE_S, KEY_PRE_S + KEY_RISE_S], [t0, t1])
    td = np.interp(time, [KEY_PRE_S + delay, KEY_PRE_S + delay + KEY_RISE_S], [td0, td1])
    return time, t, td


def pwl(name, time, volts):
    lines = [f"V_{name} {name} 0 PWL("]
    lines += [f"+ {seconds:.12g} {voltage:.10g}" for seconds, voltage in zip(time, volts)]
    return [*lines, "+ )"]


def key_run(includes, elements, case, edge):
    time, t, td = key_drive(case, edge)
    run_id = f"{case}-{edge}"
    waveform = GENERATED / f"{run_id}.txt"
    step = 1 / (KEY_CARRIER_HZ * SAMPLES_PER_CYCLE)
    # Opposite RF polarities cancel the output transient common to both boards.
    # Coherent demodulation then measures the 3.5 MHz carrier through keying.
    run_spice(run_id, "keyed RF transient", [
        *includes, ".subckt driver vcc t td alc rfin rfout", *circuit_lines(elements, {}), ".ends driver",
        f"V_supply vcc 0 {SUPPLY_V}", f"V_alc alc 0 {ALC_V}", *pwl("t", time, t), *pwl("td", time, td),
        "X_positive vcc t td alc in_pos out_pos driver", "X_negative vcc t td alc in_neg out_neg driver",
        f"V_positive src_pos 0 SIN(0 {KEY_DRIVE_VPK} {KEY_CARRIER_HZ})",
        f"V_negative src_neg 0 SIN(0 {-KEY_DRIVE_VPK} {KEY_CARRIER_HZ})",
        "R_in_pos src_pos in_pos 50", "R_in_neg src_neg in_neg 50", "R_out_pos out_pos 0 50", "R_out_neg out_neg 0 50",
        ".options reltol=1e-5 vntol=1e-8 abstol=1e-11", ".control",
        f"tran {step:.12g} {time[-1]:.12g} 0 {step:.12g}", "linearize v(out_pos) v(out_neg)",
        "let carrier = (v(out_pos)-v(out_neg))/2", "set wr_singlescale", "set numdgt=12",
        f"wrdata {waveform.name} carrier", "quit", ".endc",
    ])
    times, carrier = np.loadtxt(waveform, unpack=True)
    bin_size = SAMPLES_PER_CYCLE * ENVELOPE_CYCLES
    complete = (len(times) // bin_size) * bin_size
    bins = times[:complete].reshape(-1, bin_size)
    signal = carrier[:complete].reshape(-1, bin_size)
    amplitude = 2 * np.abs(np.mean(signal * np.exp(-2j * np.pi * KEY_CARRIER_HZ * bins), axis=1))
    center = bins.mean(axis=1)
    return np.column_stack(((center - KEY_PRE_S) * 1e3, np.interp(center, time, t),
                            np.interp(center, time, td), amplitude * 1e3))


def decorate(axis, x, y):
    axis.set(xlabel=x, ylabel=y)
    axis.grid(alpha=.22)


def plot_gain(nominal, alc_data):
    figure, axes = plt.subplots(2, 2, figsize=(11, 7), layout="constrained")
    frequency = nominal["frequency_hz"] / 1e6
    axes[0, 0].plot(frequency, nominal["gain_db"], color=COLORS[0])
    axes[0, 0].set_title("Gain between board pins at 4.3 V ALC")
    decorate(axes[0, 0], "Frequency (MHz)", "OUT / IN (dB)")
    for index, (key, label) in enumerate(zip(("q3c_over_in_db", "q4c_over_q3c_db", "out_over_q4c_db"), ("Q85-3 C / IN", "Q85-4 C / Q85-3 C", "OUT / Q85-4 C"))):
        axes[1, 0].plot(frequency, nominal[key], label=label, color=COLORS[index])
    axes[1, 0].set_title("Internal collectors, simulation only")
    axes[1, 0].legend(fontsize=8, loc="best")
    decorate(axes[1, 0], "Frequency (MHz)", "Voltage ratio (dB)")
    for index, mhz in enumerate((3.5, 7., 14., 28.)):
        values = [sampled_value(ac, "gain_db", mhz) for _, ac, _ in alc_data]
        axes[0, 1].plot([volts for volts, _, _ in alc_data], values, label=f"{mhz:g} MHz", color=COLORS[index])
    axes[0, 1].set_title("ALC reduces gain as its voltage falls")
    axes[0, 1].legend(fontsize=8, loc="best")
    decorate(axes[0, 1], "ALC pin (V)", "OUT / IN (dB)")
    volts = [voltage for voltage, _, _ in alc_data]
    for index, (signal, label) in enumerate((("q1c", "Q85-1 collector"), ("q2c", "Q85-2 collector"))):
        axes[1, 1].plot(volts, [op[signal] for _, _, op in alc_data], label=label, color=COLORS[index])
    axes[1, 1].set_title("ALC transistors, simulation only")
    axes[1, 1].legend(fontsize=8, loc="best")
    decorate(axes[1, 1], "ALC pin (V)", "Collector voltage (V)")
    figure.savefig(STUDY / "figures/gain-and-alc.png", dpi=160)
    plt.close(figure)


def plot_keying(key_results):
    figure, axes = plt.subplots(3, 2, figsize=(11, 9), layout="constrained")
    for column, edge in enumerate(("down", "up")):
        axes[0, column].set_title(f"Key-{edge}")
        for index, case in enumerate(LABELS):
            time, t, td, out = key_results[case, edge].T
            rail_axis = axes[0 if index < 2 else 1, column]
            if edge != "up" or case != "delayed":
                rail_axis.plot(time, t, color=COLORS[index], label=LABELS[case])
                rail_axis.plot(time, td, color=COLORS[index], linestyle="--")
                axes[2, column].plot(time, out, color=COLORS[index], label=LABELS[case])
        for row in range(3):
            axis = axes[row, column]
            axis.axvline(0, color="#777777", linewidth=.8, linestyle=":")
            decorate(axis, "Time from key command (ms)", "OUT carrier (mV peak)" if row == 2 else "T solid, tD dashed (V)")
        axes[0, column].set_ylim(-.5, 11.5)
        axes[1, column].set_ylim(-2.5, 11.5)
        axes[2, column].set_ylim(bottom=0)
    for row in range(3):
        axes[row, 0].legend(fontsize=8, loc="best")
    figure.savefig(STUDY / "figures/keyed-carrier.png", dpi=160)
    plt.close(figure)


def plot_sensitivity(cases):
    figure, axes = plt.subplots(2, 2, figsize=(11, 7), layout="constrained")
    nominal = cases["nominal"]
    frequency = nominal["frequency_hz"] / 1e6
    groups = {"Tap position": "tap", "Coil inductance": "inductance", "Transformer ratio": "ratio", "Output load": "load"}
    for index, (label, prefix) in enumerate(groups.items()):
        for axis, key, subtract in ((axes[0, 1], "gain_db", True), (axes[1, 1], "zin_magnitude_ohm", False)):
            samples = np.array([data[key] for case, data in cases.items() if case.startswith(prefix)])
            if subtract:
                samples = samples - nominal[key]
            axis.fill_between(frequency, samples.min(axis=0), samples.max(axis=0), alpha=.18, color=COLORS[index], label=label)
    axes[0, 0].plot(frequency, nominal["gain_db"], color=COLORS[0])
    axes[0, 0].set_title("Nominal board gain")
    axes[0, 1].set_title("Gain change across each assumption sweep")
    axes[1, 0].plot(frequency, nominal["zin_real_ohm"], label="Resistance", color=COLORS[0])
    axes[1, 0].plot(frequency, nominal["zin_imag_ohm"], label="Reactance", color=COLORS[1])
    axes[1, 0].axhline(0, color="#777777", linewidth=.8)
    axes[1, 0].set_title("Nominal input impedance")
    axes[1, 1].plot(frequency, nominal["zin_magnitude_ohm"], color="#324458", linewidth=1.1, label="Nominal")
    axes[1, 1].set_title("Input impedance magnitude across assumption sweeps")
    for axis, units in zip(axes.flat, ("OUT / IN (dB)", "Difference from nominal (dB)", "Impedance (Ω)", "Magnitude (Ω)")):
        decorate(axis, "Frequency (MHz)", units)
    axes[1, 0].legend(fontsize=8, loc="best")
    axes[1, 1].legend(fontsize=8, loc="best")
    figure.savefig(STUDY / "figures/winding-sensitivity.png", dpi=160)
    plt.close(figure)


def main():
    for path in (GENERATED, STUDY / "data", STUDY / "figures"):
        path.mkdir(parents=True, exist_ok=True)
    includes, elements = export_circuit()
    manifest = []
    bias = {}
    for case, t, td in (("receive", .2, .2), ("t-only", 10.4, .2), ("transmit", 10.4, 4.4)):
        bias[case] = bias_run(includes, elements, case, t, td)
        manifest.append((case, "op", f"T={t} V; tD={td} V; ALC=4.3 V; +12=13 V"))
    nodes = ("vcc", "t", "td", "alc", "rfin", "rfout", "q1c", "q1b", "q2c", "q2b",
             "q3c", "q3b", "q3e", "q4c", "q4b", "q4e", "q5c", "q5b", "q5e")
    write_csv(STUDY / "data/bias.csv", ["case", *(n + "_v" for n in nodes), "q3_emitter_ma", "q4_emitter_ma", "q5_emitter_ma"],
              ((case, *(op[n] for n in nodes), (op["q3e"]-op["q2c"])*100, (op["q4e"]-op["q1c"])*100, op["q5e"]/3.3*1000)
               for case, op in bias.items()))
    print("Bias: three states", flush=True)

    alc_data = []
    for step in range(2, 44):
        voltage = step / 10
        case = f"alc-{step:02}"
        ac = ac_run(includes, elements, case, alc=voltage)
        op = run_spice(f"{case}-op", "ALC bias", [*includes, *circuit_lines(elements, {}), *fixture(alc=voltage),
                                                   ".op", ".options filetype=ascii"], raw=True)
        collectors = {node: op[f"v({node})"][0].real for node in ("q1c", "q2c")}
        alc_data.append((voltage, ac, collectors))
        manifest.extend(((case, "ac", f"ALC={voltage:g} V; 3.5–30 MHz at 100 kHz; 50 ohm load"),
                         (f"{case}-op", "op", f"ALC={voltage:g} V; Q85-1 and Q85-2 collector nodes")))
    nominal = alc_data[-1][1]
    write_csv(STUDY / "data/rf.csv", list(nominal), zip(*nominal.values()))
    write_csv(STUDY / "data/alc.csv", ("alc_v", "frequency_hz", "gain_db", "source_to_out_db", "q1_collector_v", "q2_collector_v"),
              ((voltage, mhz * 1e6, sampled_value(data, "gain_db", mhz), sampled_value(data, "source_to_out_db", mhz), op["q1c"], op["q2c"])
               for voltage, data, op in alc_data for mhz in FREQUENCIES))
    plot_gain(nominal, alc_data)
    print("RF: 42 ALC settings", flush=True)

    cases = {"nominal": nominal}
    variants = [(f"tap-L{coil}-{value:g}", 50, {f"XL85-{coil}": [f"F={value}"]})
                for coil in (1, 2) for value in (.20, .45)]
    variants += [(f"inductance-L{coil}-{value}u", 50, {f"XL85-{coil}": [f"LEND={value}u"]})
                 for coil in (1, 2) for value in (6, 16)]
    variants += [(f"ratio-{ratio:g}", 50, {"XT85-1": [f"LS={10 / ratio**2:.8g}u"]}) for ratio in (1.5, 3.)]
    variants += [(f"load-{load}", load, {}) for load in (25, 100)]
    for case, load, adjustments in variants:
        cases[case] = ac_run(includes, elements, case, load=load, overrides=adjustments)
        manifest.append((case, "ac", f"load={load} ohm; instance overrides={adjustments}"))
    write_csv(STUDY / "data/sensitivity.csv", ["case", *nominal],
              ((case, *row) for case, data in cases.items() for row in zip(*data.values())))
    plot_sensitivity(cases)
    print("Sensitivity: twelve perturbations", flush=True)

    key_results = {}
    for case in LABELS:
        for edge in ("down", "up"):
            if case == "delayed" and edge == "up":
                key_results[case, edge] = key_results["simultaneous", edge]
                continue
            key_results[case, edge] = key_run(includes, elements, case, edge)
            manifest.append((f"{case}-{edge}", "tran", f"{LABELS[case]}; 3.5 MHz, 10 uV peak source; 50 ohm source/load; 32-cycle envelope"))
            print(f"Keying: {case} {edge}", flush=True)
    write_csv(STUDY / "data/keying.csv", ("case", "edge", "relative_time_ms", "t_v", "td_v", "out_carrier_mv_peak"),
              ((case, edge, *row) for (case, edge), data in key_results.items() for row in data))
    plot_keying(key_results)
    write_csv(STUDY / "manifest.csv", ("case", "analysis", "fixture"), manifest)


if __name__ == "__main__":
    main()
