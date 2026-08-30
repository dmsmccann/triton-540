# 80166 manual-alignment study

This directory contains the curated evidence used by the AC-alignment section
of the project-level [`80166.md`](../../../../80166.md).

## Contents

- `manifest.csv` records the purpose and settings of each retained run.
- `data/final/` contains the L1-bypassed and final response for each manual
  alignment frequency, plus the saved-schematic validation run.
- `data/29mhz-iterations/` contains only the C13 trials used by the 29 MHz
  convergence figure.
- `fixtures/` contains the corrected placement image for the temporary
  0.01 µF L2-bypass capacitor.
- `figures/` contains plots generated from the retained CSVs:
  `all-bands.png` (normalized final response on every band),
  `29mhz-adjustment.png` (the rack-then-C13 sequence), and
  `alignment-split.png` (the ANT-to-OUT overlay of the L1-only and
  full-stage responses, which is the same pin-to-pin ratio the bench
  sweep in [`bench/80166`](../../../../bench/80166/README.md) produces).

The long original export filenames have been replaced by stable run IDs.
Electrical settings and provenance belong in `manifest.csv`, not in filenames.

`data/29mhz-iterations/` is the deliberate exception. Those files are a
convergence sequence in a single variable, and the C13 value in each name is
what distinguishes one iteration from the next; carrying it in the filename
keeps the sequence readable in directory order and in the figure's legend.
Every run, iterations included, still has a full row in `manifest.csv`.

Regenerate both figures with:

```powershell
python spice\tools\plot_80166_manual_alignment.py
```

Absolute gain from these lightly loaded models is not treated as a receiver
specification. The alignment study uses peak frequency and loss at the manual
target as its primary results.
