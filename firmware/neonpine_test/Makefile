# NeonPine test firmware (user flash at 0x08000000).
#   make            build neonpine_test.bin
#   make flash      flash over USB through the rv003usb bootloader (the running app is rebooted into it)
#   make flash-swd  flash over SWD with a WCH-LinkE on the J2 pogo pads

all : build

TARGET:=neonpine_test
RV003USB:=../deps/rv003usb
CH32FUN:=$(RV003USB)/ch32fun/ch32fun
TARGET_MCU:=CH32V003

ADDITIONAL_C_FILES+=$(RV003USB)/rv003usb/rv003usb.S $(RV003USB)/rv003usb/rv003usb.c anim.c
EXTRA_CFLAGS:=-I. -I$(RV003USB)/lib -I$(RV003USB)/rv003usb -I$(CH32FUN)/../extralibs

# -C b003boot: talk to the USB bootloader (1209:B003); minichlink reboots a running app (1209:D003) into it first.
FLASH_COMMAND=$(MINICHLINK)/minichlink -C b003boot -w $(TARGET).bin flash -b

include $(CH32FUN)/ch32fun.mk

flash : cv_flash

flash-swd : $(TARGET).bin $(MINICHLINK)/minichlink
	$(MINICHLINK)/minichlink -w $< flash -b

clean : cv_clean
