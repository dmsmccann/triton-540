# Assembly 80274 bench corroboration

## Status

**Not yet performed. This is the proposed hardware procedure.** No files under
`bench/80274/data/` or `bench/80274/plots/` should be created until readings
have actually been taken.

## Purpose

Corroborate the receive gain, transmit mute, CW sidetone, and receive-recovery
behavior predicted by the
[how-it-works simulation](../../spice/studies/80274/how-it-works/README.md).

## Equipment and connections

| Item | Connection or setting |
|:--|:--|
| Regulated supply | Board `+12` and `GND`; begin at 13.28 V; 0.5 A current limit |
| Function generator | Board `INPUT` to `GND`; 1 kHz, 20 mV peak-to-peak, zero DC offset |
| Dummy load | 8 ohm, 5 W or greater, board `OUTPUT` to `GND` |
| Oscilloscope CH1 | 10x probe from `INPUT` to board `GND` |
| Oscilloscope CH2 | 10x probe from `OUTPUT` to board `GND` |
| DMM | Verify supply and control-line DC levels at the board pins |
| T control | 0.2 V receive / 10.4 V transmit, referred to board `GND` |
| SIDETONE control | 0.2 V off / 10.4 V CW on, referred to board `GND` |

Use the board's AC-coupled `OUTPUT` terminal. Do not short or place the dummy
load directly on LM380 pin 8. Keep the speaker disconnected while quantitative
load measurements are made.

## Procedure

1. Disconnect power and confirm the 8 ohm dummy load is connected from board
   `OUTPUT` to `GND`.
2. Set `T` and `SIDETONE` to their 0.2 V states. Set R74-5 and R74-7 to their
   measured electrical midpoints and record how those positions were found.
3. Apply 13.28 V with a 0.5 A current limit. Stop if supply current rises
   unexpectedly, U74-1 heats rapidly, or the output has sustained DC.
4. Let the board settle for at least one second. Verify the supply and control
   voltages with the DMM.
5. Apply 1 kHz at 20 mV peak-to-peak. Record RMS voltage at `INPUT` and
   `OUTPUT`. Do not change generator amplitude for the remaining state tests.
6. Raise only `T` to 10.4 V. Record residual 1 kHz voltage at `OUTPUT`, using
   averaging or an FFT if it approaches the scope's noise floor.
7. Leave `T` high and raise `SIDETONE` to 10.4 V. Record output frequency and
   RMS voltage.
8. Return both controls to 0.2 V in one action. Capture a single-shot waveform
   and measure from the falling `T` edge until the 1 kHz output envelope reaches
   90% of its settled receive value.
9. With both control lines high, move R74-7 through three recorded positions
   while leaving R74-5 fixed; record frequency. Restore R74-7 to midpoint.
10. Move R74-5 through three recorded positions while leaving R74-7 fixed;
    record RMS output. Do not exceed the dummy load's rating or drive U74-1
    into sustained clipping.
11. Return the controls to receive, remove generator drive, and power down.

## Results template

The comparison table is retained in the simulation README. When performed,
save the readings in `bench/80274/data/`, plots in `bench/80274/plots/`, and
replace the blank measured column there without changing the simulated values.
