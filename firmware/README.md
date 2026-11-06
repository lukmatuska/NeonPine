# NeonPine firmware

| Dir | What |
|---|---|
| `bootloader/` | [rv003usb](https://github.com/cnlohr/rv003usb) USB HID bootloader (1209:B003) in the CH32V003's 1920‑byte boot area, configured for D+ = PD2, D− = PD4, no D− pull‑up pin |
| `neonpine_test/` | Bring‑up test firmware (1209:D003): HV boost regulation, lamp/pin‑map self‑test, sensors, status over USB |
| `installer/` | Writes the bootloader + option bytes from the chip itself, for programmers that only write main flash (PicoRVD) |
| `tools/nptest.py` | Talks to the test firmware over USB (Linux hidraw, no pip packages) |
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
`minichlink -C b003boot` finds the running test firmware (1209:D003) and sends it the reboot feature report. The board
re‑enumerates as the bootloader (1209:B003), minichlink writes the new image and starts it (`-b`).

**If the application is broken** (it doesn't enumerate, so minichlink can't reboot it), use the bootloader window instead:
after every power‑up the bootloader waits ≈ 5 s (lamps dark) before it starts the application. Run this and then plug the board in:
```sh
until make -C neonpine_test flash; do sleep 0.3; done
```
The SWD path (`make flash-swd`, or `make first-flash` again) always works.

## What the test firmware does
After the ≈ 5 s bootloader wait:

1. **Charge** (1.5 s): boost soft‑starts to 100 V (0.2 V/ms), all lamps dark.
2. **Each lamp on its own**, LA1 → LA10, for 0.7 s on the **K side** (lamp pad 1 glows) and then 0.7 s on the **A side** (pad 2 glows),
   each after 0.4 s dark so HV is back at the setpoint when the lamp has to strike.
   This walks every switch once, so it checks the pin map (mcu‑netlist.md tables): a wrong lamp or a wrong electrode means a
   swapped net, assembly fault or table error.
3. **All K** 2 s, **all A** 2 s, **all AC** 3 s (each lamp alternates electrodes at 100 Hz, so both glow).
   With all ten lamps on, the load (≈ 1 W at 105 V, DESIGN.md §2.3) is above what the boost delivers, so expect HV to sag
   and lamps to flicker or drop out. The status shows how far HV sags – that measures the real boost capability.
4. Repeat from step 2.

**TP2 (trunk) tap** pauses / resumes the sequence on the current step. The baseline is taken during the first 0.3 s, so
don't touch the pad while plugging in.

### Boost control
TIM2_CH3 on PD6 runs at 30 kHz with a **fixed gate on‑time** (default 15 µs → I_pk ≈ 0.23 A in 330 µH, inside the
300 mA rating of the SWPA6028). For each period, the main loop reads HV (PD3/A4, scaled against Vrefint) and either lets
the pulse through or skips it (pulse skipping). The on‑time can be raised to 20 µs (the 60 % clamp) with `nptest.py ton 20`.
Pulse skipping can make L11 audibly whine – that's expected in this test firmware.

Protection (firmware only, the real limits are R2/D2/F1):
* **OVERVOLTAGE**: HV ≥ 115 V → boost off, lamps off.
* **NO RISE**: HV under 20 V for 1 s while boosting (open feedback divider, dead boost, short on HV+) → boost off.
  Sagging under lamp load is not a fault.
* IWDG 0.5 s.

A fault latches until `nptest.py clear` or re‑plugging.

## nptest.py
```sh
tools/nptest.py watch          # live status: HV, VDD, duty, light sensor, touch, lamp states, faults
tools/nptest.py pause on       # freeze the sequence on the current step
tools/nptest.py hv 80          # setpoint 0–105 V (0 = boost off)
tools/nptest.py lamps all=off 3k 7a 10ac   # manual lamp states (switches to manual mode)
tools/nptest.py mode auto      # back to the sequence (restarts at "charge")
tools/nptest.py mode off       # boost + lamps off
tools/nptest.py bootloader     # reboot into the USB bootloader
```

Bench checks this enables (manufacturing.md §5):
* HV reading vs. a meter on C4: if they disagree, correct Vrefint (nominal 1.2 V) or the divider constants in `neonpine_test.c`.
* Pulsing % at 100 V with all lamps dark (no load except the 2 M divider) vs. with lamps lit – shows the boost headroom.
* Light sensor: the value with the hood/hand vs. room light. Touch: raw value vs. baseline. If tap detection is too eager
  or too deaf, set the threshold with `nptest.py touch N`.

## Notes
* Pinned libraries: rv003usb `16d5cd4` with ch32fun `1e4887e` (see `Makefile`); `bootloader/bootloader.c` and the linker script are
  unmodified copies from that commit, with the configuration in `bootloader/usb_config.h`.
* VID:PID 1209:D003 / 1209:B003 are rv003usb's shared pid.codes IDs, fine for development. A product needs its own PID.
* After flashing over SWD the chip stays in whatever state minichlink leaves it; power‑cycle if USB doesn't enumerate.
