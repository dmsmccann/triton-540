# SPICE model reference

## MC1747 dual operational amplifier

`MC1747.sub` contains a five-terminal Motorola-style MC1747 op-amp core and
a project-added fourteen-pin package wrapper. The wrapper instantiates the
core twice, preserving the device's separate positive supplies and common
negative supply:

```spice
XU inv_a noninv_a off_a1 vee off_b1 noninv_b inv_b off_b2 vcc_b out_b nc out_a vcc_a off_a2 MC1747
```

Use a one-to-one physical-pin mapping in KiCad:

| Pin | Function | Pin | Function |
|---:|---|---:|---|
| 1 | Inverting input A | 8 | Offset adjust B |
| 2 | Noninverting input A | 9 | VCC B |
| 3 | Offset adjust A | 10 | Output B |
| 4 | VEE, common | 11 | NC |
| 5 | Offset adjust B | 12 | Output A |
| 6 | Noninverting input B | 13 | VCC A |
| 7 | Inverting input B | 14 | Offset adjust A |

The `triton_iv:MC1747` symbol already selects
`${KIPRJMOD}/spice/models/MC1747.sub`, subcircuit `MC1747`, with physical
pins 1 through 14 mapped one-to-one.

### Model basis and limits

The five-pin core was extracted from the local KiCad-Spice-Library file
`Models/uncategorized/spice_complete/MOTOR.LIB`, whose source tag identifies
the entry as a Motorola internally compensated MC1747 model. The same
electrical core appears as `MC1747` in the Bordodynovs `OPAMPS.LIB` and as
`MC1747_MC` in `m_opamp.lib`.

The source core models one amplifier only. The project modification renames
it `MC1747_CORE`, instantiates it once for section A and once for section B,
and adds high-value stabilization resistors to the four offset-adjust pins
and pin 11. Consequently, offset-null adjustment is not modeled. DC bias,
closed-loop gain, bandwidth, slew rate, output limiting, input bias current,
and supply loading are modeled nominally; noise, device spread, temperature
variation, and inter-section coupling are not validated.

`../validation/MC1747_validation.cir` checks both sections on separate 13.8 V
positive-supply pins. Its unity-follower regression gives 6.80002 V and
7.00002 V DC outputs, approximately 1.595 MHz closed-loop bandwidth, and
0.498 V/us large-signal slew rate under ngspice 46.

The source aggregator's README states that its GPLv3 license covers its
scripts, not the collected model files, and it does not establish the license
of this individual model. Treat `MC1747.sub` as a local simulation asset and
review or replace it before including it in a public release.

### References

- Ten-Tec, *Triton IV Model 540 Owner's Manual*, local PDF page 32 / printed
  page 3-16: the two IC-1 amplifier functions on assembly 80279.
- Same manual, local PDF page 33 / printed page 3-17: IC-1 connections and
  operating-point voltages.
- `datasheets/MC1747_MC1747C_Motorola_1976.pdf`, printed pages 3-83 through
  3-86: package pinout and electrical characteristics.

## 80279 discrete active-device models

`MPS3693.lib` is an empirical NPN model for Q79-1 and Q79-2. No factory
SPICE model was found. Its constraints are the surviving 45 V voltage
ratings, 30 mA collector-current rating, minimum gain of 40, approximately
200 MHz transition frequency, and approximately 3.5 pF collector
capacitance. `BF=60` was selected as a nominal value compatible with the
manual's approximately 1.3 mA and 5 mA emitter-current operating points.
The model is intended for 9 MHz bias and small-signal studies, not noise,
distortion, breakdown, temperature, or production-spread predictions.

`HP5082_3379.sub` is an empirical two-terminal PIN-diode model for D79-1,
D79-2, and D79-3. Its external order follows the KiCad diode symbol:

```spice
XD cathode anode HP5082_3379
```

The model uses the HP/Agilent data-sheet values of 50 V minimum breakdown,
0.4 pF maximum total capacitance at 50 V, 1.3 us typical carrier lifetime,
and typical Outline-15 package parasitics of 2.5 nH and 0.13 pF. A
low-pass-controlled behavioral resistance follows the documented
current-controlled RF resistance without following the 9 MHz carrier. Its
8 mV/current relationship gives approximately 1000 ohms at 10 uA and 8 ohms
at 1 mA; this is an engineering interpolation, not an HP compact model.

`../validation/80279_device_models_validation.cir` gives nominal ngspice 46
results of beta 55.4 for MPS3693 at 50 uA base drive. In the documented
80279 bias networks it gives Q79-1 C/B/E = 13.64/1.046/0.362 V and Q79-2
C/B/E = 13.32/1.788/1.070 V, compared with manual readings of
13.7/1.0/0.3 V and 13.3/1.8/1.1 V. The PIN-diode impedance magnitudes are
802 ohms, 8.22 ohms, and 0.611 ohm at 9 MHz for 10 uA, 1 mA, and 20 mA
forward bias respectively.

The existing `MPS6514.lib` model is assigned to Q79-4, Q79-5, and Q79-6.
The existing `40823.sub` model is assigned to Q79-3 with one-to-one physical
pin order `D, G2, G1, S`. The complete assignments are stored directly in
`80279_if_agc.kicad_sch` so KiCad exports all required includes.

### References

- Ten-Tec, *Triton IV Model 540 Owner's Manual*, local PDF pages 32-33 /
  printed pages 3-16 to 3-17: circuit functions and no-signal voltages.
- HP/Agilent, *PIN Diodes for RF Switching and Attenuating*, technical data
  5968-7182E: 5082-3379 capacitance, lifetime, breakdown, package parasitics,
  and RF-resistance behavior.

## MC1496P balanced modulator

`MC1496P.sub` is a nominal transistor-level model for the MC1496P
double-balanced mixers used as U89-1 in VFO assembly 80289 and U87-1/U87-2
in TX-RX mixer assembly 80287.
It implements the onsemi internal topology: a four-transistor upper switching
quad, a two-transistor signal stage, two emitter-degenerated current-source
transistors, and the bias diode. The bias diode is represented electrically by
a diode-connected NPN. Figure 23 shows three internal 500 ohm resistors.

The subcircuit exposes all fourteen physical package pins:

```spice
XU signal+ gain1 gain2 signal- bias output+ nc carrier+ nc carrier- nc output- nc vee MC1496P
```

Use a one-to-one physical-pin mapping in KiCad:

| Pin | Function | Pin | Function |
|---:|---|---:|---|
| 1 | Signal input + | 8 | Carrier input + |
| 2 | Gain adjust | 9 | NC |
| 3 | Gain adjust | 10 | Carrier input - |
| 4 | Signal input - | 11 | NC |
| 5 | Bias | 12 | Output - |
| 6 | Output + | 13 | NC |
| 7 | NC | 14 | VEE |

In KiCad Simulator, associate U89-1 with a **Subcircuit** model, browse to
`${KIPRJMOD}/spice/models/MC1496P.sub`, select `MC1496P`, and map physical
pins 1 through 14 one-to-one. The four NC pins are accepted by the subcircuit
but intentionally unused internally.

### Model basis and limits

- The topology and internal 500 ohm resistors are documented in onsemi
  MC1496/D Figure 23.
- The transistor beta, Early voltage, and capacitance terms are engineering
  fits to the data sheet's typical 12 uA input bias current, 40 kohm output
  resistance, 5 pF output capacitance, and published RF response. They are not
  a recovered Motorola semiconductor-process model.
- A fixed 0.2 percent mismatch in one switching transistor makes the external
  mixer-balance control produce a finite null. This is a nominal simulation
  device mismatch, not a measured value for U89-1.

The model is intended for DC bias, conversion-gain trends, carrier balance,
injection-level studies, wanted/unwanted mixing products, and loading of the
80289 output filters from 5 to 21 MHz. It is not validated for absolute noise,
unit-to-unit spread, temperature drift, exact intercept points, or carrier
feedthrough caused by physical PCB coupling.

The settled schematic-native 80287 DC regression passes 33 of the 40 connected-
pin/mode checks against the manual's stated 15 percent service tolerance. All
U87-1 transmit points and every U87-2 point pass. Seven U87-1 receive points
remain outside tolerance, while its two collector voltages pass. Because the
same model reproduces U87-2 pin 5 but cannot simultaneously reproduce the
documented U87-1 pin-5 value with the drawn R87-3 network, no global transistor
parameter was fitted to those seven points. Absolute gain, balance, and
feedthrough remain unvalidated.

`../validation/MC1496P_validation.cir` checks DC operating current and
5 MHz by 8 MHz mixer action with 3 MHz and 13 MHz differential outputs, then
repeats at a 15 MHz carrier to check 10 MHz and 20 MHz products near the top
of the 80289 operating range.

`../tools/run_mc1496_dc_regression.py` exports the complete KiCad hierarchy,
allows the 80287 bias capacitors to settle for 500 us, and compares all 40
documented U87-1/U87-2 operating points. Add `--strict` when a nonzero exit is
desired for any out-of-tolerance manual point.

### References

- Ten-Tec, *Triton IV Model 540 Owner's Manual*, local PDF page 29 / printed
  page 3-13: U89-1 circuit connections and external bias network.
- Same manual, local PDF pages 27-28 / printed pages 3-11 to 3-12:
  mixer-balance, crystal-injection, and output-filter alignment.
- onsemi, [MC1496/MC1496B data sheet](https://www.onsemi.com/download/data-sheet/pdf/mc1496-d.pdf):
  pinout, internal circuit, operating equations, test circuits, impedance,
  frequency response, and mixer applications.

## TX-RX mixer 80287 magnetics

`80287_txrx_magnetics.lib` contains `TXRX_L2_CT`, the simulation starting
model for the center-tapped transmit-output transformer L87-2. It uses two
10 uH halves, 1 ohm winding resistance in each half, coupling `K=0.98`, and
2 pF end-to-end capacitance.

The Ten-Tec manual shows the winding topology but supplies none of those
quantities. They are explicit estimates chosen to make the schematic runnable,
not recovered factory specifications. L87-2 needs measurement or original
winding information before the model can support absolute output-level or
balance claims.

The receive load L87-3 is represented directly in the schematic as 2 uH. This
is the rounded result of resonating the documented C87-5 value of 150 pF at
9 MHz (2.08 uH before transistor, board, and winding capacitance). L87-1 is a
1 uH inferred starting value and likewise remains unverified.

## RCA 40823 dual-gate MOSFET

`40823.sub` is an empirical four-terminal macro-model for the RCA 40823
protected dual-gate N-channel depletion MOSFET used as Q66-1 in the Triton 540
RF amplifier.

The subcircuit call is:

```spice
XQ drain gate2 gate1 source RCA40823
```

The custom project symbol is drawn using pin positions that do not correspond
to its displayed pin names.  For the existing `80166_rf_amp.kicad_sch`
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

## Ganged S89-1 four-pole, five-position VFO bandswitch

`SW_Rotary_4x5.sub` models the four mechanically linked wafers of S89-1 as
one 24-pin subcircuit.  Its pins map one-to-one to the project-local symbol:

| Model pins | VFO switch terminals |
|---:|---|
| 1-5, 6 | A1-A5, A common |
| 7-11, 12 | B1-B5, B common |
| 13-17, 18 | C1-C5, C common |
| 19-23, 24 | D1-D5, D common |

All four wafers use the same `POS` parameter.  The S89-1 schematic instance
passes `POS={S4_POS}`, so the root-sheet directive that controls S4A and S4B
also controls the VFO bandswitch:

| `S4_POS` | Amateur band | Nominal band frequency |
|---:|---:|---:|
| 1 | 80 m | 3.5 MHz |
| 2 | 40 m | 7 MHz |
| 3 | 20 m | 14 MHz |
| 4 | 15 m | 21 MHz |
| 5 | 10 m | 28 MHz |

The model uses the same 20 milliohm selected-contact resistance and 1 teraohm
unselected-contact resistance as the S4 model.  It does not model contact
parasitics, break-before-make motion, or contact bounce.

`../validation/SW_Rotary_4x5_validation.cir` checks every wafer in all five
positions.

## S5 four-position ten-meter segment switch

`SW_Rotary_1x4.sub` models the top-sheet S5 SP4T selector. Model pins 1–4
map one-to-one to the four crystal contacts and pin 5 is the common/wiper
connected to the VFO sheet's `S5` input. The schematic instance passes:

```spice
POS={S5_POS}
```

The root-sheet directive defaults to `.param S5_POS=1`. Positions 1–4 select
Y1 through Y4:

| `S5_POS` | Dial segment | Ideal source |
|---:|:--|--:|
| 1 | 28.0–28.5 MHz | Y1, 13.99 MHz |
| 2 | 28.5–29.0 MHz | Y2, 14.49 MHz |
| 3 | 29.0–29.5 MHz | Y3, 14.99 MHz |
| 4 | 29.5–30.0 MHz | Y4, 15.49 MHz |

The four frequencies are the documented 10 kHz-low crystal plan combined
with the band-dependent PTO correction. Y1–Y4 are functional ideal sine
sources with 2.2 V DC bias and 1 V peak amplitude, matching the ideal-source
convention used for Y89-1 through Y89-3. They do not model crystal startup,
motional parameters, loading, or production tolerance.

The switch uses 20 milliohms for the selected contact and 1 teraohm for each
unselected contact. These are stable simulation defaults, not measurements.
`../validation/SW_Rotary_1x4_validation.cir` checks all four positions.

## Fixed-position potentiometer

`Potentiometer_Position.sub` represents a three-terminal linear
potentiometer at a fixed simulation setting. Its model pins are terminal 1,
wiper 2, and terminal 3. The instance parameters are:

```spice
R=1k POS=0.5
```

`POS=0` places the wiper at terminal 1 and `POS=1` places it at terminal 3.
A 1 milliohm minimum segment resistance avoids a zero-ohm branch at either
endpoint.

The 80289 schematic uses this model only for the two alignment controls.
R89-2 has `POS={VFO_R2_POS}`, with the saved
`.param VFO_R2_POS=0.760`; R89-27 has `POS={VFO_R27_POS}`, with the saved
`.param VFO_R27_POS=0.100`. The dedicated mixer-balance sweep places the
R89-2 minimum at 0.760. The crystal-injection sweep retains R89-27 at 0.100
as an inferred compromise, but the simplified model does not reach the
manual's 200 mV minimum throughout the T1 range. These are simulation-aligned
estimates obtained in the manual's adjustment order, not measured production
settings. The ordinary schematic resistance and three-terminal topology are
preserved.

`../validation/Potentiometer_Position_validation.cir` checks the wiper at
positions 0.25, 0.50, and 0.75.

## MV2201 varactors

`MV2201.lib` contains the junction-capacitance diode model used by D89-2 and
D89-3 in the 80289 PTO.  The electrical parameters were imported from
`Models/Diode/DIODE2.lib` in the local KiCad-SPICE-Library:

```spice
.model MV2201 D(Is=1.365p Rs=1 Cjo=14.93p M=.4261 Vj=.75 Isr=16.02p Nr=2 Bv=25 Ibv=10u)
```

The source library's `Vpk`, `mfg`, and `type` fields are metadata not
recognized as ngspice diode parameters; the project-local file records them
in comments but omits them from the active model statement.

Both schematic symbols retain the KiCad pin mapping `1=K 2=A`.  KiCad
therefore emits the SPICE diode nodes in anode-cathode order.  The model
captures nominal reverse-bias capacitance and series resistance, but its
provenance as an original Motorola/OnSemi factory model has not been
established.  Do not treat it as evidence of production spread, temperature
drift, package parasitics, or measured behavior of the installed parts.

`../validation/MV2201_validation.cir` checks the nominal small-signal
capacitance at 0, 2, 8, and 12 V reverse bias.

## 2N5486 N-channel JFETs

`2N5486.lib` contains the model used by Q89-1 and Q89-3 in VFO assembly
80289.  Its parameters were imported from the `2N5486/PLP` entry in the
local KiCad-SPICE-Library's `spice_complete/phil_fet.lib`; the model name was
changed to `2N5486` for portable KiCad/ngspice use, without changing its
electrical parameters.

The plain `2N5486` and `2N5486X` entries elsewhere in that library use
`BETA=4m` and `VTO=-4 V`, implying a much higher zero-bias drain current.
The selected Philips-family entry uses `BETA=832.666u` and `VTO=-3.847 V`,
giving a nominal IDSS near 12 mA, consistent with the 2N5486 device family
and the VFO's documented Q89-1 bias.

Both KiCad symbols use `Device:Q_NJFET_DSG`:

| KiCad pin | Function | SPICE JFET node |
|---:|---|---|
| 1 | Drain | D |
| 2 | Source | S |
| 3 | Gate | G |

The model is useful for nominal DC bias, oscillator startup, buffer loading,
and RF gain trends.  Its provenance as an original factory model has not
been independently established, and it does not represent the broad
production spread normally associated with discrete JFET IDSS and cutoff
voltage.

`../validation/2N5486_validation.cir` checks IDSS, cutoff trend, and a
source-follower approximation of the manual's Q89-1 voltage data.

The onsemi 2N5486 data sheet confirms physical pins 1=D, 2=S, 3=G,
`IDSS=8-20 mA` at `VDS=15 V`, and `VGS(off)=-2` to `-6 V`:
<https://www.onsemi.com/download/data-sheet/pdf/2n5486-d.pdf>.

## MPS6514 NPN transistors

`MPS6514.lib` contains the model used by Q89-2 and Q89-4 in VFO assembly
80289.  It was imported from the local KiCad-SPICE-Library's
`spice_complete/fairch.lib`, which identifies it as a Fairchild TO-92 model
created on 1988-09-08.

The model includes Early voltage, high-current beta rolloff, base and
collector resistance, junction capacitances, and forward/reverse transit
times.  Both KiCad instances retain the stock `Q_NPN_EBC` mapping:

| KiCad pin | Function | SPICE BJT node |
|---:|---|---|
| 1 | Emitter | E |
| 2 | Base | B |
| 3 | Collector | C |

The historical Fairchild data gives MPS6514 DC gain of 150-300 at 2 mA,
minimum gain 90 at 100 mA, 25 V minimum collector-emitter breakdown, and
3.5 pF maximum output capacitance:
<https://media.digikey.com/pdf/Data%20Sheets/Fairchild%20PDFs/NPN%2C%20PNP%20Amplifiers.pdf>.
The model's internal `BF=522` is not the same as terminal hFE at every
collector current.

The model is suitable for nominal bias, follower loading, and RF transient
work.  It does not establish installed-device gain, temperature behavior,
or production spread.

`../validation/MPS6514_validation.cir` checks the model against the manual's
Q89-2 and Q89-4 collector/base/emitter voltage data.

## MPS6512 PTO transistor

`MPS6512.lib` contains the nominal NPN model used by Q89-5 in VFO assembly
80289.  No usable MPS6512 model was found in the installed
KiCad-Spice-Library or in the web search performed for this work, so this
model was developed from the original Fairchild data sheet:
<https://bitsavers.trailing-edge.com/components/fairchild/_dataBooks/1971_Fairchild_TO92_Plastic_Transistors.pdf>.

The Fairchild data distinguishes the adjacent gain selections: MPS6512 is
specified for `hFE=50-100` at `IC=2 mA, VCE=10 V`; MPS6513 is the
`hFE=90-180` part.  MPS6512 also has `VCEO=30 V`, `hFE>=30` at 100 mA,
`Cob<=3.5 pF`, and `fT>=250 MHz` at 2 mA.  The model uses a nominal gain
near the middle of the 2 mA bin, high-current rolloff, 3.1 pF
collector-junction capacitance, and an estimated transit time chosen to
retain ample gain at the PTO frequency.

Q89-5 retains the stock `Q_NPN_EBC` mapping:

| KiCad pin | Function | SPICE BJT node |
|---:|---|---|
| 1 | Emitter | E |
| 2 | Base | B |
| 3 | Collector | C |

This model is intended to reproduce bias, oscillator startup, and loading
well enough to study the radio signal path.  It is not a fitted production
model and should not be used to predict noise, temperature drift,
breakdown, device spread, or exact oscillator amplitude.

`../validation/MPS6512_validation.cir` checks the nominal current gain and
the DC portion of Q89-5's bias network.  The manual voltage table lists
Q89-5 collector/base/emitter as 8.0/2.2/2.3 V (PDF page 28, printed page
3-12); the emitter-above-base reading is not a physically consistent NPN
DC junction voltage, so the model is not forced to match that datum.

## 1N4154 crystal-oscillator clamp diode

`1N4154.lib` contains the model used by D89-1 in VFO assembly 80289.  It
was imported from the local KiCad-Spice-Library's
`spice_complete/DIODE.LIB`, where the entry is identified as a Unitrode
35 V, 0.20 A, 2 ns silicon switching-diode model dated 1990-07-01.  The
source model name `DN4154` was changed to `1N4154`; its electrical
parameters were preserved.

D89-1 is connected with its anode at Q89-3's gate and cathode at ground.
It therefore clamps the positive gate excursion of the selected crystal
oscillator.  The model includes forward conduction, series resistance,
reverse leakage and breakdown, 4 pF zero-bias junction capacitance, and
2.88 ns transit time.  This is sufficient for oscillator startup and
waveform-limiting studies; it is not evidence of the installed diode's
exact leakage, capacitance, or switching-time distribution.

The stock KiCad diode symbol maps pin 1 to cathode and pin 2 to anode.
KiCad consequently emits the SPICE nodes in the required anode-cathode
order.

`../validation/1N4154_validation.cir` checks light-current forward clamp
voltages and reverse-biased junction capacitance.

## VFO 80289 magnetics

`80289_vfo_magnetics.lib` supplies four parameterized starting models:

| Model | Physical parts | Default starting values |
|---|---|---|
| `80278_PTO_COILS` | PTO L1, L2, L3 | 0.8 uH + (10 uH || 13 uH) |
| `80277_L4` | Oscillator-board L4 | 12 uH, Q=60, 2 pF parasitic |
| `80289_T1` | Coupled output-filter windings | 5.221 uH : 4.567 uH, K=0.2463 |
| `80289_RFC_1MH` | Four documented RF chokes | 1 mH, estimated 10 ohm DCR |

The manual documents the topology but not the tuned inductances, winding
resistance, Q, coupling, or parasitic capacitance.  The defaults are
calculated and inferred starting values, not Ten-Tec specifications.

For the PTO, PDF page 26 / printed page 3-10 states that L3 is the main
permeability-tuned coil, L2 shunts L3, and L1 is in series.  With about
140-150 pF effective tank capacitance from the surrounding circuit,
L1=0.8 uH, L2=10 uH, and an L3 sweep of roughly 10-16 uH provide an
appropriate 5.0-5.5 MHz starting range.  L1 and L2 remain parameters so
the manual endpoint/linearity alignment can be reproduced.

L4 is calculated from its documented 360 pF and 100 pF shunt capacitors.
Their 78.3 pF series equivalent requires about 11.7 uH at 5.25 MHz, rounded
to 12 uH.

The T1 estimate follows the alignment and switched topology on PDF pages
27 and 29 / printed pages 3-11 and 3-13. On 10 meters no trimmer pair is
selected. A loaded AC alignment of a fresh KiCad netlist gives 5.221 uH and
4.567 uH for the independently slug-tuned windings with K=0.2463. The fitted
trimmer settings are C7=25.73 pF, C10=20.35 pF, C8=6.697 pF, C11=7.050 pF,
C9=31.28 pF, and C12=13.93 pF. All six are within the documented 5–60 pF
range. The resulting three trimmer-selected responses are symmetrical and
the T1 path has a 0.535 dB center dip, consistent with the manual's
description of an overcoupled, shallow double-peaked response. These are
simulation-aligned estimates, not measured inductances, trimmer settings, or
a factory coupling coefficient.

C89-35 is documented only as selected in production.  A 3 pF starting
estimate is used so the netlist is numeric while adding only a small
correction to the PTO tank.  It should be swept or fitted during PTO
linearity work rather than treated as a factory value.

The four RFC values are explicitly marked 1 mH on the schematic.  Their
10 ohm winding resistance is estimated.  The default model intentionally
omits parallel capacitance because the original construction and
self-resonant frequency are unknown.

`../validation/80289_vfo_magnetics_validation.cir` checks the estimated
PTO endpoint resonances, L4 network, T1 transfer/syntax, and RFC impedance.
Its simple source and load are not the complete VFO loading, so study 4's
fresh-netlist AC response is the alignment evidence for T1 and the trimmers.

### System-level VFO transient setup

The complete-radio transient intentionally uses behavioral sources for the
two undocumented oscillators rather than claiming that the estimated PTO and
crystal networks reproduce startup:

- Q89-5 remains drawn and retains its validated MPS6512 model, but its
  schematic instance is excluded from the system simulation.  The root-sheet
  directive injects a 5.25 MHz, 300 mV-peak source at the Q89-5 emitter node
  with a 1.7 V DC offset.
- Y89-1, Y89-2, and Y89-3 act as ideal 7.5, 11, and 6.99 MHz sources.  Their
  1 V-peak amplitude is a behavioral calibration and their source polarity
  establishes the manual's approximately -2.2 V Q89-3 gate bias.
- `.options rshunt=1e12` supplies negligible DC paths for capacitively isolated
  nodes so ngspice can calculate a stable operating point.

With `S4_POS=1`, the saved 5.25 MHz PTO and 7.5 MHz crystal sources produce a
12.75 MHz wanted component of about 42.5 mV peak-to-peak into the schematic's
50 ohm load, or about 68.7 mV peak-to-peak with a 1 Mohm instrument load.
The model demonstrates frequency conversion and selection but does not match
the manual's absolute 200–300 mV alignment range on every band. It therefore
does not validate oscillator amplitude, phase noise, startup margin, pulling,
transformer loss/turns ratio, or production output level.
