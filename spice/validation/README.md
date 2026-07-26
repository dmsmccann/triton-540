# Model validation circuits

These fixtures check model syntax and basic behavior independently of the
complete Triton schematic.

| Circuit | Purpose |
|:--|:--|
| `40823_validation.cir` | Gate-1 transfer, gate-2 control, and manual bias point |
| `80166_rf_magnetics_validation.cir` | L1/L2 continuity and 9 MHz trap response |
| `SW_Rotary_1x5_validation.cir` | All five switch positions |

Run them from this directory so their relative model paths resolve:

```powershell
New-Item -ItemType Directory -Force ..\generated\validation | Out-Null
& 'C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe' -b -D ngbehavior=ltpsa 40823_validation.cir
& 'C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe' -b -D ngbehavior=ltpsa 80166_rf_magnetics_validation.cir
& 'C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe' -b -D ngbehavior=ltpsa SW_Rotary_1x5_validation.cir
```

Any CSVs created by the validation circuits go to
`spice/generated/validation/` and are not versioned.
