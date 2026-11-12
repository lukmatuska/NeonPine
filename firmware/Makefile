# NeonPine firmware – top level. See README.md.
#
#   make deps              fetch rv003usb + ch32fun (pinned) into deps/
#   make                   build bootloader + firmware + minichlink
#   make first-flash       SWD (WCH-LinkE on J2), once per board: option bytes, USB bootloader, firmware
#   make pico              PicoRVD instead of a WCH-LinkE: loads the bootloader installer (PORT=/dev/ttyACM0)
#   make flash             USB: flash the firmware through the bootloader
#   make flash-swd         SWD: flash only the firmware

RV003USB_URL := https://github.com/cnlohr/rv003usb
# 2026-10-30, ch32fun submodule at 1e4887e; bootloader/bootloader.c is a copy from this commit
RV003USB_REV := 16d5cd4

DEPS := deps/rv003usb/ch32fun/ch32fun/ch32fun.mk
MINICHLINK := deps/rv003usb/ch32fun/minichlink/minichlink

# Option bytes: a5 5a = no read protection; USER 0xff = boot into the bootloader area (START_MODE),
# NRST disabled (RST_MODE = GPIO: PD7 drives SR_DATA), software IWDG, no reset on stop/standby.
OPTION_BYTES := +a55aff00

all : build

$(DEPS) :
	git clone $(RV003USB_URL) deps/rv003usb
	git -C deps/rv003usb checkout -q $(RV003USB_REV)
	git -C deps/rv003usb submodule update --init ch32fun

deps : $(DEPS)

$(MINICHLINK) : $(DEPS)
	$(MAKE) -C $(dir $(MINICHLINK)) minichlink

build : $(DEPS) $(MINICHLINK)
	$(MAKE) -C bootloader build
	$(MAKE) -C neonpine build
	$(MAKE) -C installer build

first-flash : build
	$(MINICHLINK) -w $(OPTION_BYTES) option
	$(MINICHLINK) -a -w bootloader/bootloader.bin bootloader -B
	$(MINICHLINK) -w neonpine/neonpine.bin flash -b

pico : build
	$(MAKE) -C installer pico

pico-result : build
	$(MAKE) -C installer result

flash : build
	$(MAKE) -C neonpine flash

flash-swd : build
	$(MAKE) -C neonpine flash-swd

clean :
	$(MAKE) -C bootloader clean
	$(MAKE) -C neonpine clean
	$(MAKE) -C installer clean

.PHONY : all deps build first-flash pico pico-result flash flash-swd clean
