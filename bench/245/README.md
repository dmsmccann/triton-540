# Model 245 CW filter bench checks

Not yet performed. This is the proposal. See [245](../../245.md) for the
circuit explanation and simulation results, and the
[operation study](../../spice/studies/245/operation/README.md) for the
simulated data.

All measurements are made at the board's edge pins. Use pin 2 (GND) as the
reference for every probe.

| Pin | Name (245 / 540 socket) | DC in a 540 (simulated) |
|:--|:--|--:|
| 1 | INPUT / IN | 0 V |
| 2 | GND / GND | 0 V |
| 3 | +12V / +REG | about 8 V |
| 4 | OUT 1 / CW2 | 0 V |
| 5 | OUT 2 / — | about 4 V |
| 6 | OUT 3 / — | about 4 V |
| 7 | OUT 4 / CW1 | 0 V |

## Two ways to connect

- **In the radio.** Leave the board in its socket and probe the socket lugs
  from the underside of the chassis (location: 540 manual PDF p.23 /
  printed p.3-7). The 80279 detector drives pin 1, and S1B loads whichever
  output it selects. Use this for the DC check.
- **On the bench.** Take the board out of the radio. Power pin 3 from a
  current-limited supply set to 8.0 V, ground pin 2, and drive pin 1 from an
  audio generator. Nothing else connects to pins 4–7. This matches the
  simulation conditions and is preferred for the frequency-response checks.
  Never exceed 10 V on pin 3 with the board out: C45-7 is rated at 10 V.

## Equipment

| Instrument | Use |
|:--|:--|
| DMM, 10 MΩ input | DC voltages |
| Audio generator, sine, 100 Hz–5 kHz, readable to 1 Hz (or a frequency counter alongside) | drive at pin 1 |
| Two-channel scope with ×10 probes, or a dual-input AC voltmeter / audio analyzer | pin 1 as reference, output pin as measurement |
| Bench supply, current-limited to 20 mA | pin 3 when the board is out of the radio |

## Procedure

Keep the generator level, probe range and supply fixed throughout each check.
Measure pin 1 and the output pin on the same type of channel, so gains can be
read as a ratio.

1. **DC.** Radio in receive, SB-N, no signal; or board on the bench with
   8.0 V on pin 3. Read pins 1, 3, 4, 5, 6 and 7. Read IC pins 1, 2, 6, 7, 10,
   12, 9 and 13 on both ICs. Record the supply current if the board is on the
   bench.
2. **CW-1 and CW-2 responses.** Board on the bench. Set 100 mV RMS at pin 1.
   Find the frequency of maximum output at pin 7 and record the pin 7 / pin 1
   ratio there. Lower and then raise the frequency until the output falls to
   0.71× the peak (−3 dB) and record both frequencies. Then find the
   −60 dB edges (0.001× the peak); a scope may need its most sensitive range.
   Repeat at pin 4, recording the −3 dB and −20 dB (0.1×) edges.
3. **Stage by stage.** Same setup. Record the peak gain and −3 dB edges at
   pins 5 and 6. Pins 5 and 6 sit at about 4 V DC, so AC-couple the scope.
4. **R45-9.** Set 750 Hz. Measure pin 4 and pin 5 on the same range, both
   AC-coupled. Record the ratio. If practical, also read R45-9's colour
   bands: red-red-yellow is 220k, brown-red-yellow is 120k.

## Results

### DC

| Point | Simulated at 8 V | Manual at 13 V | Measured | Supply at pin 3 when measured |
|:--|--:|--:|:--|:--|
| Pin 3 | 8.00 V | 13 V | | |
| Pins 5, 6 | 4.04 V | 6.5 V | | |
| IC pins 1, 2, 6, 7 | 4.00 V | 6.5 V | | |
| IC pins 10, 12 | 4.04 V | 6.5 V | | |
| Supply current | 2.1 mA | 2 mA | | |

### CW-1 (pin 7) and CW-2 (pin 4)

| Quantity | Manual | Simulated | Measured |
|:--|--:|--:|:--|
| Pin 7 peak frequency | 750 Hz | 748 Hz | |
| Pin 7 / pin 1 at peak | ≈ +2.5 dB | +2.0 dB | |
| Pin 7 −3 dB edges (width) | (150 Hz) | 684 / 818 Hz (134 Hz) | |
| Pin 7 −60 dB edges (width) | (1450 Hz) | 281 / 1992 Hz (1710 Hz) | |
| Pin 4 / pin 1 at peak | — | +0.3 dB | |
| Pin 4 −3 dB edges (width) | (260 Hz) | 609 / 922 Hz (313 Hz) | |
| Pin 4 −20 dB edges (width) | (2800 Hz) | 180 / 3304 Hz (3124 Hz) | |

### Stage by stage

| Pin | Simulated peak gain | Simulated −3 dB width | Measured gain | Measured width |
|:--|--:|--:|:--|:--|
| 4 | +0.3 dB | 313 Hz | | |
| 5 | +0.9 dB | 199 Hz | | |
| 6 | +1.5 dB | 157 Hz | | |
| 7 | +2.0 dB | 134 Hz | | |

### R45-9

| Quantity | Simulated, 220k | Simulated, 120k | Measured |
|:--|--:|--:|:--|
| Pin 5 / pin 4 at 750 Hz | +0.57 dB | +5.71 dB | |
| Colour bands | red-red-yellow | brown-red-yellow | |

## Why these measurements matter

- **DC:** shows whether a 540 runs the filter at 8 V (the chassis trace) or
  at 13 V (the 245 sheet).
- **Response widths:** show whether real stages are tuned close together,
  as the nominal model assumes, or spread apart. A spread would explain why
  the manual's 150 Hz / 260 Hz pair is wider than identical stages allow.
- **Stage by stage:** shows which stage, if any, is off-tune.
- **R45-9:** settles the one value the scan cannot show.
