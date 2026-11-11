# Model 249 bench corroboration

## Status

**Not yet performed. This is the proposed hardware procedure.** Do not create
`bench/249/data/` or `bench/249/plots/` results until measurements have actually
been taken.

## Purpose

Corroborate the normal 9 MHz transfer, detector trigger, PIN-diode blanking, and
recovery predicted by the
[how-it-works simulation](../../spice/studies/249/how-it-works/README.md).

## Equipment and connections

| Item | Connection or setting |
|:--|:--|
| Receiver | Model 249 installed in its normal socket, radio in receive, no antenna signal |
| Supply check | DMM at board `+12`, `+12_SW`, and `GND`; compare with 13.28 V simulation value |
| RF generator | 9 MHz carrier with gated/burst mode, 50 ohm output, connected to board `IN` through appropriate DC isolation/attenuation |
| Oscilloscope CH1 | Low-capacitance 10x probe at board `IN`, referenced to the adjacent board ground |
| Oscilloscope CH2 | Low-capacitance 10x probe at board `OUT`, referenced to the adjacent board ground |
| Blanker switch | Use the radio control to switch `+12_SW`; verify its voltage in both states |
| Starting level | 10 mV peak or less at `IN`; increase only as needed for a repeatable trigger |

Do not use the simulation's 5 V burst as a starting bench level. It was chosen
to demonstrate model topology, not to predict safe sensitivity. Do not probe
L49-2, C49-18, MC1350 pins 1/8, or the diode-gate nodes during the pin-level
comparison; probe capacitance can detune or load them.

## Procedure

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

## Results template

The comparison table with simulated values is retained in the simulation
README. When this test is performed, save raw captures and a CSV of extracted
readings under `bench/249/`, then fill its blank measured column without
altering the simulation values.
