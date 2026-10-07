# NeonPine – regulatory roadmap

**Product:** NeonPine, a USB‑powered decorative neon‑lamp Christmas tree (night light).
**Model / rev:** NP‑1 rev A (*placeholder model number*).
**Target markets:** EU (CE), UK, USA (FCC). Canada is noted as an option.
**Status:** pre‑compliance. This document lists what applies, what doesn't, and why. It is an engineering assessment, **not
legal advice**. Confirm the classification with the chosen accredited test lab before testing starts.

## 1. Product classification
| Property | Value | Consequence |
|---|---|---|
| Supply | 5 V DC from any USB‑C port or adapter (adapter **not** supplied) | LVD not applicable (below 75 V DC rated input) |
| Internal voltage | 75–105 V DC, ≤ 123 V under fault | Electrical safety covered under GPSR using IEC 60598 / 62368 methods; needs a rear cover (risk assessment) |
| Function | decorative lighting, neon glow lamps, < 60 lm | Lighting EMC standards; outside Ecodesign / energy label scope |
| Electronics | 48 MHz MCU, 30 kHz boost converter | FCC Part 15 Subpart B *unintentional radiator* (digital device) |
| Radio | none | RED and FCC certification not needed |
| Battery | none | Batteries Regulation not applicable |
| Toy? | no: a festive decoration, explicitly *not a toy* under TSD 2009/48/EC Annex I | Toy Safety Directive not applicable (state "Not a toy" in the docs) |

## 2. European Union – CE marking
| Legislation | Applies? | Route / evidence |
|---|---|---|
| **EMC Directive 2014/30/EU** | **Yes** | Module A self‑declaration. Testing to **EN IEC 55015** (emissions, lighting) + **EN 61547** (immunity, lighting). An alternative if the lab classifies it otherwise is EN 55032 Class B + EN 55035. See [02-emc-test-plan.md](02-emc-test-plan.md) |
| **RoHS 2011/65/EU** (+ (EU) 2015/863) | **Yes** | Technical documentation per EN IEC 63000: supplier declarations for every BOM line, plus a risk‑based check of high‑risk parts (lamp, connector, solder) |
| **WEEE 2012/19/EU** | **Yes** | Producer registration in **each** EU country of sale (or an authorised representative); crossed‑out bin symbol (EN 50419) on product/packaging; take‑back info in the manual |
| **General Product Safety Regulation (EU) 2023/988** | **Yes** | Covers electrical, mechanical, chemical and child safety for this low‑voltage product. Needs an internal risk assessment ([01-risk-assessment.md](01-risk-assessment.md)) and technical documentation; markings per Art. 9; an EU economic operator (Art. 16); and a safety‑incident reporting process (Safety Business Gateway) |
| **REACH (EC) 1907/2006** | **Yes** | SVHC > 0.1 % w/w in any article → Art. 33 information duty and SCIP notification. Collect supplier declarations |
| **Packaging & Packaging Waste Reg. (EU) 2025/40** | **Yes** (applies from 12 Aug 2026) | Packaging minimisation, heavy‑metal limits, labelling as implementing acts phase in; national EPR registration for packaging |
| Low Voltage Directive 2014/35/EU | **No** | Rated input 5 V DC is below the 75 V DC lower limit. Safety is handled under GPSR instead |
| Toy Safety Directive 2009/48/EC | **No** | "Decorative objects for festivities and celebrations" are listed in Annex I as not toys |
| Ecodesign light sources (EU) 2019/2020 / energy label (EU) 2019/2015 | **No** | Light sources are defined as 60–82 000 lm; the neon indicators give ≪ 60 lm |
| Radio Equipment Directive 2014/53/EU | **No** | No radio |

**Safety standards used as a "state of the art" reference under GPSR** (no harmonised standard gives presumption of
conformity for a 5 V decorative light):
* **EN IEC 60598‑1** + **EN 60598‑2‑20** (lighting chains) or **‑2‑4** (portable luminaires), the closest product family. The lab decides.
* **EN IEC 62368‑1**, for its energy‑source classification method (ES1/ES2, PS1).
* **EN 62471 / IEC TR 62778**, photobiological safety; expected Exempt Group for orange neon.
* **EN IEC 62493**, EMF from lighting equipment; trivial at 5 V and < 1 W, but list it.

## 3. United Kingdom
* The UK continues to recognise **CE** for EMC and electrical products, so the same test reports can be used. **UKCA** is optional.
* Product safety: **General Product Safety Regulations 2005** (UK) plus PSTI (no connectivity, so N/A). UK RoHS, UK WEEE producer
  registration, UK packaging EPR.
* An importer's or UK manufacturer's name and address must be on the product or packaging.

## 4. United States
| Requirement | Route |
|---|---|
| **FCC 47 CFR Part 15 Subpart B, Class B** (digital device, residential) | **SDoC.** Test at an accredited lab: conducted emissions (§15.107, on the AC mains of a representative USB adapter), radiated emissions (§15.109, 30 MHz–1 GHz since the highest internal frequency is 48 MHz). A **US‑based responsible party** is required. Labelling per §15.19 and user info per §15.105(b) / §15.21 ([05-fcc-sdoc.md](05-fcc-sdoc.md)) |
| FCC Part 18 (RF lighting) | Not expected: light is produced by a DC glow discharge, not RF energy. Confirm with the lab |
| CPSC / safety | No mandatory federal standard for USB‑powered decorations. Retailers commonly require **UL 588** (seasonal & holiday decorative products) or a comparable NRTL listing, so check retailer requirements early |
| California **Prop 65** | Brass and copper alloys in the USB connector and solder may contain lead (RoHS exemption 6(c)). Either confirm lead‑free parts or add a Prop 65 warning |
| Customs | Country of origin marking on product or packaging (19 CFR 134) |

## 5. Canada (optional)
* ISED **ICES‑005** (radio frequency lighting devices) is likely the applicable standard instead of ICES‑003; confirm with the lab.
  Labelling: "CAN ICES‑005 (B) / NMB‑005 (B)". The FCC Part 15 test data are usually reusable.

## 6. What must exist before the test lab
1. The **rev B hardware** with the blocking design actions done (rear cover, HV+ off the front, markings): see `DESIGN.md` §7.
2. **Final firmware** with an EMC test mode (all lamps lit at 105 V, steady animation) and a "typical" mode.
3. 3 samples for EMC, plus 2 for safety evaluation, and 1 opened sample with the cover removed for the safety inspection.
4. A representative USB‑C adapter (listed / CE) and a 1 m USB‑C cable (used for testing and stated in the manual).
5. Technical file draft ([07-technical-file-index.md](07-technical-file-index.md)).

## 7. Status tracker
| Item | Owner | Status |
|---|---|---|
| Risk assessment rev 1 | design | **draft done** – blocking findings open |
| Rev B hardware (cover, HV routing, markings, Cd‑free sensor, stand, ESD) | design | **layout done 2026‑10‑06** – order samples |
| Firmware with test modes | firmware | open |
| Pre‑compliance EMC scan (in‑house near‑field + LISN) | design | open |
| Accredited EMC test, EU + FCC | lab | open |
| Safety evaluation (GPSR, IEC 60598/62368 method) | lab / design | open |
| Supplier declarations (RoHS, REACH, Kr‑85‑free lamps) | purchasing | open |
| Replace CdS LDR R8 (cadmium) with a Cd‑free sensor | design | **done** (TEPT4400) |
| EU DoC + FCC SDoC signed | manufacturer | template ready |
| WEEE / packaging EPR registrations per country | manufacturer | open |
| EU economic operator / UK importer / US responsible party named | manufacturer | open |
| User manual translations (each EU language of sale) | docs | English draft done |
