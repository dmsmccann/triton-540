# 80279 Simulation 6: closed-loop AGC attack and release

## Question answered

Does a strong-signal step make the 80279 control circuit reduce IF gain, and
does gain return slowly and stably after the signal becomes weak again?

## Why the study is split

A multi-second transient with a 1 ns maximum timestep would require billions
of 9 MHz integration steps. This study therefore uses complementary tests:

1. A complete 9 MHz weak/strong/weak transient checks the initial detector and
   control behavior.
2. A full-RF control-state comparison holds C79-22 at a known strong-signal
   voltage and verifies the actual Q79-4/Q79-5, D79-5, PIN-diode, transformer,
   and Q79-3 attenuation path.
3. A calibrated 1 kHz envelope keeps the physical audio, detector, storage,
   Darlington, PIN-bias, and S-meter circuits for attack/release timing.

The envelope source uses 172.4477 V/V from board-input peak voltage to filter-
loop audio peak voltage, taken from Simulation 4's 100 uV-peak, 400 mV-peak
BFO case. Its attenuation is piecewise interpolated from Simulation 3's
measured model relationship between PIN-bias bus voltage and 9 MHz loss.

## Reproduction

With KiCad closed, run from the project root:

```powershell
python spice/tools/run_80279_closed_loop_agc.py
```

The runner exports `80279_if_agc.kicad_sch` afresh and writes only disposable
netlists below `spice/generated/80279-closed-loop-agc/`. The complete default
run includes the long envelope, the 10 ms full-RF onset window, and the 3 ms
precharged full-RF comparison. `--envelope-only`, `--rf-only`,
`--precharge-only`, and `--figures-only` support focused reruns or
post-processing of already completed raw data.

The long envelope is weak from 0-0.2 s, strong from 0.2-1.2 s, and weak from
1.2-12 s. Board-input levels are 1 and 100 uV peak. The full-RF tests use a
9.001 MHz IF, 9.000 MHz BFO, 400 mV-peak BFO RF, and a 1 ns maximum timestep.

## Full-RF evidence

The 100 uV-peak full-RF onset run produces about 115.49 mV peak-to-peak at
Q79-3 gate 1. Its six-millisecond strong interval raises C79-22 from about
1.086 to 1.186 V but remains below the modeled Q79-5/PIN turn-on threshold.
That absence of rapid attenuation is consistent with the 59 ms attack found
by the long envelope; it is not treated as a failed loop direction test.

The staged comparison holds C79-22 at 2.325351 V, the Simulation 5 result for
10 mV-peak filter audio after 120 ms:

| State | One PIN branch | Q79-3 G1 | AUDIO |
|---|---:|---:|---:|
| Baseline storage | Approximately 0 | 115.486 mV p-p | 3.351 V p-p near end of strong window |
| C79-22 held at 2.325 V | 20.60 uA | 12.819 mV p-p | 0.392 V p-p after settling |

The controlled state reduces the actual Q79-3 gate-1 IF by 19.09 dB, about a
nine-times voltage reduction.

![Full-RF control-state comparison](figures/80279-full-rf-control-crosscheck.png)

The Simulation 3 table predicts somewhat less attenuation at approximately
20 uA. The 19.09 dB full-circuit result includes the tuned nonlinear path and
is therefore used as a direction and order-of-magnitude cross-check, not an
exact regression target.

## Calibrated attack and release

| Metric | Result |
|---|---:|
| Input step | 40.00 dB, 1 to 100 uV peak |
| Weak AUDIO | 0.03366 V p-p |
| First strong AUDIO peak | 3.365 V p-p |
| Regulated strong AUDIO | 0.54825 V p-p |
| Regulated output step | 24.24 dB |
| Compression of input step | 15.76 dB |
| Weak / strong C79-22 | 1.074 / 2.336 V |
| Weak / strong PIN current | Approximately 0 / 22.98 uA per branch |
| Weak / strong S-meter current | Approximately 0 / 101.57 uA |
| C79-22 attack, 10%-90% | 59.0 ms |
| C79-22 release, 90%-10% | 1.991 s |
| Post-release AUDIO overshoot | 0.0035% |

![Modeled AGC attack and release](figures/80279-agc-attack-release.png)

The 3.365 V peak-to-peak initial strong output is about 514% above the later
regulated strong level. This is the expected momentary response before the
control capacitor charges. It decays smoothly rather than ringing. After the
signal returns weak, output approaches its original level without overshoot.

The 1.991 s 90%-10% release should not equal the 3.20 s R79-24/C79-22 product.
They are different definitions, and Q79-4/Q79-5 plus the diode paths provide
additional discharge loading.

## Assessment and limits

**Functional pass with split-model qualification.** The actual RF path loses
gain when the actual Darlington/PIN path is driven, and the calibrated loop
compresses a strong-signal step, moves the meter in the correct direction,
attacks faster than it releases, and remains stable.

The manual documents circuit function but not timing, compression, input
levels, or S-meter current. All numerical results are model predictions. The
envelope assumes Simulation 4 detector scaling and interpolated Simulation 3
attenuation; it omits cycle-by-cycle RF distortion and dynamic PIN charge.
The empirical 40823/PIN models, fitted transformers, generic MC1747 model, and
Q79-5 low-current discrepancy limit absolute accuracy.

A 1 mV-peak high-drive dynamic RF attempt was stopped after more than two
hours and approximately 8.9 GB of memory without creating an output file. No
number from that aborted run is retained or used. The staged full-RF state
comparison supplies the physical direction check without claiming a completed
all-RF attack curve.

The S-meter result is current through the saved 1 kOhm fixture at R79-20's
saved midpoint. It is not an S-unit calibration; that remains Simulation 7.

## Retained evidence

`manifest.csv` lists the curated files. Principal data are:

- `data/80279-full-rf-agc-envelope.csv`
- `data/80279-full-rf-precharged-envelope.csv`
- `data/80279-agc-envelope-timeline.csv`
- `data/80279-agc-summary.csv`

Disposable netlists, logs, and raw data remain under
`spice/generated/80279-closed-loop-agc/`.
