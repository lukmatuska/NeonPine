// NeonPine animations: fixed-point port of frame(m, t) from the NeonPine simulator artifact.
// Values are Q12 (4096 = 1.0). e1 = left electrode (lamp pad 1, K-side switch), e2 = right (pad 2, A side).
#pragma once
#include <stdint.h>

enum {
	ANIM_CANDLE = 0,   // every electrode flickers on its own
	ANIM_BREATHE,      // the whole tree breathes (rail), glow drifts left <-> right
	ANIM_TWINKLE,      // random electrodes swell and fade
	ANIM_GARLAND,      // chase up the tiers, half a lamp at a time, then a star flash
	ANIM_SNOWFALL,     // soft pulses drifting down the tree
	ANIM_HEARTBEAT,    // steady tree, the star beats twice per second (left, then right electrode)
	ANIM_DRIFT,        // cycles through the drift list (default 0-5), 3 min each, crossfades
	ANIM_SLEEP,        // candle + the sleep timer
	ANIMS
};
#define ANIM_BASIC    6   // modes 0-5 have parameters (speed, gain, offset)
#define ANIM_LIVE     15  // frames streamed over USB by the companion app (NP_REPORT_LIVE)
#define ANIM_CUSTOM0  16  // custom keyframe animations from the store: 16 .. 16 + ANIM_CUSTOMS - 1
#define ANIM_CUSTOMS  8
#define IS_ANIM( s )  ( (s) < ANIMS || ( (s) >= ANIM_LIVE && (s) < ANIM_CUSTOM0 + ANIM_CUSTOMS ) )

// Store: the last STORE_PAGES flash pages. Page 0 = settings (neonpine_test.c), pages 1.. = custom
// animation blob (format in anim.c and ../../companion). Firmware updates don't touch it as long as
// the image stays below STORE_ADDR (the Makefile checks).
#define STORE_PAGES   16
#define STORE_ADDR    ( 0x08004000u - STORE_PAGES * 64u )
#define BLOB_ADDR     ( STORE_ADDR + 64u )
#define BLOB_MAX      ( ( STORE_PAGES - 1 ) * 64u )

struct anim_par { uint8_t speed, gain; int8_t offset; };  // speed 64 = 1x, gain 128 = 1x, offset in 1/256

void anim_tick_ms( void );                        // advance the animation clocks, every ms
void anim_start( int cur, int prev, int32_t k );  // start a frame: prev * (1 - k) + cur * k, k in Q12
int anim_step( void );                            // one electrode of work; 1 = frame complete
int anim_busy( void );
void anim_params_changed( void );                 // after changing anim_pars
void anim_store_changed( void );                  // after the custom blob in flash changed: validate it
int anim_custom_count( void );

extern int16_t anim_e1[10], anim_e2[10];  // last completed frame, Q12 duty requests (before share())
extern int32_t anim_rail;                 // 0..4096: the simulator's "rail" (whole-tree brightness)
extern struct anim_par anim_pars[ANIM_BASIC];
extern uint8_t anim_live[21];             // live report: [id], left electrodes LA1-10, then right, 0-255
extern uint32_t anim_cur_t0, anim_prev_t0;  // when the current / previous show started (custom time)
extern uint16_t anim_drift_s;             // drift: time per animation, s
extern uint16_t anim_drift_mask;          // drift list: bits 0-5 = modes 0-5, bits 8-15 = custom 0-7
extern uint8_t anim_fade_ds;              // crossfade between modes, 0.1 s
extern uint8_t anim_dark;                 // retro style: modes 0-5 without brightness floors, dim electrodes off

int32_t anim_smooth( int32_t x );  // smoothstep, Q12
