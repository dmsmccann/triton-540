# 80308 bench checks

These procedures are proposals for corroborating the simulations in
[`80308.md`](../../80308.md). **They have not yet been performed.** Put raw
instrument captures in `bench/80308/data/` and derived plots in
`bench/80308/plots/`; do not place measured files in the simulation tree.

## Safety and common setup

- Power the radio normally and use the board's own CALIBRATE switch.
- Connect every instrument ground to a board/chassis `GND` pin.
- Use ×10 probes. Do not probe across Y08-1 or C08-1; added capacitance changes
  oscillator frequency and may stop it.
- Ground `25/100` only to board/chassis ground. Never drive it with voltage.
- Record instrument model, probe capacitance, radio band/mode, RF-gain setting,
  supply voltage, and ambient temperature with every run.

## 1. Oscillator and C08-1

1. Set RF gain fully clockwise, CALIBRATE on, and R08-6 in the pulsing region.
2. Ground `25/100` and connect a high-impedance counter to `OUT`.
3. Record frequency at the existing C08-1 setting before moving it.
4. If alignment is actually required, receive WWV using the manual's Section 2
   procedure and adjust C08-1 for zero beat. Do not use the simulated 30 pF as
   a physical setting.
5. With the frequency recorded, measure Q08-1 collector and base DC. Capture
   the collector waveform with a ×10 probe without disturbing C08-1.

| Quantity | Simulated | Measured |
|:--|--:|--:|
| Frequency near center model setting | 100.007 kHz | |
| Q08-1 collector DC | 4.63 V | |
| Q08-1 collector waveform | 6.30 V p-p | |
| Q08-1 base DC | +0.70 V | |

## 2. R08-6 pulse rate

1. Remove the `25/100` ground and leave the counter or scope on `OUT`.
2. Start at one end of R08-6 and move slowly until stable pulsing begins.
3. Record the physical shaft position and period at three useful settings.
4. Continue to the other end and record where pulsing stops. Do not disturb
   C08-1 between runs.

| Physical R08-6 position | Simulated model rate | Measured rate |
|:--|--:|--:|
| First stable point | 3.44 Hz at model 0.70 | |
| Middle useful point | 3.85 Hz at model 0.75 | |
| Last stable point | 4.71 Hz at model 0.80 | |

## 3. Divider modes and OUT amplitude

1. Keep CALIBRATE on and R08-6 unchanged.
2. Capture at least one complete burst at `OUT` with `25/100` open.
3. Ground `25/100` and repeat without changing probe, vertical scale, or load.
4. Use the counter or FFT to identify 25 and 100 kHz components.

| Mode | Simulated result | Measured result |
|:--|--:|--:|
| Open | 25 kHz component, 3.55 V p-p | |
| Grounded | 100 kHz component, 0.320 V p-p | |

## 4. Regulator and DEFEAT

1. Set RF gain fully clockwise and measure the switched `+12`, D08-1 cathode,
   and `DEFEAT` with CALIBRATE off.
2. Switch CALIBRATE on and repeat. Do not change RF gain between states.
3. If a current-limited bench supply is used instead of the radio, do not infer
   the 3.9 V DEFEAT off-state unless the RF-amplifier connection is present.

| Quantity | Simulated | Manual | Measured |
|:--|--:|--:|--:|
| Switched supply, on | 13.75 V study sample | 13.8 V | |
| Logic rail, on | 5.735 V | 5.6 V | |
| `DEFEAT`, on | 0.163 V | 0.1 V | |
| `DEFEAT`, off | 3.900 V | 3.9 V | |
