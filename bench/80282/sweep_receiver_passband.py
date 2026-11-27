#!/usr/bin/env python3
"""Automated receive-passband sweep for the Ten-Tec Triton IV 80282 filter.

The Siglent SDG1032X drives the radio antenna through an external attenuator.
The SDS1202X-E measures recovered audio at the 80279 AUDIO board pin.  The
script steps the RF source rather than using a continuous hardware sweep so
every retained row has a settled, averaged scope measurement.

This is an end-to-end receive test.  Its curve includes the RF amplifier,
mixer, crystal filter, product detector, and audio preamplifier.  It is not a
measurement of the bare crystal lattice and must not be described as one.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import re
import socket
import statistics
import sys
import time
from pathlib import Path


DEFAULT_SCOPE = "192.168.1.157"
DEFAULT_GEN = "192.168.1.158"
DEFAULT_START = 14.095e6
DEFAULT_STOP = 14.105e6
DEFAULT_POINTS = 201  # 50 Hz spacing over the default 10 kHz span
MAX_ANTENNA_VPP = 100e-6

VDIV_STEPS = [
    500e-6, 1e-3, 2e-3, 5e-3, 10e-3, 20e-3, 50e-3,
    0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0,
]

_NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def parse_number(text: str) -> float:
    match = _NUM_RE.search(text)
    if not match:
        raise ValueError(f"no number in reply {text!r}")
    return float(match.group(0))


def vdiv_token(volts: float) -> str:
    if volts < 1e-3:
        return f"{round(volts * 1e6)}UV"
    if volts < 1.0:
        return f"{round(volts * 1e3)}MV"
    return f"{round(volts)}V"


class Link:
    """Minimal VXI-11 or raw-socket SCPI link."""

    def __init__(self, host: str, transport: str, port: int, timeout: float = 6.0):
        self._resource = None
        self._socket = None
        if transport == "vxi11":
            try:
                import pyvisa
            except ImportError as exc:
                raise SystemExit(
                    "pyvisa is required for VXI-11. Install pyvisa and pyvisa-py."
                ) from exc
            manager = pyvisa.ResourceManager("@py")
            self._resource = manager.open_resource(f"TCPIP0::{host}::INSTR")
            self._resource.timeout = int(timeout * 1000)
            self._resource.read_termination = "\n"
            self._resource.write_termination = "\n"
        elif transport == "socket":
            self._socket = socket.create_connection((host, port), timeout=timeout)
            self._socket.settimeout(timeout)
        else:
            raise ValueError(f"unsupported transport {transport!r}")

    def write(self, command: str) -> None:
        if self._resource is not None:
            self._resource.write(command)
        else:
            assert self._socket is not None
            self._socket.sendall((command + "\n").encode("ascii"))

    def query(self, command: str) -> str:
        if self._resource is not None:
            return self._resource.query(command).strip()
        self.write(command)
        assert self._socket is not None
        reply = b""
        while not reply.endswith(b"\n"):
            block = self._socket.recv(4096)
            if not block:
                break
            reply += block
        return reply.decode("ascii", "replace").strip()

    def close(self) -> None:
        try:
            if self._resource is not None:
                self._resource.close()
            elif self._socket is not None:
                self._socket.close()
        except Exception:
            pass


class Generator:
    """Siglent SDG1032X channel 1 with the output normally kept off."""

    def __init__(self, link: Link):
        self.link = link

    def idn(self) -> str:
        return self.link.query("*IDN?")

    def configure(self, frequency: float, amplitude_vpp: float) -> None:
        for state in ("SWWV", "MDWV", "BTWV"):
            self.link.write(f"C1:{state} STATE,OFF")
        self.link.write("C1:OUTP LOAD,50")
        self.link.write(
            "C1:BSWV WVTP,SINE,"
            f"FRQ,{frequency:.6f},AMP,{amplitude_vpp:.9f},OFST,0"
        )

    def set_frequency(self, frequency: float) -> None:
        self.link.write(f"C1:BSWV FRQ,{frequency:.6f}")

    def set_amplitude(self, amplitude_vpp: float) -> None:
        self.link.write(f"C1:BSWV AMP,{amplitude_vpp:.9f}")

    def output(self, enabled: bool) -> None:
        self.link.write(f"C1:OUTP {'ON' if enabled else 'OFF'}")


class Scope:
    """Siglent SDS1202X-E measuring audio on channel 2."""

    def __init__(self, link: Link, attenuation: float, averages: int):
        self.link = link
        self.attenuation = attenuation
        self.averages = averages
        self.current_vdiv = 0.1 * attenuation

    def idn(self) -> str:
        return self.link.query("*IDN?")

    def configure(self) -> None:
        self.link.write("CHDR OFF")
        self.link.write("C1:TRA OFF")
        self.link.write("C2:TRA ON")
        self.link.write("C2:CPL A1M")
        self.link.write(f"C2:ATTN {self.attenuation:g}")
        self.link.write("C2:OFST 0V")
        self.link.write("BWL C2,ON")
        self.link.write("TDIV 5MS")
        self.link.write("TRSE EDGE,SR,C2,HT,OFF")
        self.link.write("C2:TRCP AC")
        self.link.write("C2:TRLV 0V")
        self.link.write("TRSL POS")
        self.link.write("TRMD AUTO")
        if self.averages > 1:
            self.link.write(f"ACQW AVERAGE,{self.averages}")
        else:
            self.link.write("ACQW SAMPLING")
        self.set_vdiv(self.current_vdiv)

    def set_vdiv(self, requested: float) -> None:
        allowed = [step * self.attenuation for step in VDIV_STEPS]
        chosen = min(allowed, key=lambda item: abs(math.log10(item / requested)))
        if chosen != self.current_vdiv:
            self.link.write(f"C2:VDIV {vdiv_token(chosen)}")
            self.current_vdiv = chosen
            time.sleep(0.08)

    def clear(self) -> None:
        if self.averages > 1:
            self.link.write("CLSW")

    def read_parameter(self, name: str, reads: int = 3) -> float:
        values = []
        for _ in range(reads):
            try:
                value = parse_number(self.link.query(f"C2:PAVA? {name}"))
            except Exception:
                time.sleep(0.04)
                continue
            if 0.0 < value < 1e30:
                values.append(value)
            time.sleep(0.04)
        return statistics.median(values) if values else float("nan")

    def autorange(self, settle: float) -> float:
        floor = VDIV_STEPS[0] * self.attenuation
        for _ in range(5):
            peak_to_peak = self.read_parameter("PKPK")
            if math.isnan(peak_to_peak):
                if self.current_vdiv <= floor:
                    return float("nan")
                self.set_vdiv(max(floor, self.current_vdiv / 5))
            else:
                occupied = peak_to_peak / self.current_vdiv
                if 1.5 <= occupied <= 6.5:
                    return peak_to_peak
                target = max(floor, peak_to_peak / 4.5)
                old = self.current_vdiv
                self.set_vdiv(target)
                if old == self.current_vdiv:
                    return peak_to_peak
            self.clear()
            time.sleep(settle)
        return self.read_parameter("PKPK")

    def measure_audio(self, settle: float) -> tuple[float, float, float]:
        peak_to_peak = self.autorange(settle)
        self.clear()
        time.sleep(settle)
        rms = self.read_parameter("RMS")
        frequency = self.read_parameter("FREQ")
        return peak_to_peak, rms, frequency


def sweep_frequencies(start: float, stop: float, points: int) -> list[float]:
    if points < 2:
        return [start]
    return [start + (stop - start) * index / (points - 1)
            for index in range(points)]


def safe_antenna_level(amplitude_vpp: float, attenuation_db: float) -> float:
    return amplitude_vpp * 10 ** (-attenuation_db / 20.0)


def run_mode(
    mode: str,
    generator: Generator,
    scope: Scope,
    frequencies: list[float],
    amplitude_vpp: float,
    settle: float,
    agc_wait: float,
) -> tuple[list[dict[str, float | str]], dict[str, float | str]]:
    generator.output(False)
    answer = input(
        f"\nSet the radio to {mode.upper()}, receive only. "
        f"Type {mode.upper()} when ready: "
    ).strip().upper()
    if answer != mode.upper():
        raise KeyboardInterrupt(f"confirmation did not match {mode.upper()}")

    rows: list[dict[str, float | str]] = []
    generator.set_amplitude(amplitude_vpp)
    generator.set_frequency(frequencies[0])
    generator.output(True)
    time.sleep(settle)
    try:
        for index, rf_frequency in enumerate(frequencies, 1):
            generator.set_frequency(rf_frequency)
            time.sleep(settle)
            scope.clear()
            time.sleep(settle)
            audio_vpp, audio_rms, audio_frequency = scope.measure_audio(settle)
            row: dict[str, float | str] = {
                "mode": mode.upper(),
                "rf_frequency_hz": rf_frequency,
                "audio_frequency_hz": audio_frequency,
                "audio_rms_v": audio_rms,
                "audio_vpp": audio_vpp,
            }
            rows.append(row)
            print(
                f"  {mode.upper()} [{index:3d}/{len(frequencies)}] "
                f"{rf_frequency/1e6:.6f} MHz  "
                f"audio {audio_frequency:8.1f} Hz  "
                f"{audio_rms*1e3:9.3f} mVrms"
            )

        valid = [row for row in rows
                 if math.isfinite(float(row["audio_rms_v"]))
                 and float(row["audio_rms_v"]) > 0]
        if not valid:
            raise RuntimeError(f"no usable audio measurements in {mode.upper()}")
        peak = max(valid, key=lambda row: float(row["audio_rms_v"]))
        peak_frequency = float(peak["rf_frequency_hz"])
        peak_rms = float(peak["audio_rms_v"])

        generator.set_frequency(peak_frequency)
        generator.set_amplitude(amplitude_vpp)
        time.sleep(agc_wait)
        _, full_rms, _ = scope.measure_audio(settle)
        generator.set_amplitude(amplitude_vpp / 2.0)
        time.sleep(agc_wait)
        _, half_rms, _ = scope.measure_audio(settle)
        generator.set_amplitude(amplitude_vpp)
        if full_rms > 0 and half_rms > 0:
            half_level_change_db = 20.0 * math.log10(full_rms / half_rms)
        else:
            half_level_change_db = float("nan")
        linearity_valid = (
            math.isfinite(half_level_change_db)
            and 5.0 <= half_level_change_db <= 7.0
        )

        summary: dict[str, float | str] = {
            "mode": mode.upper(),
            "peak_rf_frequency_hz": peak_frequency,
            "peak_audio_rms_v": peak_rms,
            "half_drive_output_change_db": half_level_change_db,
            "linearity_expectation_db": 6.0206,
            "evidence_status": (
                "usable_linear_response" if linearity_valid
                else "invalid_agc_compression_or_noise"
            ),
        }
        return rows, summary
    finally:
        generator.output(False)


def infer_zero_reference(rows: list[dict[str, float | str]]) -> tuple[float, int]:
    """Infer the RF zero-beat reference and passed-side sign from audio frequency.

    For a valid point, zero beat is either RF-audio or RF+audio.  The correct
    sign produces a nearly constant result across the passed band.
    """
    amplitudes = [float(row["audio_rms_v"]) for row in rows
                  if math.isfinite(float(row["audio_rms_v"]))]
    if not amplitudes:
        return float("nan"), 0
    threshold = max(amplitudes) * 10 ** (-15.0 / 20.0)
    usable = [row for row in rows
              if math.isfinite(float(row["audio_rms_v"]))
              and float(row["audio_rms_v"]) >= threshold
              and math.isfinite(float(row["audio_frequency_hz"]))
              and 100.0 <= float(row["audio_frequency_hz"]) <= 5000.0]
    if len(usable) < 3:
        return float("nan"), 0
    candidates = {}
    for sign in (-1, 1):
        values = [float(row["rf_frequency_hz"])
                  + sign * float(row["audio_frequency_hz"])
                  for row in usable]
        candidates[sign] = (statistics.pstdev(values), statistics.median(values))
    sign = min(candidates, key=lambda item: candidates[item][0])
    return candidates[sign][1], sign


def finish_rows(rows: list[dict[str, float | str]]) -> tuple[float, int]:
    valid = [float(row["audio_rms_v"]) for row in rows
             if math.isfinite(float(row["audio_rms_v"]))
             and float(row["audio_rms_v"]) > 0]
    peak = max(valid) if valid else float("nan")
    zero_reference, sign = infer_zero_reference(rows)
    for row in rows:
        rms = float(row["audio_rms_v"])
        if peak > 0 and rms > 0 and math.isfinite(rms):
            row["relative_db"] = 20.0 * math.log10(rms / peak)
        else:
            row["relative_db"] = float("nan")
        if math.isfinite(zero_reference):
            row["rf_offset_from_inferred_zero_hz"] = abs(
                float(row["rf_frequency_hz"]) - zero_reference
            )
        else:
            row["rf_offset_from_inferred_zero_hz"] = float("nan")
    return zero_reference, sign


def write_csv(
    path: Path,
    rows: list[dict[str, float | str]],
    metadata: dict[str, str | float | int],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "mode", "rf_frequency_hz", "audio_frequency_hz", "audio_rms_v",
        "audio_vpp", "relative_db", "rf_offset_from_inferred_zero_hz",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        stream.write("# Ten-Tec 540 80282 end-to-end receive-passband sweep\n")
        stream.write("# This is measured whole-receiver evidence, not a bare-filter trace.\n")
        for key, value in metadata.items():
            stream.write(f"# {key},{value}\n")
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, summaries: list[dict[str, float | str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "mode", "peak_rf_frequency_hz", "peak_audio_rms_v",
        "half_drive_output_change_db", "linearity_expectation_db",
        "evidence_status", "inferred_zero_reference_hz", "zero_reference_sign",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summaries)


def write_plot(path: Path, rows: list[dict[str, float | str]]) -> bool:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    figure, axis = plt.subplots(figsize=(9.2, 5.6))
    for mode, color in (("SB-N", "#176b87"), ("SB-R", "#b34b35")):
        selected = [row for row in rows
                    if row["mode"] == mode
                    and math.isfinite(float(row["relative_db"]))]
        selected.sort(key=lambda row: float(row["rf_frequency_hz"]))
        axis.plot(
            [float(row["rf_frequency_hz"]) / 1e6 for row in selected],
            [float(row["relative_db"]) for row in selected],
            marker=".", markersize=3, linewidth=1.2, label=mode, color=color,
        )
    axis.set(
        xlabel="SDG frequency at the antenna (MHz)",
        ylabel="Recovered AUDIO level relative to each mode's peak (dB)",
        title="Triton 540 end-to-end receive response: SB-N and SB-R",
        ylim=(-45, 2),
    )
    axis.grid(True, alpha=0.25)
    axis.legend()
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Automated SB-N/SB-R receive-passband sweep for assembly 80282.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--scope", default=DEFAULT_SCOPE)
    parser.add_argument("--gen", default=DEFAULT_GEN)
    parser.add_argument("--transport", choices=("vxi11", "socket"), default="vxi11")
    parser.add_argument("--scope-port", type=int, default=5025)
    parser.add_argument("--gen-port", type=int, default=5024)
    parser.add_argument("--start", type=float, default=DEFAULT_START)
    parser.add_argument("--stop", type=float, default=DEFAULT_STOP)
    parser.add_argument("--points", type=int, default=DEFAULT_POINTS)
    parser.add_argument("--amplitude", type=float, default=0.010,
                        help="SDG amplitude before the external attenuator, Vpp")
    parser.add_argument("--attenuation-db", type=float, default=60.0,
                        help="physical attenuation between SDG and antenna jack")
    parser.add_argument("--scope-attenuation", type=float, default=10.0,
                        help="scope CH2 probe factor")
    parser.add_argument("--averages", type=int, default=16)
    parser.add_argument("--settle", type=float, default=0.30)
    parser.add_argument("--agc-wait", type=float, default=3.0,
                        help="seconds allowed after a linearity-test level change")
    parser.add_argument("--mode", choices=("both", "sbn", "sbr"), default="both")
    parser.add_argument("--identify-only", action="store_true",
                        help="query instrument identities with SDG output off, then exit")
    parser.add_argument("--out-dir", default=str(Path(__file__).parent))
    args = parser.parse_args(argv)

    if not (args.start < args.stop):
        parser.error("--start must be below --stop")
    if args.points < 2:
        parser.error("--points must be at least 2")
    antenna_vpp = safe_antenna_level(args.amplitude, args.attenuation_db)
    if antenna_vpp > MAX_ANTENNA_VPP:
        parser.error(
            f"predicted antenna level {antenna_vpp*1e6:.1f} uVpp exceeds the "
            f"{MAX_ANTENNA_VPP*1e6:.0f} uVpp safety limit"
        )

    print("SAFETY: radio must remain in receive; disconnect microphone and key.")
    print("SAFETY: the entered attenuation must be physically installed.")
    print(
        f"SDG {args.amplitude*1e3:.3f} mVpp through {args.attenuation_db:.1f} dB "
        f"predicts {antenna_vpp*1e6:.3f} uVpp at the antenna."
    )

    generator_link = Link(args.gen, args.transport, args.gen_port)
    scope_link = Link(args.scope, args.transport, args.scope_port)
    generator = Generator(generator_link)
    scope = Scope(scope_link, args.scope_attenuation, args.averages)
    rows: list[dict[str, float | str]] = []
    summaries: list[dict[str, float | str]] = []
    try:
        generator.output(False)
        generator_id = generator.idn()
        scope_id = scope.idn()
        print(f"generator: {generator_id}")
        print(f"scope    : {scope_id}")
        if args.identify_only:
            return 0

        centre = (args.start + args.stop) / 2.0
        generator.configure(centre, args.amplitude)
        scope.configure()
        frequency_points = sweep_frequencies(args.start, args.stop, args.points)
        modes = ("sbn", "sbr") if args.mode == "both" else (args.mode,)
        for mode in modes:
            mode_rows, summary = run_mode(
                mode, generator, scope, frequency_points,
                args.amplitude, args.settle, args.agc_wait,
            )
            zero_reference, sign = finish_rows(mode_rows)
            summary["inferred_zero_reference_hz"] = zero_reference
            summary["zero_reference_sign"] = sign
            rows.extend(mode_rows)
            summaries.append(summary)
    finally:
        try:
            generator.output(False)
        except Exception:
            pass
        generator_link.close()
        scope_link.close()

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = Path(args.out_dir)
    data_path = base / "data" / f"80282-receive-passband-{stamp}.csv"
    summary_path = base / "data" / f"80282-receive-passband-summary-{stamp}.csv"
    plot_path = base / "plots" / f"80282-receive-passband-{stamp}.png"
    metadata: dict[str, str | float | int] = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "generator": generator_id,
        "scope": scope_id,
        "sdg_amplitude_vpp": args.amplitude,
        "external_attenuation_db": args.attenuation_db,
        "predicted_antenna_vpp": antenna_vpp,
        "start_hz": args.start,
        "stop_hz": args.stop,
        "points": args.points,
        "spacing_hz": (args.stop - args.start) / (args.points - 1),
        "scope_probe_attenuation": args.scope_attenuation,
        "scope_averages": args.averages,
        "agc_linearity_wait_s": args.agc_wait,
    }
    write_csv(data_path, rows, metadata)
    write_summary(summary_path, summaries)
    plotted = write_plot(plot_path, rows)

    print(f"\nwrote {data_path}")
    print(f"wrote {summary_path}")
    if plotted:
        print(f"wrote {plot_path}")
    else:
        print("matplotlib is unavailable; CSV files were written without a plot")
    for summary in summaries:
        print(
            f"{summary['mode']}: inferred zero "
            f"{float(summary['inferred_zero_reference_hz'])/1e6:.9f} MHz; "
            f"half-drive output change "
            f"{float(summary['half_drive_output_change_db']):.2f} dB "
            f"(ideal 6.02 dB); {summary['evidence_status']}"
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nSweep cancelled; SDG output was turned off.", file=sys.stderr)
        sys.exit(130)
