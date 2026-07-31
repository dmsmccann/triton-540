# SPICE assets

This directory separates reusable simulation source from study evidence and
disposable simulator output.

| Directory | Contents | Versioned |
|:--|:--|:--:|
| [`models/`](models/) | KiCad-facing subcircuits and model documentation | Yes |
| [`validation/`](validation/) | Small standalone regression circuits | Yes |
| [`tools/`](tools/) | Netlist runner and plotting utilities | Yes |
| [`studies/`](studies/) | Curated CSV evidence, manifests, fixtures, and figures | Yes |
| `generated/` | Exported netlists, ngspice raw files, logs, caches, and temporary CSVs | No |

The KiCad schematics are the circuit source of truth. The 80166 runner exports
a fresh SPICE netlist from `triton_540.kicad_sch` before applying run-specific
parameters to a generated copy.

## Common commands

Check the project tools, KiCad exports, model regressions, and scanned-manual
toolchain without modifying source schematics:

```powershell
pwsh -File spice\tools\run_project_preflight.ps1
```

The preflight writes disposable BOMs, logs, rendered pages, and OCR output
below `spice/generated/preflight/`. Use `-SkipKicad`, `-SkipSpice`, or
`-SkipPdf` to omit a group.

Regenerate the documented 80166 figures:

```powershell
python spice\tools\plot_80166_manual_alignment.py
```

Run the 3.5 MHz normal-operation study from a fresh KiCad export:

```powershell
python spice\tools\run_80166_operation.py
```

Regenerate the 80289 frequency-plan and ten-meter alignment evidence from
fresh KiCad exports:

```powershell
python spice\tools\run_80289_frequency_plan.py
python spice\tools\run_80289_filter_ac_response.py
python spice\tools\run_80289_filter_response.py
python spice\tools\run_80289_output_loading.py
python spice\tools\run_80289_mixer_balance.py
python spice\tools\run_80289_crystal_injection.py
python spice\tools\run_80289_ten_meter_alignment.py
```

Run the final 29 MHz validation from a fresh KiCad export:

```powershell
python spice\tools\run_80166_headless.py `
  --tag final-29mhz-validation `
  --s4-pos 5 `
  --l-rack 1.4253u `
  --start 28.97Meg `
  --stop 29.03Meg `
  --points-per-decade 150000 `
  --set-component C13=5.787p
```

Generated output is written below `spice/generated/` and is intentionally
excluded from Git.
