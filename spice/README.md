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

Regenerate the documented 80166 figures:

```powershell
python spice\tools\plot_80166_manual_alignment.py
```

Run the 3.5 MHz normal-operation study from a fresh KiCad export:

```powershell
python spice\tools\run_80166_operation.py
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
