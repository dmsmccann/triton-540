---
name: triton-540-restoration
description: Analyze and reconstruct Ten-Tec Triton IV Model 540 circuits in KiCad from local service-manual scans, schematics, chassis wiring, photographs, and project files. Use when identifying legacy parts or suitable KiCad symbols, tracing board and off-board connections, estimating undocumented inductors or transformers, checking a recreated assembly against the manual, creating semantically accurate custom symbols, or validating a Model 540 schematic.
---

# Triton 540 Restoration

Reconstruct the radio faithfully while keeping documented facts separate from engineering estimates.

## Core workflow

1. Inspect the project instructions, relevant KiCad files, lock files, manual, and literature directory.
2. Identify the original Ten-Tec assembly number and locate its service description, schematic, alignment procedure, chassis wiring, and photographs.
3. Trace connections that leave the assembly. Values omitted from a board schematic may appear on the main chassis wiring or a bandswitch wafer.
4. Establish evidence in this order:
   - Explicit manual schematic, parts list, or service text
   - Main chassis wiring and off-board component values
   - Alignment instructions and voltage tables
   - Board and chassis photographs
   - Resonance, impedance, bias, and period-component calculations
   - Primary-source web material, followed by clearly identified secondary sources
5. State which conclusions are documented, calculated, inferred, or still unknown.
6. Recommend the KiCad representation and pin mapping. Prefer a custom symbol when a stock symbol would imply the wrong electrical topology.
7. Modify project files only when the user asks for implementation. Preserve unrelated user work.
8. Validate proportionately with KiCad CLI, ERC, exports, file parsing, or targeted calculations.

## Read scanned manual pages

- Try searchable PDF text first.
- When a page is image-only, render the exact page at sufficient resolution and crop the relevant region.
- Inspect adjacent pages when the service text refers to a figure, trimmer board, bandswitch, or chassis assembly.
- Cite both the PDF page number and the printed manual page when they differ.
- Read [references/source-map.md](references/source-map.md) for the known project artifacts and established RF-amplifier page map. Update it when another assembly is analyzed.

## Analyze undocumented tuned components

- Determine which winding section is resonated and which terminals are taps or isolated windings.
- Use the complete selected capacitance, including off-board parts and a justified parasitic-capacitance range.
- Use \(L=1/(4\pi^2 f^2 C)\) or \(C=1/(4\pi^2 f^2 L)\), calculate a range, and test it against every switched band.
- Treat schematic coil-loop counts as illustrative unless construction data proves otherwise.
- Infer turns ratio only when impedance transformation, tap location, photographs, or measurements support it.
- For coupled resonators, describe primary and secondary roles, expected coupling, Q, core type, shielding, and adjustment method without inventing exact turns.

## Choose KiCad symbols

- Match electrical topology before visual resemblance.
- Do not represent a tapped continuous winding as two isolated coupled inductors.
- For legacy tapped or permeability-tuned coils, create a custom symbol with explicit endpoint and tap pins when no stock symbol is exact.
- Preserve original reference designators, assembly numbers, net names, and functional labels.
- Record full-winding values separately from tap-to-end values; inductance does not divide linearly with turns.
- Keep symbol pin numbering synchronized with the intended footprint or documented physical terminals.

## Editing safeguards

- Check for `~*.lck` files before editing KiCad documents. If the relevant document is open, do not rewrite it without user confirmation.
- Do not replace newer user edits with autosaves or backups.
- Keep custom symbols in project-local libraries unless the user requests a shared library.
- Avoid cosmetic modernization that changes the meaning or appearance of the historical schematic unless requested.
- Report any inferred value in a field or note as an estimate, not as a Ten-Tec specification.

## Report results

Lead with the recommended symbol or component value. Then provide:

1. Circuit function and topology
2. Documentary evidence and page locations
3. Calculation or inference
4. Likely range and confidence
5. KiCad implementation recommendation
6. Remaining measurement or documentation needed for certainty
