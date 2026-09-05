# Archived component datasheets

This directory holds project-local copies of documentation for obsolete and
historical components used in the Ten-Tec Triton IV Model 540 reconstruction.
KiCad symbols should point to these local files so the design does not depend
on external links remaining available.

## RCA 40823

- Used by: `80166` receiver RF amplifier (Q1) and `80279` 9 MHz IF
  amplifier stages
- File: `RCA_40823_SC-15_1971.pdf`
- Manufacturer: RCA Corporation, Solid-State Division
- Document: *RCA Transistor, Thyristor & Diode Manual*, Technical Series SC-15
- Original publication: 1971
- Extracted pages: printed pages 386 through 388 (40821, 40822, and 40823
  electrical data) and printed page 670 (JEDEC TO-72, RCA outline No. 28)
- Note: RCA specifies the 40823 as identical to the 40821 except for the listed
  ratings and characteristics, and refers to the 40822 for typical curves.
- Archive source:
  <https://www.worldradiohistory.com/BOOKSHELF-ARH/Technology/RCA-Books/RCA-Transistor-Thyristor-%26-Diode-Manual-1971.pdf>
- Archived file SHA-256:
  `AC18E00AAA3F6D3BE2EAAB2780D9C1DC1EC17F6025724F54BAAE7D126BE33B09`

## MC1747 / MC1747C

- Used by: `80279` AGC and audio preamplifier
- File: `MC1747_MC1747C_Motorola_1976.pdf`
- Manufacturer: Motorola Semiconductor Products Inc.
- Document: MC1747 / MC1747C dual operational amplifier, document DS 9254
- Original publication: 1976 Motorola Semiconductor Data Library, Volume 6,
  Series B, *Linear Integrated Circuits*
- Extracted pages: printed pages 3-83 through 3-86 (four-page device sheet)
- Archive source:
  <https://www.bitsavers.org/components/motorola/_dataBooks/1976_Motorola_Semiconductor_Data_Library_Volume_6_Series_B_Linear_Integrated_Circuits.pdf>
- Archived file SHA-256:
  `D2F00DBC59EEE32FA07F4A339DD53DEB0EA124C4779C71F2E761D8EE11318594`

## 80274 audio power amplifier

These archives support the parts shown on manual PDF page 35 / printed page 3-19.
The manufacturer documents are primary evidence; the hosting sites are archives.
Later datasheet revisions are identified below and are not proof of the production
lot or package revision fitted to this radio. No substitute parts are assigned.

### MPSU01 (Q74-1)

- File: [Motorola_MPSU01_TechnicalData_undated.pdf](Motorola_MPSU01_TechnicalData_undated.pdf)
- Manufacturer: Motorola Semiconductor Products
- Document: *MPS-U01 / MPS-U01A NPN Silicon Audio Transistors, Semiconductor Technical Data*
- Original publication: Undated original; scan creation date is not the publication year
- Extracted pages: Both device pages; case 152-02 and E-B-C lead numbering appear on page 1
- Used by: assembly 80274, Q74-1
- Archive source: <https://datasheet4u.com/pdf/505844/MPSU01.pdf>
- Archived file SHA-256: 36074E59597EBAD8F55A46C62B235A8F31B9F6712FD52B6E3EC39E4E847FE000

### MPS6514 (Q74-3)

- File: [Motorola_MPS6514_DeviceData_undated.pdf](Motorola_MPS6514_DeviceData_undated.pdf)
- Manufacturer: Motorola Semiconductor Products
- Document: *MPS6512 through MPS6519 Amplifier Transistor*
- Original publication: Undated device page; package supplement from 1991 DL126 Rev. 3
- Extracted pages: Device printed page 2-204; appended package/style page 8-2 (PDF page 837) from 1991 DL126 Rev. 3. Style 1 is 1=E, 2=B, 3=C; the later case 29-04 outline is supplementary, while the device page specifies case 29-02
- Used by: assembly 80274, Q74-3
- Archive source: <https://datasheet4u.com/pdf/1115234/MPS6514.pdf>
- Package supplement source: <https://www.bitsavers.org/components/motorola/_dataBooks/1991_DL126r3_Motorola_Small-Signal_Transistors_FETs_and_Diodes.pdf>
- Archived file SHA-256: E9A2791869ED3FDE04CC2622717A615A8F2C78B47AEB910D0CD93B5A73E7CB82

### 2N4870 (Q74-2)

- File: [Motorola_2N4870_ThyristorDeviceData_undated.pdf](Motorola_2N4870_ThyristorDeviceData_undated.pdf)
- Manufacturer: Motorola Semiconductor Products
- Document: *2N4870 / 2N4871 PN Unijunction Transistors, Thyristor Device Data*
- Original publication: Undated device pages; package supplement from 1991 DL126 Rev. 3
- Extracted pages: Device printed pages 3-22 through 3-26; appended package/style page 8-2 (PDF page 837) from 1991 DL126 Rev. 3. Case 29 style 9 is 1=B1, 2=E, 3=B2
- Used by: assembly 80274, Q74-2
- Archive source: <https://datasheet.octopart.com/2N4870-Motorola-datasheet-180793037.pdf>
- Package supplement source: <https://www.bitsavers.org/components/motorola/_dataBooks/1991_DL126r3_Motorola_Small-Signal_Transistors_FETs_and_Diodes.pdf>
- Archived file SHA-256: 3FBFE4898E3A0DED2CEFB50942763706FAECF680F558580B240C8897FA77EA2A

### LM380N (U74-1)

- File: [National_LM380_DS006977_2000.pdf](National_LM380_DS006977_2000.pdf)
- Manufacturer: National Semiconductor
- Document: *LM380 2.5W Audio Power Amplifier, DS006977*
- Original publication: August 2000
- Extracted pages: Source PDF pages 2 through 8 (manufacturer device pages 1 through 7, including the N14A DIP-14 package); distributor cover and final notes page omitted
- Used by: assembly 80274, U74-1
- Archive source: <https://datasheet.octopart.com/LM380N-National-Semiconductor-datasheet-7275687.pdf>
- Archived file SHA-256: 2A93CBCC4B527A974060AC2FE1396408B5B9E5A819E0162A482459EF5F6C0398

### 1N4154 (D74-1)

- File: [Fairchild_1N4154_DiscretePowerAndSignal_1998.pdf](Fairchild_1N4154_DiscretePowerAndSignal_1998.pdf)
- Manufacturer: Fairchild Semiconductor
- Document: *1N4154 High Conductance Fast Diode, Discrete Power and Signal Technologies*
- Original publication: Revision A, September 21, 1998 (copyright 1997)
- Extracted pages: Source PDF page 1, including DO-35 dimensions and cathode band; trademark page omitted
- Used by: assembly 80274, D74-1
- Archive source: <https://www.sm0vpo.com/_pdf/1N/1N4154.pdf>
- Archived file SHA-256: 0F6607CE3231C1A442E40ED800AEFC8D2FCE1A501A83BF57C706B4C019EE583B

### D74-2: documented value, unidentified device

The manual specifies only an **8.2 V Zener**. Manufacturer, part number,
power rating, and package are unknown. Its placed-symbol Datasheet field
therefore remains blank; linking a named replacement would misrepresent the
source. Its Evidence field records this limitation.

### LM380N / ULN2280B choice

The manual explicitly lists LM380N / ULN2280B. The schematic represents the
documented LM380N alternative with all 14 physical pins. Pins 9 and 13 are
internal NCs; pins 3, 4, 5, 7, 10, 11 and 12 are grounded. The local symbol
changes the drawing arrangement, not the pinout. The ULN2280B is noted as a
manual alternative, not silently substituted or modeled.
