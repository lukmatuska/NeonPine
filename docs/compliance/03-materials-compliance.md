# NeonPine – materials compliance (RoHS / REACH) data collection

The RoHS assessment follows EN IEC 63000: rate each part's risk, then collect evidence proportional to that risk.
"Evidence" is a supplier RoHS/REACH declaration, a full material declaration (IPC‑1752A), or a test report.

| BOM line | Part | Supplier | Risk | Evidence needed | Status |
|---|---|---|---|---|---|
| LA1–LA10 | Brightmaster NEON‑3 neon lamp | TME / Brightmaster | **High** (glass, lead‑in wires, small brand, possible Kr‑85) | RoHS + REACH declaration **and a written statement "no radioactive substances"**; for the first lot, an XRF check of the leads | open |
| U1 | CH32V003F4P6 | WCH | Low | RoHS/REACH declaration from WCH | open |
| Q1 | DMN15H310SE | Diodes Inc. | Low | datasheet says RoHS, halogen/antimony‑free; keep the datasheet | ok (datasheet) |
| Q11–Q20 | MMBTA42 | `[make]` | Low | manufacturer declaration | open |
| D1, D2 | ES1D, SMAJ100A | `[make]` | Low | declaration | open |
| L11 | SWPA6028S331MT 330 µH | Sunlord | Medium (ferrite, magnet wire) | declaration | open |
| C1–C7 | MLCC | `[make]` | Low | declaration | open |
| R* | thick‑film chip resistors | `[make]` | Low (glass‑frit Pb exempt 7(c)‑I) | declaration, exemptions listed | open |
| ~~R8~~ → **Q2** | ~~GL5528 CdS LDR~~ → **Vishay TEPT4400** phototransistor | Vishay | Low | Vishay RoHS / REACH declaration (Cd‑free silicon) | **rev B: replaced** – declaration to file |
| J1 | USB‑C GCT USB4125‑GF‑A | GCT | Medium (copper alloy Pb, exemption 6(c)) | declaration incl. exemptions → Prop 65 decision | open |
| F1 | MF‑NSMF050‑2 PTC 1206 | Bourns | Low | declaration | open |
| D3 / FB1 | SMF5.0A TVS / 600 Ω ferrite 0603 | `[make]` | Low | declaration | open |
| J2 | ~~pin header~~ → bare pogo pads (rev B) | – | – | none (no part) | **removed** |
| mech | rear cover + stand PCBs; 3 × M2 × 5 standoff, 6 × M2 × 4 screw | `[fab]`, `[make]` | Medium (brass standoffs: Pb exemption 6(c)) | fab statement; standoff/screw declarations | open |
| PCB | FR‑4, ENIG, LPI mask, silkscreen | `[fab]` | Low | fab RoHS/REACH statement, UL 94 V‑0 file number | open |
| Solder | SAC305 paste + wire | `[assembler]` | Low | declaration | open |
| Packaging | carton, insert | `[supplier]` | Low | PPWR heavy‑metal declaration | open |

> ✔ **Resolved in rev B:** the CdS photoresistor GL5528 (cadmium, not RoHS‑compliant as a standalone part) was replaced by the Vishay
> TEPT4400 silicon phototransistor (+5V → C, E → PD5, R9 = 22k).
