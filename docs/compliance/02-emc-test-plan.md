# NeonPine – EMC design review & test plan

## 1. Standards (confirm the classification with the lab)
| Market | Emissions | Immunity |
|---|---|---|
| EU / UK | **EN IEC 55015** (lighting equipment, decorative lighting is in scope) | **EN 61547** (lighting immunity) |
| EU (alternative classification) | EN 55032 Class B | EN 55035 |
| USA | **FCC Part 15 Subpart B, Class B** (§15.107 conducted, §15.109 radiated, 30 MHz – 1 GHz) | – |
| Canada (option) | ICES‑005 (lighting) | – |

**Test configuration:**
* the product in its final form (rev B with the rear cover) on a non‑conductive table;
* powered by a **representative CE/UL‑listed 5 V USB‑C adapter** through a 1 m USB‑C cable. Conducted emissions are measured on the adapter's AC mains through a LISN; the adapter is support equipment. Record its model in the report and the manual;
* firmware in **EMC mode**: all lamps lit, HV at 105 V, boost at its highest duty. Also scan a dimmed animation mode (75 V, BAM active) and standby.

## 2. Noise sources in the design
| Source | Frequency content | Coupling path | Risk |
|---|---|---|---|
| Boost converter Q1/L11/D1 | 30 kHz fundamental, fast edges → harmonics up to ~100 MHz | **Magnetic field** from the boost loop (EN 55015 large‑loop‑antenna test, 9 kHz – 30 MHz); conducted on VBUS → USB cable → adapter | **High** – the 30 kHz fundamental and low harmonics sit inside the EN 55015 magnetic range |
| SW node (≈ 105 V swing) | edges ~20 ns | electric field from the SW copper area; USB cable as an antenna | Medium |
| MCU 48 MHz clock (HSI × 2) | 48, 96, 144 … MHz | radiated via the USB cable and the board | Medium |
| BAM lamp switching | 1 kHz frame, ~105 V edges through 150 k | low current → weak | Low |
| Touch pads (TKEY) | sampling | – | Low (emissions); **ESD entry point** (immunity) |

## 3. Design measures already in rev A
* Shielded drum inductor (L11); boost input cap C3 next to L11/Q1, with a short return to the Q1 source (placement optimiser weights).
* Output loop D1 → C4 → GND kept tight (D1, C4, D2 grouped directly above the boost).
* GND pour on both layers; tented vias; decoupling C6 at U1 VDD; ADC filter C5 at U1.
* R1 47 Ω in the gate drive slows the turn‑on edge; R2 keeps the boost off during reset.
* USB data lines not connected (power‑only connector).

## 4. Additions for rev B
| # | Measure | Cost | Helps | Rev B status |
|---|---|---|---|---|
| E1 | **Ferrite bead (e.g. 600 Ω @ 100 MHz, 0603) in VBUS** after F1, plus the existing C1/C2 → a π filter | ≈ $0.01 | conducted emissions, radiated via the cable, 48 MHz harmonics | **done** (FB1) |
| E2 | **Frequency dithering** of the 30 kHz boost (± 5 %, triangular, ~200 Hz) in firmware | free | spreads the boost harmonics (lowers quasi‑peak) | firmware |
| E3 | Optional footprint: RC snubber across Q1 D‑S (e.g. 100 pF + 100 Ω) | ≈ $0.01 | SW‑node ringing, 30–100 MHz | **footprint done** (R12/C8, DNP) |
| E4 | GND stitching vias along the board edge and around the boost (every ~5 mm) | free | edge radiation | not done – add if the pre‑scan needs it |
| E5 | **Solder mask over TP1/TP2** (capacitive touch works through the mask) | free | ESD to the touch inputs | **done** (TP2 masked; TP1 removed) |
| E6 | TVS on VBUS (e.g. 5 V uni‑directional, SOD‑323) at J1 | ≈ $0.02 | ESD/surge on the connector | **done** (D3 SMF5.0A, 5.7 mm from VBUS) |
| E7 | Keep the boost‑off window as short as possible during standby wakeups | free | – | firmware |

## 5. Immunity tests (EN 61547) and acceptance criteria
| Phenomenon | Basic standard | Level (confirm with lab) | Where | Criterion |
|---|---|---|---|---|
| ESD | IEC 61000‑4‑2 | ± 4 kV contact / ± 8 kV air | touch pads, lamps, USB shell, edges | **B**: temporary change allowed, self‑recovers; no HV above setpoint |
| Radiated RF | IEC 61000‑4‑3 | 3 V/m, 80 MHz – 1 GHz (+ bands to 6 GHz per edition), 80 % AM | whole unit | **A**: no visible flicker |
| Conducted RF (if cable > 3 m / adapter port) | IEC 61000‑4‑6 | 3 V | adapter AC port | A |
| EFT / surge / dips | IEC 61000‑4‑4/‑5/‑11 | per standard (applied to the adapter's AC input) | via adapter | B / C |

The lighting performance criterion is about light output: no visible change during the test (A), or a change that recovers by itself (B).

## 6. In‑house pre‑compliance (before booking the lab)
1. **Near‑field scan** (H‑field probe + spectrum analyser, 9 kHz – 1 GHz) over the boost area; compare 30 kHz harmonics with and without E2 dithering.
2. **Conducted**: an AC LISN in front of the adapter, 150 kHz – 30 MHz, compared with the Class B / EN 55015 limits minus a 6 dB margin.
3. **Radiated (rough)**: a biconical/log‑periodic or calibrated near‑field at 1 m in an office; look for 48 MHz harmonics and cable resonance; try clip‑on ferrites to find the coupling path.
4. **ESD**: an ESD gun at ± 4/8 kV on the touch pads; check for resets, latch‑up and HV overshoot on a scope (HV+ through a 100:1 HV probe).

## 7. Deliverables for the technical file
* Pre‑compliance scan plots (rev B), the accredited lab report (EU + FCC), the test setup photo, adapter and cable identification,
  and the firmware version used.
