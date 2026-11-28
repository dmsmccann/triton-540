# 80285 low-level driver bench checks

**Proposed. No measurements have been made.** The [board README](../../80285.md) has the comparison tables and the [operation study](../../spice/studies/80285/operation/README.md) describes the fixtures. The factory voltage table is on PDF page 42 / printed 3-26 of the [Model 540 manual](../../literature/540%20Triton%20Owner%20Manual.pdf). Use the top-view board drawing on PDF page 43 / printed 3-27 to identify the terminals.

## General setup

| Item | Connection or setting |
|:--|:--|
| Reference | Connect instrument returns to board `GND`. Avoid scope-ground clips on active pins. |
| Installed radio | Connect the antenna output to a suitably rated 50 Ω dummy load. For factory DC checks select SB-N, set DRIVE fully counterclockwise and use no RF signal. Select CW for the keying check. |
| Isolated board | Disconnect the chassis wiring before substituting supplies. Connect current-limited supplies with a common return. Start with `+12` at 13.0 V, `ALC` at 4.3 V and both `T` and `tD` at 0.2 V. Verify terminal identification and voltage before increasing either keying input. |
| RF fixture | Connect a calibrated 50 Ω source through a DC block to `IN`. Connect a 50 Ω termination at `OUT`. Include fixture loss, probe loading and any attenuator in the calibration. |

## 1. Bias and the two transmit feeds

1. In the installed radio, record `+12`, `T`, `tD`, `ALC`, `IN` and `OUT` in receive and after transmit settles. Keep DRIVE fully counterclockwise. Record actual `+12` on every run.
2. On the isolated board, measure supply current with both feeds low, with only `T` at 10.4 V, and then with `tD` also at 4.4 V. Keep `ALC` and `+12` fixed and RF off. Monitor both feeds at the pins. For the intermediate state change `T` alone.
3. If there is clear access on the chassis, use an insulated DMM probe for Q85-5’s DC base and emitter readings. The model’s Q85-3/Q85-4 base and emitter voltages are internal diagnostics. Ten-Tec marks these nodes inaccessible. Avoid probing their RF collectors with a standard scope probe.

## 2. Gain and ALC

1. Use the isolated fixture. Set `T` to 10.4 V and `tD` to 4.4 V. Set `ALC` to 4.3 V and verify each voltage at the board. Set the RF source as low as practical. Halve the drive and check that `OUT` also halves within measurement uncertainty before logging gain.
2. At 3.5, 7, 14, 21, 28 and 30 MHz measure the RF voltage at the loaded `IN` and `OUT` pins. Use a calibrated high-impedance probe or a two-port measurement with fixture corrections. Record `20 log10(|OUT|/|IN|)`, which compares voltages at the pins.
3. With source, load, bias and frequency held fixed, sweep `ALC` toward 0.2 V. Start in 0.1 V steps and return to the initial reading afterward. Capture the output floor separately with RF input off. Report readings below the instrument floor as bounds.

## 3. CW envelope and keying

1. On the isolated board, supply a steady 3.5 MHz tone starting near 10 µV peak open-circuit at the generator. Increase it only as needed for signal-to-noise ratio and repeat the half-drive check. Split the scope channels between `T`, `tD`, `OUT` and the key command. Keep `ALC` and `+12` at the same settings for both waveforms.
2. Use paired pulse sources set to the receive/transmit levels above. First step both feeds together. Repeat with `tD` rising 1.73 ms after `T`. Use simultaneous falling edges in both runs. Record carrier amplitude versus time and the first crossing of half the settled amplitude. Capture key-up with the same time base and gain.
3. If checking the installed radio, select CW and key the transmitter briefly into the dummy load. Record the real `T`, `tD`, and driver `OUT` waveforms with the 80281 connected. Use a high-impedance RF probe on the installed `OUT` line to avoid changing the final-amplifier input load. Record the actual drive and compare timing and sequence. Retain the waveforms and record trigger and amplitude thresholds.

## 4. Input impedance and transformer/load sensitivity

1. Calibrate a vector network analyzer or impedance fixture at the `IN` reference plane with bias isolated from the instrument. With the board keyed in the isolated fixture, use low excitation and terminate `OUT` in 50 Ω. Record resistance and reactance at the six frequencies listed above, with `ALC` held at 4.3 V.
2. With the same bias and source reference plane, substitute calibrated 25 Ω and 100 Ω loads at `OUT`. Repeat the input impedance and gain measurements. Use external loads and keep drive small to limit power in the board.
3. If the load comparison leaves the transformer ratio uncertain, power down and disconnect the winding terminals as needed to isolate them. With a low-level AC source, measure primary-to-secondary open-circuit voltage ratio away from self-resonance and record the frequency. With the board unpowered, measure L85-1 and L85-2 end-to-end and each section with the unused section open. Record DC winding resistance and test frequency. These measurements replace the starting estimates before further RF studies.
