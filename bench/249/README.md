# Model 249 bench corroboration

## Status

**Not yet performed. This is the proposed hardware procedure.** Do not create
`bench/249/data/` or `bench/249/plots/` results until measurements have actually
been taken.

## Purpose

Corroborate the normal 9 MHz transfer, detector trigger, PIN-diode blanking, and
recovery predicted by the
[how-it-works simulation](../../spice/studies/249/how-it-works/README.md).
Also preserve Ten-Tec's separate factory checks from the original
[Model 249 instruction sheet](../../literature/Ten_Tec_249.pdf): the no-signal
DC voltage table, the C49-18 detector alignment, and the post-installation
TX-RX-mixer L3 retune. PDF page 2 / printed page -1 contains the procedures;
it also contains the connector-voltage table. PDF page 1 / printed page -2
contains the schematic and semiconductor-voltage tables.

## Equipment and connections

| Item | Connection or setting |
|:--|:--|
| Receiver | Model 249 installed in its normal socket, radio in receive, no antenna signal |
| Supply check | DMM at board `+12`, `+12_SW`, and `GND`; factory reference is 13.8 V in receive/no-signal/blanker-energized conditions, while the retained simulation used 13.28 V |
| RF generator | 9 MHz carrier with gated/burst mode, 50 ohm output, connected to board `IN` through appropriate DC isolation/attenuation |
| Oscilloscope CH1 | Low-capacitance 10x probe at board `IN`, referenced to the adjacent board ground |
| Oscilloscope CH2 | Low-capacitance 10x probe at board `OUT`, referenced to the adjacent board ground |
| Blanker control | Pull the ALC knob out to energize `+12_SW`; verify its voltage in both states |
| Starting level | 10 mV peak or less at `IN`; increase only as needed for a repeatable trigger |

Do not use the simulation's 5 V burst as a starting bench level. It was chosen
to demonstrate model topology, not to predict safe sensitivity. Do not probe
L49-2, C49-18, MC1350 pins 1/8, or the diode-gate nodes during the pin-level
comparison; probe capacitance can detune or load them. The later factory
alignment is a separate test and deliberately probes Q49-4's base.

## Pin-level simulation corroboration

1. With power off, inspect the board orientation and confirm the connector pins
   against the original drawing. Set the generator to minimum output.
2. Install the board, connect both probes at `IN` and `OUT`, and power the radio
   in receive with the blanker on. Stop for abnormal current, odor, or heating.
3. Verify `+12` and `+12_SW`. Apply a small continuous 9 MHz signal and record
   input/output RMS voltage.
4. Turn the blanker off. Verify `+12_SW` falls while `+12` remains present.
   Repeat the continuous-signal reading without changing probes or generator.
5. Select a short 9 MHz burst with a low duty cycle. Capture `IN` and `OUT` in
   one acquisition with blanking off.
6. Turn blanking on without changing generator amplitude, burst width, receiver
   controls, probes, or C49-18. Capture the same acquisition.
7. If no difference is visible, increase burst amplitude in small steps. Record
   the lowest repeatable trigger level at the board `IN` pin. Stop before the
   input or output clips continuously.
8. From matched off/on captures, record the leading peak, later burst envelope,
   delay to attenuation, and time for normal output to recover after the burst.
9. Power down before removing probes or the board.

## Factory no-signal DC check

*Not yet performed. This is the proposed hardware procedure.*

With the receiver in receive, no signal applied, and the blanker energized by
pulling the ALC knob out, verify `+12` and `+12_SW` and then record the following
points. Use the top-view transistor and IC pin orientation shown on PDF page 1 /
printed page -2. Do not infer lead order from a modern replacement package.

| Device | Factory reference | Measured |
|:--|:--|:--|
| Q49-1 C/B/E | 7.8 / 2.6 / 1.9 V | |
| Q49-2 C/B/E | 11.8 / 7.8 / 7.2 V | |
| Q49-3 C/B/E | 11.8 / 9.0 / 8.4 V | |
| Q49-4 C/B/E | 9.0 / 0 / 0 V | |
| Q49-5 C/B/E | 13.6 / 0.3 / 0 V | |
| Q49-6 C/B/E | 3.7 / 13.1 / 13.8 V | |
| IC49-1 pins 1-4 | 13.1 / 12.8 / 0 / 4.4 V | |
| IC49-1 pins 5-8 | 5.5 / 4.4 / 0 / 13.1 V | |

This check matters because it tests the quiescent device models, including the
MC1350 AGC pin, before pulse sensitivity or blanking depth is interpreted.

## Factory C49-18 detector alignment

*Not yet performed. This is the proposed hardware procedure.*

1. Keep the board installed and the blanker energized. Apply a small continuous
   9 MHz signal at board `IN` through the same protected 50-ohm connection.
2. Connect a low-capacitance 10x probe to the base of Q49-4. Do not probe L49-2
   or the MC1350 outputs, because that capacitance would move the resonance.
3. Adjust C49-18 for maximum 9 MHz signal at Q49-4's base, exactly as specified
   by Ten-Tec. The peak should be broad because the tuned circuit has low Q.
4. Record the generator level, probe, C49-18 starting position, final position,
   peak amplitude, and the response on each side of the maximum.

| Measurement | Manual expectation | Simulated | Measured |
|:--|:--|:--|:--|
| Q49-4-base response versus C49-18 | Broad maximum at 9 MHz; adjustment not critical | | |

This check determines the real L49-2 inductance, loaded Q, stray capacitance,
and installed C49-18 setting. Lowest trigger level is not the factory alignment
criterion.

## Post-installation TX-RX mixer L3 retune

*Not yet performed. This is the proposed hardware procedure.*

Ten-Tec installation step 6 says to remove the radio top, tune a station no
stronger than S5, and adjust L3 on the TX-RX mixer for maximum S-meter reading.
The blanker may be on or off. Use the weaker signal so receiver AGC does not
flatten the meter response and hide the resonance peak. Record the starting and
final L3 positions without disturbing C49-18.

| Measurement | Manual expectation | Measured |
|:--|:--|:--|
| S-meter response while adjusting TX-RX mixer L3 | Clear maximum on a station no stronger than S5 | |

## Results template

The comparison table with simulated values is retained in the simulation
README. When this test is performed, save raw captures and a CSV of extracted
readings under `bench/249/`, then fill its blank measured column without
altering the simulation values.
