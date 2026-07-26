# SPICE model reference

## RCA 40823 dual-gate MOSFET

`40823.sub` is an empirical four-terminal macro-model for the RCA 40823
protected dual-gate N-channel depletion MOSFET used as Q66-1 in the Triton 540
RF amplifier.

The subcircuit call is:

```spice
XQ drain gate2 gate1 source RCA40823
```

The custom project symbol is drawn using pin positions that do not correspond
to its displayed pin names.  For the existing `RF_Amp_80166.kicad_sch`
connections, map the symbol pins to the subcircuit as follows:

| KiCad symbol pin | Circuit terminal | Subcircuit node |
|---:|---|---:|
| 1 | Drain | 1 |
| 3 | Gate 2 / DEFEAT bias | 2 |
| 4 | Gate 1 / tuned-input tap | 3 |
| 2 | Source / R6-C5 | 4 |

In KiCad Simulator, select Q66-1, choose a **Subcircuit** model, browse to
`${KIPRJMOD}/spice/models/40823.sub`, select `RCA40823`, and use the mapping
`1=1 2=4 3=2 4=3` already stored on Q66-1.  This produces the subcircuit
order drain, gate 2, gate 1, source.

### Model basis and limits

No RCA factory SPICE model was found. The DC and capacitance targets are based
on published 3N204/NTE222 data, a documented close replacement for the 40823:
6-30 mA IDSS, 10-22 mS forward transfer admittance, 3.3 pF typical input
capacitance, 0.005-0.03 pF reverse transfer capacitance, and 1.4 pF typical
output capacitance at the stated test biases.

This nominal model is intended for bias checks, gain-control trends, and
small-signal work across the Triton's 2-30 MHz receiver range. It is not
validated for noise figure, strong-signal IMD, temperature extremes,
manufacturing spread, or VHF/UHF S-parameters. Measurements from an original
40823 would be required to fit those behaviors.

`../validation/40823_validation.cir` provides standalone ngspice DC transfer
sweeps.

### References

- Ten-Tec, *Triton IV Model 540 Owner's Manual*, local PDF page 25 / printed
  page 3-9: Q1 identity, D/G2/G1/S pin order, and receive/transmit voltages.
- NTE Electronics, [NTE222 datasheet](https://www.tme.eu/Document/55128e117c9002a9dd7c0a2ab56da1a3/nte222.pdf):
  DC limits, forward transfer admittance, capacitances, and protected-gate
  characteristics.
- Motorola, [3N204/3N205 data](https://www.tvsat.com.pl/pdf/3/3n204-5_mot.pdf):
  depletion-mode topology and matching DC/RF characteristic limits.

## RF-amplifier magnetics

`80166_rf_magnetics.lib` supplies three parameterized ngspice
subcircuits:

| Model | Pins | Default starting values |
|---|---|---|
| `80166_L1` | band end, RF ground, antenna tap, G1 tap | 2.2 uH full winding, 6 pF parasitic |
| `80166_L2` | DC end, band end, output tap, drain tap | 2.2 uH full winding, 6 pF parasitic |
| `80166_T1_9MHZ` | primary A/B, secondary A/B | 0.35 uH : 12.5 uH, K=0.35 |

L1 and L2 are both modeled as strongly coupled series sections, not as
isolated transformer windings.  This preserves their continuous
double-tapped-winding topology while allowing every schematic tap to be
connected.

The L1/L2 `LT` parameter is the full-winding value at the current RESONATE
control position.  Use 2.2 uH as a nominal starting point and sweep about
1.7-3.3 uH.  The T1 defaults resonate near 9 MHz when the external C7 is about
20 pF; its 5 pF default `CPS` parameter represents estimated secondary,
wiring, and socket capacitance.

Example explicit instances are:

```spice
X_L1 band_end 0 ant_tap g1_tap 80166_L1 params: LT=2.2u
X_L2 dc_end band_end out_tap drain_tap 80166_L2 params: LT=2.2u
X_T1 primary_a primary_b secondary_a secondary_b 80166_T1_9MHZ
```

In KiCad Simulator, associate each custom symbol with a **Subcircuit** model,
browse to `${KIPRJMOD}/spice/models/80166_rf_magnetics.lib`, select the matching
subcircuit, and use a 1:1 model-pin mapping:

| Reference | KiCad/model pin 1 | Pin 2 | Pin 3 | Pin 4 |
|---|---|---|---|---|
| L66-1 / L1 | band/S4A | RF ground | antenna/T1 tap | C2/G1 tap |
| L66-2 / L2 | DC/C6 end | band/S4B | OUT tap | drain/gimmick tap |
| T66-1 / T1 | primary A | primary B | secondary A | secondary B |

### Evidence and limitations

- Ten-Tec, *Triton IV Model 540 Owner's Manual*, local PDF page 24 / printed
  page 3-8: L1/L2 slug tuning, mechanical ganging, and T1/C7 trap function.
- Same manual, local PDF page 25 / printed page 3-9: winding and tap topology.
- Same manual, local PDF page 21 / printed page 3-4: L1 band capacitors of
  620, 220, 56, 22, and 10 pF and five 5-60 pF L2 trimmers.

The manual does not document inductance, turns, tap ratios, coupling, Q, or
parasitic capacitance.  The model defaults are calculated/inferred starting
values, not Ten-Tec specifications.  Refine `LT`, tap fractions, `KTRAP`,
`QP`/`QS`, and parasitics from an original assembly or a measured response.
`../validation/80166_rf_magnetics_validation.cir` is a standalone AC fixture
for syntax and trap-response checks. The complete manual-alignment study is
documented in `../studies/80166/manual-alignment/`.

## Ganged S4A/S4B five-position rotary switches

`SW_Rotary_1x5.sub` is a parameter-selected SP5T model used by both the S4A
and S4B bandswitch wafers.  Each instance has the following pin order:

| Model pin | Switch terminal |
|---:|---|
| 1-5 | Five stationary contacts |
| 6 | Common/wiper |

The model uses a 20 milliohm resistance for the selected contact and 1 teraohm
for each unselected contact.  These are stable simulation defaults, not
measurements of the original switch.  Contact capacitance, inductance,
break-before-make motion, and contact bounce are not modeled.

In KiCad, associate both wafers with a **Subcircuit** model, browse to
`${KIPRJMOD}/spice/models/SW_Rotary_1x5.sub`, select `SW_ROTARY_1X5`, and map pins
1 through 6 one-to-one.  Both model instances use the same parameter:

```spice
POS={S4_POS}
```

The top-sheet SPICE directive is:

```spice
.param S4_POS=1
```

Change the integer from 1 through 5 to select a contact, then rerun the
simulation.  Because S4A and S4B reference the same parameter, both wafers
move together.  The present S4A drawing maps the switch contacts as:

| `S4_POS` | Band label | Capacitor |
|---:|---:|---:|
| 1 | 3.5 MHz | 620 pF |
| 2 | 7 MHz | 220 pF |
| 3 | 14 MHz | 56 pF |
| 4 | 21 MHz | 22 pF |
| 5 | 28 MHz | 10 pF |

The S4B output networks use C19, C17, C16, C15, and the C13-C14 series pair.
Their fitted simulation values and the distinction between documented
trimmer range and inferred parasitics are recorded in the manual-alignment
study rather than in this model description.

`../validation/SW_Rotary_1x5_validation.cir` instantiates the model in all
five positions and checks that only the selected throw conducts.
