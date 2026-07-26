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
- `figures/` contains plots generated from the retained CSVs.

The long original export filenames have been replaced by stable run IDs.
Electrical settings and provenance belong in `manifest.csv`, not in filenames.

Regenerate both figures with:

```powershell
python spice\tools\plot_80166_manual_alignment.py
```

Absolute gain from these lightly loaded models is not treated as a receiver
specification. The alignment study uses peak frequency and loss at the manual
target as its primary results.
