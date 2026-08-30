# 80166 rf amplifier — L1/L2 tracking check on 80 m

Swept-frequency measurement of the receiver rf amplifier in the Ten-Tec Triton IV
Model 540, using a Siglent SDG1032X function generator and an SDS1202X-E
oscilloscope under Python control over LAN.

The point of the measurement is the one the factory alignment cares about: **do L1
and L2 peak at the same frequency as the RESONATE rack moves across 80 m?** The
manual sets tracking on this band only (p. 3-8, PDF p. 24) — the 3.5 MHz trimmer
and the L2 slug are the two adjustments, and the higher bands get trimmer-only
touch-ups afterwards with "no further adjustment of L2 necessary".

## How the two coils are separated

L1 (input) and L2 (output) sit either side of Q1, so a single sweep from the
antenna jack to the stage output shows the product L1 × Q1 × L2, not the two peaks
individually. The manual's own alignment trick splits them: the `.01 µF` clipped
from the band's trimmer terminal to chassis shorts the trimmer that sits **across
L2**, swamping the output tank.

| Run | `.01 µF` on the 3.5 MHz trimmer terminal | Curve shows |
|---|---|---|
| `l1-only` | fitted | L1 alone |
| `composite` | removed | L1 × Q1 × L2 |

On 3.5 MHz that trimmer is **C19**; the L1 side of the stage carries the fixed
620 pF C12 instead. The split — fixed capacitors across L1, adjustable trimmers
across L2 — is what makes this work, and is set out per band in
[`../../80166.md`](../../80166.md).

Overlay the two and the offset between their peaks is the tracking error.

> The manual writes this cap as ".01 mF". In 1978 US usage `mF`/`mfd` means
> **microfarad**; it is 0.01 µF, not a typo.

## Instruments

| Instrument | Address | Role |
|---|---|---|
| Siglent SDG1032X | `192.168.1.158` | stimulus, CH1 output |
| Siglent SDS1202X-E | `192.168.1.157` | CH1 = drive reference, CH2 = stage output |

Control is SCPI over VXI-11 via `pyvisa` + `pyvisa-py`, so no NI-VISA install is
needed:

```powershell
python -m pip install pyvisa pyvisa-py matplotlib
```

If VXI-11 gives trouble, `--transport socket` falls back to raw TCP
(scope 5025, generator 5024).

## Connections

Generator and scope CH1 both land on the antenna jack — that single node is where
the drive has to be measured. A BNC tee is the tidy way to do it, but tapping the
jack at two physical points works just as well at 3.5 MHz and needs no tee:

```text
  SDG1032X CH1 ──clip leads── SO-239 centre solder lug   (inside the rear apron)
                 (short, run together, ground clip to
                  chassis right at the jack)

  scope CH1 ──short coax──── 540 ANTENNA jack (SO-239)   1x direct, no probe

  scope CH2 ── x10 probe ── 80166 OUT pin                ground clip to nearest
                            (or 80287 "Rx In")           chassis point, short lead
```

- **Measure the drive, don't assume it.** The receiver input is not a flat 50 Ω
  across the sweep, so CH1 has to see the voltage that actually reaches the jack.
  That ratio is what makes the result a true transfer function.
- **Clip leads are fine here.** A few inches is about 100 nH, roughly 2 Ω at
  3.5 MHz against a 50 Ω source. Do not carry this arrangement up to 28 MHz.
- **Keep the CH1 coax short.** It is an unterminated stub into the scope's 1 MΩ
  input, so it hangs its own capacitance across the antenna input — RG-58 is
  about 100 pF/m. See the loading note below.
- **CH1 is a direct coax feed**, so run the script with `--ch1-attn 1` (the
  default). CH2 uses a ×10 probe, `--ch2-attn 10` (also the default). A ×10 probe
  on CH1 would load less but divides the 10 mVpp reference down to two divisions
  on screen; the direct feed gives a much cleaner reference and is the better
  trade.
- **Do not disturb the hookup between the two sweeps.** Same cable, same clip
  positions, same routing for `l1-only` and `composite`.
- **CH2 pickup point.** The 80166 `OUT` pin goes to `S4B` and on to the TX-RX
  mixer. The `Rx In` pin on the 80287 plug-in socket is the same net and is
  usually easier to reach. Access to the rf amp itself is on the RESONATE
  subchassis with the rack plate off (Figure 1, p. 3-6).
- The 9 MHz trap T1/C7 is in the input path but is irrelevant at 3.5–4.0 MHz.

### Transceiver settings

| Control | Setting |
|---|---|
| Antenna | **disconnected** — the generator is on that jack |
| T/R-REC switch | **T/R** |
| BAND | 3.5 MHz |
| MODE | SB-N, receive, PTT open, key up |
| RF GAIN | **fully clockwise** (this is the supply to the stage) |
| CALIBRATE | **OFF** — the calibrator's TTL gate pulls DEFEAT low and drops stage gain ~25 dB |
| Blanker | off |
| RESONATE | set as described in the run order below, then **do not touch it** for the rest of that pair of sweeps |

> **Do not transmit.** The generator is connected to the antenna jack; keying the
> transmitter will destroy the SDG output stage. Keep the unit in receive
> throughout, key unplugged, mic unplugged.

## Run order

The RESONATE position is part of the measurement — L1 and L2 are ganged to the
same rack, so the sweep only tells you about tracking at the rack position you
left it in. Take both sweeps of a pair without moving RESONATE.

1. Clip the `.01 µF` from the 3.5 MHz trimmer terminal — C19, on the small
   trimmer board beneath the amplifier board, Figure 2, p. 3-7 — to chassis.
2. Set RESONATE for peak response at 3.5 MHz. Easiest way is to run a quick
   coarse sweep and adjust until the peak lands on 3.5 MHz:

   ```powershell
   python bode_80166.py --label l1-only --points 61 --note "RESONATE set for 3.5 MHz peak"
   ```

3. When the peak is on 3.5 MHz, take the reference sweep at full resolution:

   ```powershell
   python bode_80166.py --label l1-only --note "RESONATE at 3.5 MHz peak, .01uF fitted"
   ```

4. Remove the `.01 µF`. **Leave RESONATE alone.** Take the composite sweep:

   ```powershell
   python bode_80166.py --label composite --note "RESONATE unchanged, .01uF removed"
   ```

5. Overlay them:

   ```powershell
   python plot_bode.py data/80166-80m-l1-only-*.csv data/80166-80m-composite-*.csv
   ```

If the composite peak is off 3.5 MHz, adjust the **3.5 MHz trimmer C19** and repeat
step 4. The 4.0 MHz end of the tracking is then set with the **L2 slug** — repeat
the whole pair with RESONATE peaked at 4.0 MHz instead, and adjust the slug rather
than the trimmer. Iterate the two ends as the manual's step 6 says, since each
interacts with the other.

## Reading the result

- **Tracking well** — the composite peak sits on the L1 peak, the composite curve
  is a single symmetric hump, and its peak gain is the highest you can obtain by
  touching the trimmer.
- **Mistracked** — the composite peak is offset from L1's, or the curve is
  broad/flat-topped/double-humped, and peak gain is down. The sign of the offset
  tells you which way to move the trimmer or slug.

`plot_bode.py` reports peak frequency, −3 dB bandwidth, loaded Q, the gain at each
alignment point, and the peak offset between the two curves.

## Measurement notes and limits

- **Drive level.** Default is 10 mVpp, which is ~60 dB above what this front end
  normally sees, chosen so the output clears the scope's noise floor. The script
  runs a linearity check first: it measures gain at full and half drive and warns
  if they differ by more than 0.5 dB, which means Q1 is compressing and the curve
  shape is lying. Reduce `--amplitude` until it passes.
- **Probe loading.** A ×10 probe adds roughly 10–15 pF at the output node. On 80 m
  that is small against the several hundred pF resonating L2, so the shift is
  tolerable — this is exactly why the check is worth doing on this band and not on
  28 MHz, where the same 10 pF would dominate. Confirm the final peak with the
  manual's audio-AC-meter method if you want the probe out of circuit.
- **Dynamic range.** At the scope's most sensitive setting the usable range is
  roughly 30–35 dB below the peak before the skirts sink into the noise. The
  script records the CH2 noise floor with the generator output off in the CSV
  header so you can see where the data stops being meaningful.
- **Amplitude only.** Phase is not recorded. Tracking is an amplitude question and
  leaving phase out removes a large source of measurement fragility.
- The scope's 20 MHz bandwidth limit is enabled by default to cut noise;
  `--no-bwl` turns it off.

## Files

| File | Purpose |
|---|---|
| `bode_80166.py` | runs one sweep, writes a timestamped CSV to `data/` |
| `plot_bode.py` | overlays CSVs, writes a PNG to `plots/`, prints the summary table |
| `data/` | captured sweeps, one CSV per run, kept as the measurement record |
| `plots/` | generated figures |

CSV columns are `frequency_hz, ch1_vpp, ch2_vpp, gain_db`, preceded by `#`
comment lines carrying the run label, instrument IDNs, drive level, sweep
settings, measured noise floor, linearity result and the free-text `--note`.

## Results

Not yet captured — this section will be filled in with the overlay plot and the
summary table once the sweeps have been run on the bench.
