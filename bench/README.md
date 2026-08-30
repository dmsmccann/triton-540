# Bench measurements

Measurements taken on real hardware, as opposed to the simulation evidence
under [`../spice/`](../spice/README.md). One directory per assembly, named by
its Ten-Tec assembly number.

| Assembly | Radio | Measurement | Status |
|---|---|---|---|
| [`80166/`](80166/) | Triton IV Model 540 | Receiver RF amplifier L1/L2 tracking on 80 m | Procedure written, sweeps not yet captured |
| [`80350/`](80350/) | **Model 544** | VFO mixer-balance adjustment of `R2 MIXER BAL.` | Complete |

The 80350 VFO belongs to a Ten-Tec Model 544, not to the Model 540 this
project reconstructs. It is kept here because the measurement technique and
instruments are the same, but its results are not evidence about the 540.

Each assembly directory holds its own procedure `README.md`, the capture and
plotting scripts, a `data/` directory holding the captured runs as the
measurement record, and a `plots/` directory for generated figures. Captured
data and plots are deliberately versioned; only tooling caches are ignored.

## Instrument control

The 80166 scripts drive a Siglent SDG1032X generator and SDS1202X-E
oscilloscope over LAN, using SCPI over VXI-11 through `pyvisa` + `pyvisa-py`,
so no NI-VISA installation is required:

```powershell
python -m pip install pyvisa pyvisa-py matplotlib
```
