# NeonPine – product risk assessment (rev 1, draft)

| | |
|---|---|
| Product | NeonPine NP‑1, **rev B** hardware (layout of 2026‑10‑06), firmware not yet written. Rev 1 of this document assessed rev A |
| Method | Hazard identification per EN ISO 12100 principles; risk levels per the EU GPSR / Safety Gate risk‑assessment method (severity × probability). Electrical energy classified with the IEC 62368‑1 ES/PS approach |
| Intended use | Decorative light for indoor, dry, domestic use, standing on a shelf or windowsill; supplied from a USB‑C port or adapter; may run unattended overnight |
| Foreseeable misuse | Picked up while on and touched on the back; handled by children; placed on a wet windowsill; powered from a poor adapter; lamps bent or pulled; dropped |
| Users | General public incl. elderly people. Children are likely to be near it (not intended users: "not a toy, 14+") |
| Author / date | design team, 2026‑10‑05 (*to be reviewed and signed by the manufacturer*) |

## 1. Energy sources (IEC 62368‑1 style classification)
| Source | Value | Class | Accessible? |
|---|---|---|---|
| USB VBUS / +5V | 5 V, ≤ 0.5 A (PTC) | ES1 / PS1 | yes (connector, back pads), acceptable |
| **HV+ / SW node** (C4, D1, D2, Q1, L11, R5, R21–R30, R12/C8) | **105 V DC** (123 V fault), boost can deliver well over 2 mA into a body (≈ 13 mA into 2 kΩ at 0.35 W) | **ES2** (above the 60 V DC / 2 mA ES1 limits) | rev A: yes. **Rev B: no.** All HVBUS copper is on the back, behind the screwed rear cover (basic safeguard); 0 HVBUS items on the front copper |
| Lamp leads (front, THT) | 105 V behind 150 kΩ → **≤ 0.70 mA DC** | ES1 (current‑limited) | yes, acceptable |
| C4 stored charge | ≤ 5.5 mJ at 105 V; bleeds through 2.04 MΩ, τ ≈ 2 s (< 60 V after ≈ 1.1 s) | ES1 after 2 s | relevant only once the rear cover is opened |
| Input power | ≤ 2.5 W (PTC hold limit at 5 V), typically 0.5 W | **PS1** (< 15 W) | no fire enclosure needed |
| Optical | orange neon, ≪ 60 lm, no UV/blue peak | expected **Exempt Group** (EN 62471) | yes |
| Thermal | < 1 W dissipated over 37 cm² | expected surface rise < 10 K | yes |

ES2 parts must be separated from ordinary persons by at least a **basic safeguard**, such as an enclosure that can only be opened
with a tool. Solder mask is **not** recognised as insulation. Firmware limits (duty clamp, OVP trip) are **not** counted as
safeguards, because there is no IEC 60730 Class B software evaluation.

## 2. Risk matrix
Severity: **1** minor (no or slight injury) · **2** moderate (needs first aid or a doctor) · **3** serious (hospital or permanent) · **4** very serious / fatal.
Probability over the product's life: **A** > 1/10 · **B** 1/100 · **C** 1/1 000 · **D** 1/10 000 · **E** < 1/100 000.
Risk level: L low · M medium · H high · S serious (S and H are **not acceptable** for placing on the market).

| Sev \ Prob | A | B | C | D | E |
|---|---|---|---|---|---|
| 4 | S | S | S | H | M |
| 3 | S | S | H | M | L |
| 2 | S | H | M | L | L |
| 1 | M | L | L | L | L |

## 3. Hazard register
"Before" = rev A as designed. "After" = with the listed mitigations implemented and verified.

| # | Hazard / scenario | Cause | Sev | Prob before | Risk before | Mitigation (design → protective → information) | Prob after | Risk after |
|---|---|---|---|---|---|---|---|---|
| H1 | **Electric shock from the back side**: the user picks the tree up while it is on and touches the back | 105 V ES2 on bare SMD pads (HV+, SW); no enclosure | 2 (painful DC shock, startle, dropped glass) – 3 for a child's wet hand | A | **S** | **[B] Rear insulating cover** (FR‑4 back plate or moulded cover) over the whole back, held by screws (tool needed), ≥ 0.4 mm solid insulation or ≥ 2 mm clearance from HV parts. Rating label on the cover | E | L |
| H2 | **Electric shock from the front HV+ tracks** after a scratch or mask defect | 27 mm of HV+ track on F.Cu, covered by solder mask only | 2 | C | **M** | **[B] Route HV nets on the back only** (F.Cu keep‑out for the HV class); front copper is then ES1 only | E | L |
| H3 | Shock from the lamp leads | 105 V on the anode side | 1 (≤ 0.7 mA DC, below perception for most people) | B | L | 150 kΩ on the **anode** side of every lamp (inherent); verify touch current ≤ 2 mA DC with the lamp shorted and with the transistor shorted | B | L |
| H4 | Shock from C4 after unplugging, when the cover is opened for repair | residual charge | 1 | D | L | 2.04 MΩ divider as a bleeder (τ ≈ 2 s); manual note: "no user‑serviceable parts" | D | L |
| H5 | Overvoltage, component overstress or fire after a firmware fault (PWM stuck on, ADC fault) | software | 2 | C | M | Hardware: D2 clamp (V_BR 111–123 V) < Q1 150 V, C4 250 V, D1 200 V, MMBTA42 300 V; R2 gate pull‑down; F1 PTC; IWDG. **Verify by fault test:** force 60 % duty, open feedback (R7 shorted / R5 open), confirm D2 temperature and no flame | D | L |
| H6 | Fire from a component failure (shorted Q1, shorted MLCC C1/C3, shorted D2) | single fault | 3 | D | M | PS1 source (USB ≤ 2.5 W through PTC); F1 0.5 A PTC; V‑0 FR‑4; parts > 5 mm from combustible packaging in use. **Single‑fault tests** on Q1 D‑S short, C3 short, D2 short, L11 short: no flame, PTC trips, surface < 90 °C | E | L |
| H7 | Overheating, burns when touched | normal use | 1 | E | L | < 1 W total; confirm with a thermal test (ΔT < 10 K) | E | L |
| H8 | **Cuts from broken glass**: lamp broken by a drop, a child, or bending the leads | glass envelope Ø4 mm on the front | 2 | B | **H** | Lamps lie flat and are **bonded with a dab of silicone** (item 6); rounded board edges (R 1.5 mm); stable stand (item 9); warnings: "Not a toy", "Do not bend the lamps", "If a lamp breaks, unplug and dispose of the product" | C | M → accept with warnings; consider an optional clear front guard for a "family" SKU |
| H9 | **Choking / ingestion of small parts** by a small child (broken lamp, detached light sensor, glass fragments) | small parts, children nearby | 3 | C | H | Not a toy; mark "Not suitable for children under 3 years / keep out of reach of children" + 14+ recommendation; lamp bonding; light sensor seated flat; packaging warnings | D | M → accepted (a decoration, not a toy) |
| H10 | **Radioactive material** in neon lamps (Kr‑85 "dark effect reduced" types) | supplier choice | 2 (regulatory, negligible dose) | C | M | **[B] Supplier declaration that NEON‑3 contains no radioactive additive**; incoming inspection; firmware handles the dark effect instead (keep‑alive BAM, ignition kick) | E | L |
| H11 | Hazardous substances (Pb, **Cd**, Hg, phthalates…) | **R8 GL5528 is a CdS photoresistor (cadmium)**; other parts, solder, cable | 2 | **A** (Cd is present by design) | **H** (regulatory: RoHS non‑conformity) | **[B] Replace R8 with a cadmium‑free phototransistor** (see 03‑materials‑compliance.md); RoHS + REACH supplier declarations; lead‑free (SAC) assembly, ENIG; no Hg (neon, not fluorescent) | E | L |
| H12 | Moisture or condensation on a windowsill → HV leakage, tracking | foreseeable misuse | 2 | C | M | Indoor dry use in the instructions; rear cover; HV clearance 0.5 mm functional; **post‑assembly flux cleaning** (residues + 105 V → leakage, and drift of the 2 MΩ feedback) | D | L |
| H13 | Unattended overnight use | intended use | 3 (fire) | E | L | PS1, PTC, sleep timer and auto‑off at daylight; no heat | E | L |
| H14 | Unsafe or non‑compliant USB adapter | external | 3 | D | M | Adapter not supplied; manual requires an adapter certified to IEC 62368‑1 (CE / UL listed); device draws ≤ 0.15 A | D | M → information only, outside product scope |
| H15 | Strangulation by the USB cable | small child | 4 | E | M | Cable not supplied (or ≤ 1 m if bundled); warning in the manual; not a toy | E | M → accepted with warning (common to all USB products) |
| H16 | Sharp edges / points (star tips, PCB edge) | handling | 1 | C | L | All outline corners R 1.5 mm; routed + deburred edges; no V‑score stubs on the product edge (panel tabs placed on the pot bottom) | D | L |
| H17 | Tip‑over → glass breakage (H8) | no stand | 2 | B | H | Cross‑stand slot + stand piece (item 9), or a weighted base; stability test (10° incline) | D | L |
| H18 | EMC: interference with radio/TV, or malfunction from ESD | boost converter, MCU clock; touch pads | 1 (not safety‑relevant) | – | – | See [02-emc-test-plan.md](02-emc-test-plan.md); worst case after ESD is a reset; HV is never higher than the setpoint after a reset (R2 keeps Q1 off) | – | – |
| H19 | Photobiological (eye) | light | 1 | E | L | Orange neon, ≪ 60 lm; EN 62471 assessment → Exempt Group expected | E | L |

## 4. Conclusion
**Rev B status:** the design mitigations for H1 (rear cover), H2 (HVBUS on the back only), H11 (Cd‑free TEPT4400 sensor),
H16/H17 (rounded edges, stand base) and H18 (masked touch pad, TVS) are implemented in hardware. The star touch pad was removed.
Their effectiveness still has to be **verified on rev B samples** (§5) before sign‑off. H10 (Kr‑85 declaration) and the
lamp‑bonding process (H8) remain open.

*Rev A conclusion (kept for the record):*
* **Rev A must not be placed on the market.** H1 is a **serious** risk and H8, H9 and H17 are **high** before mitigation.
* H11 is **high** as a regulatory non‑conformity (cadmium in the CdS LDR).
* With the **[B]** actions (rear cover, HV routing on the back only, Kr‑85‑free lamp declaration, Cd‑free light sensor) plus lamp bonding, the stand
  and the instructions, every residual risk is **L or M**. The M items are accepted for a decorative product with warnings
  (H8, H9, H14, H15).
* Verification to be recorded in this document (§5) before the manufacturer signs it off.

## 5. Verification record (to fill in on rev B samples)
| Test | Requirement | Result |
|---|---|---|
| Touch current, lamp leads, normal + lamp short + transistor C‑E short | ≤ 2 mA DC through 2 kΩ | |
| Accessibility probe (IEC 61032 test probe B) on the assembled product incl. cover | no ES2 part touchable | |
| Rear cover fixing needs a tool; cover pull / drop test | cover stays, no ES2 exposed | |
| C4 discharge after unplugging | < 60 V within 2 s | |
| Fault tests H5/H6 (duty stuck, open feedback, Q1/C3/D2/L11 short) | no fire, no part > 90 °C, PTC trips, no ES2 exposure | |
| Thermal test, 4 h at max brightness, 35 °C ambient | ΔT < 10 K on accessible surfaces | |
| Drop test 1 m onto hardwood (3 ×) | no exposed ES2; glass breakage noted | |
| Stability on a 10° incline | does not tip | |
| EN 62471 assessment | Exempt Group | |
| Supplier declarations (RoHS, REACH, no radioactive additive) | on file | |

## 6. Revision history
| Rev | Date | Change |
|---|---|---|
| 1 | 2026‑10‑05 | First issue on rev A layout |
| 2 | 2026‑10‑06 | Rev B: cover, HVBUS back‑only, Cd‑free sensor, stand, ESD measures implemented; verification pending |
