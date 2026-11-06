// NeonPine bring-up test firmware – CH32V003F4P6, ch32fun + rv003usb.
//
// Pin map and lamp tables: docs/mcu-netlist.md, hardware: DESIGN.md §2.
//
// * HV boost: PD6 = TIM2_CH3 (full remap) at 30 kHz. Pulse skipping against the PD3 (A4) feedback:
//   every main-loop pass reads HV and either lets the next gate pulse through or skips it. The pulse
//   width is fixed (default 15 us -> I_pk = 5 V * 15 us / 330 uH = 0.23 A), so L11 stays below I_sat
//   whatever the load does. Soft start 0.2 V/ms.
// * Protection (firmware only; the hardware limits are R2, D2, F1): overvoltage trip, "no rise" trip
//   (HV below 20 V for 1 s while boosting: open feedback, dead boost, shorted rail), IWDG.
//   A rail that only sags under lamp load is not a fault – the status shows how far it sags.
// * Auto test sequence: each lamp's pad-1 (K) then pad-2 (A) electrode on its own, then all K, all A,
//   all AC (both electrodes, 100 Hz) – checks every switch and the whole pin map – then a brightness
//   sweep of all lamps (dark -> full -> dark).
// * Brightness: PWM with a 1 ms frame, run from the main loop (no ISR next to rv003usb), gamma ~2.
// * TP2 touch: tap pauses / resumes the sequence.
// * USB HID 1209:D003 with feature reports: 0xAA status, 0xAB commands (../tools/nptest.py).
//   minichlink reboots it into the rv003usb bootloader by itself (report 0xFD) before flashing.

#include "ch32fun.h"
#include <string.h>
#include "rv003usb.h"
#include "ch32v003_touch.h"

#define FW_VERSION 1

// ---- Boost -------------------------------------------------------------------------------------
#define BOOST_PERIOD      1600     // TIM2 ticks at 48 MHz -> 30 kHz (default, nptest.py freq changes it)
#define PERIOD_MAX        9600     // 5 kHz
#define PERIOD_MARGIN     192      // >= 4 us off-time per period: L11 must empty (DCM) before the next pulse
#define TON_DEFAULT       720      // gate on-time, ticks: 15 us -> I_pk 0.23 A
#define TON_MIN           48       // 1 us
#define TON_LIMIT         960      // 20 us = the 60 % duty clamp of DESIGN.md §2.2 (I_pk 0.30 A)
#define HV_DEFAULT_V      100      // test setpoint; NEON-3 strikes at <= 90 V
#define HV_MAX_V          105
#define HV_TRIP_MV        115000   // overvoltage trip (D2 clamps at 111-123 V)
#define HV_RAMP_MV_PER_MS 200      // soft start
#define NORISE_MS         1000     // HV below NORISE_MV for this long while boosting -> fault
#define NORISE_MV         20000
// Feedback divider: R5 + R6 = 2 M on top, R7 = 39 k to GND (105 V -> 2.0 V)
#define DIV_TOP_K         2000
#define DIV_BOT_K         39

enum { FAULT_NONE = 0, FAULT_OVERVOLTAGE = 1, FAULT_NO_RISE = 2 };

// ---- GPIO --------------------------------------------------------------------------------------
#define SR_DATA_D   (1u << 7)  // PD7 (NRST pin -> option bytes must set RST_MODE = GPIO)
#define SR_LATCH_D  (1u << 5)  // PD5
#define SR_CLK_C    (1u << 7)  // PC7 (also TP3)

#define ADC_CH_TOUCH 0  // PA2, TP2 through R11
#define ADC_CH_LDR   1  // PA1, TEPT4400 emitter, 22k to GND
#define ADC_CH_VFB   4  // PD3, HV divider
#define ADC_CH_VREF  8  // internal 1.2 V reference

// ---- Lamps -------------------------------------------------------------------------------------
// The lamp switches are collected in one 32-bit output word:
// bits 0-15 = 74HC595 chain word (U3 QH = bit 15 ... U2 QA = bit 0), bits 16-22 = PC0-PC6, bit 24 = PD0.
#define SW_SR(b) (b)
#define SW_PC(b) (16 + (b))
#define SW_PD(b) (24 + (b))
#define OUT_PC_MASK 0x7f  // PC7 is SR_CLK, not a lamp switch
#define OUT_PD_MASK 0x01

// {K side = lamp pad 1 (net LAMPn), A side = lamp pad 2 (net LAMPAn)} – docs/mcu-netlist.md "Lamps"
static const uint8_t lamp_sw[10][2] = {
	{ SW_SR(5),  SW_SR(4)  }, // LA1
	{ SW_PC(2),  SW_SR(3)  }, // LA2
	{ SW_PC(4),  SW_SR(7)  }, // LA3
	{ SW_PC(1),  SW_SR(2)  }, // LA4
	{ SW_PC(3),  SW_SR(6)  }, // LA5
	{ SW_PC(6),  SW_SR(15) }, // LA6
	{ SW_PC(0),  SW_SR(1)  }, // LA7
	{ SW_PD(0),  SW_SR(0)  }, // LA8
	{ SW_PC(5),  SW_SR(13) }, // LA9
	{ SW_SR(12), SW_SR(11) }, // LA10
};

// Lamp state, 2 bits per lamp (LA1 = bits 1:0)
enum { LAMP_OFF = 0, LAMP_K = 1, LAMP_A = 2, LAMP_AC = 3 };
#define ALL_LAMPS(s) ( (s) * 0x55555u )

// ---- Modes / sequence --------------------------------------------------------------------------
enum { MODE_OFF = 0, MODE_AUTO = 1, MODE_MANUAL = 2 };

#define SEQ_CHARGE   0   // HV up, all dark
#define SEQ_LAMP0    1   // 1..20: lamp (s-1)/2, K then A
#define SEQ_ALL_K    21
#define SEQ_ALL_A    22
#define SEQ_ALL_AC   23
#define SEQ_SWEEP    24  // all lamps AC, brightness 0 -> 255 -> 0
#define SEQ_STEPS    25
#define SWEEP_MS     8000

#define PWM_FRAME    DELAY_MS_TIME  // 1 ms in SysTick ticks
#define AC_FRAMES    5              // AC: switch electrodes every 5 frames = 100 Hz
#define SEQ_GAP_MS   400  // dark before each single-lamp step: HV recovers, so every lamp strikes from the full setpoint

// ---- USB protocol (feature reports, see ../tools/nptest.py) ------------------------------------
enum {
	CMD_MODE = 1,         // [2] = mode
	CMD_HV = 2,           // [2] = volts (0 = boost off)
	CMD_LAMPS = 3,        // [2..5] = lamp word (LE), switches to manual mode
	CMD_CLEAR_FAULT = 4,
	CMD_TON = 5,          // [2..3] = gate on-time in 48 MHz ticks (LE)
	CMD_PAUSE = 6,        // [2] = 0 run / 1 pause
	CMD_TOUCH_DELTA = 7,  // [2..3] = touch threshold above baseline (0 = auto)
	CMD_PERIOD = 8,       // [2..3] = boost period in 48 MHz ticks (LE)
	CMD_LEVEL = 9,        // [2] = brightness 0-255 in manual mode
};

struct np_status {
	uint8_t  report_id;   //  0 = NP_REPORT_STATUS
	uint8_t  fw_version;  //  1
	uint8_t  mode;        //  2
	uint8_t  step;        //  3 sequence step
	uint8_t  fault;       //  4
	uint8_t  flags;       //  5 b0 touched, b1 paused, b2 boost running
	uint8_t  hv_set;      //  6 V
	uint8_t  period_us;   //  7 boost period, us
	uint16_t hv_cv;       //  8 measured HV, 10 mV units
	uint16_t vdd_mv;      // 10 from Vrefint
	uint16_t adc_vfb;     // 12
	uint16_t adc_ldr;     // 14
	uint16_t touch;       // 16 raw touch sum
	uint16_t touch_base;  // 18
	uint16_t ton;         // 20 gate on-time, ticks
	uint16_t duty_pm;     // 22 share of boost periods that pulsed, per mille
	uint32_t uptime_ms;   // 24
	uint32_t lamps;       // 28 lamp word currently shown
	uint8_t  level;       // 32 brightness 0-255
	uint8_t  reserved[3]; // 33
} __attribute__((packed, aligned(4)));
_Static_assert( sizeof( struct np_status ) == 36, "status report is 35 bytes + id (usb_config.h)" );

static struct np_status status;
static uint8_t cmd_buf[8] __attribute__((aligned(4)));
static volatile uint8_t cmd_pending;
static uint8_t usb_set_report_id;

// ---- State -------------------------------------------------------------------------------------
static uint8_t mode = MODE_AUTO, step, paused, fault;
static uint16_t step_ms;
static uint32_t manual_lamps;
static uint32_t lamps_shown;
static uint8_t ac_phase;
static uint8_t manual_level = 255, level;
static uint32_t outs_frame[2];             // lamp outputs for AC phase 0 / 1 (set every ms)
static uint32_t pwm_on_ticks = PWM_FRAME;  // lit part of each PWM frame

static uint8_t hv_set_v = HV_DEFAULT_V;
static uint16_t ton = TON_DEFAULT;
static uint16_t period = BOOST_PERIOD;
static uint8_t boost_on;
static uint32_t ramp_mv;         // soft-start setpoint
static uint32_t vdd_mv = 5000;
static int vfb_target, vfb_trip; // in ADC counts
static int vfb_last;
static uint16_t low_ms;          // time spent below half the setpoint
static uint32_t passes, pulse_passes;

static uint16_t touch_raw, touch_base, touch_delta;
static uint8_t touched, touch_count;

static uint32_t outs_now = 0xffffffff;

// ---- Lamp outputs ------------------------------------------------------------------------------

static inline void short_delay( void )
{
	__asm__ volatile( "nop\nnop\nnop\nnop" );  // 74HC595 setup / pulse width (>= 25 ns at 4.5 V)
}

static void outs_write( uint32_t o )
{
	// 16 bits, MSB first: after 16 clocks bit 15 sits in U3 QH, bit 0 in U2 QA.
	for( int b = 15; b >= 0; b-- )
	{
		GPIOD->BSHR = ( ( o >> b ) & 1 ) ? SR_DATA_D : ( SR_DATA_D << 16 );
		short_delay();
		GPIOC->BSHR = SR_CLK_C;
		short_delay();
		GPIOC->BSHR = SR_CLK_C << 16;
	}
	GPIOD->BSHR = SR_LATCH_D;
	short_delay();
	GPIOD->BSHR = SR_LATCH_D << 16;

	uint32_t pc = ( o >> 16 ) & OUT_PC_MASK;
	uint32_t pd = ( o >> 24 ) & OUT_PD_MASK;
	GPIOC->BSHR = pc | ( ( ~pc & OUT_PC_MASK ) << 16 );
	GPIOD->BSHR = pd | ( ( ~pd & OUT_PD_MASK ) << 16 );
}

static void outs_set( uint32_t o )
{
	if( o == outs_now ) return;
	// Break before make: switch off what goes off first, so a lamp moving K <-> A never has both
	// of its switches on, not even for the microseconds between the 595 latch and the port write.
	uint32_t mid = outs_now & o;
	if( mid != outs_now ) outs_write( mid );
	outs_write( o );
	outs_now = o;
}

static uint32_t lamps_to_outs( uint32_t lamps, int phase )
{
	uint32_t o = 0;
	for( int i = 0; i < 10; i++ )
	{
		int s = ( lamps >> ( 2 * i ) ) & 3;
		if( s == LAMP_AC ) s = phase ? LAMP_A : LAMP_K;
		if( s == LAMP_K ) o |= 1u << lamp_sw[i][0];
		else if( s == LAMP_A ) o |= 1u << lamp_sw[i][1];
	}
	return o;
}

// ---- ADC ---------------------------------------------------------------------------------------

static void adc_init( void )
{
	RCC->APB2PCENR |= RCC_APB2Periph_ADC1;
	RCC->APB2PRSTR |= RCC_APB2Periph_ADC1;
	RCC->APB2PRSTR &= ~RCC_APB2Periph_ADC1;
	InitTouchADC();  // ADCCLK = 24 MHz, software trigger, calibration
}

static int adc_read( int ch )
{
	// ReadTouchPin() rewrites SAMPTR2 and CTLR2, so set both every time.
	ADC1->RSQR3 = ch;
	ADC1->SAMPTR2 = ADC_SampleTime_241Cycles << ( 3 * ch );  // 10 us: the divider node is high impedance
	ADC1->CTLR2 = ADC_ADON | ADC_EXTSEL | ADC_TSVREFE | ADC_SWSTART;
	while( !( ADC1->STATR & ADC_EOC ) );
	return ADC1->RDATAR;
}

static void measure_vdd( void )
{
	adc_read( ADC_CH_VREF );  // TSVREFE may just have been switched back on
	int sum = 0;
	for( int i = 0; i < 8; i++ ) sum += adc_read( ADC_CH_VREF );
	if( sum < 8 ) return;
	uint32_t mv = 1200u * 1023u * 8u / sum;  // Vrefint nominal 1.2 V
	if( mv < 4000 || mv > 5600 ) mv = 5000;  // implausible -> assume nominal USB 5 V
	vdd_mv = mv;
}

static uint32_t vfb_to_mv( int counts )
{
	return (uint32_t)counts * vdd_mv / 1023u * ( DIV_TOP_K + DIV_BOT_K ) / DIV_BOT_K;
}

static int mv_to_vfb( uint32_t mv )
{
	return mv * DIV_BOT_K / ( DIV_TOP_K + DIV_BOT_K ) * 1023u / vdd_mv;
}

// ---- Boost -------------------------------------------------------------------------------------

static void boost_init( void )
{
	RCC->APB1PCENR |= RCC_APB1Periph_TIM2;
	AFIO->PCFR1 = ( AFIO->PCFR1 & ~AFIO_PCFR1_TIM2_REMAP ) | AFIO_PCFR1_TIM2_REMAP_FULLREMAP;  // CH3 -> PD6

	TIM2->PSC = 0;
	TIM2->ATRLR = BOOST_PERIOD - 1;
	TIM2->CH3CVR = 0;                                            // gate low
	TIM2->CHCTLR2 = TIM_OC3M_2 | TIM_OC3M_1 | TIM_OC3PE;         // PWM mode 1, preloaded
	TIM2->CCER = TIM_CC3E;                                       // only CH3: CH1/CH2/CH4 (PC1/PC7/PD5) stay GPIO
	TIM2->CTLR1 = TIM_ARPE;
	TIM2->SWEVGR = TIM_UG;
	TIM2->CTLR1 |= TIM_CEN;

	funPinMode( PD6, GPIO_CFGLR_OUT_10Mhz_AF_PP );
}

static void set_fault( int f )
{
	TIM2->CH3CVR = 0;
	boost_on = 0;
	if( !fault ) fault = f;
}

// Every main-loop pass (~15 us, i.e. about every boost period).
static void boost_regulate( void )
{
	int v = adc_read( ADC_CH_VFB );
	vfb_last = v;
	if( v >= vfb_trip )
	{
		set_fault( FAULT_OVERVOLTAGE );
		return;
	}
	if( !boost_on ) return;
	int pulse = v < vfb_target;
	TIM2->CH3CVR = pulse ? ton : 0;
	passes++;
	pulse_passes += pulse;
}

// ---- Touch -------------------------------------------------------------------------------------

static void touch_task( void )
{
	static uint8_t samples;
	touch_raw = ReadTouchPin( GPIOA, 2, ADC_CH_TOUCH, 3 );

	if( samples < 16 )  // first 16 reads (0.3 s): baseline, the pad must not be touched at power-up
	{
		touch_base = samples ? ( touch_base * samples + touch_raw ) / ( samples + 1 ) : touch_raw;
		samples++;
		return;
	}

	int delta = touch_delta ? touch_delta : touch_base / 16 + 2;
	int now = touch_raw > touch_base + delta;
	if( !now ) touch_base = ( touch_base * 63 + touch_raw ) / 64;  // follow slow drift

	if( now ) { if( touch_count < 2 ) touch_count++; }
	else touch_count = 0;

	int t = touch_count >= 2;  // debounce: two reads in a row
	if( t && !touched && mode == MODE_AUTO ) paused = !paused;
	touched = t;
}

// ---- USB ---------------------------------------------------------------------------------------

void usb_handle_user_in_request( struct usb_endpoint * e, uint8_t * scratchpad, int endp, uint32_t sendtok, struct rv003usb_internal * ist )
{
	// Only control transfers are used; the interrupt endpoint stays empty.
	usb_send_empty( sendtok );
}

void usb_handle_hid_get_report_start( struct usb_endpoint * e, int reqLen, uint32_t lValueLSBIndexMSB )
{
	if( ( lValueLSBIndexMSB & 0xff ) == NP_REPORT_STATUS )
	{
		if( reqLen > (int)sizeof( status ) ) reqLen = sizeof( status );
		e->opaque = (uint8_t *)&status;
		e->max_len = reqLen;
	}
}

void usb_handle_hid_set_report_start( struct usb_endpoint * e, int reqLen, uint32_t lValueLSBIndexMSB )
{
	usb_set_report_id = lValueLSBIndexMSB & 0xff;
	if( usb_set_report_id != NP_REPORT_COMMAND ) return;  // 0xFD (reboot) is handled inside rv003usb
	if( reqLen > (int)sizeof( cmd_buf ) ) reqLen = sizeof( cmd_buf );
	e->max_len = reqLen;
}

void usb_handle_user_data( struct usb_endpoint * e, int current_endpoint, uint8_t * data, int len, struct rv003usb_internal * ist )
{
	if( current_endpoint || usb_set_report_id != NP_REPORT_COMMAND ) return;
	int offset = e->count << 3;
	int torx = e->max_len - offset;
	if( torx > len ) torx = len;
	if( torx <= 0 ) return;
	memcpy( cmd_buf + offset, data, torx );
	e->count++;
	if( offset + torx >= e->max_len ) cmd_pending = 1;
}

static void handle_command( void )
{
	uint8_t c[8];
	memcpy( c, cmd_buf, sizeof( c ) );
	cmd_pending = 0;
	if( c[0] != NP_REPORT_COMMAND ) return;

	uint32_t arg32 = c[2] | ( c[3] << 8 ) | ( (uint32_t)c[4] << 16 ) | ( (uint32_t)c[5] << 24 );
	uint32_t arg16 = c[2] | ( c[3] << 8 );
	switch( c[1] )
	{
	case CMD_MODE:
		if( c[2] <= MODE_MANUAL ) mode = c[2];
		if( mode == MODE_AUTO ) { step = SEQ_CHARGE; step_ms = 0; paused = 0; }
		break;
	case CMD_HV:
		hv_set_v = c[2] > HV_MAX_V ? HV_MAX_V : c[2];
		break;
	case CMD_LAMPS:
		manual_lamps = arg32 & ALL_LAMPS( 3 );
		mode = MODE_MANUAL;
		break;
	case CMD_CLEAR_FAULT:
		fault = FAULT_NONE;
		break;
	case CMD_TON:
		ton = arg16 < TON_MIN ? TON_MIN : arg16 > TON_LIMIT ? TON_LIMIT : arg16;
		if( ton > period - PERIOD_MARGIN ) ton = period - PERIOD_MARGIN;
		break;
	case CMD_PAUSE:
		paused = c[2] != 0;
		break;
	case CMD_LEVEL:
		manual_level = c[2];
		break;
	case CMD_PERIOD:
		period = arg16 > PERIOD_MAX ? PERIOD_MAX : arg16 < ton + PERIOD_MARGIN ? ton + PERIOD_MARGIN : arg16;
		TIM2->ATRLR = period - 1;  // preloaded (ARPE): takes effect at the next update
		break;
	case CMD_TOUCH_DELTA:
		touch_delta = arg16;
		break;
	}
}

// ---- 1 ms housekeeping -------------------------------------------------------------------------

static uint32_t seq_lamps( int s )
{
	if( s >= SEQ_LAMP0 && s < SEQ_ALL_K )
	{
		int lamp = ( s - SEQ_LAMP0 ) >> 1;
		return (uint32_t)( ( ( s - SEQ_LAMP0 ) & 1 ) ? LAMP_A : LAMP_K ) << ( 2 * lamp );
	}
	if( s == SEQ_ALL_K ) return ALL_LAMPS( LAMP_K );
	if( s == SEQ_ALL_A ) return ALL_LAMPS( LAMP_A );
	if( s == SEQ_ALL_AC || s == SEQ_SWEEP ) return ALL_LAMPS( LAMP_AC );
	return 0;
}

static uint16_t seq_len_ms( int s )
{
	if( s == SEQ_CHARGE ) return 1500;
	if( s < SEQ_ALL_K ) return SEQ_GAP_MS + 700;
	if( s == SEQ_ALL_AC ) return 3000;
	if( s == SEQ_SWEEP ) return SWEEP_MS;
	return 2000;
}

static void ms_task( void )
{
	static uint32_t ms;
	static uint32_t hv_mv;
	ms++;

	if( cmd_pending ) handle_command();

	// HV regulation targets (VDD is re-measured every 100 ms).
	if( ms % 100 == 0 ) measure_vdd();
	hv_mv = vfb_to_mv( vfb_last );
	vfb_trip = mv_to_vfb( HV_TRIP_MV );

	int want = mode != MODE_OFF && hv_set_v && !fault;
	if( want && !boost_on )
	{
		boost_on = 1;
		ramp_mv = hv_mv;
		low_ms = 0;
	}
	else if( !want && boost_on )
	{
		boost_on = 0;
		TIM2->CH3CVR = 0;
	}
	uint32_t set_mv = hv_set_v * 1000u;
	if( ramp_mv + HV_RAMP_MV_PER_MS < set_mv ) ramp_mv += HV_RAMP_MV_PER_MS;
	else ramp_mv = set_mv;
	vfb_target = mv_to_vfb( ramp_mv );

	if( boost_on && hv_mv < NORISE_MV )
	{
		if( ++low_ms >= NORISE_MS ) set_fault( FAULT_NO_RISE );
	}
	else low_ms = 0;

	// Lamps
	if( mode == MODE_AUTO && !paused && !fault )
	{
		if( ++step_ms >= seq_len_ms( step ) )
		{
			step_ms = 0;
			if( ++step >= SEQ_STEPS ) step = SEQ_LAMP0;
		}
	}

	uint32_t lamps = 0;
	if( !fault && boost_on )
	{
		if( mode == MODE_AUTO && !( step >= SEQ_LAMP0 && step < SEQ_ALL_K && step_ms < SEQ_GAP_MS ) )
			lamps = seq_lamps( step );
		else if( mode == MODE_MANUAL ) lamps = manual_lamps;
	}
	level = 255;
	if( mode == MODE_MANUAL ) level = manual_level;
	else if( step == SEQ_SWEEP )  // triangle, 0 -> 255 -> 0
	{
		uint32_t half = SWEEP_MS / 2;
		uint32_t t = step_ms < half ? step_ms : SWEEP_MS - 1 - step_ms;
		level = t * 255 / ( half - 1 );
	}
	if( !level ) lamps = 0;
	lamps_shown = lamps;
	// Gamma ~2: perceived brightness roughly linear in level. 255 = always on.
	pwm_on_ticks = (uint32_t)level * level * PWM_FRAME / ( 255u * 255u );
	outs_frame[0] = lamps_to_outs( lamps, 0 );
	outs_frame[1] = lamps_to_outs( lamps, 1 );

	// Sensors
	if( ms % 20 == 0 )
	{
		touch_task();
		status.adc_ldr = adc_read( ADC_CH_LDR );
	}

	// Status block for USB
	if( ms % 100 == 0 )
	{
		status.duty_pm = passes ? pulse_passes * 1000 / passes : 0;
		passes = pulse_passes = 0;
	}
	status.report_id = NP_REPORT_STATUS;
	status.fw_version = FW_VERSION;
	status.mode = mode;
	status.step = step;
	status.fault = fault;
	status.flags = ( touched ? 1 : 0 ) | ( paused ? 2 : 0 ) | ( boost_on ? 4 : 0 );
	status.hv_set = hv_set_v;
	status.period_us = period / 48;
	status.hv_cv = hv_mv / 10;
	status.vdd_mv = vdd_mv;
	status.adc_vfb = vfb_last;
	status.touch = touch_raw;
	status.touch_base = touch_base;
	status.ton = ton;
	status.uptime_ms = ms;
	status.lamps = lamps_shown;
	status.level = level;
}

// Every main-loop pass: lamp PWM. Edges jitter by one pass (~15 us of 1000).
static void lamp_pwm( void )
{
	static uint32_t frame_start;
	static uint8_t frames;
	uint32_t t = SysTick->CNT - frame_start;
	if( t >= PWM_FRAME )
	{
		frame_start += PWM_FRAME;
		if( SysTick->CNT - frame_start >= PWM_FRAME ) frame_start = SysTick->CNT;  // fell behind (USB): resync
		if( ++frames >= AC_FRAMES ) { frames = 0; ac_phase = !ac_phase; }
		t = SysTick->CNT - frame_start;
	}
	outs_set( t < pwm_on_ticks ? outs_frame[ac_phase] : 0 );
}

// ---- Init --------------------------------------------------------------------------------------

static void gpio_init( void )
{
	funGpioInitAll();

	// Lamp switches PC0-PC6 + PD0, 595 interface PC7 / PD5 / PD7: outputs, all low.
	GPIOC->BSHR = 0xffu << 16;
	GPIOD->BSHR = ( SR_DATA_D | SR_LATCH_D | 1u ) << 16;
	GPIOC->CFGLR = 0x11111111 * GPIO_CFGLR_OUT_50Mhz_PP;  // all of port C
	funPinMode( PD0, GPIO_CFGLR_OUT_10Mhz_PP );
	funPinMode( PD5, GPIO_CFGLR_OUT_50Mhz_PP );
	funPinMode( PD7, GPIO_CFGLR_OUT_50Mhz_PP );

	// Every lamp switch off (also latches the random power-up state of the 595s away).
	outs_set( 0 );

	// Analog inputs
	funPinMode( PD3, GPIO_CFGLR_IN_ANALOG );
	funPinMode( PA1, GPIO_CFGLR_IN_ANALOG );
}

static void iwdg_init( void )
{
	RCC->RSTSCKR |= RCC_LSION;
	while( !( RCC->RSTSCKR & RCC_LSIRDY ) );
	IWDG->CTLR = 0x5555;           // unlock PSCR / RLDR
	IWDG->PSCR = IWDG_Prescaler_64;  // 128 kHz / 64 = 2 kHz
	IWDG->RLDR = 1000;             // 0.5 s
	IWDG->CTLR = 0xaaaa;
	IWDG->CTLR = 0xcccc;           // start
}

int main()
{
	SystemInit();

	gpio_init();  // lamps off before anything else (R2 holds the boost gate low until TIM2 runs)

	// Force re-enumeration: the bootloader may have just been on the bus with the same D- pull-up.
	funPinMode( PD4, GPIO_CFGLR_OUT_10Mhz_PP );
	GPIOD->BSHR = 1u << ( 4 + 16 );
	Delay_Ms( 20 );
	usb_setup();

	adc_init();
	measure_vdd();
	vfb_trip = mv_to_vfb( HV_TRIP_MV );
	boost_init();
	iwdg_init();

	uint32_t ms_tick = SysTick->CNT;
	while( 1 )
	{
		IWDG->CTLR = 0xaaaa;
		boost_regulate();
		lamp_pwm();
		if( (int32_t)( SysTick->CNT - ms_tick ) >= (int32_t)DELAY_MS_TIME )
		{
			ms_tick += DELAY_MS_TIME;
			ms_task();
		}
	}
}
