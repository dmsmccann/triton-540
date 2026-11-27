# 80280 control-board bench checks

Not yet performed. This is the proposal. Use the board's GND terminal as
the measurement reference. See [80280](../../80280.md) for the circuit
explanation, service references and simulation setup.

| Check | Instruments and board pins | Radio settings and drive |
|---|---|---|
| Receive/transmit DC | High-impedance DMM at T/R, R, T, tD, +12 and +REG | SB-N and DRIVE fully CCW. OFFSET centered and pushed in. Use stock PTT for transmit. |
| PTT/CW timing | Four-channel scope at T/R, R, T and tD. Use ×10 probes and trigger on T/R. | Use SB-N for PTT. Use CW for the key and keep DRIVE at minimum. |
| OFFSET and zero alignment | High-impedance DMM at OT and OT ON-OFF. Use received audio to judge the beat pitch. | Start in receive with a stable CW signal and the knob centered and pushed in. |
| Regulator transition | Scope or DMM at +12 and +REG simultaneously | Compare the same receive and keyed conditions used above. Use DC coupling for the scope. |

Connect the transmitter output to a suitable 50 Ω dummy load before
keying and keep the transmissions brief. For the OFFSET pitch check,
return to the receive signal source with the transmitter unkeyed.

1. Record rail voltages with PTT open and closed. Keep the same power
   supply and chassis connections for both readings.
2. Capture the first key pulse after a long receive interval, then a
   series of short pulses. Keep the wiring and controls fixed. Zoom
   into the first 10 ms of each edge, including any tD jump or negative
   excursion. Use the midpoint between settled RX and TX levels for
   timing. A driver-only measurement requires isolating the 80281 tD
   branch with power off. Run that comparison only with the transmitter
   RF path inhibited and the other driver connections preserved.
3. In receive, record OT at the two ends and center with the switch
   pushed in. Keep the tuning fixed. Pull the knob and record OT again.
   If alignment is intended, adjust only R80-16 for matching beat
   pitch and repeat the center measurements. Finally compare keyed OT.
4. Keep the normal board loads connected. Capture +12 and +REG across
   the transmit transition and note the steady voltage and largest dip.

| Quantity | Simulation | Measured |
|---|---:|---|
| R, receive / transmit | 12.16 / 0.00 V | |
| T, receive / transmit | 0.06 / 10.28 V | |
| tD, receive / transmit | 0.06 / 4.04 V | |
| tD midpoint relative to T, driver load only | +1.73 ms | |
| tD first sample after closure, nominal loaded case | 6.6 V at +2 µs | |
| R midpoint after key opens | 3.9 ms | |
| OT at center, engaged / aligned disengaged | 3.179 / 3.176 V | |
| OT endpoints, receive engaged | 2.02 / 4.42 V | |
| +REG near 13.8 V input | 8.03 V | |
| +REG through the modeled 30 to 60 mA keyed load step | about 8.03 V | |

The DC test constrains the effective rail loads. The timing test checks
the role of the 80281 C3 path. The pitch comparison checks whether the
voltage match holds with the actual VFO connected. The regulator capture
checks the supply and load response against the functional model.
