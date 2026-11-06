# rv003usb USB bootloader for NeonPine (lives in the 1920-byte boot area at 0x1FFFF000).
# bootloader.c / the .ld are copies of rv003usb/bootloader at the commit pinned in ../Makefile;
# only usb_config.h differs (D+ = PD2, D- = PD4, no D- pull-up pin).
# Flashed once over SWD (WCH-LinkE on the J2 pogo pads): `make flash` from ../ does option bytes + this.

all : build

TARGET:=bootloader
RV003USB:=../deps/rv003usb
CH32FUN:=$(RV003USB)/ch32fun/ch32fun
TARGET_MCU:=CH32V003

ADDITIONAL_C_FILES+=$(RV003USB)/rv003usb/rv003usb.S
SYSTEM_C:=
EXTRA_CFLAGS:=-I. -I$(RV003USB)/lib -DUSE_TINY_BOOT -I$(RV003USB)/rv003usb

LINKER_SCRIPT:=ch32v003fun-usb-bootloader.ld
WRITE_SECTION:=bootloader
FLASH_COMMAND=$(MINICHLINK)/minichlink -a -w $(TARGET).bin $(WRITE_SECTION) -B

include $(CH32FUN)/ch32fun.mk

flash : cv_flash
clean : cv_clean
