# 80166 RF GAIN as the stage's supply

The `R` pin looks like a 12 V rail and is not one. Ten-Tec is explicit: *"The
stage is powered through the RF GAIN terminal, which connects to a variable DC
voltage obtained from RF control"* (Owner's Manual PDF p. 24 / printed p. 3-8).
Turning the front-panel RF GAIN knob down literally lowers this board's supply
voltage.

That matters more than it first appears, because **R4 (470 kΩ) hangs off the
same decoupled node as the drain feed**. R5 (100 Ω) and C6 (0.1 µF) form that
node; L2's cold end, Q1's drain supply and R4 all sit on it. R4 and R3 (47 kΩ)
divide it down to set gate 1's DC voltage. So one knob moves two things at once:

- the **drain supply**, which sets how much voltage swing the tuned load can
  develop, and
- the **gate-1 bias**, which with R6's self-bias sets the drain current and
  therefore the transconductance.

This study puts both mechanisms and the resulting gain on one voltage axis.

The circuit source is `triton_540.kicad_sch`. The study script exports a fresh
KiCad SPICE netlist on every run; it does not maintain a second hand-written
copy of the circuit.

## Configuration

- Bandswitch: `S4_POS=1` (3.5 MHz)
- Aligned rack model: `L_RACK=17.2 µH`, `C19=36 pF`
- L2 tracking fit: `L2 = 1.97963 µH + 0.0849053 × L_RACK`
- `/DEFEAT` held at 3.9 V — the calibrator is off throughout, so the only
  thing moving is the supply
- Swept supply: `/R` from 12 V to 0 V
- Drive: `AC 1` through 50 Ω at `ANT`
- Load: the schematic's provisional `1 MΩ || 5 pF` at `OUT`
- Bias: one `.dc` run stepping `/R` in 50 mV steps, 241 points
- Gain: fifteen separate AC sweeps, 3.0–4.2 MHz at 10 000 points per decade,
  because an AC analysis linearizes about one operating point and cannot itself
  sweep a DC supply

ngspice will not accept a hyphenated source name on a `.dc` card, and every
Ten-Tec reference on this board is hyphenated, so the bias run renames `V66-2`
to `VRFGAIN` in its own generated copy of the netlist.

Observation points are the board pins `ANT` and `OUT`. Q1's terminals come from
the DC run, where nothing is moving and probe capacitance would not matter; on
hardware the equivalent numbers come from a meter, exactly as in bench check 1.

## Runs

The single bias sweep and the fifteen AC sweeps are listed in
[`manifest.csv`](manifest.csv).

## What the retained results show

![Drain current, gate bias and gain against the RF GAIN supply voltage](figures/rf-gain-supply.png)

**Figure 66-8.** Drain current, gate bias and gain against the RF GAIN supply
voltage

| `/R` | Gate 1 | Source | V_GS | Drain current | Drain | Gain at 3.500 MHz | Change | −3 dB BW |
|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 12.00 V | 1.051 V | 2.071 V | −1.021 V | 4.407 mA | 11.547 V | 20.189 dB | 0.000 dB | 202.2 kHz |
| 10.00 V | 0.872 V | 1.928 V | −1.056 V | 4.101 mA | 9.579 V | 19.883 dB | −0.305 dB | 202.2 kHz |
| 8.00 V | 0.693 V | 1.785 V | −1.092 V | 3.797 mA | 7.611 V | 19.556 dB | −0.633 dB | 202.2 kHz |
| 6.00 V | 0.514 V | 1.643 V | −1.130 V | 3.496 mA | 5.642 V | 19.204 dB | −0.985 dB | 202.2 kHz |
| 5.00 V | 0.424 V | 1.572 V | −1.148 V | 3.344 mA | 4.658 V | 18.964 dB | −1.225 dB | 203.3 kHz |
| 4.00 V | 0.335 V | 1.499 V | −1.165 V | 3.190 mA | 3.674 V | 18.731 dB | −1.457 dB | 203.4 kHz |
| 3.00 V | 0.245 V | 1.427 V | −1.182 V | 3.037 mA | 2.689 V | 18.491 dB | −1.698 dB | 203.4 kHz |
| 2.50 V | 0.200 V | 1.391 V | −1.191 V | 2.960 mA | 2.197 V | 16.880 dB | −3.308 dB | 225.1 kHz |
| 2.00 V | 0.157 V | 1.258 V | −1.100 V | 2.676 mA | 1.727 V | 6.390 dB | −13.799 dB | 396.4 kHz |
| 1.50 V | 0.117 V | 1.012 V | −0.895 V | 2.153 mA | 1.280 V | −1.863 dB | −22.051 dB | 535.2 kHz |
| 1.00 V | 0.077 V | 0.704 V | −0.627 V | 1.498 mA | 0.847 V | −9.780 dB | −29.968 dB | 651.9 kHz |
| 0.75 V | 0.058 V | 0.536 V | −0.478 V | 1.141 mA | 0.633 V | −14.148 dB | −34.337 dB | 704.0 kHz |
| 0.50 V | 0.038 V | 0.362 V | −0.323 V | 0.770 mA | 0.421 V | −19.390 dB | −39.578 dB | 752.5 kHz |
| 0.25 V | 0.019 V | 0.183 V | −0.164 V | 0.389 mA | 0.210 V | −27.077 dB | −47.265 dB | 798.0 kHz |
| 0.00 V | 0.000 V | 0.000 V | 0.000 V | 0.000 mA | 0.000 V | −58.676 dB | −78.864 dB | 840.6 kHz |

**Gate 1 tracks the supply exactly.** At every point in the table, gate 1 is
9.09% of the decoupled node, which is 470 kΩ and 47 kΩ doing arithmetic. That is
the second mechanism, visible and measurable with a meter.

**Drain current and gain fall smoothly and never reverse.** Both move
monotonically with the supply, and the stage is completely off at 0 V — no
current, no bias, 58.7 dB of loss where there was 20.2 dB of gain. There is no
discontinuity anywhere in the 241-point bias sweep.

**V_GS is the exception, and it is not monotonic.** It deepens from −1.021 V at
12 V to about −1.19 V near 2.5 V, then relaxes back toward zero as the supply
runs out. That is R6's self-bias doing its job in both directions: on the way
down, gate 1 falls faster than the source does, so the gate goes more negative
relative to the source; below about 2.5 V there is no longer enough drain
voltage to sustain the current, the source voltage collapses, and V_GS follows
it back to zero. **Gain does not turn round with it** — the reversal in V_GS is
a consequence of the stage shutting off, not a second control mechanism, and
the gain curve is smooth and monotonic straight through it.

**The control is very unevenly distributed.** From 12 V down to 3 V, three
quarters of the supply range, the gain falls only 1.7 dB. Everything else
happens in the last 3 V. In receiver terms: over most of the RF GAIN knob's
travel the gain is barely changing, and the useful part of the control is
crowded into the last part of its rotation. Whether the real radio behaves that
way depends on what the front-panel control actually delivers to the `R` pin,
which is a measurement nobody has made — the last row of bench check 1 is
exactly that measurement, and it is why it is there.

**Bandwidth widens as the supply falls**, from 202 kHz to 841 kHz, and the
peak drifts up by about 8 kHz. That is the transistor's own input and output
capacitances changing with bias, and its output resistance falling, both of
which load the tuned circuits. A restorer would notice this as the receiver
going slightly broader and slightly off-peak when RF GAIN is well down — not as
a fault.

## Resolution

The AC sweeps are sampled on a logarithmic grid whose spacing is 806 Hz at
3.5 MHz. Peak frequencies are quantized to that grid: the 8 kHz drift between
12 V and 0 V is ten grid steps and is resolved, but a difference of one or two
steps between adjacent rows is not. Gains at 3.500 MHz are interpolated between
the two samples that straddle it. The bias sweep is a DC analysis and is exact
at each of its 50 mV steps.

## Evidence and limitations

- **Documented:** that `R` is a variable supply from the RF control, and the
  receive pin voltages the manual tabulates with RF CONTROL fully clockwise
  (PDF pp. 24–25 / printed pp. 3-8–3-9).
- **Calculated:** the divider ratio, and every current, bias and gain above,
  from the retained CSVs. Drain current is the voltage across R6 divided by
  470 Ω, because R6 carries the whole of it.
- **Fitted:** the rack inductance and L2 tracking equation.
- **Model-dependent:** where the knee sits and how steep it is. The empirical
  40823 model already needs about twice the manual's negative V_GS to settle
  (see Simulation 1 in the board document), so the supply voltage at which the
  stage gives up is a property of that model.
- **Not established:** the relationship between RF GAIN knob position and `R`
  pin voltage. Every voltage in this study is applied, not measured. The study
  answers "what does the stage do at a given supply voltage", not "what does
  the knob do".
- **Still provisional:** coil Q, tap ratios, and the `1 MΩ || 5 pF` OUT load.

## Reproduce

With KiCad 10 and ngspice 46 installed at the paths configured near the top of
`spice/tools/run_80166_headless.py`, and the `RF_Amp_80166` sheet included in
simulation:

```powershell
python spice\tools\run_80166_rf_gain_supply.py
```

Curated CSVs and the figure are replaced in this directory. Exported netlists,
raw files and logs go to ignored `spice/generated/80166-rf-gain/`.
