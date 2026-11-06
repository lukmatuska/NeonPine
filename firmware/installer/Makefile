# Bootloader installer for programmers that only write main flash (PicoRVD). See ../README.md.
#   make                      build installer.elf (embeds ../bootloader/bootloader.bin)
#   make pico PORT=/dev/ttyACM0   load it through PicoRVD's GDB server
#   make result PORT=...      read install_result back through PicoRVD

all : build

TARGET:=installer
RV003USB:=../deps/rv003usb
CH32FUN:=$(RV003USB)/ch32fun/ch32fun
TARGET_MCU:=CH32V003
EXTRA_CFLAGS:=-I.
EXTRA_ELF_DEPENDENCIES:=bootloader_image.h
PORT?=/dev/ttyACM0
GDB?=riscv64-elf-gdb

include $(CH32FUN)/ch32fun.mk

../bootloader/bootloader.bin :
	$(MAKE) -C ../bootloader build

bootloader_image.h : ../bootloader/bootloader.bin
	python3 -c "import sys; d=open(sys.argv[1],'rb').read(); \
	print('// generated from', sys.argv[1], '- do not edit'); \
	print('#define BOOTLOADER_IMAGE_SIZE %du' % len(d)); \
	print('static const uint8_t bootloader_image[] = {'); \
	[print('\t' + ', '.join('0x%02x' % b for b in d[i:i+16]) + ',') for i in range(0, len(d), 16)]; \
	print('};')" $< > $@

pico : $(TARGET).elf
	$(GDB) -batch -ex "target extended-remote $(PORT)" -ex load -ex "monitor reset" -ex detach $<

# PicoRVD answers every memory read with the data of the *previous* read request, so each value is
# read twice: a silent dummy read, then the printed one.
rd=-ex "set \$$d = *(unsigned*)($(1))" -ex "printf \"%08x  $(2)\\n\", *(unsigned*)($(1))"

result : $(TARGET).elf
	$(GDB) -batch -ex "target extended-remote $(PORT)" -ex "set mem inaccessible-by-default off" \
		$(call rd,&install_result,install_result) $(call rd,&install_statr,install_statr) \
		$(call rd,&install_ctlr,install_ctlr) $(call rd,&install_page,install_page) \
		$(call rd,0x1ffff800,option bytes RDPR/USER - want 00ff5aa5) \
		$(call rd,0x1ffff000,boot area word 0) -ex detach $<

clean : cv_clean
	rm -f bootloader_image.h

.PHONY : pico result
