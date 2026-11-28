# Triton 540 project source map

## Local artifacts

- `literature/540 Triton Owner Manual.pdf` — primary service and alignment source
- `literature/Model 245.pdf` — original Model 245 CW filter instruction sheet;
  specifications, installation, operational check, voltages, schematic, photograph
- `literature/Ten_Tec_249.pdf` — original Model 249 instruction sheet; installation,
  operation, theory, alignment, schematic, photograph, and service voltages
- `triton_540.kicad_pro` — project configuration
- `triton_540.kicad_sch` — root schematic
- `80166_rf_amp.kicad_sch` — receiver RF amplifier reconstruction
- `80287_tx_rx_mixer.kicad_sch` — receiver/transmitter mixer reconstruction
- `80282_ssb_generator.kicad_sch` — SSB generator and bidirectional crystal-filter reconstruction
- `80308_crystal_calibrator.kicad_sch` — crystal-calibrator reconstruction
- `triton_iv.kicad_sym` and other project-local `.kicad_sym` files — custom legacy symbols
- `sym-lib-table` — project symbol-library mappings
- `spice/models/` — project-local active-device, RF-magnetics, and bandswitch models, including the 80282 filter/T1 model
- `spice/validation/` — standalone regression fixtures for those models
- `spice/studies/80166/manual-alignment/` — curated CSV evidence, manifest,
  placement fixture, and generated documentation figures
- `spice/studies/80166/operation-3p5mhz/` — reproducible AC rack sweep and
  small-signal transient study showing normal 3.5 MHz board operation
- `spice/studies/80308/operation/` — staged crystal-oscillator, pulse-gate,
  divider/mode, regulator, and DEFEAT study
- `mod_249.kicad_sch` — Model 249 optional 9 MHz IF noise-blanker reconstruction
- `245_cw_filt.kicad_sch` — Model 245 optional 750 Hz audio CW-filter reconstruction
- `spice/studies/249/how-it-works/` — normal transfer and PIN-diode gate study
- `bandpass_80291.kicad_sch` — 80291 transmit band-filter reconstruction; T91-1..T91-4 use the two-unit `T_Trim_dual_tap` symbol
- `spice/studies/80291/operation/` — 80291 passband, mixer-product, termination, detune and pin-resistance study (`spice/tools/run_80291_operation.py`)
- `spice/studies/245/operation/` — Model 245 DC, CW-1/CW-2, stage-by-stage and R45-9 study (`spice/tools/run_245_operation.py`)
- `triton_540-backups/` — user backups; inspect but do not restore over current work without approval

## Known manual map

PDF page numbers below are one-based.

- PDF page 21 / printed page 3-4 — main chassis wiring, including switched receiver-tuning capacitors
- PDF page 22 / printed page 3-6 — top chassis photograph and RF-amplifier/9 MHz trap location
- PDF page 23 / printed page 3-7 — bottom chassis photograph and receiver trimmer locations
- PDF page 24 / printed page 3-8 — assembly 80166 description and alignment procedure
- PDF page 25 / printed page 3-9 — assembly 80166 schematic and voltage data
- PDF page 26 / printed page 3-10 — VFO frequency plan, 80278 PTO description, and PTO alignment
- PDF page 27 / printed page 3-11 — 21/28 MHz correction and mixer-output alignment
- PDF page 28 / printed page 3-12 — mixer-balance completion and VFO semiconductor voltages
- PDF page 29 / printed page 3-13 — 80289 schematic, including nested 80278 PTO and 80277 oscillator board
- PDF page 30 / printed page 3-14 — receiver/transmitter mixer use of the internal or external VFO
- PDF page 31 / printed page 3-15 — 80287 schematic, parts, photograph, and voltage data
- PDF page 32 / printed page 3-16 — 80279 IF-AGC receive path after the SSB-generator crystal filter
- PDF page 33 / printed page 3-17 — 80279 IF-AGC schematic, IC-1 pin voltages, and top-view IC pin orientation
- PDF page 34 / printed page 3-18 — 80274 audio-power-amplifier receive, mute, and sidetone description
- PDF page 35 / printed page 3-19 — 80274 schematic, parts, and semiconductor voltage table
- PDF page 36 / printed page 3-20 — 80308 theory, terminal voltages, and semiconductor voltages
- PDF page 37 / printed page 3-21 — 80308 crystal-calibrator schematic, board photograph, SN7400 gate-unit pin use, and SN7476 flip-flop-unit pin use
- PDF page 23 / printed page 3-7 — installed Model 249 accessory-board location;
  the Model 540 manual itself has no Model 249 theory or alignment section
- PDF page 38 / printed page 3-22 — 80282 bidirectional crystal-filter and SSB-generator signal routing
- PDF page 39 / printed page 3-23 — 80282 carrier-oscillator and balanced-modulator alignment
- PDF page 40 / printed page 3-24 — 80282 schematic, board photograph, filter coils, and T1 topology
- PDF page 41 / printed page 3-25 — 80291 switched filters following the transmit mixer
- PDF page 42 / printed page 3-26 — 80285 low-level driver following the mixer and band filters

## Established 80166 evidence

- L1 and L2 are slug-tuned and mechanically ganged by the RESONATE rack.
- L1 is a continuous double-tapped winding, not two isolated windings.
- L2 is a continuous tapped output winding.
- The main wiring shows L1 band capacitors of 620, 220, 56, 22, and 10 pF for 3.5, 7, 14, 21, and 28 MHz respectively.
- Five receiver-output trimmers are identified as 5–60 pF.
- T1 and C7 form a sharply tuned 9 MHz input trap; “9 MHz” is the trap frequency, not an inductance value.
- The alignment procedure uses a temporary 0.01 µF capacitor from the selected
  L2-trimmer terminal to chassis to suppress the output resonance while L1 is
  peaked.
- Alternating the 3.5 and 4.0 MHz steps establishes L2-to-L1 tracking. The
  manual then says no further L2 slug adjustment is needed; the 7, 14.2, 21.2,
  and 29.0 MHz steps use the rack followed by the selected output trimmer.

## Current 80166 simulation fit

- The fitted L2 relationship is
  `L2 = 1.97963u + 0.0849053 * L_RACK`. This is an empirical model parameter,
  not a measured coil law or factory specification.
- The completed manual-sequence model peaks within 0.54 dB of its maximum at
  3.5, 4.0, 7.0, 14.2, 21.2, and 29.0 MHz.
- The 7 MHz model uses about 68 pF effective output capacitance: the documented
  60 pF trimmer limit plus approximately 8 pF of inferred parasitic
  capacitance.
- The final 29 MHz saved state uses `S4_POS=5`, `L_RACK=1.4253u`, C13 =
  5.787 pF, and gives a simulated `OUT/ANT` peak at 28.999365 MHz.
- In the 3.5 MHz normal-operation study, `L_RACK=17.2u` produces a 3.5012 MHz
  peak and 20.189 dB simulated voltage gain from the loaded `ANT` node to
  `OUT`. Treat this as circuit-action evidence, not a factory power-gain
  specification.

Treat calculated inductances and inferred winding ratios as estimates until supported by measurements or original construction data.

## Established 80282 evidence

- L2 and L3 are center-tapped 9 MHz crystal-filter coils, each shunted
  end-to-end by a documented 68 pF N220 capacitor. Ideal resonance calculates
  to 4.599 uH end-to-end before winding and board parasitics.
- T1 has a center-tapped tuned primary shunted by C82-12 = 220 pF and a
  separate secondary winding. Ideal 9 MHz resonance calculates to 1.421 uH
  end-to-end for the primary.
- The manual states that T1 was factory swept with the crystal lattice and
  should not be field adjusted; its setting affects filter flatness and audio
  character.
- `spice/models/80282_ssb_generator_magnetics.lib` preserves the documented
  topology. Equal winding halves and their K=0.98 are modeling assumptions;
  the 0.36 uH secondary and primary-secondary K=0.90 are inferred starting
  values, not Ten-Tec specifications.
- The reconstructed sheet now grounds the Y82-2/Y82-3 common node, connects
  `RX IF` to the L3/Y82-3/Y82-5 end of the first lattice, and uses the manual's
  C82-28 = 220 pF between sections. These were topology/value corrections, not
  simulation fitting.
- `spice/tools/run_80282_operation.py` verifies a fresh KiCad export and sweeps
  the filter at the accessible `Out` and `RX IF` pins on a 5 Hz grid. The
  current fitted crystal model peaks at 9.001780 MHz, has a 605 Hz -3 dB width,
  and places the documented +750 Hz CW point 4.12 dB below peak. This is a
  partial functional result; original crystal and termination measurements
  are still required.

## Established Model 249 evidence

- `literature/Ten_Tec_249.pdf` is scanned in reverse printed-page order. PDF
  page 2 / printed page -1 gives installation, operation, theory, C49-18
  alignment, and connector voltages. PDF page 1 / printed page -2 gives the
  schematic, board photograph, transistor voltages, and IC voltages.
- Ten-Tec identifies the Model 249 as a plug-in IF noise blanker for Models 540
  and 544, installed between the first-mixer output and crystal-filter input.
  Pulling the ALC knob out energizes it.
- C49-18 is the only on-board adjustment. With 9 MHz applied at `IN`, it is set
  for the broad maximum at Q49-4's base. After board installation, TX-RX mixer
  L3 is separately retuned for maximum S-meter indication on a station no
  stronger than S5; the blanker may be on or off.
- The factory receive/no-signal/blanker-energized table gives 13.8 V at `+12`
  and `+12_SW`, 5.5 V at IC49-1 pin 5, and complete Q49-1 through Q49-6 and
  IC49-1 pin 1-8 service voltages.
- The original Model 249 drawing dated 1976-06-02 documents a 9 MHz signal
  path through Q49-1/Q49-2, T49-1, D49-1/D49-2, and L49-1/C49-3, with a
  parallel MC1350 detector and Q49-3/Q49-4 gate-control path.
- Historical Ten-Tec catalog material describes the accessory as a plug-in IF
  noise blanker with nominal 0 dB signal gain and a front-panel disable switch.
- The current how-it-works study uses the live 13.28 V supply, an inferred
  10 kohm installed-stage load, C49-18 = 40 pF, and a model-only 5.1 kohm AGC
  shunt required by the archived MC1350 macro-model. It gives -4.36 dB enabled
  normal-path gain and 14.95 dB settled strong-burst suppression after a
  0.244 us modeled trigger delay. The leading peak is not suppressed, so this
  is a partial functional result, not a factory sensitivity specification.

## Established 80274 evidence

- U74-1 is the LM380 receive-audio power amplifier. Q74-1 grounds the
  R74-3/R74-4 junction during transmit; C74-1 with R74-1/R74-2 delays the
  return of receive audio.
- Q74-2 is the sidetone relaxation oscillator, Q74-3 is its CW enable switch,
  R74-7 controls pitch, and R74-5 controls level. R74-4 lets sidetone reach
  U74-1 while Q74-1 mutes received audio.
- The completed how-it-works study uses the live 13.28 V root-sheet supply and
  one inferred 8 ohm resistive speaker load. At midpoint controls it gives
  171.892 mV RMS receive output for 10 mV peak input, 64.98 dB modeled mute
  suppression, a 771.3 Hz / 1.056 V RMS sidetone, and 30.406 ms modeled audio
  recovery. These are fitted-model predictions, not factory specifications.

## Established 80279 evidence

- IC-1 is an MC1747 dual internally compensated operational amplifier. The
  first section amplifies recovered audio for the AUDIO terminal; the second
  section further amplifies it for AGC generation.
- The manual's top-view voltage table identifies pin 4 as 0 V, pins 9 and 13
  as 13.8 V, pins 10 and 12 as the two outputs, and pins 3, 5, 8, 11, and 14
  as unused in the assembly.
- The Motorola DIP pinout uses separate VCC pins for sections A and B and a
  shared VEE pin. The project symbol and `spice/models/MC1747.sub` wrapper
  preserve all fourteen physical pins one-to-one.
- The imported five-pin core does not model offset-null behavior. Its nominal
  dual wrapper is suitable for DC, closed-loop gain, bandwidth, slew-rate,
  and AGC/audio signal-path studies, but not noise, production spread,
  temperature drift, or inter-section coupling.
- Q79-1/Q79-2 use an empirical `MPS3693.lib` model constrained by sparse
  surviving data and the manual's no-signal bias points. It is not a factory
  Motorola model.
- D79-1/D79-2/D79-3 use the empirical `HP5082_3379.sub` PIN-diode model. Its
  50 V breakdown, 0.4 pF capacitance, 1.3 us lifetime, and package parasitics
  are documented; its continuous RF-resistance law is an engineering fit.
- The 80279 model regression gives nominal MPS3693 beta 55.4 and PIN-diode
  impedances of about 802 ohms, 8.22 ohms, and 0.611 ohm at 9 MHz for 10 uA,
  1 mA, and 20 mA forward bias respectively.
- With the manual's 12.1 V R rail and 13.8 V supply, the MPS3693 model gives
  Q79-1 C/B/E = 13.64/1.046/0.362 V and Q79-2 C/B/E =
  13.32/1.788/1.070 V, close to the documented 13.7/1.0/0.3 V and
  13.3/1.8/1.1 V readings.
- The schematic-native receive/no-signal fixture supplies +12=13.8 V,
  +REG=8.0 V, R=12.1 V, T=0.2 V, BFO=6.5 V, a no-filter FILT IN/FILT OUT
  jumper, the root-sheet 25 kohm AUDIO and 1 kohm S-meter loads, and a 1 TOhm
  numerical shunt. The corrected RCA lead-network wiring puts
  R79-13/C79-11/C79-12 on gate 1, C79-19/R79-16 on gate 2, and
  R79-15/R79-16/C79-15/C79-16 on the source. The 2026-08-17 ngspice-46
  operating point gives Q79-3 D/G1/S/G2 = 3.349/0.641/1.737/1.737 V, all
  within 15 percent of the documented 3.0/0.6/2.0/2.0 V. After correction of
  the surrounding IC1 wiring, all nine documented connected MC1747 pins agree
  with the manual within 2 percent; its DC prerequisite for audio and
  closed-loop AGC studies now passes. Q79-5 emitter remains a separate
  low-current model discrepancy at 0.040 V versus the documented 0.2 V.
- The completed 80279 small-signal IF study uses an alignment estimate of
  2.63 uH for L79-3 through L79-6 and `K=0.25` for T79-1 and T79-2. It peaks
  at 8.9997 MHz with 55.066 dB modeled transfer from board `IN` to Q79-3 G1,
  an 83.240 kHz -3 dB bandwidth, and loaded Q 108.1. These are simulation-fit
  results, not measured transformer values or factory gain/bandwidth data.
- The completed open-loop PIN-diode study forces equal forward current through
  D79-1, D79-2, and D79-3 with D79-5 opened. At 9 MHz the empirical model gives
  8.888 dB attenuation at 10 uA per diode, 35.705 dB at 100 uA, and 87.557 dB
  at 1 mA relative to zero current. The 12 mA point gives 132.659 dB modeled
  isolation but requires 12.85 V on the bus and is only a supply-boundary
  checkpoint. These are idealized model trends, not measured receiver AGC
  range or factory data.
- The completed product-detector transient applies 100 uV peak at 9.001 MHz
  to board `IN` and sweeps the undocumented 9.000 MHz BFO RF amplitude. With
  400 mV-peak BFO drive, Q79-3 produces 34.490 mV peak-to-peak at 1 kHz on the
  jumpered filter loop with 1.897 percent modeled THD. BFO-off and IF-off
  controls are 0.0195 and 0.307 mV peak-to-peak respectively. The transient
  gate-1 IF amplitude agrees with Simulation 2 within 0.96 percent. This is a
  functional mixing result, not a factory conversion-gain or distortion
  specification.
- The completed audio/AGC study directly drives the jumpered filter node. At
  1 kHz the model gives 97.635 V/V to `AUDIO` and 305.313 V/V to the second
  IC1 output, about 3.3 percent below the 101 and 316 resistor calculations.
  The modeled -3 dB speech band is about 139 Hz to 2.97 kHz. At 10 mV-peak
  input the 120 ms result gives 2.325 V on C79-22 and 20.8 uA in each nominal
  PIN branch; 15 mV peak gives 2.983 V and 393 uA. AUDIO remains low-distortion
  through 50 mV peak and clips strongly by 75 mV peak. These are functional
  model results, not factory audio or AGC specifications, and absolute PIN
  levels retain the Q79-5 model caveat.
- The completed split closed-loop AGC study combines the actual downstream
  audio/control circuit with the Simulation 4 detector scale and Simulation 3
  attenuation table for multi-second timing. A 1-to-100 uV peak input step is
  compressed from 40.00 dB to 24.24 dB at AUDIO. Modeled C79-22 attack is
  59.0 ms (10-90 percent) and release is 1.991 s (90-10 percent), with 22.98
  uA per PIN branch and 101.57 uA S-meter current in the strong state. A
  separate full-RF cross-check holds C79-22 at 2.325 V, produces 20.60 uA per
  branch, and reduces Q79-3 gate-1 IF by 19.09 dB through the actual
  Q79-4/Q79-5/PIN/tuned path. These are model results, not factory timing or
  compression specifications, and retain the Q79-5 caveat.
- The completed S-meter/transmit study uses that calibrated envelope while
  retaining the actual meter and T/R control circuitry. At the saved R79-20
  midpoint, modeled meter current is 3.270 uA at 10 uV, 91.424 uA at 50 uV,
  and 101.567 uA at 100 uV peak 80279 board input. At 100 uV, R79-20 positions
  0.05 through 0.95 give 60.20 through 368.68 uA while changing PIN current by
  less than 1 percent. A documented R/T step turns Q79-6 on, drops C79-22 from
  2.336 to 0.0805 V in 168 us for 90 percent reset, reduces each PIN branch
  from 22.96 uA to 6.27 nA, and removes receive meter current. These board-input
  results are not S units; factory S9 requires 50 uV at the antenna and the
  preceding receiver plus original meter movement. A separate transmit-state
  check applies 1 V to `S MTR`; D79-4's board-side anode remains at 3.01 uV
  and C79-22 at 0.0806 V, confirming modeled reverse isolation.

## Established 80289 evidence

- The manual schematic labels the complete unit `VFO S/A 80289`, the nested
  unit `PTO S/A 80278`, and the inner board `OSC CIRCUIT BD S/A 80277`.
- The PTO covers 5.0–5.5 MHz. L3 is the main permeability-tuned coil, L2
  shunts L3, and L1 is in series; L1/L2 adjustment establishes endpoints and
  linearity.
- The 14 MHz band uses the PTO directly. Other bands combine the PTO with a
  selected crystal oscillator in an MC1496 double-balanced mixer and select
  the wanted product with switched, double-tuned filters.
- Front-panel receive OFFSET and the fixed 21/28 MHz 10 kHz correction are
  distinct varactor functions.
- The documented VFO output target is at least 200 mV and may range to about
  300 mV; excess crystal injection increases unwanted mixer products.
- The current system-level transient preserves the physical oscillator
  schematics but substitutes ideal sources: 5.25 MHz at 300 mV peak on the
  Q89-5 emitter node and the selected crystal at 1 V peak with approximately
  -2.2 V Q89-3 gate bias.  On `S4_POS=1`, the modeled wanted 12.75 MHz
  component is about 194 mV peak-to-peak and total `OUT` swing is about
  230 mV peak-to-peak.  These amplitudes are behavioral calibration values,
  not measurements of oscillator terminals.

## Current 80289 magnetic-model starting values

- `spice/models/80289_vfo_magnetics.lib` preserves the documented PTO
  topology as L1 in series with L2 in parallel with the main tuning coil L3.
- Starting estimates are PTO L1=0.8 uH, L2=10 uH, L3 adjustable about
  10-16 uH; oscillator-board L4=12 uH; and T1=5.3 uH per winding with
  K=0.08.
- The L4 value is calculated from C21=360 pF and C22=100 pF at the
  5.25 MHz PTO midpoint.  The PTO and T1 values are circuit-fit estimates.
- All four RFCs are documented as 1 mH.  Their model uses an estimated
  10 ohm winding resistance and deliberately omits unknown self-capacitance.
- Proposed numeric simulation settings are C7/C10=20 pF, C8/C11=6.2 pF,
  C9/C12=17 pF, and C35=3 pF.  The first three pairs are calculated
  mid-band trimmer settings; C35 is only a small starting estimate for a
  production-selected part.

Treat all tuned-inductor values, Q, coupling, winding resistance, and
parasitic capacitance as adjustable estimates until measured on an original
assembly.

## Established 80287 evidence

- U87-1 converts the received operating-frequency signal to the 9 MHz IF;
  U87-2 converts the 9 MHz transmit signal to the operating frequency.
- The manual shows C87-5 as 150 pF, C87-14 as 100 pF, and C87-15/C87-18 as 22 pF.
- L87-3 with 150 pF calculates to 2.08 uH at 9 MHz before device, board, and
  winding capacitance; the schematic uses a rounded 2 uH starting value.
- The manual shows L87-2 as a continuous center-tapped output winding but does
  not document its inductance, resistance, coupling, or parasitics.
- `spice/models/80287_txrx_magnetics.lib` preserves that topology with two
  estimated 10 uH halves, 1 ohm per-half resistance, K=0.98, and 2 pF
  end-to-end capacitance.
- A schematic-native 12.500 MHz VFO translates a 3.499 MHz receive component
  to 9.001 MHz and a 9.001 MHz transmit component back to 3.499 MHz.
- The settled schematic-native MC1496 regression passes 33 of 40 documented
  connected-pin/mode voltages within the manual's 15 percent service tolerance.
  All U87-1 transmit points and all U87-2 points pass; U87-1 receive pins 1,
  2, 3, 4, 5, 8, and 10 fail while its collectors pass.
- The initial low-bias ngspice solution is a startup state, not the settled DC
  result. RF excitation and 500 us settling are used for the DC regression.
- Absolute gain, balance, unwanted-product suppression, and feedthrough are
  not validated against hardware.
- The present model's VFO-feedthrough nulls are R87-1 position 0.025 and
  R87-19 position 0.77. Each improves simulated VFO rejection by about 36 dB
  from midpoint without reducing the wanted product. These normalized model
  positions are not physical or factory adjustment settings.

## Established Model 245 evidence

- `literature/Model 245.pdf`: PDF page 1 gives specifications and installation;
  PDF page 2 / printed page 3-41 gives the operational check, board-pin and
  IC-pin voltages and the 14-pin top view; PDF page 3 / printed page 3-42 gives
  the board photograph and schematic. PDF page 4 is bleed-through only.
- The 540 manual shows the socket on main chassis wiring PDF page 21 / printed
  page 3-4 (pins IN, GND, +REG, CW2, -, -, CW1, with "remove blue jumper to
  install 245"), the location on PDF page 23 / printed page 3-7, and the
  FILT IN / FILT OUT routing on PDF page 32 / printed page 3-16.
- Four identical multiple-feedback bandpass stages in two uA747C duals:
  220k input, 15k + 6.8k series leg to a half-supply bias rail, 0.0022 uF to
  the output, 0.0022 uF to the inverting input, 470k feedback. The 15k/6.8k
  junctions are not connected to the non-inverting line; the drawing has no
  dots there.
- Bias rail: R4 = R6 = 15k from +12 V, C7 = 32 uF 10 V. Manual reads 6.5 V on
  all inputs and outputs with 13 V on the supply pins.
- OUT 1 (stage 1, CW-2) and OUT 4 (all stages, CW-1) are AC-coupled through
  0.1 uF with 220k / 470k pull-downs; the manual reads 0 V on them. OUT 2 and
  OUT 3 are direct op-amp outputs at 6.5 V and are unused by the 540 socket.
- Calculated: f0 = 1/(2 pi C sqrt(470k x (220k || 21.8k))) = 750 Hz;
  single-stage Q of about 2.4 (BW about 310 Hz) and four-stage BW of about
  135 Hz, against the manual's 260 Hz and 150 Hz. Stage gain 470k/(2 x 220k)
  gives about +2.3 dB over four stages, against the manual's "app. 2.5 dB".
- Inferred: R9's leading digit is illegible in the scan ("?20K"). 220k fits
  the other three stages, the 750 Hz center, and the insertion gain; 120k
  would give about 777 Hz and about 7.5 dB of gain.
- Inferred: board pin numbers 1-7 = INPUT, GND, +12V, OUT 1-4, from the
  socket order and the instruction to clip the jumper between pins 1 and 4.
- KiCad sheet pins use the 540 chassis-wiring names: IN, +REG, CW2 (board
  OUT 1), CW1 (board OUT 4). Socket pins 5 and 6 are drawn unnamed and
  unwired, so the sheet keeps the board names OUT 2 / OUT 3 with no-connect
  flags on the root sheet.
- Traced on PDF page 21: socket +REG runs about 1 mm below the driver/80280 T
  line for most of its length but has no junction with it; it ends on the
  80280 Control Board +REG pin, not T. T is a transmit-only supply, which
  would leave the receive filter unpowered.
- Traced on PDF page 21: 80279 FILT IN (shielded) -> socket IN and S1B
  positions 1 (SB-R) and 4 (SB-N); S1B position 2 (CW1) -> socket CW1;
  position 3 (CW2) -> socket CW2; position 5 (LOCK) open; S1B common
  -> 80279 FILT OUT. Root KiCad S1B pins 7-11 are positions 1-5, pin 12 the
  common. As shipped, the blue IN-CW2 jumper makes CW-2 a bypass and CW-1
  silent, matching the manual's "receive CW only in the CW-2 position".
- The 80279 sheet still contains a FILT IN-FILT OUT wire standing in for the
  no-filter case; while it exists the full-project netlist bypasses the 245.
- Open question: 80280 +REG is about 8 V, while the 245 sheet lists 13 V on
  "+12" and 6.5 V bias. In a 540 the bias rail should sit near 4 V. The 245
  sheet appears to describe the filter for TRITONs generally.
- Manual designators R1-R20, C1-C12, IC1, IC2 are prefixed `45-` in KiCad to
  remain unique against the root sheet's R1, C1, and so on.
- Simulated (fresh KiCad export, MC1747 macromodel, +REG 8 V, unloaded pins):
  centre 748-749 Hz; CW-1 +2.0 dB, 134 Hz at -3 dB, 1710 Hz at -60 dB,
  shape factor 8.6; CW-2 +0.3 dB, 313 Hz at -3 dB, 3124 Hz at -20 dB. Manual:
  150 / 1450 Hz, 7.2, 260 / 2800 Hz, app. 2.5 dB. Identical stages force a
  CW-1/CW-2 width ratio of about 0.43; the manual implies 0.58 (open).
- R45-9 = 120k would give +7.2 dB CW-1 insertion gain and +5.7 dB at pin 5
  relative to pin 4 at 750 Hz, against +2.0 dB and +0.57 dB for 220k.

## Established 80291 evidence

- PDF page 41 / printed page 3-25 is the only 80291 page: theory, schematic,
  photograph, and the resistance check. No alignment or voltage table.
- Right-hand manual pins are the input from 80287 `OUT` (S4F); left-hand pins
  go to the 80285 driver (S4E). KiCad labels: `-I` = mixer side, `-O` = driver.
- Manual T1-T4 are KiCad T91-1..T91-4 (40, 20, 15, 10 m). Unit A is the
  mixer-side winding, unit B the driver-side winding. Manual C1-C12, L1-L2, R1
  are C91-n, L91-n, R91-1.
- Documented: tuning capacitors 82/56/22/10 pF, low-pass C 1500/1500/1500/750 pF,
  R1 47 ohm; pin resistance zero (band-pass), infinite (3.5 in), 47 ohm (3.5 out).
- Calculated: 5.60, 2.08, 2.16, 2.15 uH per winding at 7.25/14.25/21.25/29.0 MHz
  with 4 pF stray. Estimated: taps, Qu 100, k 0.08, L91-1/L91-2 2.7 uH.
- VFO plan for spur frequencies: PDF page 26 / printed page 3-10.
- The passband depends strongly on the undocumented 80287 output and 80285
  input impedances; both must be low (tens to hundreds of ohms).
