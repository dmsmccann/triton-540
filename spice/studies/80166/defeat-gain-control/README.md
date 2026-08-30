# 80166 DEFEAT gain reduction

This study tests a number Ten-Tec published and this project had never
checked: that energizing the crystal calibrator drops the RF amplifier's gain
by about 25 dB (Owner's Manual PDF p. 24 / printed p. 3-8).

The reduction happens at Q1's **gate 2**. A dual-gate MOSFET has two control
gates in series in the same channel; gate 1 takes the signal and gate 2 takes a
separate control voltage, and drain current depends on both. Gate 2 reaches the
outside world at the board's `DEFEAT` pin through R1 (33 kΩ), which pulls it
toward ground when nothing is driving it, and C4 (0.01 µF), which grounds it for
RF while leaving the DC control voltage alone. In normal reception `DEFEAT`
sits at about 3.9 V. When the calibrator is switched on, a TTL gate on that
assembly pulls the line low.

The circuit source is `triton_540.kicad_sch`. The study script exports a fresh
KiCad SPICE netlist on every run; it does not maintain a second hand-written
copy of the circuit.

## Configuration

- Bandswitch: `S4_POS=1` (3.5 MHz)
- Aligned rack model: `L_RACK=17.2 µH`, `C19=36 pF`
- L2 tracking fit: `L2 = 1.97963 µH + 0.0849053 × L_RACK`
- RF GAIN supply: `/R = 12 V` (RF CONTROL fully clockwise)
- Swept control: `/DEFEAT` from 3.9 V to 0 V in 17 steps, dense below 1 V
- Drive: `AC 1` through 50 Ω at `ANT`
- Load: the schematic's provisional `1 MΩ || 5 pF` at `OUT`
- AC sweep: 3.0–4.2 MHz, 10 000 points per decade
- A second run at every step asks for the DC operating point only, so the bias
  the stage settles at can be read beside the gain it delivers

Observation points are the board pins `ANT` and `OUT`. Q1's own terminals are
recorded from the operating-point runs, where a probe's capacitance would not
matter because nothing is moving.

## Runs

Each `/DEFEAT` step is two runs: an AC sweep and an operating point. They are
listed in [`manifest.csv`](manifest.csv).

## What the retained results show

![ANT-to-OUT gain against DEFEAT voltage, and the response curves at 3.9 V and 0 V](figures/defeat-gain.png)

**Figure 66-7.** ANT-to-OUT gain against DEFEAT voltage, and the response
curves at 3.9 V and 0 V

| `/DEFEAT` | Gain at 3.500 MHz | Change from normal | Drain current | V_GS | −3 dB bandwidth |
|--:|--:|--:|--:|--:|--:|
| 3.900 V | 20.189 dB | 0.000 dB | 4.407 mA | −1.021 V | 202.24 kHz |
| 3.500 V | 20.172 dB | −0.016 dB | 4.405 mA | −1.020 V | 202.24 kHz |
| 3.000 V | 20.152 dB | −0.036 dB | 4.401 mA | −1.018 V | 202.24 kHz |
| 2.500 V | 20.132 dB | −0.057 dB | 4.398 mA | −1.016 V | 202.24 kHz |
| 2.000 V | 17.263 dB | −2.925 dB | 4.362 mA | −0.999 V | 202.29 kHz |
| 1.750 V | 13.864 dB | −6.325 dB | 4.234 mA | −0.938 V | 202.34 kHz |
| 1.500 V | 10.611 dB | −9.577 dB | 4.029 mA | −0.840 V | 202.38 kHz |
| 1.250 V | 7.465 dB | −12.723 dB | 3.766 mA | −0.714 V | 202.40 kHz |
| 1.000 V | 4.381 dB | −15.808 dB | 3.461 mA | −0.567 V | 202.40 kHz |
| 0.875 V | 2.845 dB | −17.343 dB | 3.297 mA | −0.489 V | 202.40 kHz |
| 0.750 V | 1.306 dB | −18.883 dB | 3.126 mA | −0.407 V | 202.40 kHz |
| 0.625 V | −0.245 dB | −20.434 dB | 2.951 mA | −0.323 V | 202.39 kHz |
| 0.500 V | −1.817 dB | −22.006 dB | 2.771 mA | −0.237 V | 202.38 kHz |
| 0.375 V | −3.419 dB | −23.607 dB | 2.588 mA | −0.150 V | 202.36 kHz |
| 0.250 V | −5.061 dB | −25.249 dB | 2.403 mA | −0.061 V | 202.35 kHz |
| 0.125 V | −6.756 dB | −26.945 dB | 2.215 mA | +0.029 V | 202.33 kHz |
| 0.000 V | −8.520 dB | −28.708 dB | 2.027 mA | +0.120 V | 202.31 kHz |

Three things stand out.

**The reduction reaches the manual's figure.** The modelled cut at a fully
grounded `DEFEAT` line is 28.7 dB, a voltage ratio of about 27:1. The manual's
25 dB — a ratio of about 18:1 — is passed at roughly 0.25 V, which is the sort
of residual a real TTL gate leaves when it pulls a line low.

**The passband keeps its shape.** The −3 dB bandwidth moves from 202.24 kHz to
202.31 kHz across the whole sweep, a change of 0.03%, and the peak frequency
does not move by even one sample of the 0.81 kHz sweep grid. That is the
signature of a gain control that is not also a tuning control: gate 2 changes
the channel's transconductance without appearing across either tuned circuit.
If it did, the response would flatten and shift as the gain came down, and the
receiver would go off tune every time the calibrator was switched on.

**The control does nothing for the top third of its range.** From 3.9 V down to
2.5 V the gain moves 0.06 dB. Everything happens below about 2.5 V. This is not
a fault: gate 2 is a switch here, not a volume control, and the calibrator drives
it to a logic level rather than anywhere in between.

The drain current falls with the gain, from 4.41 mA to 2.03 mA, which is the
mechanism visible in a form a meter can read: with gate 2 taken down, less of
the channel is open, so less current flows and the transconductance that sets
the gain falls with it. Because R6 (470 Ω) sets the source voltage from that
current, V_GS relaxes from −1.02 V toward zero at the same time — self-bias
partly opposing the gain reduction, which is why the curve is a smooth slope
rather than a cliff.

## Resolution

The sweep is sampled on a logarithmic grid whose spacing is 806 Hz at 3.5 MHz.
Peak frequencies are quantized to that grid, so "the peak did not move" means
it moved by less than 0.81 kHz, not that it did not move at all. Gains at
3.500 MHz are interpolated between the two samples that straddle it and are not
limited by the grid in the same way.

## Evidence and limitations

- **Documented:** the approximately 25 dB gain reduction, the dual-gate
  topology, the 3.9 V normal-receive value on `DEFEAT`, and the calibrator's
  TTL gate as what pulls the line low, all from the Ten-Tec manual, PDF
  pp. 24–25 / printed pp. 3-8–3-9.
- **Calculated:** every gain, bandwidth, drain current and V_GS above, from
  the retained CSVs.
- **Fitted:** the rack inductance and L2 tracking equation, from the
  manual-sequence alignment study.
- **Model-dependent:** the size of the reduction. The empirical 40823 model's
  gate-2 section has an assumed threshold, so the shape of the knee and the
  final 28.7 dB are properties of that model, not of an RCA device. What the
  study establishes firmly is the *direction*, the *order of magnitude*, and
  the *absence of a shape change*.
- **Still provisional:** coil Q, tap ratios, and the `1 MΩ || 5 pF` OUT load.
  See the [loading-sensitivity study](../loading-sensitivity/README.md) for
  what that load is worth.

## Reproduce

With KiCad 10 and ngspice 46 installed at the paths configured near the top of
`spice/tools/run_80166_headless.py`, and the `RF_Amp_80166` sheet included in
simulation:

```powershell
python spice\tools\run_80166_defeat_gain.py
```

Curated CSVs and the figure are replaced in this directory. Exported netlists,
raw files and logs go to ignored `spice/generated/80166-defeat-gain/`.
