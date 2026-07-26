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

## Reusable workflow

Use the project skill `$triton-540-restoration` for component identification, manual research, tuned-circuit estimates, custom-symbol decisions, schematic comparisons, and assembly validation.
