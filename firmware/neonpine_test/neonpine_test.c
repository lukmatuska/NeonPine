// NeonPine firmware – CH32V003F4P6, ch32fun + rv003usb.
//
// Pin map and lamp tables: docs/mcu-netlist.md, hardware: DESIGN.md §2, animations: anim.c (a port of
// the NeonPine simulator artifact).
//
// * HV boost: PD6 = TIM2_CH3 (full remap), 40 kHz, fixed 20 us gate pulses (I_pk 0.30 A). Pulse skipping
//   against the PD3 (A4) feedback: every main-loop pass reads HV and lets the next pulse through or not.
//   Soft start 0.2 V/ms.
// * Protection (firmware only; the hardware limits are R2, D2, F1): overvoltage trip, "no rise" trip
//   (HV below 20 V for 1 s while boosting: open feedback, dead boost, shorted rail), IWDG.
// * Lamps: each lamp has a PWM window (7 ms frame, the ten windows staggered across the frame so the HV
//   load is smooth). Inside its window the left electrode (pad 1, K switch) glows first, then the right
//   one (pad 2, A switch); together at most the whole window (simulator share()). Every lit electrode
//   gets at least the minimum on-time (neon needs time to strike); style normal = 400 us, retro = 300 us
//   (borderline: random flicker).
// * Power budget: when HV (averaged) sags, the part of every on-time above the minimum is scaled down;
//   it creeps back when HV holds.
// * Shows: the 8 simulator animations (candle, breathe, twinkle, garland, snowfall, heartbeat, drift,
//   sleep; 1.5 s crossfades) plus the bring-up test sequence, a brightness sweep and a steady glow.
// * Brightness: the simulator dims with the HV rail (75-105 V). With PWM every window has to strike
//   anew, which needs up to 90 V, so by default the same 1/3 .. 1 range is applied to the duty instead
//   and HV stays at 100 V. Rail dimming is selectable (nptest.py dim rail) to try.
// * TP2 touch (DESIGN.md §2.4): tap = next animation, double tap = sleep timer (dims over 20 min, then
//   off), triple tap = style, hold = brightness ramp, hold 3 s = off / on.
// * Light sensor (TEPT4400 on PA1): read in a 0.5 ms all-dark slot every 100 ms, so the tree's own light
//   doesn't count. Off in daylight, on at dusk, room-adaptive brightness, wave a hand = next animation.
// * USB HID 1209:D003 with feature reports: 0xAA status, 0xAB commands (../tools/nptest.py), 0xAC live
//   frames and 0xAE store pages (../../companion). minichlink reboots it into the rv003usb bootloader
//   by itself (report 0xFD) before flashing.
// * Store (last 1 kB of flash, anim.h): page 0 = settings (power-up animation / style / brightness,
//   light sensor, dimming, animation parameters, tap and drift lists, sleep time, crossfade, tree name),
//   saved 3 s after the last change; pages 1-15 = custom keyframe animations (anim.c). While a page is
//   written the CPU stalls for ~5 ms, so boost and lamps are switched off for it.

#include "ch32fun.h"
#include <string.h>
#include <stddef.h>
#include "rv003usb.h"
#include "ch32v003_touch.h"
#include "anim.h"

#define FW_VERSION 3
#define Q 4096  // Q12 fixed point: 1.0

// ---- Boost -------------------------------------------------------------------------------------
#define BOOST_PERIOD      1200     // TIM2 ticks at 48 MHz -> 40 kHz (default, nptest.py freq changes it)
#define PERIOD_MAX        9600     // 5 kHz
#define PERIOD_MARGIN     192      // >= 4 us off-time per period: L11 must empty (DCM) before the next pulse
#define TON_DEFAULT       960      // gate on-time, ticks: 20 us -> I_pk 0.30 A (L11 CR5040-331M: 400 mA)
                                   // 20 us / 40 kHz measured best: ~0.45 W, all lamps at full -> 75 V
#define TON_MIN           48       // 1 us
#define TON_LIMIT         960      // 20 us = the 60 % duty clamp of DESIGN.md §2.2 (I_pk 0.30 A)
#define HV_DEFAULT_V      100      // NEON-3 strikes at <= 90 V
#define HV_MAX_V          105
#define HV_TRIP_MV        115000   // overvoltage trip (D2 clamps at 111-123 V)
#define HV_RAMP_MV_PER_MS 200      // soft start
#define NORISE_MS         1000     // HV below NORISE_MV for this long while boosting -> fault
#define NORISE_MV         20000
// Feedback divider: R5 + R6 = 2 M on top, R7 = 39 k to GND (105 V -> 2.0 V)
#define DIV_TOP_K         2000
#define DIV_BOT_K         39
// Rail dimming (simulator): 75 V + 30 V * brightness, kicked to >= 95 V after a start so lamps strike
#define RAIL_MIN_MV       75000
#define RAIL_SPAN_MV      30000
#define RAIL_KICK_MV      95000
#define KICK_MS           500

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

// {K side = lamp pad 1 (net LAMPn), A side = lamp pad 2 (net LAMPAn)} – docs/mcu-netlist.md "Lamps".
// Pad 1 is the left lead seen from the front on every lamp (NeonPine.kicad_pcb), and the K switch
// makes pad 1 the cathode, so K lights the LEFT electrode (simulator e1), A the right one (e2).
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

// Lamp state for the test shows / manual mode, 2 bits per lamp (LA1 = bits 1:0)
enum { LAMP_OFF = 0, LAMP_K = 1, LAMP_A = 2, LAMP_AC = 3 };
#define ALL_LAMPS(s) ( (s) * 0x55555u )

// ---- Modes / shows -----------------------------------------------------------------------------
enum { MODE_OFF = 0, MODE_AUTO = 1, MODE_MANUAL = 2 };
// Shows 0-7 are the animations (anim.h); then the bring-up shows, reachable over USB only.
enum { SHOW_TEST = ANIMS, SHOW_SWEEP, SHOW_GLOW, SHOWS };
enum { STYLE_NORMAL = 0, STYLE_RETRO = 1 };
enum { GESTURE_TAP = 1, GESTURE_DOUBLE = 2, GESTURE_HOLD = 3, GESTURE_LONG = 4, GESTURE_TRIPLE = 5, GESTURE_WAVE = 6 };

#define ANIM_PERIOD_MS 20        // animation frame rate: 50 Hz
#define SLEEP_MIN      20        // sleep timer default: dims over 20 min, then off
#define LIVE_TIMEOUT_MS 2500     // live mode ends this long after the last frame
#define SAVE_DELAY_MS  3000      // settings are saved this long after the last change

// TP2 (board 1): idle ~3700 +-160, touched +1100..+2000 (sum of 9 ADC samples)
#define TOUCH_DELTA_DEFAULT  500   // pressed above baseline + this
#define TOUCH_RELEASE_DIV    2     // released below baseline + delta / 2 (hysteresis)
#define TAP_MAX_MS           450   // shorter press = tap
#define DOUBLE_GAP_MS        350   // next tap within this after a release = double / triple tap
#define LONG_HOLD_MS         3000  // off / on
#define USER_LEVEL_MIN       8

// Light sensor: TEPT4400 + 22k, DESIGN.md: 100 lx -> 4.4 V, i.e. 44 mV per lux.
#define LIGHT_SLOT_MS     100      // a dark slot (all lamps off) this often
#define DARK_SLOT_US      500      // long enough for the phototransistor + 22k to settle
#define MV_PER_LUX        44
#define AUTO_OFF_LUX      100      // simulator: 150 lx, but with 22k the sensor saturates at ~110 lx
#define AUTO_ON_LUX       20
#define AUTO_CONFIRM_MS   5000     // a reading has to hold this long before the tree switches
#define WAVE_MIN_AMB      40       // shadow detection needs some room light (ADC counts)
#define WAVE_MIN_REFL     30       // reflection rise needed (own light per unit duty, counts)
#define WAVE_MIN_SAMPLES  2        // a wave lasts 0.2 .. 1.5 s
#define WAVE_MAX_SAMPLES  15

#define SEQ_CHARGE   0   // HV up, all dark
#define SEQ_LAMP0    1   // 1..20: lamp (s-1)/2, K then A
#define SEQ_ALL_K    21
#define SEQ_ALL_A    22
#define SEQ_ALL_AC   23
#define SEQ_SWEEP    24  // all lamps AC, brightness 0 -> 255 -> 0
#define SEQ_STEPS    25
#define SWEEP_MS     8000
#define SEQ_GAP_MS   400  // dark before each single-lamp step: HV recovers, so every lamp strikes from the full setpoint

#define PWM_FRAME_MS_DEFAULT 7      // board 1, by eye: the slowest frame without visible flicker
#define PWM_FRAME_MS_MAX     20
// Styles (board 1, by eye at 7 ms): 400 us strikes every time, 300 us is borderline -> random flicker.
// Shorter frames need a longer minimum (board 1: 2 ms -> 400 us, 4 ms -> 200 us).
#define PWM_MIN_US_NORMAL    400
#define PWM_MIN_US_RETRO     300
// Power budget: if HV sags more than BUDGET_SAG_MV below the soft-start target, the on-time above the
// minimum is scaled down (fast); within BUDGET_OK_MV it creeps back up (1/256 per ms).
#define BUDGET_SAG_MV        3000
#define BUDGET_OK_MV         1000
#define BUDGET_MIN           8
// Main-loop scheduling: lamp edges are switched when lamp_pwm() runs, so a long piece of work right
// before an edge makes that pulse longer or shorter. Work only starts when the next edge is further
// away than it takes (board 1: animation step <= ~125 us).
#define GUARD_BG_US          150
#define GUARD_MS_US          70    // the 1 ms core (touch, light, status run as separate jobs)
#define GUARD_JOB_US         100
#define MS_TASK_MAX_DELAY_US 1000  // the 1 ms task waits at most this long for a gap

// ---- USB protocol (feature reports, see ../tools/nptest.py) ------------------------------------
enum {
	CMD_MODE = 1,         // [2] = mode
	CMD_HV = 2,           // [2] = volts (0 = boost off)
	CMD_LAMPS = 3,        // [2..5] = lamp word (LE), switches to manual mode
	CMD_CLEAR_FAULT = 4,
	CMD_TON = 5,          // [2..3] = gate on-time in 48 MHz ticks (LE)
	CMD_PAUSE = 6,        // [2] = 0 run / 1 pause (test show)
	CMD_TOUCH_DELTA = 7,  // [2..3] = touch threshold above baseline (0 = default)
	CMD_PERIOD = 8,       // [2..3] = boost period in 48 MHz ticks (LE)
	CMD_LEVEL = 9,        // [2] = brightness 0-255 in manual mode
	CMD_PWM = 10,         // [2] = PWM frame ms (1-20), [3..4] = minimum on-time, us (LE)
	CMD_BUDGET = 11,      // [2] = 0 power budget off / 1 on
	CMD_STYLE = 12,       // [2] = 0 normal / 1 retro
	CMD_SHOW = 13,        // [2] = show (0-7 animations, 8 test, 9 sweep, 10 glow)
	CMD_USER_LEVEL = 14,  // [2] = overall brightness 8-255 (what the touch ramp changes)
	CMD_SLEEP = 15,       // [2] = 0 sleep timer off / 1 start
	CMD_AUTOLIGHT = 16,   // [2] = 0 / 1: light sensor features (auto on/off, adaptive brightness, wave)
	CMD_DIM = 17,         // [2] = 0 dim with duty / 1 dim with the HV rail
	CMD_WAVE = 18,        // pretend a hand waved
	CMD_SAVE = 19,        // save the settings now (if changed)
};

// Store report (NP_REPORT_STORE): [id][page][op / state][0][64 bytes]. SET with op READ selects a page,
// WRITE writes it (page 0: settings, applied and saved; 1..: custom blob), APPLY applies settings without
// saving. GET returns the page; state = op until done, then ST_OK / ST_ERR.
enum { ST_OP_READ = 1, ST_OP_WRITE = 2, ST_OP_APPLY = 3, ST_OK = 0x80, ST_ERR = 0x81 };

// Settings page (store page 0). The name is only used by the companion app.
#define CFG_MAGIC   0x4350
#define CFG_VERSION 1
enum { CFG_AUTOLIGHT = 1, CFG_DIM_RAIL = 2, CFG_REMEMBER = 4 };
struct cfg_page {
	uint16_t magic;
	uint8_t  version, show, style, level;  // power-up show / style / brightness
	uint8_t  flags, sleep_min;             // CFG_*, sleep timer minutes
	uint16_t tap_mask, drift_mask;         // bits 0-7 animations, 8-15 custom 0-7
	uint16_t drift_s;
	uint8_t  fade_ds, rsv0;
	struct anim_par pars[ANIM_BASIC];      // 16
	char     name[16];                     // 34
	uint8_t  rsv1[12];
	uint16_t sum;                          // 62: sum of bytes 0-61
};
_Static_assert( sizeof( struct cfg_page ) == 64, "settings page" );
#define CFG_SUM 62

struct np_status {
	uint8_t  report_id;   //  0 = NP_REPORT_STATUS
	uint8_t  fw_version;  //  1
	uint8_t  mode;        //  2
	uint8_t  step;        //  3 test sequence step
	uint8_t  fault;       //  4
	uint8_t  flags;       //  5 b0 touched, b1 paused, b2 boost running
	uint8_t  hv_set;      //  6 V (current HV target)
	uint8_t  period_us;   //  7 boost period, us
	uint16_t hv_cv;       //  8 measured HV, 10 mV units
	uint16_t vdd_mv;      // 10 from Vrefint
	uint16_t adc_vfb;     // 12
	uint16_t adc_ldr;     // 14 light sensor, average with the lamps as they are
	uint16_t touch;       // 16 raw touch sum
	uint16_t touch_base;  // 18
	uint16_t ton;         // 20 gate on-time, ticks
	uint16_t duty_pm;     // 22 share of boost periods that pulsed, per mille
	uint32_t uptime_ms;   // 24
	uint32_t lamps;       // 28 which electrodes are lit (2 bits per lamp: b0 left/K, b1 right/A)
	uint8_t  level;       // 32 brightness 0-255 (test shows: level, animations: duty factor)
	uint8_t  budget;      // 33 power budget scale, 255 = no limit
	uint8_t  pwm_ms;      // 34 PWM frame
	uint8_t  pwm_min_10us;// 35 minimum on-time, 10 us units
	uint8_t  show;        // 36
	uint8_t  style;       // 37
	uint8_t  user_level;  // 38 overall brightness (touch hold ramp)
	uint8_t  gesture;     // 39 last gesture (low nibble) + event counter (high nibble)
	uint8_t  sleep_min;   // 40 sleep timer, minutes left (0 = off)
	uint8_t  flags2;      // 41 b0 sleep timer, b1 off for daylight, b2 light sensor features, b3 rail dimming
	uint16_t ambient;     // 42 light sensor in the dark slot (room light only), ADC counts
	uint16_t reflection;  // 44 own light seen by the sensor per unit duty
	uint8_t  lux;         // 46
	uint8_t  adapt;       // 47 room-adaptive brightness factor, /255
	uint16_t late_us;     // 48 latest lamp edge in the last 100 ms (how late an on/off switch happened)
	uint16_t late_peak_us;// 50 the same since the previous status read
	uint8_t  caps;        // 52 b0 store, b1 live frames, b2 animation parameters
	uint8_t  store_pages; // 53
	uint8_t  n_custom;    // 54 valid custom animations in the store
	uint8_t  cfg_flags;   // 55 settings flags (CFG_*), b7 unsaved changes
	uint16_t store_gen;   // 56 counts store writes (the app re-reads when it changes)
	uint16_t stack_free;  // 58 bytes of stack never used since power-up
	uint32_t uid;         // 60 chip unique ID (folded to 32 bits)
} __attribute__((packed, aligned(4)));
_Static_assert( sizeof( struct np_status ) == 64, "status report is 63 bytes + id (usb_config.h)" );

static struct np_status status;
static uint8_t cmd_buf[8] __attribute__((aligned(4)));
static volatile uint8_t cmd_pending;
static uint8_t usb_set_report_id;
// Store page buffer for both directions; the data starts word aligned at store_buf + 4.
static uint8_t store_buf[68] __attribute__((aligned(4)));
static volatile uint8_t store_req, store_lock, live_req;
static volatile uint32_t store_req_ms;  // a page write waits a few ms, so the USB transfer's status stage is done first
#define store_cfg ( (struct cfg_page *)( store_buf + 4 ) )
#define flash_cfg ( (const struct cfg_page *)STORE_ADDR )
static uint16_t store_gen;

// ---- State -------------------------------------------------------------------------------------
static uint32_t now_ms;
static uint8_t mode = MODE_AUTO, step, paused, fault;
static uint16_t step_ms;
static uint32_t manual_lamps;
static uint8_t manual_level = 255, level;

static uint8_t show = ANIM_CANDLE, prev_show = ANIM_CANDLE, style = STYLE_NORMAL, user_level = 255, gesture;
static uint32_t fade_start, kick_until = KICK_MS;
static uint8_t sleep_active;
static uint32_t sleep_left_ms, sleep_ms = SLEEP_MIN * 60000u, sleep_div;
static uint8_t autolight = 1, daylight_off, dim_rail;
// Settings: power-up show / style / brightness (follow the live ones with "remember"), tap list
// (bits 0-7 animations, 8-15 custom 0-7), sleep minutes; unsaved since cfg_dirty_ms.
static uint8_t cfg_show = ANIM_CANDLE, cfg_style, cfg_level = 255, cfg_sleep_min = SLEEP_MIN, cfg_remember = 1;
static uint16_t tap_mask = 0xff;
static uint8_t cfg_dirty;
static uint32_t cfg_dirty_ms, live_until;
static uint8_t live_return = ANIM_CANDLE;
static int32_t sleep_q = Q, adapt_q = Q, anim_sm = Q, anim_L = Q;  // Q12 factors

// Lamp PWM. Published on-times (us, per lamp and electrode) -> full_on (ticks) -> nx (ticks, after the
// power budget; scale job) -> on (what lamp_pwm uses; each lamp takes nx at the start of its own window,
// so a pulse never changes halfway).
static uint32_t pwm_frame_us = PWM_FRAME_MS_DEFAULT * 1000, pwm_min_us = PWM_MIN_US_NORMAL;
static uint32_t k_mask[10], a_mask[10];
static uint16_t st1[10], st2[10];        // staging, us
static uint32_t full_on1[10], full_on2[10];
static uint32_t nx1[10], nx2[10];
static uint32_t on1[10], on2[10];
static uint32_t lamps_shown;             // 2 bits per lamp: b0 left lit, b1 right lit
static uint8_t lamps_lit;
static int32_t duty_q12;                 // average lit share of a window, over all lamps
static uint16_t budget = 256;            // power budget scale, /256
static uint8_t budget_enabled = 1;
static uint8_t anim_active, pub_i = 10;  // animation output enabled; lamp being published (10 = idle)
static uint8_t pub_states, pub_level;    // publishing a test show / manual state instead of an animation
static uint32_t pub_lamps;

// Boost
static uint8_t hv_set_v = HV_DEFAULT_V;
static uint32_t hv_target_mv;
static uint16_t ton = TON_DEFAULT;
static uint16_t period = BOOST_PERIOD;
static uint8_t boost_on;
static uint32_t ramp_mv;         // soft-start setpoint
static uint32_t vdd_mv = 5000;
static int vfb_target, vfb_trip; // in ADC counts
static int vfb_last;
static uint32_t mv_per_count_q4 = 4090, count_per_mv_q20 = 4100;  // HV <-> ADC counts, set with VDD
static uint16_t low_ms;
static uint32_t hv_mv;
static uint32_t passes, pulse_passes;

// Touch
static uint16_t touch_raw, touch_base, touch_delta = TOUCH_DELTA_DEFAULT;
static uint8_t touched, touch_count;

// Light sensor
static volatile uint8_t dark_req, dark_done;
static uint16_t ldr_dark;
static uint32_t ldr_acc, duty_acc, ldr_n;
static uint32_t lux;

static uint32_t outs_now = 0xffffffff;
static uint32_t late_max, late_peak;  // SysTick ticks
static volatile uint8_t status_read;
static uint8_t job_touch, job_light, job_status, job_scale, job_save, job_stack;  // deferred work, run in gaps between lamp edges

// ---- Lamp outputs ------------------------------------------------------------------------------

static inline void short_delay( void )
{
	__asm__ volatile( "nop\nnop" );  // >= 42 ns: 74HC595 setup 25 ns / clock pulse 20 ns at 4.5 V
}

static void outs_write( uint32_t o, uint32_t was )
{
	if( ( o ^ was ) & 0xffff )  // shift register part changed
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
	}
	uint32_t pc = ( o >> 16 ) & OUT_PC_MASK;
	uint32_t pd = ( o >> 24 ) & OUT_PD_MASK;
	GPIOC->BSHR = pc | ( ( ~pc & OUT_PC_MASK ) << 16 );
	GPIOD->BSHR = pd | ( ( ~pd & OUT_PD_MASK ) << 16 );
}

static void outs_set( uint32_t o )
{
	if( o == outs_now ) return;
	// Break before make: when switches go off and others on in the same step, switch the ones going
	// off first, so a lamp moving K <-> A never has both switches on, not even for the microseconds
	// between the 595 latch and the port write.
	uint32_t mid = outs_now & o;
	if( mid != outs_now && mid != o ) { outs_write( mid, outs_now ); outs_now = mid; }
	outs_write( o, outs_now );
	outs_now = o;
}

// Q12 duty requests of one lamp's left / right electrode -> on-times (us) inside its window.
// The electrodes take turns (simulator share()): together at most the whole window.
static void lamp_times( int i, int32_t d1, int32_t d2 )
{
	int32_t s = d1 + d2;
	if( s > Q ) { d1 = d1 * Q / s; d2 = Q - d1; }
	uint32_t fr = pwm_frame_us, mn = pwm_min_us;
	uint32_t a = d1 > 0 ? mn + ( ( fr - mn ) * d1 >> 12 ) : 0;
	uint32_t b = d2 > 0 ? mn + ( ( fr - mn ) * d2 >> 12 ) : 0;
	if( a + b > fr ) { a = a * fr / ( a + b ); b = fr - a; }
	st1[i] = a;
	st2[i] = b;
}

// Staging -> what lamp_pwm uses from its next frame on.
static void lamps_commit( void )
{
	uint32_t shown = 0, sum = 0;
	for( int i = 0; i < 10; i++ )
	{
		full_on1[i] = st1[i] * DELAY_US_TIME;
		full_on2[i] = st2[i] * DELAY_US_TIME;
		shown |= ( ( st1[i] ? 1u : 0 ) | ( st2[i] ? 2u : 0 ) ) << ( 2 * i );
		sum += st1[i] + st2[i];
	}
	lamps_shown = shown;
	lamps_lit = shown != 0;
	job_scale = 1;
	duty_q12 = sum * Q / ( 10 * pwm_frame_us );
}

// One lamp per main-loop pass (the divisions add up): from the last animation frame, or for the test
// shows / manual mode from lamp states + one level (gamma ~2). After the 10th lamp it goes live.
static void publish_lamp( void )
{
	int i = pub_i;
	if( pub_states )
	{
		int32_t d = (int32_t)pub_level * pub_level * Q / ( 255 * 255 );
		int s = pub_level ? ( pub_lamps >> ( 2 * i ) ) & 3 : LAMP_OFF;
		lamp_times( i, s == LAMP_K ? d : s == LAMP_AC ? d / 2 : 0,
		               s == LAMP_A ? d : s == LAMP_AC ? d / 2 : 0 );
	}
	else
	{
		int32_t a = anim_e1[i] * anim_sm >> 12, b = anim_e2[i] * anim_sm >> 12;
		int32_t s = a + b;
		if( s > Q ) { a = a * Q / s; b = Q - a; }  // share() before the brightness factor, like the simulator
		lamp_times( i, a * anim_L >> 12, b * anim_L >> 12 );
	}
	if( ++pub_i == 10 && ( pub_states ? !anim_active : anim_active ) ) lamps_commit();
}

// Power budget applied to the published on-times, above the minimum (so the budget never pushes a pulse
// below the time the neon needs to strike). 20 multiplications: a deferred job, not in the edge path.
static void scale_task( void )
{
	uint32_t mn = pwm_min_us * DELAY_US_TIME, b = budget;
	for( int i = 0; i < 10; i++ )
	{
		uint32_t x = full_on1[i], y = full_on2[i];
		nx1[i] = x > mn ? mn + ( ( x - mn ) * b >> 8 ) : x;
		nx2[i] = y > mn ? mn + ( ( y - mn ) * b >> 8 ) : y;
	}
}

// ---- ADC ---------------------------------------------------------------------------------------

static void adc_init( void )
{
	RCC->APB2PCENR |= RCC_APB2Periph_ADC1;
	RCC->APB2PRSTR |= RCC_APB2Periph_ADC1;
	RCC->APB2PRSTR &= ~RCC_APB2Periph_ADC1;
	InitTouchADC();  // ADCCLK = 24 MHz, software trigger, calibration
}

static uint8_t vfb_pending;  // a VFB conversion was started by boost_regulate() and nobody else used the ADC since

// Before anything else uses the ADC: let a running VFB conversion finish and throw it away. Starting a
// new conversion on top of it makes the result land on the wrong channel (seen on board 1: HV read too
// low, the boost ran flat out into the 115 V trip).
static void adc_claim( void )
{
	if( vfb_pending )
	{
		while( !( ADC1->STATR & ADC_EOC ) );
		(void)ADC1->RDATAR;
		vfb_pending = 0;
	}
}

static int adc_read( int ch )
{
	adc_claim();
	(void)ADC1->RDATAR;  // clear a stale EOC, so the wait below is for this conversion
	// ReadTouchPin() rewrites SAMPTR2 and CTLR2, so set both every time.
	ADC1->RSQR3 = ch;
	ADC1->SAMPTR2 = ADC_SampleTime_241Cycles << ( 3 * ch );  // 10 us: the divider node is high impedance
	ADC1->CTLR2 = ADC_ADON | ADC_EXTSEL | ADC_TSVREFE | ADC_SWSTART;
	while( !( ADC1->STATR & ADC_EOC ) );
	return ADC1->RDATAR;
}

static void measure_vdd( void )  // at start-up: 8 conversions at once
{
	adc_read( ADC_CH_VREF );  // TSVREFE may just have been switched back on
	int sum = 0;
	for( int i = 0; i < 8; i++ ) sum += adc_read( ADC_CH_VREF );
	if( sum < 8 ) return;
	uint32_t mv = 1200u * 1023u * 8u / sum;  // Vrefint nominal 1.2 V
	if( mv < 4000 || mv > 5600 ) mv = 5000;  // implausible -> assume nominal USB 5 V
	vdd_mv = mv;
}

static void hv_scale_update( void )
{
	// hv_mv = counts * VDD / 1023 * 2039 / 39, without divisions in the 1 ms task
	mv_per_count_q4 = ( ( DIV_TOP_K + DIV_BOT_K ) * vdd_mv << 4 ) / ( 1023u * DIV_BOT_K );
	count_per_mv_q20 = ( 1023u * DIV_BOT_K << 12 ) / ( ( DIV_TOP_K + DIV_BOT_K ) * vdd_mv >> 8 );
	vfb_trip = HV_TRIP_MV * count_per_mv_q20 >> 20;
}

static void vdd_task( uint32_t ms )  // running: one conversion per ms (ms 10..17 of every 100), keeps passes short
{
	static uint32_t sum;
	uint32_t k = ms % 100;
	if( k < 10 || k > 17 ) return;
	if( k == 10 ) sum = 0;
	sum += adc_read( ADC_CH_VREF );
	if( k == 17 && sum >= 8 )
	{
		uint32_t mv = 1200u * 1023u * 8u / sum;
		vdd_mv = mv < 4000 || mv > 5600 ? 5000 : mv;
		hv_scale_update();
	}
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

// Every main-loop pass (~15-60 us, i.e. about every 1-2 boost periods). The VFB conversion runs in the
// background: started here, picked up at the next pass, so the pass doesn't wait 10 us for it.
static void boost_regulate( void )
{
	if( vfb_pending )
	{
		while( !( ADC1->STATR & ADC_EOC ) );  // usually done already: a pass takes longer than 10 us
		vfb_last = ADC1->RDATAR;
	}
	else vfb_last = adc_read( ADC_CH_VFB );  // another reading used the ADC: measure now, blocking
	// start the next one
	ADC1->RSQR3 = ADC_CH_VFB;
	ADC1->SAMPTR2 = ADC_SampleTime_241Cycles << ( 3 * ADC_CH_VFB );
	ADC1->CTLR2 = ADC_ADON | ADC_EXTSEL | ADC_TSVREFE | ADC_SWSTART;
	vfb_pending = 1;

	int v = vfb_last;
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

// ---- Shows, power, gestures --------------------------------------------------------------------

static void set_style( int st )
{
	style = st;
	pwm_min_us = st == STYLE_RETRO ? PWM_MIN_US_RETRO : PWM_MIN_US_NORMAL;
}

static void sleep_set( int on )
{
	sleep_active = on;
	sleep_ms = cfg_sleep_min * 60000u;
	sleep_left_ms = sleep_ms;
	sleep_div = sleep_ms / Q + 1;
}

static void set_show( int sh )
{
	if( sh != show ) { prev_show = show; fade_start = now_ms; anim_prev_t0 = anim_cur_t0; anim_cur_t0 = now_ms; }
	show = sh;
	if( sh == ANIM_SLEEP && !sleep_active ) sleep_set( 1 );
	step = sh == SHOW_SWEEP ? SEQ_SWEEP : SEQ_CHARGE;
	step_ms = 0;
	paused = 0;
	kick_until = now_ms + KICK_MS;
}

static void power_on( void )
{
	mode = MODE_AUTO;
	kick_until = now_ms + KICK_MS;
}

static void power_off( void )
{
	mode = MODE_OFF;
	sleep_active = 0;
}

// Settings changed: saved SAVE_DELAY_MS after the last change.
static void cfg_touch( void )
{
	cfg_dirty = 1;
	cfg_dirty_ms = now_ms;
}

// Show / style / brightness changed by the user: with "remember" they are the power-up values too.
static void state_changed( void )
{
	if( !cfg_remember ) return;
	if( show <= ANIM_DRIFT || show >= ANIM_CUSTOM0 ) cfg_show = show;  // not sleep, bring-up shows, live
	cfg_style = style;
	cfg_level = user_level;
	cfg_touch();
}

// Next show in the tap list: animations 0-7, then the custom ones (bits 8-15).
static int next_show( void )
{
	int s = show == ANIM_LIVE ? live_return : show;
	int cur = s < ANIMS ? s : s >= ANIM_CUSTOM0 ? s - ANIM_CUSTOM0 + 8 : -1;
	for( int k = 1; k <= 16; k++ )
	{
		int i = ( cur + k ) & 15;
		if( !( tap_mask >> i & 1 ) || ( i >= 8 && i - 8 >= anim_custom_count() ) ) continue;
		return i < 8 ? i : ANIM_CUSTOM0 + i - 8;
	}
	return s < ANIMS ? s : ANIM_CANDLE;
}

static void on_gesture( int g )
{
	gesture = ( ( gesture + 0x10 ) & 0xf0 ) | g;
	if( g == GESTURE_LONG )
	{
		if( mode == MODE_OFF ) power_on();
		else power_off();
		return;
	}
	if( mode == MODE_OFF || daylight_off ) return;  // off: only "hold 3 s" turns it on (simulator)
	if( g == GESTURE_TAP || g == GESTURE_WAVE )
	{
		mode = MODE_AUTO;
		set_show( next_show() );
		state_changed();
	}
	else if( g == GESTURE_DOUBLE ) sleep_set( !sleep_active );
	else if( g == GESTURE_TRIPLE ) { set_style( !style ); state_changed(); }
}

// ---- Touch -------------------------------------------------------------------------------------

// Every 20 ms.
static void touch_task( void )
{
	static uint8_t samples, taps, hold_done;
	static int8_t ramp_dir = 1;
	static uint32_t press_ms, release_ms;
	static uint8_t level_at_press;
	uint32_t ms = now_ms;

	adc_claim();
	touch_raw = ReadTouchPin( GPIOA, 2, ADC_CH_TOUCH, 3 );
	(void)ADC1->RDATAR;  // leave EOC clear

	if( samples < 16 )  // first 16 reads (0.3 s): baseline, the pad must not be touched at power-up
	{
		touch_base = samples ? ( touch_base * samples + touch_raw ) / ( samples + 1 ) : touch_raw;
		samples++;
		return;
	}

	// Hysteresis: press above base + delta, release below base + delta / 2.
	int above = touch_raw > touch_base + ( touched ? touch_delta / TOUCH_RELEASE_DIV : touch_delta );
	if( !above && touch_raw < touch_base + touch_delta / TOUCH_RELEASE_DIV )
		touch_base = ( touch_base * 63 + touch_raw ) / 64;  // follow slow drift while untouched

	if( above ) { if( touch_count < 2 ) touch_count++; }
	else touch_count = 0;
	int t = touched ? above : touch_count >= 2;  // debounce the press: two reads in a row

	if( t && !touched )  // press
	{
		press_ms = ms;
		hold_done = 0;
		level_at_press = user_level;
		if( ramp_dir > 0 && user_level == 255 ) ramp_dir = -1;
		if( ramp_dir < 0 && user_level == USER_LEVEL_MIN ) ramp_dir = 1;
	}
	else if( t && touched )  // held
	{
		uint32_t held = ms - press_ms;
		if( held >= LONG_HOLD_MS && !hold_done )
		{
			hold_done = 1;
			user_level = level_at_press;  // the 3 s gesture means off / on, not "ramp"
			taps = 0;
			on_gesture( GESTURE_LONG );
		}
		else if( held >= TAP_MAX_MS && !hold_done && mode != MODE_OFF && !daylight_off )
		{
			// Brightness ramp: full range in ~1.7 s.
			int l = user_level + 3 * ramp_dir;
			user_level = l < USER_LEVEL_MIN ? USER_LEVEL_MIN : l > 255 ? 255 : l;
		}
	}
	else if( !t && touched )  // release
	{
		uint32_t held = ms - press_ms;
		if( held < TAP_MAX_MS ) { taps++; release_ms = ms; }
		else if( !hold_done ) { ramp_dir = -ramp_dir; gesture = ( ( gesture + 0x10 ) & 0xf0 ) | GESTURE_HOLD; state_changed(); }
	}
	touched = t;

	// Taps are reported once no further tap can follow any more.
	if( taps && !touched && ms - release_ms > DOUBLE_GAP_MS )
	{
		on_gesture( taps >= 3 ? GESTURE_TRIPLE : taps == 2 ? GESTURE_DOUBLE : GESTURE_TAP );
		taps = 0;
	}
}

// ---- Light sensor ------------------------------------------------------------------------------

static int32_t adapt_from_lux( uint32_t lx )
{
	// simulator: 0.75 + 0.25 * clamp(log10(5 lux + 1) / 2.2); log2 from the bit length, linear between
	uint32_t y = 5 * lx + 1;
	uint32_t msb = 0;
	while( y >> ( msb + 1 ) ) msb++;  // not __builtin_clz: that pulls in a 256-byte table
	uint32_t log2_q16 = ( msb << 16 ) + ( ( ( y << 16 ) >> msb ) & 0xffff );
	int32_t x = ( log2_q16 >> 4 ) * 8967 >> 16;  // * log10(2) / 2.2, to Q12
	if( x > Q ) x = Q;
	return 3072 + ( x >> 2 );
}

// Every LIGHT_SLOT_MS, once the dark slot has been read.
static void light_task( void )
{
	static int32_t amb_s32, refl_s32;  // slow averages (x32)
	static uint8_t cand, cooldown = 30, confirm;

	uint32_t lit = ldr_n ? ldr_acc / ldr_n : 0;
	int32_t duty = ldr_n ? duty_acc / ldr_n : 0;
	ldr_acc = duty_acc = ldr_n = 0;

	uint32_t amb = ldr_dark;
	uint32_t own = lit > amb ? lit - amb : 0;
	uint32_t refl = own * 1024 / ( duty > 205 ? duty : 205 );  // own light per unit duty
	lux = amb * vdd_mv / 1023 / MV_PER_LUX;
	status.ambient = amb;
	status.reflection = refl > 65535 ? 65535 : refl;
	status.adc_ldr = lit;

	if( !autolight ) { daylight_off = 0; adapt_q = Q; cand = confirm = 0; return; }
	adapt_q = adapt_from_lux( lux );

	// Off in daylight, on at dusk (hysteresis + AUTO_CONFIRM_MS)
	int over = daylight_off ? lux < AUTO_ON_LUX : lux > AUTO_OFF_LUX;
	if( !over ) confirm = 0;
	else if( ++confirm >= AUTO_CONFIRM_MS / LIGHT_SLOT_MS )
	{
		confirm = 0;
		daylight_off = !daylight_off;
		if( !daylight_off ) kick_until = now_ms + KICK_MS;
	}

	// Wave: a short shadow (room lit) or a short rise of the tree's light reflected back (dark room)
	int32_t amb_slow = amb_s32 / 32, refl_slow = refl_s32 / 32;
	int32_t rise = refl_slow / 2 > WAVE_MIN_REFL ? refl_slow / 2 : WAVE_MIN_REFL;
	int shadow = amb_slow > WAVE_MIN_AMB && amb * 10 < (uint32_t)amb_slow * 7;
	int reflect = lamps_lit && (int32_t)refl > refl_slow + rise;
	if( cooldown ) cooldown--;
	if( shadow || reflect )
	{
		if( ++cand > WAVE_MAX_SAMPLES )  // not a wave: the room or the tree changed, take it as the new normal
		{
			amb_s32 = amb * 32;
			refl_s32 = refl * 32;
			cand = 0;
		}
	}
	else
	{
		if( cand >= WAVE_MIN_SAMPLES && !cooldown && mode == MODE_AUTO )
		{
			on_gesture( GESTURE_WAVE );
			cooldown = 15;
		}
		cand = 0;
		amb_s32 += amb - amb_s32 / 32;
		refl_s32 += refl - refl_s32 / 32;
	}
}

// ---- Store -------------------------------------------------------------------------------------

// Erase + program one 64-byte page (fast mode). The CPU stalls ~5 ms on the busy flash and TIM2 would
// keep its last gate setting, so the boost and the lamps are switched off first. 0 = verified.
static int flash_page_write( uint32_t addr, const uint32_t * src )
{
	TIM2->CH3CVR = 0;
	outs_set( 0 );
	FLASH->KEYR = FLASH_KEY1;
	FLASH->KEYR = FLASH_KEY2;
	FLASH->MODEKEYR = FLASH_KEY1;
	FLASH->MODEKEYR = FLASH_KEY2;
	FLASH->CTLR = CR_PAGE_ER;
	FLASH->ADDR = addr;
	FLASH->CTLR = CR_PAGE_ER | CR_STRT_Set;
	while( FLASH->STATR & FLASH_STATR_BSY );
	FLASH->CTLR = CR_PAGE_PG;
	FLASH->CTLR = CR_PAGE_PG | CR_BUF_RST;
	while( FLASH->STATR & FLASH_STATR_BSY );
	for( int i = 0; i < 16; i++ )
	{
		( (volatile uint32_t *)addr )[i] = src[i];
		FLASH->CTLR = CR_PAGE_PG | CR_BUF_LOAD;
		while( FLASH->STATR & FLASH_STATR_BSY );
	}
	FLASH->ADDR = addr;
	FLASH->CTLR = CR_PAGE_PG | CR_STRT_Set;
	while( FLASH->STATR & FLASH_STATR_BSY );
	FLASH->CTLR = CR_LOCK_Set | 0x8000;  // LOCK + FLOCK (fast mode)
	return memcmp( (const void *)addr, src, 64 );
}

static uint32_t sum16( const uint8_t * p, int n )
{
	uint32_t s = 0;
	while( n-- ) s += *p++;
	return s & 0xffff;
}

static void cfg_build( struct cfg_page * p )  // everything but the name
{
	memset( p, 0, offsetof( struct cfg_page, name ) );
	memset( p->rsv1, 0, sizeof( p->rsv1 ) );
	p->magic = CFG_MAGIC;
	p->version = CFG_VERSION;
	p->show = cfg_show;
	p->style = cfg_style;
	p->level = cfg_level;
	p->flags = ( autolight ? CFG_AUTOLIGHT : 0 ) | ( dim_rail ? CFG_DIM_RAIL : 0 ) | ( cfg_remember ? CFG_REMEMBER : 0 );
	p->sleep_min = cfg_sleep_min;
	p->tap_mask = tap_mask;
	p->drift_mask = anim_drift_mask;
	p->drift_s = anim_drift_s;
	p->fade_ds = anim_fade_ds;
	memcpy( p->pars, anim_pars, sizeof( anim_pars ) );
	p->sum = sum16( (const uint8_t *)p, CFG_SUM );
}

static int cfg_apply( const struct cfg_page * p )
{
	if( p->magic != CFG_MAGIC || p->version != CFG_VERSION || p->sum != sum16( (const uint8_t *)p, CFG_SUM ) ) return 0;
	cfg_show = p->show;
	cfg_style = p->style ? STYLE_RETRO : STYLE_NORMAL;
	cfg_level = p->level < USER_LEVEL_MIN ? USER_LEVEL_MIN : p->level;
	autolight = ( p->flags & CFG_AUTOLIGHT ) != 0;
	dim_rail = ( p->flags & CFG_DIM_RAIL ) != 0;
	cfg_remember = ( p->flags & CFG_REMEMBER ) != 0;
	cfg_sleep_min = p->sleep_min ? p->sleep_min : SLEEP_MIN;
	tap_mask = p->tap_mask;
	anim_drift_mask = p->drift_mask;
	anim_drift_s = p->drift_s < 5 ? 5 : p->drift_s;
	anim_fade_ds = p->fade_ds;
	memcpy( anim_pars, p->pars, sizeof( anim_pars ) );
	anim_params_changed();
	return 1;
}

static void cfg_name_from_flash( struct cfg_page * p )
{
	if( flash_cfg->magic == CFG_MAGIC ) memcpy( p->name, flash_cfg->name, 16 );
	else memset( p->name, 0, 16 );
}

// A store request from USB (NP_REPORT_STORE), in store_buf.
static void store_task( void )
{
	store_lock = 1;
	store_req = 0;
	int page = store_buf[1], op = store_buf[2], st = ST_OK;
	uint8_t * d = store_buf + 4;
	if( page >= STORE_PAGES || op < ST_OP_READ || op > ST_OP_APPLY || ( page && op == ST_OP_APPLY ) ) st = ST_ERR;
	else if( page == 0 )
	{
		if( op == ST_OP_READ ) cfg_name_from_flash( store_cfg );
		else if( !cfg_apply( store_cfg ) ) st = ST_ERR;
		else store_gen++;
		cfg_build( store_cfg );  // reply: the settings as they are now
		if( st == ST_OK && op == ST_OP_WRITE )
		{
			if( flash_page_write( STORE_ADDR, (const uint32_t *)d ) ) st = ST_ERR;
			cfg_dirty = 0;
		}
	}
	else
	{
		uint32_t addr = STORE_ADDR + page * 64;
		if( op == ST_OP_WRITE )
		{
			if( flash_page_write( addr, (const uint32_t *)d ) ) st = ST_ERR;
			anim_store_changed();
			store_gen++;
			if( show >= ANIM_CUSTOM0 && show - ANIM_CUSTOM0 >= anim_custom_count() ) set_show( ANIM_CANDLE );
		}
		memcpy( d, (const void *)addr, 64 );
	}
	store_buf[2] = st;
	store_lock = 0;
}

static void save_task( void )
{
	store_lock = 1;
	if( store_req ) { store_lock = 0; return; }  // a USB request is waiting for the buffer: later
	store_buf[1] = 0xff;  // the buffer no longer holds a page the app asked for
	store_buf[2] = 0;
	cfg_name_from_flash( store_cfg );
	cfg_build( store_cfg );
	if( memcmp( store_cfg, flash_cfg, 64 ) ) flash_page_write( STORE_ADDR, (const uint32_t *)store_cfg );
	cfg_dirty = 0;
	store_lock = 0;
}

// ---- USB ---------------------------------------------------------------------------------------

void usb_handle_user_in_request( struct usb_endpoint * e, uint8_t * scratchpad, int endp, uint32_t sendtok, struct rv003usb_internal * ist )
{
	// Only control transfers are used; the interrupt endpoint stays empty.
	usb_send_empty( sendtok );
}

void usb_handle_hid_get_report_start( struct usb_endpoint * e, int reqLen, uint32_t lValueLSBIndexMSB )
{
	int id = lValueLSBIndexMSB & 0xff;
	if( id == NP_REPORT_STATUS )
	{
		if( reqLen > (int)sizeof( status ) ) reqLen = sizeof( status );
		e->opaque = (uint8_t *)&status;
		e->max_len = reqLen;
		status_read = 1;
	}
	else if( id == NP_REPORT_STORE )
	{
		if( reqLen > (int)sizeof( store_buf ) ) reqLen = sizeof( store_buf );
		store_buf[0] = NP_REPORT_STORE;
		e->opaque = store_buf;
		e->max_len = reqLen;
	}
}

void usb_handle_hid_set_report_start( struct usb_endpoint * e, int reqLen, uint32_t lValueLSBIndexMSB )
{
	int id = usb_set_report_id = lValueLSBIndexMSB & 0xff;
	int max = id == NP_REPORT_COMMAND ? (int)sizeof( cmd_buf ) : id == NP_REPORT_LIVE ? 21 : id == NP_REPORT_STORE ? (int)sizeof( store_buf ) : 0;
	if( !max ) return;  // 0xFD (reboot) is handled inside rv003usb
	if( reqLen > max ) reqLen = max;
	e->max_len = reqLen;
}

void usb_handle_user_data( struct usb_endpoint * e, int current_endpoint, uint8_t * data, int len, struct rv003usb_internal * ist )
{
	int id = usb_set_report_id;
	uint8_t * dst = id == NP_REPORT_COMMAND ? cmd_buf : id == NP_REPORT_LIVE ? anim_live : id == NP_REPORT_STORE ? store_buf : 0;
	if( current_endpoint || !dst ) return;
	if( dst == store_buf && store_lock ) { usb_set_report_id = 0; return; }  // the main loop has the buffer: dropped, the app retries
	int offset = e->count << 3;
	int torx = e->max_len - offset;
	if( torx > len ) torx = len;
	if( torx <= 0 ) return;
	memcpy( dst + offset, data, torx );  // the live frame goes straight into anim_live
	e->count++;
	if( offset + torx >= e->max_len )
	{
		if( id == NP_REPORT_COMMAND ) cmd_pending = 1;
		else if( id == NP_REPORT_LIVE ) live_req = 1;
		else { store_req = 1; store_req_ms = now_ms; }
	}
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
		if( c[2] == MODE_OFF ) power_off();
		else if( c[2] == MODE_AUTO ) { power_on(); set_show( show ); }
		else if( c[2] == MODE_MANUAL ) mode = MODE_MANUAL;
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
	case CMD_PWM:
	{
		uint32_t f = c[2] < 1 ? 1 : c[2] > PWM_FRAME_MS_MAX ? PWM_FRAME_MS_MAX : c[2];
		uint32_t m = c[3] | ( c[4] << 8 );
		if( m > f * 1000 ) m = f * 1000;
		pwm_frame_us = f * 1000;
		pwm_min_us = m;
		break;
	}
	case CMD_STYLE:
		set_style( c[2] ? STYLE_RETRO : STYLE_NORMAL );
		state_changed();
		break;
	case CMD_SHOW:
		if( c[2] < SHOWS || ( c[2] >= ANIM_CUSTOM0 && c[2] - ANIM_CUSTOM0 < anim_custom_count() ) )
		{
			power_on();
			set_show( c[2] );
			state_changed();
		}
		break;
	case CMD_USER_LEVEL:
		user_level = c[2] < USER_LEVEL_MIN ? USER_LEVEL_MIN : c[2];
		state_changed();
		break;
	case CMD_BUDGET:
		budget_enabled = c[2] != 0;
		break;
	case CMD_PERIOD:
		period = arg16 > PERIOD_MAX ? PERIOD_MAX : arg16 < ton + PERIOD_MARGIN ? ton + PERIOD_MARGIN : arg16;
		TIM2->ATRLR = period - 1;  // preloaded (ARPE): takes effect at the next update
		break;
	case CMD_TOUCH_DELTA:
		touch_delta = arg16 ? arg16 : TOUCH_DELTA_DEFAULT;
		break;
	case CMD_SLEEP:
		sleep_set( c[2] != 0 );
		break;
	case CMD_AUTOLIGHT:
		autolight = c[2] != 0;
		cfg_touch();
		break;
	case CMD_DIM:
		dim_rail = c[2] != 0;
		kick_until = now_ms + KICK_MS;
		cfg_touch();
		break;
	case CMD_WAVE:
		on_gesture( GESTURE_WAVE );
		break;
	case CMD_SAVE:
		if( cfg_dirty ) cfg_dirty_ms = now_ms - SAVE_DELAY_MS;
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

// HV target: fixed (duty dimming, test shows) or the simulator's rail for the animations.
static uint32_t hv_target( int animating )
{
	if( !animating || !dim_rail ) return hv_set_v * 1000u;
	if( sleep_q <= 82 ) return 0;  // sleep timer at its end (simulator: sleepMul <= 0.02)
	uint32_t vset = RAIL_SPAN_MV * user_level / 255;
	uint32_t vs = vset * ( adapt_q * sleep_q >> 12 ) >> 12;
	if( (int32_t)( now_ms - kick_until ) < 0 ) return vs + RAIL_MIN_MV > RAIL_KICK_MV ? vs + RAIL_MIN_MV : RAIL_KICK_MV;
	return RAIL_MIN_MV + ( vs * anim_rail >> 12 );
}

static void ms_task( void )
{
	static uint32_t anim_last, pub_key;
	uint32_t ms = ++now_ms;
	anim_tick_ms();

	if( cmd_pending ) handle_command();

	// Live frames from the app: switch to live mode while they keep coming (not while the tree is off).
	if( live_req )
	{
		live_req = 0;
		if( mode != MODE_OFF && !daylight_off && !fault )
		{
			if( show != ANIM_LIVE ) { live_return = show; mode = MODE_AUTO; set_show( ANIM_LIVE ); }
			live_until = ms + LIVE_TIMEOUT_MS;
		}
	}
	if( show == ANIM_LIVE && (int32_t)( ms - live_until ) >= 0 ) set_show( live_return );
	if( cfg_dirty && ms - cfg_dirty_ms >= SAVE_DELAY_MS ) job_save = 1;

	// Sleep timer: dims over 20 minutes, then the tree switches off.
	if( sleep_active && mode != MODE_OFF )
	{
		if( sleep_left_ms ) sleep_left_ms--;
		else power_off();
	}
	if( sleep_active ) sleep_q = sleep_left_ms / sleep_div;
	else sleep_q = Q;

	int on = mode != MODE_OFF && !daylight_off;
	int animating = on && mode == MODE_AUTO && IS_ANIM( show );

	// HV regulation targets (VDD is re-measured every 100 ms).
	vdd_task( ms );
	hv_mv = vfb_last * mv_per_count_q4 >> 4;
	hv_target_mv = on ? hv_target( animating ) : 0;

	int want = on && hv_target_mv && !fault;
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
	uint32_t set_mv = hv_target_mv;
	if( ramp_mv + HV_RAMP_MV_PER_MS < set_mv ) ramp_mv += HV_RAMP_MV_PER_MS;
	else ramp_mv = set_mv;
	vfb_target = ramp_mv * count_per_mv_q20 >> 20;

	if( boost_on && hv_mv < NORISE_MV )
	{
		if( ++low_ms >= NORISE_MS ) set_fault( FAULT_NO_RISE );
	}
	else low_ms = 0;

	// ---- Lamps
	int lamps_ok = on && !fault && boost_on;
	if( animating && lamps_ok )
	{
		// Brightness factors for publish_lamp(): sleep fade, and (duty dimming) the simulator's
		// rail span 75..105 V as lamp current 1/3 .. 1.
		anim_sm = sleep_q * 5734 >> 12;  // clamp(1.4 * sleepMul)
		if( anim_sm > Q ) anim_sm = Q;
		if( dim_rail ) anim_L = Q;
		else
		{
			int32_t x = ( user_level * Q / 255 ) * adapt_q >> 12;
			x = ( x * sleep_q >> 12 ) * anim_rail >> 12;
			anim_L = 1365 + ( 2731 * x >> 12 );
		}
		anim_active = 1;
		if( !anim_busy() && pub_i >= 10 && ms - anim_last >= ANIM_PERIOD_MS )
		{
			anim_last = ms;
			int prev = IS_ANIM( prev_show ) ? prev_show : show;
			uint32_t since = ms - fade_start, fd = anim_fade_ds ? anim_fade_ds * 100 : 1;  // clamp first: * Q overflows
			if( since > fd ) since = fd;
			anim_start( show, prev, anim_smooth( since * Q / fd ) );
		}
		level = anim_L >> 4;
		pub_key = 0xffffffff;
	}
	else
	{
		anim_active = 0;
		if( mode == MODE_AUTO && !paused && !fault && !IS_ANIM( show ) )
		{
			if( ++step_ms >= seq_len_ms( step ) )
			{
				step_ms = 0;
				if( show == SHOW_TEST && ++step >= SEQ_STEPS ) step = SEQ_LAMP0;
			}
		}

		uint32_t lamps = 0;
		if( lamps_ok )
		{
			if( mode == MODE_AUTO && show == SHOW_GLOW )
				lamps = ALL_LAMPS( LAMP_AC );
			else if( mode == MODE_AUTO && !( step >= SEQ_LAMP0 && step < SEQ_ALL_K && step_ms < SEQ_GAP_MS ) )
				lamps = seq_lamps( step );
			else if( mode == MODE_MANUAL ) lamps = manual_lamps;
		}
		level = 255;
		if( mode == MODE_MANUAL ) level = manual_level;
		else if( show != SHOW_GLOW && step == SEQ_SWEEP )  // triangle, 0 -> 255 -> 0
		{
			uint32_t half = SWEEP_MS / 2;
			uint32_t t = step_ms < half ? step_ms : SWEEP_MS - 1 - step_ms;
			level = t * 255 / ( half - 1 );
		}
		if( mode == MODE_AUTO && level )  // overall brightness from the touch ramp
		{
			level = level * user_level / 255;
			if( !level ) level = 1;
		}
		// Only recompute when something changed; done lamp by lamp in the background (publish_lamp).
		uint32_t key = lamps ^ ( (uint32_t)level << 20 ) ^ ( pwm_frame_us << 3 ) ^ ( pwm_min_us << 16 );
		if( key != pub_key && pub_i >= 10 && !anim_busy() )
		{
			pub_key = key;
			pub_lamps = lamps;
			pub_level = level;
			pub_states = 1;
			pub_i = 0;
		}
	}

	// Power budget: the rail is the sensor. Sagging -> scale every lamp's on-time (above the minimum)
	// down quickly; holding the target -> let it creep back. HV averaged over ~16 ms, because C4 dips a
	// little whenever a window starts even when the boost has power to spare on average.
	static uint32_t hv_avg_x16;
	hv_avg_x16 += hv_mv - hv_avg_x16 / 16;
	uint32_t hv_avg = hv_avg_x16 / 16;
	uint16_t old_budget = budget;
	if( !budget_enabled ) budget = 256;
	else if( boost_on && lamps_lit )
	{
		if( hv_avg + BUDGET_SAG_MV < ramp_mv ) { if( budget > BUDGET_MIN ) budget -= budget / 64 + 1; }
		else if( hv_avg + BUDGET_OK_MV >= ramp_mv && budget < 256 ) budget++;
	}
	if( budget != old_budget ) job_scale = 1;

	// ---- Sensors
	if( ms % 20 == 0 ) job_touch = 1;
	if( autolight )
	{
		if( ms % 4 == 2 )  // 25 samples per light slot
		{
			ldr_acc += adc_read( ADC_CH_LDR );
			duty_acc += duty_q12;
			ldr_n++;
		}
		// Dark-slot blanking (all lamps off for DARK_SLOT_US every LIGHT_SLOT_MS) is commented out for now.
		// Without it the "ambient" reading is the plain average, i.e. room light + the tree's own light:
		// auto on/off sees the tree too, and only shadow waves work (reflection = 0).
		// if( ms % LIGHT_SLOT_MS == 0 ) dark_req = 1;
		// if( dark_done ) { dark_done = 0; job_light = 1; }
		if( ms % LIGHT_SLOT_MS == 0 && ldr_n )
		{
			ldr_dark = ldr_acc / ldr_n;
			job_light = 1;
		}
	}
	else if( ms % LIGHT_SLOT_MS == 0 )
	{
		ldr_dark = 0;
		job_light = 1;  // clears the light features
	}

	if( ms % 16 == 5 ) job_status = 1;
	if( ms % 1000 == 500 ) job_stack = 1;
}

// Status block for USB (every 16 ms is plenty), as a deferred job.
static void status_task( void )
{
	uint32_t ms = now_ms;
	if( ms % 100 < 16 )
	{
		status.duty_pm = passes ? pulse_passes * 1000 / passes : 0;
		passes = pulse_passes = 0;
		status.late_us = late_max / DELAY_US_TIME;
		late_max = 0;
	}
	status.report_id = NP_REPORT_STATUS;
	status.fw_version = FW_VERSION;
	status.mode = mode;
	status.step = step;
	status.fault = fault;
	status.flags = ( touched ? 1 : 0 ) | ( paused ? 2 : 0 ) | ( boost_on ? 4 : 0 );
	status.hv_set = hv_target_mv / 1000;
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
	status.budget = budget > 255 ? 255 : budget;
	status.pwm_ms = pwm_frame_us / 1000;
	status.pwm_min_10us = pwm_min_us / 10 > 255 ? 255 : pwm_min_us / 10;
	status.show = show;
	status.style = style;
	status.user_level = user_level;
	status.gesture = gesture;
	status.sleep_min = sleep_active ? ( sleep_left_ms + 59999 ) / 60000 : 0;
	status.flags2 = ( sleep_active ? 1 : 0 ) | ( daylight_off ? 2 : 0 ) | ( autolight ? 4 : 0 ) | ( dim_rail ? 8 : 0 );
	status.lux = lux > 255 ? 255 : lux;
	status.late_peak_us = late_peak / DELAY_US_TIME;
	if( status_read ) { status_read = 0; late_peak = 0; }
	status.adapt = adapt_q >> 4 > 255 ? 255 : adapt_q >> 4;
	status.caps = 7;
	status.store_pages = STORE_PAGES;
	status.n_custom = anim_custom_count();
	status.cfg_flags = ( autolight ? CFG_AUTOLIGHT : 0 ) | ( dim_rail ? CFG_DIM_RAIL : 0 ) | ( cfg_remember ? CFG_REMEMBER : 0 ) | ( cfg_dirty ? 0x80 : 0 );
	status.store_gen = store_gen;
}

// Stack use: main() paints the free RAM above .bss at start-up; whatever is still painted was never used.
extern uint32_t _ebss[];
#define STACK_PAINT 0xa5a5a5a5u

static void __attribute__((noinline)) stack_paint( void )
{
	uint32_t * p = _ebss, * sp;
	__asm__ volatile( "mv %0, sp" : "=r"( sp ) );
	while( p < sp - 16 ) *p++ = STACK_PAINT;
}

static void stack_task( void )
{
	uint32_t * p = _ebss;
	while( *p == STACK_PAINT ) p++;
	status.stack_free = ( p - _ebss ) * 4;
}

// Every main-loop pass: lamp PWM. Returns the time (SysTick ticks) to the next lamp edge, so the main
// loop can keep longer work away from edges.
// Lamp i's window starts i/10 of a frame later than lamp i-1's, so the HV load is spread over the
// frame instead of arriving as one block (C4 can't buffer a block; the boost would idle the rest).
// Inside its window a lamp lights its left electrode first, then the right one.
static uint32_t lamp_pwm( void )
{
	static uint32_t frame_start, dark_until, edge_at;
	static uint8_t dark;
	uint32_t now = SysTick->CNT;

	// How late is this call for the edge the previous call predicted?
	int32_t late = (int32_t)( now - edge_at );
	if( late > 0 )
	{
		if( (uint32_t)late > late_max ) late_max = late;
		if( (uint32_t)late > late_peak ) late_peak = late;
	}

	if( dark )  // light sensor dark slot: everything off, read the room at its end
	{
		if( (int32_t)( now - dark_until ) >= 0 )
		{
			ldr_dark = adc_read( ADC_CH_LDR );
			dark = 0;
			dark_done = 1;
			edge_at = now;
			return 0;
		}
		edge_at = dark_until;
		return dark_until - now;
	}
	if( dark_req )
	{
		dark_req = 0;
		dark = 1;
		dark_until = now + DARK_SLOT_US * DELAY_US_TIME;
		outs_set( 0 );
		edge_at = dark_until;
		return dark_until - now;
	}

	uint32_t frame = pwm_frame_us * DELAY_US_TIME;
	uint32_t t = now - frame_start;
	if( t >= frame )
	{
		frame_start += frame;
		if( now - frame_start >= frame ) frame_start = now;  // fell behind (USB): resync
		t = now - frame_start;
	}
	static uint32_t last_u[10];
	uint32_t o = 0, off = 0, step10 = frame / 10, next = frame - t;  // frame start at the latest
	for( int i = 0; i < 10; i++, off += step10 )
	{
		uint32_t u = t >= off ? t - off : t + frame - off;  // position inside lamp i's own window
		if( u < last_u[i] ) { on1[i] = nx1[i]; on2[i] = nx2[i]; }  // its window just started: new values
		last_u[i] = u;
		uint32_t e1 = on1[i], e2 = on1[i] + on2[i], d;
		if( u < e1 ) { o |= k_mask[i]; d = e1 - u; }
		else if( u < e2 ) { o |= a_mask[i]; d = e2 - u; }
		else if( e2 ) d = frame - u;   // this lamp's next window start
		else continue;                 // dark lamp: no edges
		if( d < next ) next = d;
	}
	outs_set( o );
	edge_at = now + next;
	return next;
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
	outs_write( 0, 0xffffffff );
	outs_now = 0;
	for( int i = 0; i < 10; i++ )
	{
		k_mask[i] = 1u << lamp_sw[i][0];
		a_mask[i] = 1u << lamp_sw[i][1];
	}

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
	stack_paint();

	gpio_init();  // lamps off before anything else (R2 holds the boost gate low until TIM2 runs)

	// Settings and custom animations from the store
	anim_store_changed();
	cfg_apply( flash_cfg );  // the static initializers are the defaults
	anim_params_changed();
	set_style( cfg_style );
	user_level = cfg_level;
	if( cfg_show <= ANIM_DRIFT || ( cfg_show >= ANIM_CUSTOM0 && cfg_show - ANIM_CUSTOM0 < anim_custom_count() ) )
		show = prev_show = cfg_show;
	sleep_set( 0 );
	status.uid = *(volatile uint32_t *)0x1ffff7e8 ^ *(volatile uint32_t *)0x1ffff7ec ^ *(volatile uint32_t *)0x1ffff7f0;

	// Force re-enumeration: the bootloader may have just been on the bus with the same D- pull-up.
	funPinMode( PD4, GPIO_CFGLR_OUT_10Mhz_PP );
	GPIOD->BSHR = 1u << ( 4 + 16 );
	Delay_Ms( 20 );
	usb_setup();

	adc_init();
	measure_vdd();
	hv_scale_update();
	boost_init();
	iwdg_init();

	uint32_t ms_tick = SysTick->CNT;
	while( 1 )
	{
		IWDG->CTLR = 0xaaaa;
		boost_regulate();
		uint32_t gap = lamp_pwm();

		// Background work, one small piece per pass and only with room before the next lamp edge:
		// animation electrodes, then publishing lamps.
		if( gap > GUARD_BG_US * DELAY_US_TIME && ( anim_busy() || pub_i < 10 ) )
		{
				if( anim_busy() ) { if( anim_step() && anim_active ) { pub_states = 0; pub_i = 0; } }
			else publish_lamp();
			gap = lamp_pwm();
		}

		// 1 ms core: also waits for a gap, but never longer than MS_TASK_MAX_DELAY_US.
		int32_t due = (int32_t)( SysTick->CNT - ms_tick ) - (int32_t)DELAY_MS_TIME;
		if( due >= 0 && ( gap > GUARD_MS_US * DELAY_US_TIME || due > MS_TASK_MAX_DELAY_US * DELAY_US_TIME ) )
		{
			ms_tick += DELAY_MS_TIME;
			ms_task();
			gap = lamp_pwm();
		}

		// Deferred jobs, one per pass, only in a gap (they are not time critical).
		if( gap > GUARD_JOB_US * DELAY_US_TIME )
		{
			if( store_req && now_ms - store_req_ms >= 3 ) store_task();
			else if( job_touch ) { job_touch = 0; touch_task(); }
			else if( job_light ) { job_light = 0; if( !autolight ) ldr_dark = 0; light_task(); }
			else if( job_scale ) { job_scale = 0; scale_task(); }
			else if( job_status ) { job_status = 0; status_task(); }
			else if( job_save ) { job_save = 0; save_task(); }
			else if( job_stack ) { job_stack = 0; stack_task(); }
		}
	}
}
