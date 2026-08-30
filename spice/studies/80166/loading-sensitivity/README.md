# 80166 output loading and coil-Q sensitivity

Every absolute gain figure in the 80166 board document carries the word
*provisional*, and this study is why. The schematic's `OUT` pin is loaded by a
placeholder `1 MΩ || 5 pF`, and the coil models default to an unloaded Q of 70
at a reference frequency of 14.2 MHz. Neither number came from Ten-Tec. Together
they produce peak gains above 70 dB and loaded Q values near 140 on the 21 MHz
band — useful for *finding* resonance during alignment, and meaningless as
predictions of what the receiver actually does.

The study does not try to produce one right answer. It maps how far the answer
moves when the two unknown quantities move, so a reader can see which
conclusions survive the uncertainty and which do not.

The circuit source is `triton_540.kicad_sch`. The study script exports a fresh
KiCad SPICE netlist on every run.

## What actually loads the OUT pin

The 80166's output goes to the 80287 receiver mixer's `Rx In` pin. Rather than
guess at that impedance, the runner exports the 80287 sub-sheet on its own,
drives `Rx In` with the `AC 1` source that sheet already carries, and divides
the applied volt by the current the source delivers:

| Frequency | Resistance | Reactance | Magnitude |
|--:|--:|--:|--:|
| 3.5 MHz | 993.8 Ω | −89.2 Ω | 997.8 Ω |
| 7.0 MHz | 986.5 Ω | −108.1 Ω | 992.4 Ω |
| 14.2 MHz | 959.0 Ω | −175.8 Ω | 974.9 Ω |
| 21.2 MHz | 920.9 Ω | −237.9 Ω | 951.1 Ω |
| 29.0 MHz | 871.3 Ω | −295.8 Ω | 920.1 Ω |

About **1 kΩ**, dominated by R87-8 and the receiver mixer-balance control R87-1
behind C87-1's 1000 pF coupling capacitor. That is a thousand times heavier than
the placeholder, and it is the row the map singles out.

This is a property of the reconstructed 80287, not a measurement of a real one,
so it is a much better guess than 1 MΩ rather than a known value.

## Configuration

Two band states from the retained alignment study:

| Band state | `S4_POS` | `L_RACK` | L2 trimmer | Sweep window |
|:--|--:|--:|:--|:--|
| 3.5 MHz | 1 | 17.2 µH | C19 = 36 pF | 2–6 MHz |
| 21.2 MHz | 4 | 2.06 µH | C15 = 16.94 pF | 12–32 MHz |

Common to every run: `/R = 12 V`, `/DEFEAT = 3.9 V`, `AC 1` through 50 Ω at
`ANT`, 20 000 points per decade, and the L2 tracking fit
`L2 = 1.97963 µH + 0.0849053 × L_RACK`.

Swept against each other:

- **`R66-100`, the OUT load resistance** — 1 MΩ, 100 kΩ, 22 kΩ, 10 kΩ, 4.7 kΩ,
  2.2 kΩ, 1 kΩ, 470 Ω. `C66-101`, the 5 pF shunt beside it, is left in place
  throughout. These two and the `ANT` drive network are simulation fixtures on
  the sub-sheet, not parts of the original assembly.
- **`QREF` on both `80166_L1` and `80166_L2`** — 70, 50, 30, 20, 10.

That is 8 × 5 × 2 = 80 AC sweeps, plus the one impedance run. They are listed in
[`manifest.csv`](manifest.csv).

## Reading the QREF parameter correctly

This turns out to be the most important thing the study found, so it belongs
before the results.

The coil models represent loss as a fixed series resistance, sized at a
reference frequency:

$$
R_\mathrm{series} = \frac{2\pi\,F_\mathrm{REF}\,L_T}{Q_\mathrm{REF}}
\qquad F_\mathrm{REF} = 14.2\ \mathrm{MHz}
$$

A fixed resistance means the coil's actual Q at any other frequency is

$$
Q(f) = \frac{2\pi f L_T}{R_\mathrm{series}}
= Q_\mathrm{REF}\,\frac{f}{F_\mathrm{REF}}
$$

The inductance cancels. **`QREF=70` therefore does not mean "a coil with a Q of
70".** It means a coil whose Q is 70 at 14.2 MHz, 17.3 at 3.5 MHz, and 143 at
29 MHz — Q rising in direct proportion to frequency. Real slug-tuned coils of
this era do not behave that way; their Q is roughly flat across HF and often
falls at the top.

That single modelling choice, not the output load, is what produces the
band-to-band gain spread the board document complains about.

## What the retained results show

![Peak gain and loaded Q against OUT load resistance and coil Q, on two band states](figures/loading-map.png)

**Figure 66-11.** Peak gain and loaded Q against OUT load resistance and coil
Q, on two band states

Four corners of the map, in words:

| Corner | 3.5 MHz peak | 3.5 MHz loaded Q | 21.2 MHz peak | 21.2 MHz loaded Q | Spread |
|:--|--:|--:|--:|--:|--:|
| 1 MΩ, `QREF`=70 (the schematic today) | 20.19 dB | 17.3 | 72.55 dB | 140.8 | 52.4 dB |
| 1 kΩ, `QREF`=70 | 15.34 dB | 10.3 | 47.62 dB | 66.9 | 32.3 dB |
| 1 kΩ, `QREF`=30 | 4.47 dB | 5.7 | 41.42 dB | 35.8 | 37.0 dB |
| 470 Ω, `QREF`=10 | −10.94 dB | 1.6 | 25.83 dB | 13.6 | 36.8 dB |

**The load matters far more on 21 MHz than on 3.5 MHz.** Going from 1 MΩ to
1 kΩ costs 4.9 dB at 3.5 MHz and 24.9 dB at 21.2 MHz. The reason is in the
table above: at 3.5 MHz the tuned circuits are already so lossy in this model
(coil Q 17.3) that the tank's own resistance dominates and an extra 1 kΩ across
a tapped winding barely registers. At 21 MHz the coils are modelled as very low
loss, so the external load is most of what damps them.

**Loading alone brings the numbers into plausible territory on 80 m but not on
15 m.** At the modelled mixer load with the default coil Q, 3.5 MHz gives
15.3 dB — comfortably inside the 10–20 dB the board document infers for a stage
like this — while 21.2 MHz still gives 47.6 dB, which no single dual-gate MOSFET
stage into a 1 kΩ load produces.

**Lowering the coil Q does not close the gap; it widens it again.** That is the
`Q(f) = QREF × f/FREF` relation biting: reducing `QREF` takes proportionally
more away from the low band, where the modelled Q is already smallest.

So the honest conclusion is a *partial* one. The study bounds what the
placeholder load was worth — about 5 dB on 80 m and about 25 dB on 15 m — and it
identifies the remaining error as living in the coil-loss model's frequency
dependence, not in the load. Until the loss model is given a frequency behaviour
that matches a real coil, no absolute gain figure on the higher bands can be
supported, whatever load is used.

## What would settle it

Bench check 3 in the board document sweeps ANT-to-OUT on 80 m and reports the
measured −3 dB bandwidth and loaded Q. **That single measurement picks the row
and column of this map**, because at 3.5 MHz the loaded Q is set almost entirely
by coil loss:

| If bench check 3 measures a loaded Q of about… | …the 3.5 MHz coil Q is about… | …which corresponds to `QREF` ≈ |
|--:|--:|--:|
| 17 | 17 | 70 |
| 12 | 12 | 50 |
| 7 | 7 | 30 |
| 5 | 5 | 20 |

A second sweep on 21 MHz would then say directly whether the coil Q rises with
frequency the way the model assumes. **That bench data does not exist yet**, so
this study reports the whole map rather than choosing a corner.

## Resolution

Sweeps are sampled on a logarithmic grid: 403 Hz per step at 3.5 MHz and
2.44 kHz at 21.2 MHz. Peak frequencies are quantized to
that spacing. Bandwidths are interpolated between the samples straddling each −3 dB crossing, and the loaded
Q figures are peak frequency divided by that bandwidth, so they inherit the
same precision. None of the Q values here is meaningful past two significant
figures.

Where the coils are very lossy the response peak shifts as well as broadens —
on 3.5 MHz it moves from 3.5009 MHz at `QREF`=70 to 3.3341 MHz at `QREF`=10 and
a 470 Ω load. That is real and worth noting: **a radio with tired coils would
need re-aligning, not just accepting as quieter.**

## Evidence and limitations

- **Documented:** nothing in this study is a Ten-Tec figure. The manual gives
  no gain, bandwidth or Q specification for this board.
- **Calculated:** every peak, bandwidth and loaded Q above, from the retained
  CSVs, and the `Q(f)` relation from the model library's own expressions.
- **Model-dependent:** the 1 kΩ mixer input is the reconstructed 80287's
  impedance, not a measured one. The tap fractions on both coils (`FANT`,
  `FG1`, `FDRN`, `FOUT`) are schematic-based estimates and were **not** swept
  here; they are the other obvious candidate for the residual band-to-band
  error and deserve their own study.
- **Not established:** the real loaded Q of either coil at any frequency, and
  therefore any absolute gain figure for this board.

## Reproduce

With KiCad 10 and ngspice 46 installed at the paths configured near the top of
`spice/tools/run_80166_headless.py`, and the `RF_Amp_80166` sheet included in
simulation:

```powershell
python spice\tools\run_80166_loading_sensitivity.py
```

The run takes a few minutes. Curated CSVs and the figure are replaced in this
directory. Exported netlists, raw files and logs go to ignored
`spice/generated/80166-loading/`.
