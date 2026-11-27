# 80282 bench checks

No measurement in this file has yet been performed.  These are proposals for
corroborating the 80282 simulation without probing the inaccessible crystal
subassembly nodes.

## Crystal-filter response at board pins

| Item | Connection or setting |
|:--|:--|
| Board state | Radio off; 80282 unplugged; discharge supply capacitors first |
| Tracking generator / VNA source | `Out` through a 50 ohm pad; start below -30 dBm |
| Receiver | `RX IF` through a high-impedance active probe or characterized buffer |
| Return | Board `GND`; keep leads very short |
| Sweep | 8.995 to 9.008 MHz, 10 Hz or finer near the skirts |
| Safety | Do not connect a grounded instrument lead to any point except `GND` |

Procedure:

1. Record the source-through-pad response with the board absent.
2. Connect the board without changing cables, sweep `Out` to `RX IF`, and save
   the calibrated trace.
3. Find the peak, the two -3 dB crossings, and the two -26 dB crossings.
4. Repeat with source and receiver reversed.  Do not adjust T82-1, which the
   manual says was factory sweep-aligned.

*Not yet performed. This is the proposal.*

| Quantity | Simulated | Measured |
|:--|--:|--:|
| Peak frequency | 9,001,780 Hz (5 Hz grid) | |
| -3 dB bandwidth | 605 Hz | |
| Low -26 dB crossing | 9,000,700 Hz | |
| High -26 dB crossing | 9,003,670 Hz | |
| CW point, 750 Hz above low skirt | -4.12 dB relative to peak | |

This measurement matters because it would determine the unknown filter-crystal
resonances, losses, and real source/load impedances rather than fitting them.

## Carrier-oscillator alignment at accessible points

| Item | Connection or setting |
|:--|:--|
| Frequency counter | Junction of R82-5 and R82-6 through 0.01 uF if the counter has DC continuity, exactly as the manual directs |
| RF level instrument | Antenna jack into a dummy load; RF VTVM or 10 MHz-capable oscilloscope |
| Radio controls | DRIVE fully counterclockwise initially; SB-R for C82-1, SB-N for C82-3, LOCK for C82-2 |
| Safety | Transmit only into a rated dummy load; use the shortest time needed for readings |

Follow manual steps 1–13 on PDF pages 38–39 / printed pages 3-22–3-23.  Record
the two 26 dB-down skirt frequencies, the LOCK frequency, and the final carrier
null without moving any filter coil or T82-1.

*Not yet performed. This is the proposal.*

| Quantity | Simulated / documented target | Measured |
|:--|--:|--:|
| Temporary center setting | 9,001,700 Hz documented | |
| Low skirt | 9,000,700 Hz modeled | |
| LOCK minus low skirt | 750 Hz documented | |
| High skirt | 9,003,670 Hz modeled | |
| Carrier-balance residual at antenna | not yet simulated | |

This check would anchor the BFO crystal model and show how the real filter,
oscillator trimmers, transmitter chain, and load interact.

## Automated whole-receiver passband sweep

`sweep_receiver_passband.py` controls the existing Siglent SDG1032X and
SDS1202X-E over LAN.  It drives the antenna through a required external
attenuator, steps across the received RF frequency, and records recovered audio
from the 80279 `AUDIO` board pin.  It pauses with the generator output off while
the operator selects SB-N and SB-R, then retains the raw CSV, a compact summary,
and an overlaid plot under this bench directory.

This is an end-to-end receiver measurement, not a bare-filter trace.  It
includes the RF amplifier, receive mixer, 80282 crystal filter, product
detector, and audio preamplifier.  The script performs a half-drive linearity
check so AGC compression is exposed rather than mistaken for a flat passband.

Physical setup:

| Item | Connection or setting |
|:--|:--|
| SDG1032X CH1 | Antenna jack through 60 dB of physically installed 50 ohm attenuation |
| SDG setting | 10 mV peak-to-peak, 50 ohm load display, zero offset |
| Oscilloscope CH2 | Times-10 probe at 80279 `AUDIO`; probe ground to chassis only |
| Radio | 14 MHz, receive only, RF GAIN fully clockwise, CALIBRATE and blanker off |
| Transmit safety | Disconnect microphone and key; never transmit into the generator |

Identify the instruments without enabling the generator output:

```powershell
python bench/80282/sweep_receiver_passband.py --identify-only
```

Run both modes at the guarded default level and 50 Hz spacing:

```powershell
python bench/80282/sweep_receiver_passband.py
```

The defaults are scope `192.168.1.157`, generator `192.168.1.158`, 14.095 to
14.105 MHz, 201 points, 10 mV peak-to-peak before the declared 60 dB external
attenuator, and 16 scope averages.  The program refuses a declared combination
above 100 microvolts peak-to-peak at the antenna and turns the generator off in
its cleanup path after completion, cancellation, or an error.

The half-drive check waits three seconds for the receiver AGC to release.  A
usable low-level curve must change by 5 to 7 dB when the generator voltage is
halved; otherwise the summary marks the sweep
`invalid_agc_compression_or_noise`, and its shape must not be used as filter
evidence.

*Not yet performed. This is the proposal.*
