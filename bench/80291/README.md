# 80291 bench checks

No measurement in this file has yet been performed. These are proposals for
corroborating the 80291 simulation in
[`spice/studies/80291/operation/`](../../spice/studies/80291/operation/README.md),
which is explained in [`80291.md`](../../80291.md).

The 80291 is a plug-in board with no active parts and no supply. Every check
below is made with the board **out of the radio**, touching only its edge
pins. Nothing inside the shield cans is probed. A probe on a winding's hot
end would add more capacitance than the 10–22 pF tuning capacitors on the
upper bands, and would detune the very thing being measured.

Pin names follow the KiCad sheet. On each band, `-I` is the input from the
transmit mixer (the manual's right-hand row of pins) and `-O` is the output
to the 80285 driver (left-hand row). Each row has a `GND` pin at both ends.

## 1. Resistance to chassis (the manual's own check)

| Item | Connection or setting |
|:--|:--|
| Instrument | Ohmmeter or DMM on its lowest resistance range |
| Board state | Out of the radio |
| Return lead | Either `GND` pin |
| Probe | Each signal pin in turn |

Null the meter leads first. The manual's figures are on PDF page 41, printed
page 3-25.

*Not yet performed. This is the proposal.*

| Pin | Manual | Simulated | Measured |
|:--|:--|--:|--:|
| `3_5-I` | infinite | open (> 1 GΩ) | |
| `3_5-O` | 47 Ω | 47 Ω | |
| `7.0-I` / `7.0-O` | zero | 0.02 Ω / 0.02 Ω | |
| `14_0-I` / `14_0-O` | zero | 0.02 Ω / 0.02 Ω | |
| `21_0-I` / `21_0-O` | zero | 0.02 Ω / 0.02 Ω | |
| `28_0-I` / `28_0-O` | zero | 0.02 Ω / 0.02 Ω | |

What a wrong reading means:

- **`3_5-O` far from 47 Ω.** Look at R91-1 or the L91-1/L91-2 path.
- **`3_5-I` conducting.** C91-1 is leaky.
- **A band-pass pin reading open.** The tap or the grounded end of that
  winding is broken.

## 2. Passband and rejection, 50 Ω both ends

| Item | Connection or setting |
|:--|:--|
| Generator | 50 Ω output, sine, about 0 dBm (0.63 V p-p into 50 Ω), to the band's `-I` pin |
| Oscilloscope or RF voltmeter | Band's `-O` pin through a 50 Ω feed-through termination |
| Return | Both instrument grounds to the nearest `GND` pin, with short leads |
| Unused pins | Leave open |
| Safety | Passive board; nothing to protect beyond keeping leads short |

Procedure:

1. **Reference.** Connect the generator straight to the feed-through
   termination and scope, using the same cables, and record the voltage at
   each test frequency. This is 0 dB. It is the same reference the simulation
   uses: 0 dB is what the generator delivers into 50 Ω directly.
2. **Measure.** Insert the board without changing cables, generator level, or
   termination. Step through the band edges, band centre, the two hump peaks,
   and the mixer-product frequencies listed below. Record the output at each,
   as dB relative to the reference.
3. Do **not** turn any slug in T91-1 to T91-4. The manual says these filters
   need no field alignment. Turning a slug destroys the factory setting this
   measurement is trying to capture.

*Not yet performed. This is the proposal.*

| Filter | Frequency (MHz) | What it is | Simulated (dB) | Measured (dB) |
|:--|--:|:--|--:|--:|
| 80 m | 3.5 / 3.75 / 4.0 | band edges and centre | −5.1 / −5.0 / −5.2 | |
| 80 m | 9.0 | IF leak | −44.0 | |
| 80 m | 12.75 | VFO leak | −59.7 | |
| 40 m T91-1 | 7.0 / 7.25 / 7.5 | band edges and centre | −1.6 / −2.5 / −1.7 | |
| 40 m T91-1 | 9.0 | IF leak | −30.7 | |
| 20 m T91-2 | 14.0 / 14.25 / 14.5 | band edges and centre | −1.9 / −2.5 / −2.1 | |
| 20 m T91-2 | 9.0 | IF leak | −38.4 | |
| 15 m T91-3 | 21.0 / 21.25 / 21.5 | band edges and centre | −2.2 / −2.5 / −2.4 | |
| 15 m T91-3 | 12.25 | VFO leak | −41.0 | |
| 10 m T91-4 | 28.0 / 29.0 / 30.0 | band edges and centre | −1.7 / −2.5 / −1.7 | |
| 10 m T91-4 | 20.75 | VFO leak, 29.5 segment | −33.7 | |

Read exact simulated values for any other frequency from
`spice/studies/80291/operation/data/response.csv`, columns `bench_<band>_db`.
The sweep grid is 10 kHz.

This measurement matters because it pins down the three estimated magnetics
parameters:

- **Coupling K.** The spacing of the two humps and the dip between them.
- **Unloaded Q.** The loss at the hump peaks.
- **Tap position.** How flat the passband is with 50 Ω terminations.

## 3. Same filters, 1 kΩ load

Repeat section 2 for the 40 m and 10 m filters. Replace the 50 Ω feed-through
with a 1 kΩ resistor from `-O` to `GND`, and use a ×10 probe across it. Keep
the 50 Ω generator. The reference is still the generator into 50 Ω.

*Not yet performed. This is the proposal.*

| Filter | Quantity | Simulated | Measured |
|:--|:--|--:|--:|
| 40 m T91-1 | −3 dB edges | 6.91–7.18 MHz | |
| 10 m T91-4 | −3 dB edges | 27.63–28.73 MHz | |
| 10 m T91-4 | Output at 29.0 MHz relative to peak | −3.5 dB | |

This shows directly how much the filters rely on low impedances at the taps.
Comparing it with section 2 separates tap position from coupling, which a
single 50 Ω sweep cannot do.
