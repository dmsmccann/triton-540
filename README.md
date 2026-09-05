# Ten-Tec Triton IV Model 540 reconstruction

This project recreates the Ten-Tec Triton IV Model 540 in KiCad, one original
assembly at a time. The schematics preserve the historical topology and
reference designators while adding project-local SPICE models, reproducible
simulation studies, and explicit documentation of estimated values.

## Documented assemblies

| Assembly | Function | Documentation and simulation evidence |
|---|---|---|
| 80166 | Receiver RF amplifier | [80166.md](80166.md) |
| 80289 | Internal VFO and frequency conversion | [80289.md](80289.md) |
| 80287 | Receive/transmit mixers | [80287.md](80287.md) |
| 80279 | 9 MHz IF, AGC, product detector, and audio preamplifier | [80279.md](80279.md) |
| 80274 | Audio power amplifier, transmit mute, and CW sidetone | [Schematic](80274_audio_power_amp.kicad_sch); manual pp. 3-18 and 3-19; simulation not yet implemented |

The 80287 study demonstrates conversion between a 3.499 MHz SSB spectral
component and the fixed 9.001 MHz IF in both directions. It includes settled
MC1496 service-voltage comparisons, receive/transmit product plots, and
separate sweeps of the two mixer-balance controls.

The 80279 study documents the complete IF-to-audio and AGC signal path. Its
completed work includes the receive DC operating-point comparison, estimated
two-stage 9 MHz IF response, and open-loop PIN-diode attenuation sweep;
product-detector, closed-loop timing, and S-meter studies remain explicitly
listed as future simulations.

## Simulation

The KiCad hierarchy is the circuit source of truth. Reproducible runners,
curated measurements, plots, and project-local models are under [`spice/`](spice/README.md).
Generated netlists and simulator caches are intentionally not versioned.

## Bench measurement

Measurements taken on real hardware live under [`bench/`](bench/README.md),
one directory per assembly. Simulation evidence and bench evidence are kept
apart so that a simulated result is never mistaken for a measured one.

The original Ten-Tec service manual is the primary source for this
reconstruction but is not redistributed in this repository.
