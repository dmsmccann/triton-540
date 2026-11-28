# Ten-Tec Triton IV Model 540 reconstruction

This project recreates the Ten-Tec Triton IV Model 540 in KiCad, one original
assembly at a time. It preserves the factory circuit topology and reference
designators and identifies estimated values and open questions in the assembly
documentation.

Open [`triton_540.kicad_pro`](triton_540.kicad_pro) in KiCad and start with
the [main schematic](triton_540.kicad_sch).

## Assembly index

| Assembly | Function | Board documentation and simulation | Bench |
|---|---|---|---|
| 80166 | Receiver RF amplifier | [Board](80166.md) · [Studies](spice/studies/80166/) | [Bench](bench/80166/README.md) |
| 80274 | Audio power amplifier, transmit mute, and CW sidetone | [Study](spice/studies/80274/README.md) | [Bench](bench/80274/README.md) |
| 80279 | 9 MHz IF amplifier, AGC, product detector, and audio preamplifier | [Board](80279.md) · [Studies](spice/studies/80279/README.md) | — |
| 80280 | Receive/transmit switching, CW driver delay, frequency offset, and regulated supply | [Board](80280.md) · [Study](spice/studies/80280/operation/README.md) | [Bench](bench/80280/README.md) |
| 80282 | SSB generator, carrier oscillator, and 9 MHz crystal filter | [Board](80282.md) · [Study](spice/studies/80282/operation/README.md) | [Bench](bench/80282/README.md) |
| 80285 | Low-level transmit driver, gain control, and CW bias sequencing | [Board](80285.md) · [Study](spice/studies/80285/operation/README.md) | [Bench](bench/80285/README.md) |
| 80287 | Receive and transmit mixers | [Board](80287.md) · [Studies](spice/studies/80287/) | — |
| 80289 | Internal VFO and frequency conversion | [Board](80289.md) · [Studies](spice/studies/80289/) | — |
| 80291 | Transmit band-pass and 80 m low-pass filters | [Board](80291.md) · [Study](spice/studies/80291/operation/README.md) | [Bench](bench/80291/README.md) |
| 80308 | Crystal calibrator with 25 kHz and 100 kHz markers | [Board](80308.md) · [Study](spice/studies/80308/README.md) | [Bench](bench/80308/README.md) |
| 245 | Optional 750 Hz audio CW filter | [Board](245.md) · [Study](spice/studies/245/operation/README.md) | [Bench](bench/245/README.md) |
| 249 | Optional 9 MHz IF noise blanker | [Board](249.md) · [Study](spice/studies/249/README.md) | [Bench](bench/249/README.md) |

## Simulation

The [SPICE directory](spice/README.md) contains reproducible runners, local
models, and retained simulation data and plots. Generated netlists and
simulator caches are excluded from version control.

The [80279 IF and AGC board](80279.md) has results for all seven planned
board-level studies, including product detection, closed-loop AGC timing,
and S-meter adjustment. Factory S9 calibration still needs whole-receiver
evidence.

The [80280 control-board study](80280.md) uses a fixture based on the factory
drawing while the KiCad sheet remains incomplete. The timing of the delayed
transmit feed with the 80281 relay branch connected still needs hardware
verification. That feed controls the first stage of the [80285 driver](80285.md).

## Bench measurement

The [bench directory](bench/README.md) holds proposed procedures and captured
hardware records by assembly. The [80282 whole-receiver sweep](bench/80282/README.md)
was inconclusive as a measurement of the crystal-filter response. The isolated
board sweep is still proposed.

## Reference material

The Ten-Tec Model 540 owner’s manual, including its service section, is the
primary reconstruction source. Board documents cite both PDF and printed
page numbers. Component references are indexed in the
[datasheet archive](datasheets/README.md).
