"""The firmware's built-in animations, ported 1:1 from firmware/neonpine_test/anim.c (same Q12 integer math
and tables), so previews in the app look exactly like the tree.

Times are ms since the tree started (the firmware's animation clock = status uptime).
"""
Q = 4096
ROW = [0, 1, 1, 2, 2, 2, 3, 3, 3, 3]
GARLAND_RANK = [9, 7, 8, 6, 5, 4, 0, 1, 2, 3]
BASE_INC = [170, 392, 869, 157, 362, 802, 46, 3050, 1291, 7047]
INC_MODE = [0, 0, 0, 0, 0, 0, 0, 1, 1, 4]
CANDLE, BREATHE, TWINKLE, GARLAND, SNOWFALL, HEARTBEAT, DRIFT, SLEEP = range(8)
M32 = 0xFFFFFFFF

# anim_tables.h (tools/gen_anim_tables.py)
SIN = [
    0, 101, 201, 301, 401, 501, 601, 700, 799, 897, 995, 1092, 1189, 1285, 1380, 1474,
    1567, 1660, 1751, 1842, 1931, 2019, 2106, 2191, 2276, 2359, 2440, 2520, 2598, 2675, 2751, 2824,
    2896, 2967, 3035, 3102, 3166, 3229, 3290, 3349, 3406, 3461, 3513, 3564, 3612, 3659, 3703, 3745,
    3784, 3822, 3857, 3889, 3920, 3948, 3973, 3996, 4017, 4036, 4052, 4065, 4076, 4085, 4091, 4095,
    4096,
]
EXP = [
    4096, 3848, 3615, 3396, 3190, 2997, 2815, 2645, 2484, 2334, 2192, 2060, 1935, 1818, 1707, 1604,
    1507, 1416, 1330, 1249, 1174, 1102, 1036, 973, 914, 859, 807, 758, 712, 669, 628, 590,
    554, 521, 489, 460, 432, 406, 381, 358, 336, 316, 297, 279, 262, 246, 231, 217,
    204, 192, 180, 169, 159, 149, 140, 132, 124, 116, 109, 103, 96, 90, 85, 80,
    75, 70, 66, 62, 58, 55, 52, 48, 46, 43, 40, 38, 35, 33, 31, 29,
    28, 26, 24, 23, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 12, 11,
    10, 10, 9, 8, 8, 7, 7, 7, 6, 6, 5, 5, 5, 5, 4, 4,
    4, 4, 3, 3, 3, 3, 3, 2, 2, 2, 2, 2, 2, 2, 2, 1,
    1,
]
PERM = [
    93, 121, 249, 184, 162, 236, 129, 14, 50, 89, 155, 243, 128, 79, 215, 179,
    20, 226, 116, 66, 186, 124, 136, 195, 7, 219, 108, 102, 169, 35, 157, 183,
    58, 40, 232, 225, 200, 32, 99, 97, 198, 211, 133, 41, 67, 119, 246, 60,
    190, 230, 247, 0, 245, 81, 125, 167, 72, 191, 188, 239, 10, 70, 96, 24,
    8, 126, 164, 174, 212, 238, 118, 132, 56, 26, 192, 163, 131, 68, 148, 145,
    114, 111, 27, 4, 37, 86, 251, 52, 21, 77, 222, 254, 49, 51, 57, 141,
    194, 120, 127, 82, 175, 29, 91, 172, 113, 242, 115, 2, 135, 6, 65, 101,
    39, 201, 235, 210, 36, 48, 78, 31, 47, 193, 22, 159, 42, 83, 61, 227,
    139, 100, 197, 221, 15, 153, 130, 206, 28, 241, 248, 54, 234, 151, 134, 12,
    38, 173, 220, 143, 137, 90, 250, 160, 104, 95, 150, 71, 73, 80, 5, 152,
    13, 55, 214, 107, 45, 170, 154, 217, 110, 62, 158, 25, 233, 109, 207, 53,
    122, 44, 213, 138, 178, 92, 252, 106, 98, 204, 105, 255, 182, 147, 218, 165,
    146, 244, 1, 74, 209, 181, 9, 16, 180, 203, 177, 237, 228, 43, 103, 88,
    231, 69, 94, 87, 64, 19, 166, 23, 112, 144, 149, 208, 189, 30, 75, 140,
    187, 240, 11, 18, 205, 223, 171, 216, 46, 3, 76, 176, 156, 224, 229, 84,
    59, 185, 85, 63, 117, 253, 168, 33, 123, 17, 34, 196, 142, 161, 199, 202,
]


def clampq(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def cdiv(a, b):  # C integer division (truncates toward zero)
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def smooth(x):
    x = clampq(x, 0, Q)
    return ((x * x >> 12) * (3 * Q - 2 * x)) >> 12


def sin_at(i):
    q = i & 127
    v = SIN[128 - q if q > 64 else q]
    return -v if i & 128 else v


def sinq(ph):
    ph &= 0xFFFF
    i, f = ph >> 8, ph & 255
    a, b = sin_at(i), sin_at(i + 1)
    return a + ((b - a) * f >> 8)


def expneg(x):
    if x <= 0:
        return Q
    if x >= 8 * Q:
        return 0
    i, f = x >> 8, x & 255
    a, b = EXP[i], EXP[i + 1]
    return a + ((b - a) * f >> 8)


def hashq(seed, i):
    return PERM[(PERM[(i ^ (i >> 8)) & 255] + seed) & 255] << 4


def vnoise(seed, x):
    x &= M32
    i = x >> 16
    a, b = hashq(seed, i), hashq(seed, (i + 1) & 0xFFFF)
    return a + ((b - a) * smooth((x >> 4) & 0xFFF) >> 12)


class Clocks:
    """The firmware's animation clocks at time t for constant parameters (as if set since power-up)."""
    __slots__ = ("ms", "a", "tw", "ga", "hb")

    def __init__(self, t, params):
        sp = [p.speed for p in params]
        self.ms = t
        self.a = [((BASE_INC[k] * sp[INC_MODE[k]]) >> 6) * t & M32 for k in range(10)]
        self.tw = (sp[TWINKLE] * t & M32) >> 6
        self.ga = (sp[GARLAND] * t & M32) >> 6
        self.hb = (sp[HEARTBEAT] * t & M32) >> 6


def candle(i, side, c):
    seed = i + 101 if side else i + 1
    a = c.a[3:6] if side else c.a[0:3]
    f = (vnoise(seed, a[0]) * 2253 + vnoise(seed + 11, a[1]) * 1147 + vnoise(seed + 23, a[2]) * 696) >> 12
    dip = 1229 if vnoise(i + 90 if side else i + 40, c.a[6]) > 3809 else 0
    return clampq(1147 + (1638 * f >> 12) - dip, 328, 2458)


def breathe(i, side, c):
    s = 2048 + (sinq((c.a[8] >> 8) - ROW[i] * 5243) >> 1)
    return Q - s if side else s


def breathe_rail(c):
    return 328 + (3768 * (2048 - (sinq((c.a[7] >> 8) + 16384) >> 1)) >> 12)


def twinkle(i, side, c):
    j = side * 10 + i
    p = 2200 + (hashq(31, j) * 3200 >> 12)
    ph = (c.tw + (hashq(57, j) * p >> 12)) % p
    e = smooth(ph * Q // 350) if ph < 350 else expneg((ph - 350) * Q // 550)
    return 246 + (3441 * e >> 12)


def garland(i, side, c):
    cyc = c.ga % 5200
    k = GARLAND_RANK[i]
    if cyc <= 3400:
        pos = cyc * 81920 // 3400
        if not side:
            return 205 + (2253 * clampq(pos - 2 * k * Q, 0, Q) >> 12)
        return 205 + (1638 * clampq(pos - (2 * k + 1) * Q, 0, Q) >> 12)
    ft = cyc - 3400
    if ft < 180 or i == 0:
        return 2048
    return 205 + (1843 * expneg(ft * 9011 // 1000) >> 12)


def snowfall(i, side, c):
    ph = (c.a[9] >> 8) - ROW[i] * 14418
    ph += 19661 + (hashq(89, i) * 7864 >> 12) if side else (hashq(51, i) * 3932 >> 12)
    s = max(0, sinq(ph))
    s2 = s * s >> 12
    s6 = ((s2 * s2 >> 12) * s2) >> 12
    return 205 + (2867 * s6 >> 12)


def heartbeat(i, side, c):
    if i:
        return 1147
    cyc = c.hb % 1000
    mu, w = (280, 60) if side else (50, 50)
    d = cdiv((cyc - mu) * Q, w)
    u = 8 * Q if d > 3 * Q or d < -3 * Q else d * d >> 12
    return clampq(614 + (3482 * expneg(u) >> 12), 0, Q)


MODES = [candle, breathe, twinkle, garland, snowfall, heartbeat]


def mode_frame(m, t, params):
    """Modes 0-5 (7 = sleep plays candle): (left[10], right[10]) Q12 after speed / gain / offset."""
    if m == SLEEP:
        m = CANDLE
    c = Clocks(int(t), params)
    fn, p = MODES[m], params[m]
    out = ([0] * 10, [0] * 10)
    for side in (0, 1):
        for i in range(10):
            out[side][i] = clampq((fn(i, side, c) * p.gain >> 7) + p.offset * 16, 0, Q)
    return out


def rail(m, t, params):
    return breathe_rail(Clocks(int(t), params)) if m == BREATHE else Q


def drift_entries(t, cfg, n_custom):
    """Drift (mode 6): [(show, weight Q12, t0)] like the firmware's add_entry()."""
    ids = [k if k < 8 else 16 + k - 8 for k in range(16)
           if cfg.drift_mask >> k & 1 and (k < 6 or (k >= 8 and k - 8 < n_custom))]
    if not ids:
        return [(CANDLE, Q, 0)]
    d = max(5, cfg.drift_s) * 1000
    step, inside = divmod(int(t), d)
    pos = step % len(ids)
    fade = cfg.fade_ds * 100 or 1
    x = inside + fade - d
    f = 0 if x <= 0 else smooth(x * Q // fade)
    return [(ids[pos], Q - f, t - inside), (ids[(pos + 1) % len(ids)], f, t - inside + d)]


def share(a, b):
    """Firmware share(): one lamp's two electrodes together at most the whole window."""
    s = a + b
    if s > Q:
        a = a * Q // s
        b = Q - a
    return a, b
