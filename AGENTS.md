# Triton IV Model 540 reconstruction

## Project purpose

Recreate the Ten-Tec Triton IV Model 540 faithfully in KiCad, one original assembly and chassis section at a time. Preserve historical topology and reference designators while making uncertainty explicit.

## Source and evidence rules

- Treat `literature/540 Triton Owner Manual.pdf` as the primary source.
- Check the assembly schematic, service description, alignment procedure, main chassis wiring, and adjacent photographs before concluding that a value is undocumented.
- Separate conclusions into documented, calculated, inferred, and unknown.
- Cite the PDF page and printed manual page for significant findings.
- Prefer original manufacturer literature and component datasheets for external research.

## KiCad conventions

- Preserve Ten-Tec assembly numbers, reference designators, signal names, and connector labels.
- Use a stock symbol only when its electrical topology is correct. Create project-local symbols for legacy multi-tapped, permeability-tuned, or otherwise unusual components.
- Keep custom symbols in project-local `.kicad_sym` libraries and maintain `sym-lib-table`.
- Put estimated values in notes or fields that clearly say `estimated`; do not present them as factory specifications.
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

## Reusable workflow

Use the project skill `$triton-540-restoration` for component identification, manual research, tuned-circuit estimates, custom-symbol decisions, schematic comparisons, and assembly validation.
