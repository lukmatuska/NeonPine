// NeonPine bootloader installer – for programmers that can only write main flash (PicoRVD over GDB).
//
// Load this into user flash. At every start it makes sure that
//   1. the boot area (0x1FFFF000, 1920 B) holds ../bootloader/bootloader.bin, and
//   2. the option bytes are RDPR = A5 (no read protection), USER = FF: start in the boot area,
//      NRST disabled (PD7 = SR_DATA), software IWDG, no reset on stop/standby  (= minichlink +a55aff00),
// writing them only where they differ, then reboots into the USB bootloader (1209:B003).
// From there `make flash` puts the real firmware over this one. Until then the board keeps
// cycling bootloader (5 s) -> installer (verify only) -> bootloader.
//
// Same register sequences as minichlink (DefaultWriteBinaryBlob / DefaultErase) and the ch32fun
// optionbytes example, run by the CPU itself instead of through the debug module.
//
// Result for a debugger: `p/x install_result` (see enum below), plus install_statr / install_ctlr / install_page.

#include "ch32fun.h"
#include "bootloader_image.h"  // generated: bootloader_image[], BOOTLOADER_IMAGE_SIZE

#define BOOT_AREA      0x1FFFF000u
#define BOOT_AREA_SIZE 1920u
#define PAGE           64u

#define STATR_WRPRTERR (1u << 4)
#define STATR_EOP      (1u << 5)
#define STATR_MODE     (1u << 14)  // boot into the boot area at the next software reset
#define STATR_BOOTLOCK (1u << 15)

#define OB_USER_WANTED ( OB_STARTMODE_BOOT | OB_RST_NoEN | OB_STDBY_NoRST | OB_STOP_NoRST | OB_IWDG_SW | 0xc0 )  // 0xFF

enum {
	RESULT_RUNNING       = 0x00,
	RESULT_INSTALLED     = 0x01,  // something was written, all verified
	RESULT_ALREADY_OK    = 0x02,  // nothing to do
	ERR_FLASH_LOCKED     = 0xe1,  // KEYR / MODEKEYR unlock did not clear LOCK
	ERR_BOOT_LOCKED      = 0xe2,  // BOOT_MODEKEYR did not clear BOOT_LOCK
	ERR_BOOT_WRITE       = 0xe3,  // WRPRTERR or timeout while erasing / programming the boot area
	ERR_BOOT_VERIFY      = 0xe4,  // boot area read back different
	ERR_OB_LOCKED        = 0xe5,  // OBKEYR did not set OPTWRE
	ERR_OB_WRITE         = 0xe6,
	ERR_OB_VERIFY        = 0xe7,
	ERR_IMAGE            = 0xe8,  // embedded image too big
};

volatile uint32_t install_result;
volatile uint32_t install_statr, install_ctlr, install_page;

// Wanted content of the boot area: the image, zero-padded to 1920 bytes.
static uint32_t want_word( uint32_t off )
{
	uint32_t w = 0;
	for( uint32_t b = 0; b < 4; b++ )
		if( off + b < BOOTLOADER_IMAGE_SIZE ) w |= (uint32_t)bootloader_image[off + b] << ( 8 * b );
	return w;
}

static int wait_flash( void )
{
	for( uint32_t t = 0; t < 2000000; t++ )  // >= 40 ms; a page erase/program takes ~3 ms
		if( !( FLASH->STATR & FLASH_STATR_BSY ) )
			return 0;
	return -1;
}

static int flash_error( void )
{
	install_statr = FLASH->STATR;
	install_ctlr = FLASH->CTLR;
	return ( install_statr & STATR_WRPRTERR ) != 0;
}

static void clear_flags( void )
{
	// EOP / WRPRTERR are write-1-to-clear; keep MODE as it is.
	FLASH->STATR = ( FLASH->STATR & STATR_MODE ) | STATR_EOP | STATR_WRPRTERR;
}

static int unlock_all( void )
{
	FLASH->KEYR = FLASH_KEY1;
	FLASH->KEYR = FLASH_KEY2;
	FLASH->OBKEYR = FLASH_KEY1;
	FLASH->OBKEYR = FLASH_KEY2;
	FLASH->MODEKEYR = FLASH_KEY1;  // fast (64 B page) erase / program
	FLASH->MODEKEYR = FLASH_KEY2;
	FLASH->BOOT_MODEKEYR = FLASH_KEY1;  // boot area
	FLASH->BOOT_MODEKEYR = FLASH_KEY2;
	install_statr = FLASH->STATR;
	install_ctlr = FLASH->CTLR;
	if( install_ctlr & 0x8080 ) return ERR_FLASH_LOCKED;  // LOCK / fast-mode lock still set
	if( install_statr & STATR_BOOTLOCK ) return ERR_BOOT_LOCKED;
	return 0;
}

static int boot_page_matches( uint32_t off )
{
	const volatile uint32_t * have = (const volatile uint32_t *)( BOOT_AREA + off );
	for( uint32_t i = 0; i < PAGE / 4; i++ )
		if( have[i] != want_word( off + 4 * i ) ) return 0;
	return 1;
}

static int write_boot_page( uint32_t off )
{
	uint32_t addr = BOOT_AREA + off;
	install_page = addr;
	clear_flags();

	// Fast page erase (64 B)
	FLASH->CTLR = CR_PAGE_ER;
	FLASH->ADDR = addr;
	FLASH->CTLR = CR_PAGE_ER | CR_STRT_Set;
	if( wait_flash() || flash_error() ) { FLASH->CTLR = 0; return ERR_BOOT_WRITE; }

	// Fast page program: reset the page buffer, load 16 words (BUF_LOAD after each), then start.
	FLASH->CTLR = CR_PAGE_PG;
	FLASH->CTLR = CR_PAGE_PG | CR_BUF_RST;
	if( wait_flash() ) { FLASH->CTLR = 0; return ERR_BOOT_WRITE; }
	for( uint32_t i = 0; i < PAGE / 4; i++ )
	{
		( (volatile uint32_t *)addr )[i] = want_word( off + 4 * i );
		FLASH->CTLR = CR_PAGE_PG | CR_BUF_LOAD;
		if( wait_flash() ) { FLASH->CTLR = 0; return ERR_BOOT_WRITE; }
	}
	FLASH->ADDR = addr;
	FLASH->CTLR = CR_PAGE_PG | CR_STRT_Set;
	if( wait_flash() || flash_error() ) { FLASH->CTLR = 0; return ERR_BOOT_WRITE; }
	FLASH->CTLR = 0;

	return boot_page_matches( off ) ? 0 : ERR_BOOT_VERIFY;
}

static int ob_ok( void )
{
	return ( OB->RDPR & 0xff ) == RDP_Key && ( OB->USER & 0xff ) == OB_USER_WANTED;
}

static int write_option_bytes( void )
{
	// Keep the user data bytes and the write protection as they are.
	uint16_t data0 = OB->Data0 & 0xff, data1 = OB->Data1 & 0xff;
	uint16_t wrpr0 = OB->WRPR0 & 0xff, wrpr1 = OB->WRPR1 & 0xff;

	// Plain CTLR writes (the boot page writes) clear OPTWRE, so unlock it again right here.
	FLASH->OBKEYR = FLASH_KEY1;
	FLASH->OBKEYR = FLASH_KEY2;
	if( !( FLASH->CTLR & FLASH_CTLR_OPTWRE ) ) return ERR_OB_LOCKED;
	clear_flags();

	FLASH->CTLR = CR_OPTER_Set | FLASH_CTLR_OPTWRE;
	FLASH->CTLR = CR_OPTER_Set | FLASH_CTLR_OPTWRE | CR_STRT_Set;
	if( wait_flash() || flash_error() ) { FLASH->CTLR = 0; return ERR_OB_WRITE; }

	// RDPR first: until it is back to A5 the chip counts as read-protected.
	// Each half-word write programs one byte; the hardware adds the complement byte.
	const struct { volatile uint16_t * a; uint16_t v; } w[] = {
		{ &OB->RDPR, RDP_Key }, { &OB->USER, OB_USER_WANTED },
		{ &OB->Data0, data0 }, { &OB->Data1, data1 }, { &OB->WRPR0, wrpr0 }, { &OB->WRPR1, wrpr1 },
	};
	for( unsigned i = 0; i < sizeof( w ) / sizeof( w[0] ); i++ )
	{
		FLASH->CTLR = CR_OPTPG_Set | FLASH_CTLR_OPTWRE;
		*w[i].a = w[i].v;
		if( wait_flash() || flash_error() ) { FLASH->CTLR = 0; return ERR_OB_WRITE; }
	}
	FLASH->CTLR = 0;

	return ob_ok() ? 0 : ERR_OB_VERIFY;
}

static int install( void )
{
	if( BOOTLOADER_IMAGE_SIZE > BOOT_AREA_SIZE ) return ERR_IMAGE;

	int wrote = 0;
	int need_boot = 0;
	for( uint32_t off = 0; off < BOOT_AREA_SIZE; off += PAGE )
		if( !boot_page_matches( off ) ) need_boot = 1;
	if( !need_boot && ob_ok() ) return RESULT_ALREADY_OK;

	int r = unlock_all();
	if( r ) return r;

	for( uint32_t off = 0; off < BOOT_AREA_SIZE; off += PAGE )
	{
		if( boot_page_matches( off ) ) continue;
		if( ( r = write_boot_page( off ) ) ) return r;
		wrote = 1;
	}

	if( !ob_ok() )
	{
		if( ( r = write_option_bytes() ) ) return r;
		wrote = 1;
	}
	return wrote ? RESULT_INSTALLED : RESULT_ALREADY_OK;
}

static void reboot_into_bootloader( void )
{
	// Force USB re-enumeration (D- low through R14, like the bootloader does before starting the app).
	funPinMode( PD4, GPIO_CFGLR_OUT_10Mhz_PP );
	GPIOD->BSHR = 1u << ( 4 + 16 );
	Delay_Ms( 50 );

	FLASH->BOOT_MODEKEYR = FLASH_KEY1;
	FLASH->BOOT_MODEKEYR = FLASH_KEY2;
	FLASH->STATR = STATR_MODE;  // next software reset starts the boot area
	FLASH->CTLR = CR_LOCK_Set;
	RCC->RSTSCKR |= 0x1000000;  // clear reset flags
	PFIC->SCTLR = 1u << 31;     // system reset
	while( 1 );
}

int main()
{
	SystemInit();
	funGpioInitAll();

	// Keep the HV side dead: boost gate (PD6) and the lamp switches on PC0-PC6 / PD0 low.
	// (R2 holds the gate low anyway; the 595 outputs stay random, which is harmless without HV.)
	GPIOD->BSHR = ( ( 1u << 6 ) | 1u ) << 16;
	funPinMode( PD6, GPIO_CFGLR_OUT_10Mhz_PP );
	funPinMode( PD0, GPIO_CFGLR_OUT_10Mhz_PP );
	GPIOC->BSHR = 0x7fu << 16;
	GPIOC->CFGLR = ( GPIOC->CFGLR & 0xf0000000 ) | ( 0x01111111 * GPIO_CFGLR_OUT_10Mhz_PP );

	Delay_Ms( 100 );  // let the supply settle before touching flash

	install_result = RESULT_RUNNING;
	install_result = install();
	FLASH->CTLR = CR_LOCK_Set;

	if( install_result == RESULT_INSTALLED || install_result == RESULT_ALREADY_OK )
		reboot_into_bootloader();

	while( 1 );  // failed: stay here for the debugger; the next power-up retries
}
