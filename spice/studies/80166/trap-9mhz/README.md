# 80166 9 MHz trap

T1 and C7 sit in the antenna lead and remove signals sitting on the receiver's
own 9 MHz intermediate frequency. Such a signal would otherwise walk into the IF
strip without ever being mixed, and appear as a birdie or a permanent carrier
that no amount of tuning removes. The board document has described the trap since
the first draft and had never modelled it.

T1's primary is in series with the antenna path; C7, a 5–60 pF trimmer,
resonates its secondary. At the secondary's resonant frequency, energy is drawn
out of the primary and the series path becomes strongly lossy. Away from that
frequency the trap does almost nothing.

The manual gives the trap its own alignment procedure (PDF p. 24 / printed
p. 3-8, "9 MHz Trap Adjustment") and warns that the null is "very sharp" — which
is another way of saying the trap is a high-Q circuit.

The circuit source is `triton_540.kicad_sch`. The study script exports a fresh
KiCad SPICE netlist on every run.

## Configuration

- Bandswitch: `S4_POS=2` (7 MHz), the position the manual aligns the trap on
- Aligned rack model: `L_RACK=3.43 µH`, `C17=68 pF` effective
- L2 tracking fit: `L2 = 1.97963 µH + 0.0849053 × L_RACK`
- `/R = 12 V`, `/DEFEAT = 3.9 V` — normal receive
- Drive: `AC 1` through 50 Ω at `ANT`; load: `1 MΩ || 5 pF` at `OUT`
- AC sweep: 3–20 MHz at 20 000 points per decade, giving 1.04 kHz spacing at
  9 MHz. The window holds every null the 5–60 pF trimmer can produce, the peak
  that sits beside each one, and half a megahertz of plain response either side
- Swept: `C66-7` (C7) at 5, 10, 15, 20, 30, 45 and 60 pF with the trap model's
  default secondary Q of 80; and `QS` on `80166_T1_9MHZ` at 80, 40, 20, 10 and 5
  with C7 held at 20 pF
- Band comparison: an 8–10 MHz sweep on each of the five band positions, with
  and without the trap

Every run has a companion run with `KTRAP` set to 1e-9 — coupling removed, the
primary winding still in the antenna path. Depth is measured against that
companion, so it means "how much the trap takes out" rather than "how much lower
this point is than its neighbours".

## How the null is located

The response with the trap, subtracted from the response without it, is the
**attenuation curve**. A null is a local maximum of that curve, looked for only
inside ±15% of where the trap can physically resonate:

$$
f_\mathrm{trap} = \frac{1}{2\pi\sqrt{L_S\,(C_7 + C_{PS})}}
\qquad L_S = 12.5\ \mu\mathrm{H},\ C_{PS} = 5\ \mathrm{pF}
$$

Both restrictions are needed. On the 7 MHz band position the front end has a very
sharp 40 dB peak of its own near 7.2 MHz. Inserting the trap shifts that peak
slightly, and the shift alone puts a 10 dB feature into the attenuation curve
that is not a null at all. Requiring a *local maximum* rejects the shoulder of
that feature, and the search window — more than a hundred times wider than the
null itself — keeps it out of range. The window does not prejudge the answer: the
measured nulls land 4 to 16 kHz away from the predicted frequency, well inside a
window that is hundreds of kilohertz wide.

Where no local maximum exists at all, the trap has stopped producing a null on
this band position. That is reported as such rather than as a frequency.

## Runs

The 26 sweeps are listed in [`manifest.csv`](manifest.csv).

## What the retained results show

### Tuning C7 moves the null

![ANT-to-OUT response for seven C7 settings, and the resulting null frequency](figures/notch-vs-c7.png)

**Figure 66-9.** ANT-to-OUT response for seven C7 settings, and the resulting
null frequency

| C7 | Predicted null | Measured null | Depth vs no trap | Depth vs ±500 kHz | −3 dB width | Usable? |
|--:|--:|--:|--:|--:|--:|:--|
| 5 pF | 14.2353 MHz | 14.2305 MHz | 25.23 dB | 20.00 dB | 112.8 kHz | yes |
| 10 pF | 11.6230 MHz | 11.6191 MHz | 24.44 dB | 20.30 dB | 112.9 kHz | yes |
| 15 pF | 10.0658 MHz | 10.0617 MHz | 24.48 dB | 20.50 dB | 113.0 kHz | yes |
| **20 pF** | 9.0032 MHz | **8.9996 MHz** | **25.36 dB** | 20.75 dB | **113.1 kHz** | yes |
| 30 pF | 7.6091 MHz | 7.6019 MHz | 32.90 dB | 25.39 dB | 117.7 kHz | yes |
| 45 pF | 6.3662 MHz | 6.3822 MHz | 15.97 dB | 15.97 dB | 138.7 kHz | yes |
| 60 pF | 5.5835 MHz | 5.5888 MHz | 2.75 dB | 1.93 dB | not resolved | **no** |

The null tracks C7 exactly as `f = 1/(2π√(LC))` requires, and 20 pF puts it on
8.9996 MHz — 0.4 kHz below the 9 MHz IF, which is less than one 1.04 kHz sweep
step and therefore not a resolved difference.

Figure 66-9 also shows something the arithmetic does not: **every null has a peak
just above it**. That is the normal behaviour of a series trap. Below its
resonance the reflected impedance is one sign, above it the other, and there is a
frequency at which the reflected reactance cancels part of the antenna path's own
reactance and the response rises. A restorer sweeping the trap will see the pair,
and should tune for the dip, not for the neighbouring hump.

At the bottom of the trimmer's range the trap stops working on this band
position: at 60 pF the null is only 2.75 dB deep. The trap is trying to resonate
at 5.59 MHz, which is far down the front end's skirt, so there is little signal
there for it to remove.

### A lossy T1 loses depth long before it loses frequency

![ANT-to-OUT response for five trap-Q settings, with null depth and centre](figures/notch-vs-trap-q.png)

**Figure 66-10.** ANT-to-OUT response for five trap-Q settings, with null depth
and centre

| Trap secondary Q | Null centre | Depth vs no trap | −3 dB width | Notch's own Q |
|--:|--:|--:|--:|--:|
| 80 | 8.9996 MHz | 25.36 dB | 113.1 kHz | 79.6 |
| 40 | 8.9892 MHz | 19.49 dB | 231.7 kHz | 38.8 |
| 20 | 8.9489 MHz | 13.90 dB | 510.1 kHz | 17.5 |
| 10 | 8.8028 MHz | 9.07 dB | 1963 kHz | 4.5 |
| 5 | no null found | 4.15 dB at 9.000 MHz | — | — |

Two things are worth pulling out.

**The null's depth collapses while its frequency barely moves.** Dropping the Q
from 80 to 10 costs 16 dB of depth and shifts the centre by 197 kHz — 2%. This is
the failure mode a restorer actually meets, and it is worth recognising: a trap
whose coil has gone lossy still nulls at about the right frequency, and can be
adjusted to look correct, while doing a fraction of its job. Getting the null on
frequency but shallow is the symptom of a tired T1, and no amount of C7
adjustment will fix it.

**The notch's own Q is a direct readout of the trap's Q.** At QS = 80 the notch's
centre divided by its −3 dB width is 79.6; at QS = 40 it is 38.8. The two track
each other closely until the null gets so broad that it merges with the peak
beside it. That makes the **measured −3 dB width the single most valuable number
in the bench check**: it reads T1's quality off a scope trace without any model
in between.

Below Q ≈ 5 the trap stops producing an identifiable null at all — the response
just sags — which is why the summary marks it "no null found" rather than
inventing a frequency for it.

### Why the manual aligns the trap on the 7 MHz band position

The manual's procedure sets the receiver to 7.0 MHz, peaks RESONATE, then moves
the generator to 9 MHz without touching anything else. The reason is measurable:

| Band position | 9.000 MHz response, trap coupling removed | With the trap | Attenuation |
|:--|--:|--:|--:|
| 3.5 MHz | −31.01 dB | −52.46 dB | 21.45 dB |
| **7 MHz** | **+0.36 dB** | −25.00 dB | **25.36 dB** |
| 14 MHz | −0.37 dB | −12.97 dB | 12.60 dB |
| 21 MHz | −8.31 dB | −25.36 dB | 17.05 dB |
| 28 MHz | −12.67 dB | −31.04 dB | 18.38 dB |

You are trying to hear a signal the receiver is designed to reject, so you must
first be on a band position that lets enough of it through to be heard at all.
The 7 MHz position passes 9 MHz at essentially unity — the best of the five — and
also gives the trap the most to work with, 25.4 dB of attenuation. On 3.5 MHz the
front end has already thrown away 31 dB of the test signal before the trap sees
it, so a null would be nulling something that was never audible. The 14 MHz
position passes 9 MHz nearly as well but gets only half the attenuation from the
trap, so the null would be less obvious to find.

That also explains the manual's other instruction, to *raise* the generator level
for this step: even on the best band position the receiver is being asked to
listen to something it exists to reject.

## Resolution

The wide sweeps are sampled on a logarithmic grid whose spacing is 1.04 kHz at
9 MHz, 1.64 kHz at 14 MHz and 0.64 kHz at 5.6 MHz. Null centres are quantized to
that spacing, so the 0.4 kHz between the C7 = 20 pF null and 9.000 MHz is **not
resolved** and must not be read as a measured offset. The 197 kHz drift across
the Q sweep is nearly two hundred grid steps and is resolved. Widths are
interpolated between the samples straddling each −3 dB crossing.

## Evidence and limitations

- **Documented:** the trap's existence and purpose, the 5–60 pF trimmer range,
  the alignment procedure and its use of the 7 MHz band position, and the
  manual's warning that the null is very sharp (PDF p. 24 / printed p. 3-8).
- **Calculated:** every null centre, depth and width above, from the retained
  CSVs, and the predicted resonances from the model's own `LS` and `CPS`.
- **Model-dependent, and this is the big one:** T1's inductances, coupling
  factor and Q are **all estimates**. The model library says so explicitly. So
  the depth (25 dB), the width (113 kHz) and the C7 setting that lands the null
  on 9 MHz (20 pF) are outputs of those estimates, not predictions about a real
  T1. What the study establishes is the *behaviour*: that the null tracks C7 as
  the resonance formula requires, that depth collapses with Q while frequency
  barely moves, and that the notch's width reads the trap's Q directly.
- **Fitted:** the rack inductance and L2 tracking equation.
- **Provisional:** coil Q, tap ratios and the `1 MΩ || 5 pF` output load.

## Reproduce

With KiCad 10 and ngspice 46 installed at the paths configured near the top of
`spice/tools/run_80166_headless.py`, and the `RF_Amp_80166` sheet included in
simulation:

```powershell
python spice\tools\run_80166_trap_9mhz.py
```

The run takes a few minutes. Simulation and measurement are separate steps in the
script, so the summary tables can be recomputed from the retained curve CSVs
without re-running ngspice. Curated CSVs and figures are replaced in this
directory; exported netlists, raw files and logs go to ignored
`spice/generated/80166-trap/`.
