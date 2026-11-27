# 80280 operation study

See the [board explanation and figures](../../../../80280.md) for the results
and the [bench procedure](../../../../bench/80280/README.md) for hardware checks.
Regenerate the figures and CSVs from the repository root:

```powershell
python spice/tools/run_80280_operation.py
```

The runner requires ngspice and Matplotlib. Set `NGSPICE_EXE` to select a
different ngspice installation. The manifest records analysis and fixture
settings. Generated decks, raw data and logs go under
`spice/generated/80280-operation/`.

## Source and circuit differences

KiCad 10 exported the current saved root sheet. The export contained
annotation diagnostics, invalid model-library paths and incomplete wiring.
The root ERC report lists 293 violations across the project, including
13 entries within the 80280 sheet. It flags Q80-6, Q80-9, C80-3, C80-5
and several IC-1 pins. The report is in the generated run directory.
The study uses a standalone transcription of the Ten-Tec circuit in
[control-board.cir](fixtures/control-board.cir). The following comparisons
use manual PDF page 52 / printed 3-36.

| Item | Fixture treatment |
|---|---|
| Q80-3 and Q80-4 | Share Q80-2 collector drive. R80-8/C80-2 take their timing edge directly from T. |
| Q80-6 | Base shares Q80-5 collector with Q80-7. The saved Q80-6 base was floating. |
| Q80-9 | Emitter grounded and base driven by R80-11/R80-12/R80-19. The saved emitter was floating. |
| C80-2 | Manual drawing shows 0.1 µF. The saved 0.01 µF is run separately. |
| R80-16 and IC-1 | Included with explicit pin connections. The export emitted placeholder instances. |
| D80-1/D80-2 and Q80-3/Q80-6 | Use project model libraries directly. The export decoded control characters in the saved model paths. |
| C80-3 and C80-5 | Connected from compensation to feedback and +12 to ground, respectively. Both were floating in the export. |

## Chassis fixture and assumptions

- A simulated dry contact grounds T/R with 0.1 Ω when keyed. Its open
  resistance is 10 GΩ. The nominal input is the manual's 13.8 V. The
  trigger returns to receive through the board's own resistors.
- The main wiring (PDF 21 / printed 3-4) routes tD to the low-level driver
  and 80281 OT-TR. The service drawing (PDF 43 / printed 3-27) shows the
  driver tD branch through R15 (470 Ω) to D3/D4. It also shows T feeding
  R12 (470 Ω), D1/D2 and C9 (0.1 µF). The diode model is generic silicon.
  The standing current of the driver transistors and other driver dynamics
  are approximated by those branches.
- The 80281 drawing (PDF 50 / printed 3-34) shows D1 feeding the upper
  plate of 32 µF C3 from T and the lower plate returning to tD. Its relay
  control is represented by half of the 10 kΩ delay adjustment plus
  680 Ω, and the 22 kΩ/base path. This models the electrical path from
  T to tD. Relay mechanics and hardware parasitics are unknown. The
  driver-only sensitivity run removes C3's effective coupling.
- Residual loads are 220 Ω on R and 82 Ω on T, estimated from the service
  voltages and the 10 Ω series legs. For example, the published Q80-4
  emitter/T gap implies about 150 mA through R80-6, including the
  roughly 20 mA driver branch. Both resistances are scaled by 0.75 and
  1.50 for the timing sensitivity. The equivalent loads lack off-board
  leakage and switching capacitance. Expect some differences in the low
  states. OT retains the 100 kΩ board return. The external 10 kΩ pot and
  a switch equivalent reproduce the manual's T-linked OT ON-OFF behavior.
  The 80281 lamp drive and VFO varactor are omitted.
- The DC, keying, and OFFSET studies use an ideal 8 V source. The
  [functional MC1723CL circuit](fixtures/mc1723cl-envelope.cir) reproduces
  the reference, error amplifier, pass stage, current sensing, and
  external feedback. Motorola gives a nominal reference of 7.15 V, a
  3 V minimum specified input-to-output differential, and roughly
  0.65 V for the nominal sense threshold (datasheet PDF pp. 1–2 /
  printed 358–359). The 3 V boundary, amplifier dynamics and pass
  resistance are model assumptions. The resulting knee, load
  regulation, and keyed response are sensitivity demonstrations.

## Retained data

| Evidence | Contents |
|---|---|
| `dc.csv` | Manual and model voltage at each selected pin and Q80-1–9 terminal. The handwritten transmit +REG value is omitted as a comparison target. |
| `keying.csv`, `driver-only-td.csv`, `timing.csv` | PTT and short-pulse test. Transient values were linearized on a 2 µs grid. Retained waveform rows are spaced 20 µs away from the expanded first-edge region. Timing comes from linear interpolation across the first crossing of the midpoint between initial and settled first-pulse voltages. |
| `offset-zero.csv`, `receive-*.csv`, `transmit-aligned.csv` | OFFSET and R80-16 sweeps at 1% increments. Positions run from the low to high end electrically. The pre-alignment R80-16 position is 25%. |
| `reg-line-*.csv`, `reg-load.csv`, `reg-keying.csv` | Input at 50 mV spacing, load at 1 mA spacing, and keyed load step sampled at 10 µs. |
