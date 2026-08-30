#!/usr/bin/env python3
"""Stepped-sine frequency response of the Ten-Tec 540 80166 receiver rf amplifier.

Drives the transceiver antenna jack with a Siglent SDG1032X and measures the
input/output amplitude ratio with a Siglent SDS1202X-E, one frequency at a time.
This is a software equivalent of the scope's built-in Bode Plot function; doing
it in Python keeps the raw per-point data so the L1-only and composite sweeps can
be overlaid afterwards.

Two sweeps make up a tracking check on 80 m (manual p. 3-8):

    l1-only     .01 uF fitted from the 3.5 MHz trimmer terminal to chassis,
                which swamps L2 and leaves L1 setting the response
    composite   .01 uF removed, so the curve is L1 x Q1 x L2

See README.md in this directory for connections and the run order.
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

# SDS1202X-E vertical steps, probe-referred values are these scaled by attenuation.
VDIV_STEPS = [
    500e-6, 1e-3, 2e-3, 5e-3, 10e-3, 20e-3, 50e-3,
    0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0,
]

# Horizontal steps, as (seconds, SCPI token).
TDIV_STEPS = []
for _decade, _suffix in ((1e-9, "NS"), (1e-6, "US"), (1e-3, "MS"), (1.0, "S")):
    for _mant in (1, 2, 5, 10, 20, 50, 100, 200, 500):
        TDIV_STEPS.append((_mant * _decade, f"{_mant}{_suffix}"))
TDIV_STEPS = sorted(t for t in TDIV_STEPS if 1e-9 <= t[0] <= 50.0)

SCREEN_VDIVS = 8       # vertical divisions
SCREEN_HDIVS = 14      # horizontal divisions on the SDS1000X-E


# --------------------------------------------------------------------------- #
# transport
# --------------------------------------------------------------------------- #

class Link:
    """Minimal SCPI link, either VXI-11 (via pyvisa-py) or a raw TCP socket."""

    def __init__(self, host: str, transport: str = "vxi11",
                 port: int | None = None, timeout: float = 5.0):
        self.host = host
        self.transport = transport
        self._sock = None
        self._res = None

        if transport == "vxi11":
            try:
                import pyvisa
            except ImportError:  # pragma: no cover - environment dependent
                raise SystemExit(
                    "pyvisa is required for --transport vxi11.\n"
                    "    python -m pip install pyvisa pyvisa-py"
                )
            rm = pyvisa.ResourceManager("@py")
            self._res = rm.open_resource(f"TCPIP0::{host}::INSTR")
            self._res.timeout = int(timeout * 1000)
            self._res.read_termination = "\n"
            self._res.write_termination = "\n"
        elif transport == "socket":
            self._sock = socket.create_connection((host, port), timeout=timeout)
            self._sock.settimeout(timeout)
        else:
            raise ValueError(f"unknown transport {transport!r}")

    def write(self, cmd: str) -> None:
        if self._res is not None:
            self._res.write(cmd)
        else:
            self._sock.sendall((cmd + "\n").encode("ascii"))

    def query(self, cmd: str) -> str:
        if self._res is not None:
            return self._res.query(cmd).strip()
        self.write(cmd)
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = self._sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        return buf.decode("ascii", "replace").strip()

    def close(self) -> None:
        try:
            if self._res is not None:
                self._res.close()
            elif self._sock is not None:
                self._sock.close()
        except Exception:
            pass


_NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def parse_number(text: str) -> float:
    """Pull the first float out of a Siglent reply such as '3.00E-02V'."""
    m = _NUM_RE.search(text)
    if not m:
        raise ValueError(f"no number in reply {text!r}")
    return float(m.group(0))


def nearest_step(value: float, steps) -> float:
    return min(steps, key=lambda s: abs(math.log10(s / value)) if value > 0 else s)


def vdiv_token(volts: float) -> str:
    if volts < 1e-3:
        return f"{round(volts * 1e6)}UV"
    if volts < 1.0:
        return f"{round(volts * 1e3)}MV"
    return f"{round(volts)}V"


# --------------------------------------------------------------------------- #
# instruments
# --------------------------------------------------------------------------- #

class Generator:
    """Siglent SDG1032X, channel 1."""

    def __init__(self, link: Link, channel: int = 1, load: str = "50"):
        self.link = link
        self.ch = f"C{channel}"
        self.load = load

    def idn(self) -> str:
        return self.link.query("*IDN?")

    def configure(self, freq: float, amplitude_vpp: float) -> None:
        for state in ("SWWV", "MDWV", "BTWV"):
            try:
                self.link.write(f"{self.ch}:{state} STATE,OFF")
            except Exception:
                pass
        self.link.write(f"{self.ch}:OUTP LOAD,{self.load}")
        self.link.write(
            f"{self.ch}:BSWV WVTP,SINE,FRQ,{freq:.6f},AMP,{amplitude_vpp:.6f},OFST,0"
        )

    def set_frequency(self, freq: float) -> None:
        self.link.write(f"{self.ch}:BSWV FRQ,{freq:.6f}")

    def set_amplitude(self, amplitude_vpp: float) -> None:
        self.link.write(f"{self.ch}:BSWV AMP,{amplitude_vpp:.6f}")

    def output(self, on: bool) -> None:
        self.link.write(f"{self.ch}:OUTP {'ON' if on else 'OFF'}")


class Scope:
    """Siglent SDS1202X-E."""

    def __init__(self, link: Link, avg_count: int = 16, bwl: bool = True):
        self.link = link
        self.avg_count = avg_count
        self.bwl = bwl
        self.averaging = False
        self._vdiv = {1: None, 2: None}
        self._attn = {1: 1.0, 2: 10.0}

    def idn(self) -> str:
        return self.link.query("*IDN?")

    def configure(self, ch1_attn: float, ch2_attn: float) -> None:
        self._attn = {1: ch1_attn, 2: ch2_attn}
        self.link.write("CHDR OFF")           # bare numeric replies
        for ch, attn in self._attn.items():
            self.link.write(f"C{ch}:TRA ON")
            self.link.write(f"C{ch}:CPL A1M")  # ac coupled, 1 Mohm
            self.link.write(f"C{ch}:ATTN {attn:g}")
            self.link.write(f"C{ch}:OFST 0V")
        self.link.write(f"BWL C1,{'ON' if self.bwl else 'OFF'},"
                        f"C2,{'ON' if self.bwl else 'OFF'}")
        self.link.write("TRSE EDGE,SR,C1,HT,OFF")
        self.link.write("C1:TRCP AC")
        self.link.write("C1:TRLV 0V")
        self.link.write("TRSL POS")
        self.link.write("TRMD NORM")
        if self.avg_count > 1:
            try:
                self.link.write(f"ACQW AVERAGE,{self.avg_count}")
                self.averaging = True
            except Exception:
                self.link.write("ACQW SAMPLING")
        else:
            self.link.write("ACQW SAMPLING")

    def set_timebase_for(self, freq: float, cycles: int = 10) -> float:
        target = (cycles / freq) / SCREEN_HDIVS
        value, token = min(TDIV_STEPS, key=lambda s: abs(math.log10(s[0] / target)))
        self.link.write(f"TDIV {token}")
        return value

    def set_vdiv(self, ch: int, volts_per_div: float) -> None:
        allowed = [s * self._attn[ch] for s in VDIV_STEPS]
        chosen = nearest_step(volts_per_div, allowed)
        if self._vdiv[ch] != chosen:
            self.link.write(f"C{ch}:VDIV {vdiv_token(chosen)}")
            self._vdiv[ch] = chosen
            time.sleep(0.05)

    def clear_sweeps(self) -> None:
        if self.averaging:
            try:
                self.link.write("CLSW")
            except Exception:
                pass

    def read_vpp(self, ch: int, reads: int = 3) -> float:
        vals = []
        for _ in range(reads):
            try:
                raw = self.link.query(f"C{ch}:PAVA? PKPK")
                v = parse_number(raw)
            except Exception:
                continue
            if 0.0 < v < 1e30:
                vals.append(v)
            time.sleep(0.02)
        if not vals:
            return float("nan")
        return statistics.median(vals)

    def autorange(self, ch: int, settle: float = 0.2, tries: int = 4) -> float:
        """Read Vpp, adjusting V/div until it fills a sane part of the screen."""
        floor = VDIV_STEPS[0] * self._attn[ch]
        for _ in range(tries):
            vpp = self.read_vpp(ch)
            vdiv = self._vdiv[ch] or floor
            if math.isnan(vpp) or vpp <= 0:
                # nothing measurable: go more sensitive, or give up at the floor
                if vdiv <= floor * 1.001:
                    return float("nan")
                self.set_vdiv(ch, vdiv / 5)
                self.clear_sweeps()
                time.sleep(settle)
                continue
            span = vpp / vdiv  # divisions occupied
            if 2.5 <= span <= 6.5:
                return vpp
            self.set_vdiv(ch, vpp / 4.5)
            if self._vdiv[ch] == vdiv:
                return vpp  # already at a rail of the V/div range
            self.clear_sweeps()
            time.sleep(settle)
        return self.read_vpp(ch)


# --------------------------------------------------------------------------- #
# sweep
# --------------------------------------------------------------------------- #

def frequencies(start: float, stop: float, points: int, log: bool):
    if points < 2:
        return [start]
    if log:
        a, b = math.log10(start), math.log10(stop)
        return [10 ** (a + (b - a) * i / (points - 1)) for i in range(points)]
    return [start + (stop - start) * i / (points - 1) for i in range(points)]


def measure_point(gen: Generator, scope: Scope, freq: float,
                  settle: float, avg_wait: float):
    gen.set_frequency(freq)
    time.sleep(settle)
    scope.clear_sweeps()
    time.sleep(avg_wait)
    ch1 = scope.autorange(1)
    ch2 = scope.autorange(2)
    if math.isnan(ch1) or math.isnan(ch2) or ch1 <= 0 or ch2 <= 0:
        gain = float("nan")
    else:
        gain = 20 * math.log10(ch2 / ch1)
    return ch1, ch2, gain


def linearity_check(gen: Generator, scope: Scope, freq: float,
                    amplitude: float, settle: float, avg_wait: float) -> str:
    """Compare gain at full and half drive; a real difference means compression."""
    gen.set_amplitude(amplitude)
    _, _, g_full = measure_point(gen, scope, freq, settle, avg_wait)
    gen.set_amplitude(amplitude / 2)
    _, _, g_half = measure_point(gen, scope, freq, settle, avg_wait)
    gen.set_amplitude(amplitude)
    time.sleep(settle)
    if math.isnan(g_full) or math.isnan(g_half):
        return "inconclusive (a level was unmeasurable)"
    delta = g_full - g_half
    verdict = "linear" if abs(delta) <= 0.5 else "COMPRESSING - reduce --amplitude"
    return (f"{verdict}: {g_full:.2f} dB at {amplitude*1e3:.1f} mVpp vs "
            f"{g_half:.2f} dB at {amplitude*1e3/2:.1f} mVpp "
            f"(delta {delta:+.2f} dB)")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Stepped-sine frequency response of the 540 80166 rf amplifier.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--label", required=True,
                   help="run name, normally 'l1-only' or 'composite'")
    p.add_argument("--scope", default=DEFAULT_SCOPE, help="SDS1202X-E address")
    p.add_argument("--gen", default=DEFAULT_GEN, help="SDG1032X address")
    p.add_argument("--transport", choices=("vxi11", "socket"), default="vxi11")
    p.add_argument("--scope-port", type=int, default=5025,
                   help="raw socket port, --transport socket only")
    p.add_argument("--gen-port", type=int, default=5024,
                   help="raw socket port, --transport socket only")
    p.add_argument("--start", type=float, default=3.0e6, help="sweep start, Hz")
    p.add_argument("--stop", type=float, default=4.5e6, help="sweep stop, Hz")
    p.add_argument("--points", type=int, default=151)
    p.add_argument("--log-sweep", action="store_true",
                   help="log frequency spacing instead of linear")
    p.add_argument("--amplitude", type=float, default=0.010,
                   help="generator drive, Vpp into a 50 ohm load setting")
    p.add_argument("--ch1-attn", type=float, default=1.0,
                   help="CH1 probe factor (1 for a direct coax feed)")
    p.add_argument("--ch2-attn", type=float, default=10.0,
                   help="CH2 probe factor (10 for a x10 probe)")
    p.add_argument("--avg-count", type=int, default=16,
                   help="scope acquisition averages, 1 disables averaging")
    p.add_argument("--settle", type=float, default=0.25,
                   help="seconds after a frequency change")
    p.add_argument("--avg-wait", type=float, default=0.35,
                   help="extra seconds for the average to converge")
    p.add_argument("--no-bwl", action="store_true",
                   help="disable the scope 20 MHz bandwidth limit")
    p.add_argument("--no-linearity-check", action="store_true")
    p.add_argument("--note", default="",
                   help="free text recorded in the csv header, e.g. RESONATE position")
    p.add_argument("--out-dir", default=str(Path(__file__).parent / "data"))
    args = p.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"80166-80m-{args.label}-{stamp}.csv"

    print(f"connecting to generator {args.gen} and scope {args.scope} "
          f"over {args.transport}")
    gen_link = Link(args.gen, args.transport, args.gen_port)
    scope_link = Link(args.scope, args.transport, args.scope_port)
    gen = Generator(gen_link)
    scope = Scope(scope_link, avg_count=args.avg_count, bwl=not args.no_bwl)

    try:
        gen_idn = gen.idn()
        scope_idn = scope.idn()
        print(f"  generator: {gen_idn}")
        print(f"  scope    : {scope_idn}")

        centre = math.sqrt(args.start * args.stop)
        scope.configure(args.ch1_attn, args.ch2_attn)
        tdiv = scope.set_timebase_for(centre)
        print(f"  timebase : {tdiv*1e9:.0f} ns/div "
              f"({centre/1e6:.3f} MHz reference)")

        # noise floor on the output channel with no drive applied
        gen.output(False)
        time.sleep(0.4)
        scope.set_vdiv(2, VDIV_STEPS[0] * args.ch2_attn)
        scope.link.write("TRMD AUTO")
        scope.clear_sweeps()
        time.sleep(0.5)
        noise_vpp = scope.read_vpp(2)
        scope.link.write("TRMD NORM")
        print(f"  ch2 noise: {noise_vpp*1e3:.2f} mVpp with the output off")

        gen.configure(centre, args.amplitude)
        gen.output(True)
        time.sleep(0.5)
        scope.set_vdiv(1, args.amplitude / 4.5)
        scope.autorange(1)
        scope.autorange(2)

        lin = ""
        if not args.no_linearity_check:
            lin = linearity_check(gen, scope, centre, args.amplitude,
                                  args.settle, args.avg_wait)
            print(f"  linearity: {lin}")

        freqs = frequencies(args.start, args.stop, args.points, args.log_sweep)
        rows = []
        t0 = time.time()
        for i, f in enumerate(freqs, 1):
            ch1, ch2, gain = measure_point(gen, scope, f, args.settle, args.avg_wait)
            rows.append((f, ch1, ch2, gain))
            print(f"  [{i:3d}/{len(freqs)}] {f/1e6:7.4f} MHz  "
                  f"in {ch1*1e3:7.3f} mVpp  out {ch2*1e3:8.3f} mVpp  "
                  f"gain {gain:7.2f} dB")
    finally:
        try:
            gen.output(False)
        except Exception:
            pass
        gen_link.close()
        scope_link.close()

    valid = [r for r in rows if not math.isnan(r[3])]
    peak = max(valid, key=lambda r: r[3]) if valid else None

    with out_path.open("w", newline="", encoding="utf-8") as fh:
        fh.write("# Ten-Tec 540 - 80166 rf amplifier stepped-sine response\n")
        fh.write(f"# label,{args.label}\n")
        fh.write(f"# timestamp,{dt.datetime.now().isoformat(timespec='seconds')}\n")
        fh.write(f"# scope,{scope_idn}\n")
        fh.write(f"# generator,{gen_idn}\n")
        fh.write(f"# drive_vpp,{args.amplitude}\n")
        fh.write(f"# start_hz,{args.start}\n")
        fh.write(f"# stop_hz,{args.stop}\n")
        fh.write(f"# points,{args.points}\n")
        fh.write(f"# sweep,{'log' if args.log_sweep else 'linear'}\n")
        fh.write(f"# ch1_attn,{args.ch1_attn}\n")
        fh.write(f"# ch2_attn,{args.ch2_attn}\n")
        fh.write(f"# avg_count,{args.avg_count}\n")
        fh.write(f"# ch2_noise_vpp,{noise_vpp:.6g}\n")
        fh.write(f"# linearity,{lin}\n")
        fh.write(f"# note,{args.note}\n")
        w = csv.writer(fh)
        w.writerow(["frequency_hz", "ch1_vpp", "ch2_vpp", "gain_db"])
        for f, ch1, ch2, gain in rows:
            w.writerow([f"{f:.1f}", f"{ch1:.6g}", f"{ch2:.6g}", f"{gain:.4f}"])

    print(f"\nwrote {out_path}")
    if peak:
        print(f"peak {peak[3]:.2f} dB at {peak[0]/1e6:.4f} MHz")
    return 0


if __name__ == "__main__":
    sys.exit(main())
