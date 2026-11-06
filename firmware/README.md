# NeonPine firmware

| Dir | What |
|---|---|
| `bootloader/` | [rv003usb](https://github.com/cnlohr/rv003usb) USB HID bootloader (1209:B003) in the CH32V003's 1920‑byte boot area, configured for D+ = PD2, D− = PD4, no D− pull‑up pin |
| `neonpine_test/` | The firmware (1209:D003): HV boost, the 8 simulator animations (`anim.c`), touch UI, light sensor, sleep timer, bring‑up shows, status over USB |
| `installer/` | Writes the bootloader + option bytes from the chip itself, for programmers that only write main flash (PicoRVD) |
| `tools/nptest.py` | Talks to the firmware over USB (Linux hidraw, no pip packages) |
| `../companion/` | The **NeonPine Companion** desktop app (Linux + Windows, tray): animations, custom keyframe animations, live modes, settings, diagnostics, firmware updates |
| `tools/gen_anim_tables.py` | Generates `neonpine_test/anim_tables.h` (sine, e^−x, noise permutation) |
| `tools/99-neonpine.rules` | udev rule: user access to the bootloader, the test firmware and the WCH‑LinkE |

## Setup (once per PC)
```sh
sudo pacman -S --needed riscv64-elf-gcc riscv64-elf-newlib   # toolchain; libusb + hidapi for minichlink are already installed
sudo cp tools/99-neonpine.rules /etc/udev/rules.d/ && sudo udevadm control --reload && sudo udevadm trigger
make            # clones rv003usb + ch32fun (pinned) into deps/, builds minichlink, bootloader and test firmware
```

## First flash (once per board, SWD)
WCH‑LinkE on the J2 pogo pads `5V – SWIO – GND` (pin 1 = square = 5V), rear cover off.
```sh
make first-flash
```
This does three steps:
1. **Option bytes** `+a55aff00`: boot into the bootloader area, **NRST disabled** (PD7 = SR_DATA), software IWDG.
2. Writes the USB bootloader into the boot area.
3. Writes the test firmware into user flash.

> ⚠ The test firmware starts the boost right away: **up to 105 V on the back side** (HV+, lamp nets, Q1, L11, D1, C4).
> Don't touch the back while it runs. C4 bleeds down below 60 V about 1 s after unplugging.

### …with a Raspberry Pi Pico (PicoRVD) instead
[PicoRVD](https://github.com/aappleby/PicoRVD) can only write main flash; it can't write the option bytes or the boot area.
`installer/` works around that. It's a small program you load into main flash, and on its next start it programs both itself:
the bootloader image (embedded from `bootloader/bootloader.bin`) into the boot area, and the option bytes `+a55aff00`.
After that it reboots into the USB bootloader.

> ⚠ **Untested on hardware.** The register sequences are minichlink's (`DefaultWriteBinaryBlob` / `DefaultErase`) and the
> ch32fun `optionbytes` example, but executed by the CPU itself instead of over SWD. Main flash is never touched, so the worst
> case is "it didn't work" – reload and try again.

**Wiring:** Pico GP28 → J2 SWIO, a **1 kΩ pull-up from SWIO to the Pico's 3V3**, Pico GND → J2 GND, and Pico **3V3 → J2 5V pad**.
The RP2040 isn't 5 V tolerant, so the board must run at 3.3 V while the Pico is attached. **Never plug USB-C in while the Pico
is connected:** USB 5 V would back-feed into the Pico's 3V3.

```sh
sudo pacman -S --needed riscv64-elf-gdb
make pico                      # PORT=/dev/ttyACMx if the PicoRVD GDB port isn't ttyACM0
```
Then **unplug the Pico** and plug the board into the PC by USB-C. The installer runs (≈ 0.2 s), writes the boot area and the
option bytes, and reboots into the bootloader:
```sh
lsusb | grep 1209:b003         # the bootloader → install worked
make flash                     # puts the test firmware over the installer
```
Until `make flash` replaces it, the board cycles **bootloader (5 s) → installer (only verifies, writes nothing) → bootloader**.
So `make flash` works whenever you run it.

**If 1209:b003 doesn't show up:** disconnect USB, reconnect the Pico and run `make pico-result`. It prints `install_result`:

| Value | Meaning |
|---|---|
| `0x0` | the installer hasn't run (or is still running) – power-cycle |
| `0x1` / `0x2` | installed now / already installed – then it's a USB problem, not the install |
| `0xe1` | flash unlock failed |
| `0xe2` | boot area stayed locked (STATR BOOT_LOCK) – the chip refuses boot-area writes from user code |
| `0xe3` / `0xe4` | boot-area erase/program error / read back different (`install_page` = failing page) |
| `0xe5` / `0xe6` / `0xe7` | option bytes: unlock / write / verify failed |
| `0xe8` | bootloader image > 1920 bytes |

`install_statr` / `install_ctlr` are the FLASH registers at the failure; the last line shows the option bytes (first word `0x00ff5aa5` = RDPR a5, USER ff).
On an error the installer stops without rebooting, and retries on every power-up.

PicoRVD quirks:
* Every memory read returns the data of the *previous* read request, so plain `x/…` in gdb shows shifted values.
  `make pico-result` reads each value twice; do the same by hand (`set $d = *(unsigned*)ADDR` first).
* With no target on SWIO it hangs as soon as gdb connects. Replug the Pico after wiring up the board.
* Detaching doesn't restart the chip; `monitor reset` does (`make pico` sends it).

First board (2026-11-05): installed on the first run. Option bytes `00ff5aa5`, and the boot area read back identical to `bootloader.bin`.

## Updating over USB (no programmer)
```sh
make flash
```
(or the Firmware page of the companion app, which does the same with a Python port of minichlink's b003boot programmer.)
`minichlink -C b003boot` finds the running test firmware (1209:D003) and sends it the reboot feature report. The board
re‑enumerates as the bootloader (1209:B003), minichlink writes the new image and starts it (`-b`).

**If the application is broken** (it doesn't enumerate, so minichlink can't reboot it), use the bootloader window instead:
after every power‑up the bootloader waits ≈ 5 s (lamps dark) before it starts the application. Run this and then plug the board in:
```sh
until make -C neonpine_test flash; do sleep 0.3; done
```
The SWD path (`make flash-swd`, or `make first-flash` again) always works.

## What the firmware does
After the ≈ 5 s bootloader wait it plays the saved animation (**Candle** on a fresh board). The directory is still called
`neonpine_test/`.

### Animations (the NeonPine simulator artifact, ported to fixed point in `anim.c`)
| # | Name | |
|---|---|---|
| 0 | candle | every electrode flickers on its own (noise), with occasional dips |
| 1 | breathe | the whole tree breathes (5.5 s) while the glow drifts left ↔ right (13 s) |
| 2 | twinkle | random electrodes swell (0.35 s) and fade (0.55 s), periods 2.2–5.4 s |
| 3 | garland | chase up the tiers, half a lamp at a time, then a star flash (5.2 s cycle) |
| 4 | snowfall | soft pulses drifting down the tiers |
| 5 | heartbeat | steady tree, the star beats twice per second: left electrode, then right |
| 6 | drift | the drift list (default modes 0–5), 3 min each |
| 7 | sleep | candle + the sleep timer |
| 15 | live | frames streamed over USB by the companion app; back to the previous show 2.5 s after the last frame |
| 16–23 | custom | keyframe animations from the store (made in the companion app) |

Mode changes crossfade over 1.5 s (setting). Modes 0–5 each have a **speed**, **gain** and **offset** (settings page), so the
companion app can retune them; the defaults (×1, 100 %, 0) are the simulator's animations. Checked on the PC against the simulator's formulas (deterministic modes within 0.6 %).
* **Electrodes:** the simulator's e1 (left) is lamp pad 1 = K switch, e2 (right) is pad 2 = A switch; pad 1 is the left
  lead on every lamp (`NeonPine.kicad_pcb`). Both share the lamp's PWM window (left first), at most 100 % together.
* **Brightness:** the simulator dims with the HV rail (75–105 V). With PWM every window has to strike anew, which needs
  up to 90 V, so by default the same 1/3 … 1 range is applied to the duty and HV stays at 100 V.
  `nptest.py dim rail` switches to the simulator's rail dimming (75–105 V, kick to ≥ 95 V on start) to try it.
* Bring‑up shows, over USB only: `test` (the pin‑map sequence: each lamp's left then right electrode, then all,
  then a brightness sweep), `sweep`, `glow`.

### Touch pad TP2
| Gesture | Action |
|---|---|
| tap | next animation |
| double tap | sleep timer on/off: dims over 20 min, then off |
| triple tap | style: normal (7 ms / 400 µs, steady) ↔ retro (7 ms / 300 µs, random flicker) |
| hold > 0.45 s | brightness ramp, alternating direction |
| hold 3 s | off / on. While off, nothing else reacts (like the simulator) |

Tap and wave step through the **tap list** (setting; default the eight animations, custom ones can be added).
Touch threshold: baseline + 500 (board 1: idle ±160, touched +1100…+2000). The baseline is taken in the first 0.3 s,
so don't touch the pad while plugging in.

### Store: settings and custom animations (fw v3)
The last 1 kB of flash (0x3C00–0x3FFF, 16 × 64‑byte pages) holds:
* **Page 0 – settings** (`struct cfg_page` in `neonpine_test.c`): power‑up animation / style / brightness (with
  "remember" they follow the last touch or USB change), light sensor on/off, dimming mode, sleep minutes, tap list, drift
  list and time per animation, crossfade time, speed/gain/offset of modes 0–5, and a 16‑character tree name. Changes are
  saved 3 s after the last one (only if the page differs).
* **Pages 1–15 – custom animations** (format at the top of `anim.c`): up to 8 animations, keys of 10 × 2 four‑bit levels,
  a duration (≤ 16.4 s) and a transition (hold / linear / smooth) each, 12 bytes per key, 952 bytes in total. The blob is
  checksummed and fully validated before anything plays it; the app writes the header page last.

Writing a page stalls the CPU ~5 ms on the busy flash; boost and lamps are switched off for it (a short blink), and the
write waits 3 ms after the USB request so its status stage completes first. **Firmware images must stay below 15 360
bytes** so updates don't erase the store – `make` checks it (`size-check`); minichlink and the app only erase the image's
own pages.

RAM is the tight resource (2 kB, 460 B of it is the touch routine running from RAM): `nptest.py` / the app show the stack
never used since power‑up (board 1, after hammering USB: 168 B free).

### Light sensor (Q2 TEPT4400 – not fitted on board 1 yet, untested)
Every 100 ms all lamps would go dark for 0.5 ms while PA1 is read, giving room light without the tree's own
light (DESIGN.md: 44 mV per lux). **That blanking is commented out for now** (`ms_task`): the reading is the plain
average, so it includes the tree's own light, and waves are only detected as shadows.
* **Off in daylight** above 100 lx, **on at dusk** below 20 lx, each after 5 s. The simulator says 150 lx, but with
  the 22k load the sensor saturates at ≈ 110 lx.
* **Room‑adaptive brightness:** 0.75 … 1.0 from 0 … 31 lx (simulator formula). Without Q2 the reading is 0 lx =
  "dark room", so the tree runs at the 0.75 end.
* **Wave = next animation:** a 0.2–1.5 s shadow (lit room) or a 0.2–1.5 s rise of the tree's light reflected back
  (dark room). The thresholds are guesses until Q2 is fitted; tune `WAVE_*` in `neonpine_test.c`.
* `nptest.py autolight off` disables all of it.

### Boost control
TIM2_CH3 on PD6, default **40 kHz with a fixed 20 µs gate on-time** (I_pk ≈ 0.30 A in L11; the CR5040-331M is rated
400 mA). For each period, the main loop reads HV (PD3/A4, scaled against Vrefint) and either lets the pulse through or
skips it (pulse skipping). Measured on board 1 with a fast D1: about 0.45 W. Tune with `nptest.py ton` / `freq`
(the period always keeps ≥ 4 µs off-time so L11 empties).

### Brightness, PWM and power budget
* **PWM** runs from the main loop: 7 ms frame. Every lit electrode gets at least the **minimum on-time** (400 µs normal,
  300 µs retro) because neon needs time to strike; shorter pulses don't light reliably. Tune with
  `nptest.py pwm <frame ms> <min µs>`. `on-time = min + (frame − min) × duty` (bring‑up shows: duty = (level/255)²).
* Found by eye on board 1: 7 ms is the slowest frame without visible flicker. Shorter frames need a *longer* minimum
  (2 ms → 400 µs, 4 ms → 200 µs stable; 4 ms / 50 µs and 2 ms / 200 µs unstable), and at 1–3 ms with
  the old minimum some lamps didn't light at all.
* The ten lamps' on-windows are **staggered** across the frame (lamp i starts i/10 later), so the HV load is smooth.
  If they all switched on together, C4 couldn't buffer the block and the boost would idle for the rest of the frame.
* A lamp takes new on-times only at the start of its own window, so no pulse changes halfway.
* **Power budget:** if HV (averaged over ~16 ms) sags more than 3 V below target, every on-time is scaled down (only the
  part above the minimum, so no pulse drops below the strike time);
  within 1 V it creeps back (full in 256 ms). Status shows `power budget N/255 (LIMITING)`. With all 10 lamps at full,
  board 1 settles at ≈ 89/255 with HV ≈ 98.5 V. `nptest.py budget off` disables it (the rail then sags instead).

### Timing
The lamp edges are switched by the main loop, so long work in front of an edge would bend that pulse. The main loop
only starts work (animation steps ≤ ~125 µs, the 1 ms core, deferred jobs: touch, light, status, budget scaling) when
the next lamp edge is far enough away. The HV conversion runs in the background between passes. Measured on board 1 with
no USB traffic: lamp edges switch ≤ ~55 µs late (`nptest.py` shows "edges late ≤"). USB traffic adds up to ~1 ms
during a status read.

Protection (firmware only, the real limits are R2/D2/F1):
* **OVERVOLTAGE**: HV ≥ 115 V → boost off, lamps off.
* **NO RISE**: HV under 20 V for 1 s while boosting (open feedback divider, dead boost, short on HV+) → boost off.
  Sagging under lamp load is not a fault.
* IWDG 0.5 s.

A fault latches until `nptest.py clear` or re‑plugging.

## nptest.py
```sh
tools/nptest.py watch          # live status: HV, VDD, duty, light sensor, touch, lamp states, faults
tools/nptest.py show garland   # candle breathe twinkle garland snowfall heartbeat drift sleep | test sweep glow
tools/nptest.py sleep on       # sleep timer
tools/nptest.py style retro    # normal / retro
tools/nptest.py bright 128     # overall brightness 8-255
tools/nptest.py dim rail       # HV rail dimming like the simulator (default: duty)
tools/nptest.py autolight off  # light sensor features off
tools/nptest.py wave           # pretend a hand waved
tools/nptest.py pause on       # freeze the test sequence on the current step
tools/nptest.py hv 80          # setpoint 0–105 V (0 = boost off)
tools/nptest.py lamps all=off 3k 7a 10ac   # manual: k = left electrode, a = right, ac = both (manual mode)
tools/nptest.py mode auto      # back to the sequence (restarts at "charge")
tools/nptest.py mode off       # boost + lamps off
tools/nptest.py bootloader     # reboot into the USB bootloader
tools/nptest.py show custom0   # a custom animation from the store (custom0 .. custom7)
tools/nptest.py save           # save the settings now
```

Bench checks this enables (manufacturing.md §5):
* HV reading vs. a meter on C4: if they disagree, correct Vrefint (nominal 1.2 V) or the divider constants in `neonpine_test.c`.
* Pulsing % at 100 V with all lamps dark (no load except the 2 M divider) vs. with lamps lit – shows the boost headroom.
* Light sensor: the value with the hood/hand vs. room light. Touch: raw value vs. baseline. If tap detection is too eager
  or too deaf, set the threshold with `nptest.py touch N`.

## USB protocol (fw v3)
Feature reports on 1209:D003 (see `usb_config.h`, `../companion/neonpine_companion/device.py`):

| ID | Dir | Bytes | |
|---|---|---|---|
| 0xAA | GET | 64 | status (`struct np_status`; v3 adds caps, store pages, custom count, settings flags, store generation, free stack, chip UID) |
| 0xAB | SET | 8 | command `[0xAB][cmd][args]` – commands 1–18 as in `nptest.py`, 19 = save settings now |
| 0xAC | SET | 21 | live frame `[0xAC][left LA1–10][right LA1–10]`, 0–255 |
| 0xAE | SET/GET | 68 | store page `[0xAE][page][op/state][seq][64 bytes]`: op 1 read, 2 write, 3 apply settings without saving; the reply has state 0x80 ok / 0x81 error and echoes `seq` |
| 0xFD | SET | 7 | reboot into the bootloader (rv003usb) |

## Notes
* The board has no switchable D− pull‑up, so the host doesn't notice when the chip restarts into the bootloader. Whoever
  asks for the reboot has to keep talking to the old device until the host resets the port (Linux: after ~1 s of errors,
  while the hidraw node is open) – minichlink and the app both do that.
* Pinned libraries: rv003usb `16d5cd4` with ch32fun `1e4887e` (see `Makefile`); `bootloader/bootloader.c` and the linker script are
  unmodified copies from that commit, with the configuration in `bootloader/usb_config.h`.
* VID:PID 1209:D003 / 1209:B003 are rv003usb's shared pid.codes IDs, fine for development. A product needs its own PID.
* After flashing over SWD the chip stays in whatever state minichlink leaves it; power‑cycle if USB doesn't enumerate.
