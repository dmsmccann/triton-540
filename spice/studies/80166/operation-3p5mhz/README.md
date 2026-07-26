# 80166 normal operation at 3.5 MHz

This study shows the reconstructed RF-amplifier board doing its normal job:
the RESONATE rack places the two tuned circuits on the wanted frequency, a
small RF signal reaches Q1, and the selected signal grows as it passes through
the input network, active stage, and output network.

The circuit source is `triton_540.kicad_sch`. The study script exports a fresh
KiCad SPICE netlist on every run; it does not maintain a second hand-written
copy of the circuit.

## Configuration

- Bandswitch: `S4_POS=1` (3.5 MHz)
- Normal receive supplies: `/R=12 V`, `/DEFEAT=3.9 V`
- Aligned rack model: `L_RACK=17.2 µH`
- 3.5 MHz L2 trimmer: `C19=36 pF`
- L2 tracking fit:
  `L2=1.97963 µH + 0.0849053 × L_RACK`
- Output load: the schematic's provisional `1 MΩ || 5 pF`
- Generator: 3.5 MHz, 10 µV peak, with 50 Ω series resistance
- Transient run: 2 ns maximum step, 60 µs duration

The 10 µV figure is the generator's open-circuit peak voltage. The tuned
network loads the 50 Ω source, so the voltage actually present at the board's
`ANT` node is 0.927 µV peak. Gains in this study are referenced to that
measured `ANT` voltage, not to the source's unloaded setting.

## What the retained results show

[`figures/rack-tuning.png`](figures/rack-tuning.png) compares frequency sweeps
at three rack settings. Increasing `L_RACK` moves the response downward in
frequency, as expected from

$$
f_0 = \frac{1}{2\pi\sqrt{LC}}.
$$

At the manual-aligned 17.2 µH setting, the modeled response peaks at
3.5012 MHz and gives 20.189 dB voltage gain at exactly 3.500 MHz. The coarse
rack sweep found a marginally larger 20.240 dB at 17.0 µH—a difference of
only 0.052 dB. This is smaller than the precision justified by the provisional
coil-loss and output-load models.

[`figures/signal-walk.png`](figures/signal-walk.png) shows both the buildup of
the resonant response after the sine source starts and the final six RF
cycles. The DC bias is removed from the waveform panels so the microvolt RF
can be seen clearly.

| Circuit point | RF peak | Voltage ratio from `ANT` | Gain from `ANT` |
|:--|--:|--:|--:|
| Board `ANT` node | 0.927 µV | 1.000× | 0.000 dB |
| Q1 gate 1 | 2.459 µV | 2.654× | 8.477 dB |
| Q1 drain | 5.669 µV | 6.119× | 15.733 dB |
| Board `OUT` node | 9.469 µV | 10.220× | 20.189 dB |

The increase from `ANT` to gate 1 is resonant voltage transformation in the
L1 input network; it is not transistor gain. The 7.256 dB increase from gate
1 to drain is produced by Q1 acting into L2's resonant drain load. The final
4.456 dB from drain to `OUT` is the voltage transformation through the tapped
L2 output network in this model. Those three contributions add to the
20.189 dB overall voltage ratio.

The upper plot's approximately 10 µs settling time is the simulated resonant
circuits building to steady state after a suddenly applied sine wave. It is
not an AGC time constant or a claim about receiver audio response.

## Evidence and limitations

- **Documented:** the single-stage dual-gate-MOSFET topology, the 3.5 MHz
  alignment frequency, the bandswitch arrangement, and the normal receive
  bias are from the Ten-Tec manual, PDF pp. 24–25 / printed pp. 3-8–3-9.
- **Fitted:** the rack inductance and L2 tracking equation come from the
  manual-sequence alignment study.
- **Calculated:** all amplitudes and gains above are calculated from the
  retained transient CSV.
- **Still provisional:** coil Q, tap ratios, the 40823 model, and the
  `1 MΩ || 5 pF` OUT load. The results demonstrate circuit action and relative
  voltage gain; they are not a factory gain specification or a prediction of
  loaded power gain in an original radio.

## Reproduce

With KiCad 10 and ngspice 46 installed at the paths configured near the top of
the script:

```powershell
python spice\tools\run_80166_operation.py
```

Curated CSVs and plots are replaced in this directory. Exported netlists, raw
files, and logs go to ignored `spice/generated/80166-operation/`.
