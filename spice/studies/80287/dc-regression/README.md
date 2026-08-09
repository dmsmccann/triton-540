# 80287 MC1496 DC regression

This study compares U87-1 and U87-2 against the semiconductor voltage table
on Ten-Tec manual PDF page 30 / printed page 3-14. The manual says service
voltages should be within 15 percent when measured with a DC voltmeter of at
least 20,000 ohms per volt (PDF page 18 / printed page 3-1).

The runner exports a fresh netlist from `triton_540.kicad_sch`; it does not use
a separately redrawn 80287 bias circuit. Receive uses R=12.8 V and T=0.2 V.
Transmit uses R=0.6 V and T=10.4 V. The RF sources remain active to move the
transistor-level model out of ngspice's low startup equilibrium, and the
regression allows 500 us for the board's bias capacitors to settle. Reported
voltages are means over the final 20 us.

## Result

- 40 connected-pin/mode readings checked; NC pins are omitted.
- 33 readings pass the manual tolerance.
- Every U87-1 transmit reading passes.
- Every U87-2 transmit and receive reading passes.
- U87-1 receive pins 1, 2, 3, 4, 5, 8, and 10 fail.
- U87-1 receive collectors pass at about 11.1 V versus 11.8 V documented.

R87-1 endpoint trials did not bring the seven U87-1 receive points into the
manual ranges. U87-2 pin 5 is 3.17 V versus 3.0 V documented, but U87-1 pin 5
is 2.68 V versus 1.2 V. Because both instances use the same internal bias law,
a global MC1496 parameter change that forces U87-1 would damage the currently
passing U87-2 result. Those seven points remain an external-network, manual,
or device-model discrepancy rather than an empirical fit target.

Run from the project root:

```powershell
python spice\tools\run_mc1496_dc_regression.py
```

Use `--strict` to return a failing exit status while any documented point is
outside tolerance. The detailed evidence is in
`data/80287-mc1496-dc-regression.csv`.
