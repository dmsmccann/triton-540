# Model validation circuits

These fixtures check model syntax and basic behavior independently of the
complete Triton schematic.

| Circuit | Purpose |
|:--|:--|
| `MC1496P_validation.cir` | DC bias and 3/13 MHz plus 10/20 MHz mixer products |
| `40823_validation.cir` | Gate-1 transfer, gate-2 control, and manual bias point |
| `80166_rf_magnetics_validation.cir` | L1/L2 continuity and 9 MHz trap response |
| `SW_Rotary_1x5_validation.cir` | All five switch positions |
| `SW_Rotary_4x5_validation.cir` | All four S89-1 wafers in all five positions |
| `SW_Rotary_1x4_validation.cir` | All four S5 ten-meter segment positions |
| `Potentiometer_Position_validation.cir` | Fixed-position linear-pot wiper division |
| `MV2201_validation.cir` | Reverse-bias capacitance at four control voltages |
| `2N5486_validation.cir` | IDSS, cutoff trend, and Q89-1 source-follower bias |
| `MPS6514_validation.cir` | Q89-2 and Q89-4 documented bias points |
| `MPS6512_validation.cir` | Datasheet gain bin and Q89-5 nominal DC bias |
| `1N4154_validation.cir` | D89-1 forward clamp and reverse capacitance |
| `80289_vfo_magnetics_validation.cir` | PTO/L4 estimates, T1 transfer/syntax sanity, and 1 mH RFC |

Run them from this directory so their relative model paths resolve:

```powershell
New-Item -ItemType Directory -Force ..\generated\validation | Out-Null
& 'C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe' -b -D ngbehavior=ltpsa MC1496P_validation.cir
& 'C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe' -b -D ngbehavior=ltpsa 40823_validation.cir
& 'C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe' -b -D ngbehavior=ltpsa 80166_rf_magnetics_validation.cir
& 'C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe' -b -D ngbehavior=ltpsa SW_Rotary_1x5_validation.cir
& 'C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe' -b -D ngbehavior=ltpsa SW_Rotary_4x5_validation.cir
& 'C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe' -b -D ngbehavior=ltpsa SW_Rotary_1x4_validation.cir
& 'C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe' -b -D ngbehavior=ltpsa Potentiometer_Position_validation.cir
& 'C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe' -b -D ngbehavior=ltpsa MV2201_validation.cir
& 'C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe' -b -D ngbehavior=ltpsa 2N5486_validation.cir
& 'C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe' -b -D ngbehavior=ltpsa MPS6514_validation.cir
& 'C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe' -b -D ngbehavior=ltpsa MPS6512_validation.cir
& 'C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe' -b -D ngbehavior=ltpsa 1N4154_validation.cir
& 'C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe' -b -D ngbehavior=ltpsa 80289_vfo_magnetics_validation.cir
```

Any CSVs created by the validation circuits go to
`spice/generated/validation/` and are not versioned.

The board-level MC1496 DC regression is a Python runner rather than a
standalone `.cir` fixture because the KiCad hierarchy is the 80287 circuit
source of truth. From the project root run:

```powershell
python spice\tools\run_mc1496_dc_regression.py
```

It writes the curated comparison to
`spice/studies/80287/dc-regression/data/`.
