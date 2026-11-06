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
	ANIM_DRIFT,        // cycles 0-5, 3 min each, 1.5 s crossfades
	ANIM_SLEEP,        // candle + the 20 min sleep timer
	ANIMS
};

#define ANIM_FADE_MS 1500  // crossfade between modes

void anim_tick_ms( void );                        // advance the animation clocks, every ms
void anim_start( int cur, int prev, int32_t k );  // start a frame: prev * (1 - k) + cur * k, k in Q12
int anim_step( void );                            // one electrode of work; 1 = frame complete
int anim_busy( void );

extern int32_t anim_e1[10], anim_e2[10];  // last completed frame, Q12 duty requests (before share())
extern int32_t anim_rail;                 // 0..4096: the simulator's "rail" (whole-tree brightness)

int32_t anim_smooth( int32_t x );  // smoothstep, Q12
