# SPICE assets

This directory separates reusable simulation source from study evidence and
disposable simulator output.

| Directory | Contents | Versioned |
|:--|:--|:--:|
| [`models/`](models/) | KiCad-facing subcircuits and model documentation | Yes |
| [`validation/`](validation/) | Small standalone regression circuits | Yes |
| [`tools/`](tools/) | Study runners, shared ngspice helpers, and plotting utilities | Yes |
| [`studies/`](studies/) | Curated CSV evidence, manifests, fixtures, and figures | Yes |
| `generated/` | Exported netlists, ngspice raw files, logs, caches, and temporary CSVs | No |
| `runtime/` | Local ngspice executable and runtime dependencies | No |

The KiCad schematics are the circuit source of truth. The 80166 runner exports
a fresh SPICE netlist from `triton_540.kicad_sch` before applying run-specific
parameters to a generated copy.

Each study has its own runner named for the assembly it exercises. Helpers
that are genuinely board-independent — reading an ngspice ASCII raw file,
converting a voltage ratio to decibels, and measuring a swept response for its
peak, its −3 dB bandwidth and its sample spacing — live in `tools/ngspice_raw.py`,
which every runner imports. A runner named for one assembly never provides
infrastructure to another.

Where several studies exercise the same board, that board's netlist editing lives
in one place: `tools/run_80166_headless.py` holds the 80166's parameter,
component, source and model-parameter edits, and the four new 80166 study runners
import it.

## Common commands

Run ngspice 46 outside KiCad through the project launcher:

```powershell
Push-Location spice\validation
& ..\tools\ngspice.cmd -b -D ngbehavior=ltpsa 40823_validation.cir
Pop-Location
```

The launcher prefers `spice/runtime/ngspice-46/bin/ngspice_con.exe`, then
checks `C:\Tools\ngspice-46\Spice64\bin` and `PATH`. The local runtime is
intentionally excluded from Git; simulation source and results remain
independently curated.

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

Run the 80166 studies from fresh KiCad exports. Each one exports the netlist,
applies its own state, runs ngspice, and rewrites its curated CSVs and figures:

```powershell
python spice\tools\run_80166_operation.py            # 3.5 MHz normal operation
python spice\tools\run_80166_defeat_gain.py          # DEFEAT gain reduction
python spice\tools\run_80166_rf_gain_supply.py       # RF GAIN as the stage supply
python spice\tools\run_80166_trap_9mhz.py            # 9 MHz trap
python spice\tools\run_80166_loading_sensitivity.py  # output loading and coil Q
```

The root schematic can only usefully simulate one assembly at a time. These
runners need the `RF_Amp_80166` sheet included in simulation and the other three
sub-sheets excluded, which is how `triton_540.kicad_sch` currently stands; a
runner stops with a clear message if the export contains no 80166 nets.

Run the 80287 receive/transmit conversion study and both mixer-balance sweeps:

```powershell
python spice\tools\run_80287_operation.py
python spice\tools\run_80287_rx_balance.py
python spice\tools\run_80287_tx_balance.py
```

Regenerate the settled 80287 MC1496 DC pin-voltage regression:

```powershell
python spice\tools\run_mc1496_dc_regression.py
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
