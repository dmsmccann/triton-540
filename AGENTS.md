# Triton IV Model 540 reconstruction

## Project purpose

Recreate the Ten-Tec Triton IV Model 540 faithfully in KiCad, one original assembly and chassis section at a time. Preserve historical topology and reference designators while making uncertainty explicit.

## Source and evidence rules

- Treat `literature/540 Triton Owner Manual.pdf` as the primary source.
- Check the assembly schematic, service description, alignment procedure, main chassis wiring, and adjacent photographs before concluding that a value is undocumented.
- Separate conclusions into documented, calculated, inferred, and unknown.
- Cite the PDF page and printed manual page for significant findings.
- Prefer original manufacturer literature and component datasheets for external research.

## Repository layout and naming

The assembly number is the organizing key. Every discipline directory uses it
as its second level, so all of one board's material is reachable by number.

| Path | Holds |
|:--|:--|
| `<assembly>.md` | the board document, at the repository root |
| `<assembly>_<function>.kicad_sch` | the board's sub-sheet, at the root beside its document |
| `spice/studies/<assembly>/<study>/` | curated CSV evidence, `manifest.csv`, fixtures, figures |
| `spice/tools/run_<assembly>_<study>.py` | the runner that regenerates one study |
| `bench/<assembly>/` | hardware measurements: procedure, scripts, `data/`, `plots/` |

Schematic filenames are lowercase, assembly number first, so a board's document
and schematic sort together. Do not rename a sub-sheet without updating its
`Sheetfile` property in `triton_540.kicad_sch` and every runner that opens it
by name.

Simulation evidence and bench evidence are kept in separate trees on purpose.
A simulated result must never be presentable as a measured one. `bench/*/data/`
and `bench/*/plots/` are the measurement record and are deliberately versioned;
`spice/generated/` and `spice/runtime/` are disposable and never versioned.

`datasheets/` names the assembly that uses each part, so a device sheet can be
traced back to the board that needs it.

## Sheet names are load-bearing

KiCad derives SPICE net prefixes from a sheet's `Sheetname` property, not from
its filename. `RF_Amp_80166`, `IF-AGC_80279`, `VFO-80289`, and
`TX RX Mixer 80287` therefore appear as `/rf_amp_80166/...` and similar in every
exported netlist, are hard-coded in the study runners, and are baked into the
retained study CSVs.

Renaming a sheet invalidates that evidence and requires re-running every study
that depends on it. Treat `Sheetname` as fixed. Their inconsistent styles are
accepted deliberately; the filenames carry the convention instead.

## Simulation tooling

- Name a runner for the assembly it exercises: `run_<assembly>_<study>.py`.
- A runner named for one assembly must never provide infrastructure to another.
  Board-independent helpers — reading an ngspice ASCII raw file, converting a
  voltage ratio to decibels — belong in `spice/tools/ngspice_raw.py`, which any
  runner may import.
- Keep board-specific netlist edits and result summaries in that board's own
  runner, where the net names and component references are already specific.

## KiCad conventions

- Preserve Ten-Tec assembly numbers, reference designators, signal names, and connector labels.
- Use a stock symbol only when its electrical topology is correct. Create project-local symbols for legacy multi-tapped, permeability-tuned, or otherwise unusual components.
- Keep custom symbols in project-local `.kicad_sym` libraries and maintain `sym-lib-table`.
- Put estimated values in notes or fields that clearly say `estimated`; do not present them as factory specifications.
- Every placed symbol carries a unique reference. If two share one, identify
  from the manual which component genuinely owns it rather than assigning the
  next free number; a wrong designator is a silent error in the reconstruction.
  Multi-unit parts sharing one reference across units are correct and expected.
- Do not modernize the circuit, rename nets, or substitute components unless the user requests it.

## Editing safety

- Check `~*.lck` before editing a KiCad document. Do not rewrite a currently open schematic without user confirmation.
- Preserve unrelated user changes and never restore an autosave or backup over current work without approval.
- Inspect backups read-only unless a recovery is explicitly requested.
- Make the smallest coherent edit and keep schematic pin mappings aligned with footprints.

## Analysis and validation

- For tuned circuits, trace all off-board switched parts and include justified parasitic ranges in resonance calculations.
- Give likely ranges and confidence levels when exact magnetics or legacy parts are undocumented.
- After requested edits, run available KiCad CLI checks, ERC/exports, parsing checks, and `git diff --check` when applicable.
- If this directory is not a valid Git worktree, report that instead of assuming version-control protection.

## Board README simulation documentation

Write board-level simulation sections for a hobbyist who understands basic
components but may not already know the circuit, the analysis type, or RF
jargon. The board README explains how the radio works; detailed study READMEs
and CSV files hold exhaustive setup and machine-readable evidence.

For every new simulation, and whenever an existing simulation section is
substantially revised, present the material in this order:

1. **How this part of the circuit works.** Trace the signal through the actual
   components and explain the job of the active devices, tuned circuits,
   coupling parts, bias parts, controls, and loads involved in the test.
2. **What a working circuit should show.** State the expected waveforms,
   frequencies, DC levels, relative amplitudes, gain or attenuation direction,
   timing, or spectral products before presenting results.
3. **How the simulation tests it.** Identify the source, load, operating state,
   swept variable, and observation points. Explain why the selected analysis
   answers the functional question.
4. **What the simulation showed.** Include the important plot or table and
   translate technical measurements into plain meaning. For example, convert
   representative decibel values to approximate voltage ratios and explain
   what a bandwidth or time constant means in the receiver.
5. **Does it meet expectations?** Give an explicit pass, partial pass, or fail;
   identify which expected behaviors were or were not reproduced and what that
   says about the board.
6. **Limits and evidence status.** Keep documented values, calculations,
   fitted model parameters, and unknown hardware behavior separate. Do not
   present simulated gain, bandwidth, attenuation, timing, or distortion as a
   factory specification unless the manual or measured hardware supports it.

Define specialized terms on first use, explain plot axes and sign conventions,
and do not lead with simulator settings or unexplained numerical tables. A
reader should understand why the tested circuit exists and recognize a healthy
result before encountering the detailed simulation data.

## Figure labeling

Label every figure `Figure XX-Y`, where `XX` is the last two digits of the
assembly number the document covers and `Y` is the figure's sequential position
in that document, counting from 1. Put the label in a caption line directly
beneath the image, followed by a short description of what the figure shows:

```markdown
![Changing the RESONATE rack moves the 3.5 MHz passband](figures/rack-tuning.png)

**Figure 66-1.** Changing the RESONATE rack moves the 3.5 MHz passband
```

Numbering restarts in each document, so a study README and the board document
that cites the same plot each number it from their own sequence, and two
documents covering one assembly may both contain a `Figure 66-1`; the
containing document is what distinguishes them. When a figure is added or
removed, renumber the rest of that document so the sequence stays contiguous.
Keep the image's alt text as well as the caption.

## Reusable workflow

Use the project skill `$triton-540-restoration` for component identification, manual research, tuned-circuit estimates, custom-symbol decisions, schematic comparisons, and assembly validation.
