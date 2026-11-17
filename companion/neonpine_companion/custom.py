"""Custom keyframe animations: the editor's model, JSON files and the tree's binary blob.

Blob (store pages 1.., parsed by anim_store_changed() in firmware/neonpine/anim.c):
  0  u16 magic 0x4E41 ("AN")   2  u16 length incl. header   4  u16 sum of bytes 6 .. length-1
  6  u8  count (<= 8)          7  u8  0
  8  per animation: u8 keys (>= 1), u8 flags (0), u32 duration ms (= sum of the keys), char name[12],
     then per key: u16 duration ms (bits 0-13) | transition to the next key (bits 14-15),
                   u8 level[10] (LA1-10: low nibble left electrode, high nibble right, 0-15)
"""
import json
import struct
from dataclasses import dataclass, field

LEVELS = 15                  # 4-bit levels per electrode
MAX_KEY_MS = 0x3FFF          # 16.383 s
HOLD, LINEAR, SMOOTH = 0, 1, 2
TRANSITIONS = ["Hold", "Linear", "Smooth"]
BLOB_MAGIC = 0x4E41
NAME_LEN = 12
KEY_SIZE = 12
ANIM_HDR = 18
MAX_ANIMS = 8


def _smooth(x):  # firmware anim_smooth(), Q12
    x = 0 if x < 0 else 4096 if x > 4096 else x
    return ((x * x >> 12) * (3 * 4096 - 2 * x)) >> 12


@dataclass
class Key:
    left: list = field(default_factory=lambda: [0] * 10)    # 0-15 per lamp, LA1..LA10
    right: list = field(default_factory=lambda: [0] * 10)
    duration: int = 500                                       # ms until the next key
    transition: int = SMOOTH

    def copy(self):
        return Key(list(self.left), list(self.right), self.duration, self.transition)

    def to_dict(self):
        return {"left": self.left, "right": self.right, "ms": self.duration, "transition": TRANSITIONS[self.transition].lower()}

    @classmethod
    def from_dict(cls, d):
        tr = d.get("transition", "smooth")
        tr = [t.lower() for t in TRANSITIONS].index(tr) if isinstance(tr, str) else int(tr)
        lv = lambda a: [max(0, min(LEVELS, int(v))) for v in (list(a) + [0] * 10)[:10]]
        return cls(lv(d.get("left", [])), lv(d.get("right", [])), max(1, min(MAX_KEY_MS, int(d.get("ms", 500)))), tr)


@dataclass
class CustomAnimation:
    name: str = "New animation"
    keys: list = field(default_factory=lambda: [Key()])

    @property
    def total_ms(self):
        return sum(k.duration for k in self.keys) or 1

    def copy(self):
        return CustomAnimation(self.name, [k.copy() for k in self.keys])

    def key_at(self, t):
        """(index, ms into that key) for time t, looping."""
        t %= self.total_ms
        for i, k in enumerate(self.keys):
            if t < k.duration or i == len(self.keys) - 1:
                return i, t
            t -= k.duration
        return 0, 0

    def frame(self, t):
        """Electrode levels at t ms as Q12 (0-4095), exactly as the firmware computes them."""
        i, dt = self.key_at(max(0, int(t)))
        a = self.keys[i]
        b = self.keys[(i + 1) % len(self.keys)]
        f = 0 if a.transition == HOLD or not a.duration else max(0, min(4096, dt * 4096 // a.duration))
        if a.transition == SMOOTH:
            f = _smooth(f)
        mix = lambda x, y: x * 273 + ((y - x) * 273 * f >> 12)
        return [mix(a.left[j], b.left[j]) for j in range(10)], [mix(a.right[j], b.right[j]) for j in range(10)]

    def to_dict(self):
        return {"name": self.name, "keys": [k.to_dict() for k in self.keys]}

    @classmethod
    def from_dict(cls, d):
        keys = [Key.from_dict(k) for k in d.get("keys", [])] or [Key()]
        return cls(str(d.get("name", "Imported"))[:40], keys)


def blob_size(anims):
    return 8 + sum(ANIM_HDR + KEY_SIZE * len(a.keys) for a in anims)


def pack_blob(anims):
    if len(anims) > MAX_ANIMS:
        raise ValueError("at most %d custom animations" % MAX_ANIMS)
    body = bytearray()
    for a in anims:
        if not 1 <= len(a.keys) <= 255:
            raise ValueError("%s: 1-255 keys" % a.name)
        body += struct.pack("<BBI", len(a.keys), 0, a.total_ms)
        body += a.name.encode("ascii", "replace")[:NAME_LEN].ljust(NAME_LEN, b"\0")
        for k in a.keys:
            body += struct.pack("<H", max(1, min(MAX_KEY_MS, k.duration)) | (k.transition & 3) << 14)
            body += bytes((max(0, min(LEVELS, k.left[j])) | max(0, min(LEVELS, k.right[j])) << 4) for j in range(10))
    tail = bytes([len(anims), 0]) + body
    length = 6 + len(tail)
    return struct.pack("<HHH", BLOB_MAGIC, length, sum(tail) & 0xFFFF) + tail


def unpack_blob(blob):
    if len(blob) < 8:
        return []
    magic, length, csum = struct.unpack_from("<HHH", blob)
    if magic != BLOB_MAGIC or length > len(blob) or sum(blob[6:length]) & 0xFFFF != csum:
        return []
    anims, p = [], 8
    for _ in range(blob[6]):
        n, _flags, _total = struct.unpack_from("<BBI", blob, p)
        name = blob[p + 6:p + 6 + NAME_LEN].split(b"\0")[0].decode("ascii", "replace")
        p += ANIM_HDR
        keys = []
        for _k in range(n):
            w, = struct.unpack_from("<H", blob, p)
            lv = blob[p + 2:p + 12]
            keys.append(Key([b & 15 for b in lv], [b >> 4 for b in lv], w & MAX_KEY_MS, w >> 14))
            p += KEY_SIZE
        anims.append(CustomAnimation(name, keys))
    return anims


def save_json(path, anims):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"format": "neonpine-animations", "version": 1, "animations": [a.to_dict() for a in anims]}, f, indent=1)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if isinstance(d, dict) and "animations" in d:
        return [CustomAnimation.from_dict(a) for a in d["animations"]]
    if isinstance(d, dict) and "keys" in d:
        return [CustomAnimation.from_dict(d)]
    raise ValueError("not a NeonPine animation file")


# ---- generators: fill an animation from a pattern -------------------------------------------------

ROW = [0, 1, 1, 2, 2, 2, 3, 3, 3, 3]          # tier of each lamp (LA1 = star)
ORDER_UP = [6, 7, 8, 9, 5, 4, 3, 1, 2, 0]     # garland order, bottom left to the star
# x position of each electrode (mm, from the PCB) for left-right sweeps
LAMP_X = [100, 95.5, 104.5, 92.01, 100, 107.99, 86, 95, 105, 114]


def _key(left, right, ms, tr=SMOOTH):
    return Key([int(round(v)) for v in left], [int(round(v)) for v in right], ms, tr)


def gen_chase(steps_ms=180, level=15, base=1, both=False):
    keys = []
    for k in ORDER_UP:
        for side in ((0, 1) if not both else (None,)):
            left, right = [base] * 10, [base] * 10
            if side in (0, None):
                left[k] = level
            if side in (1, None):
                right[k] = level
            keys.append(_key(left, right, steps_ms, LINEAR))
    return CustomAnimation("Chase", keys)


def gen_rise(level=15, base=1, ms=600):
    keys = []
    for tier in range(3, -1, -1):
        lv = [level if ROW[i] == tier else base for i in range(10)]
        keys.append(_key(lv, lv, ms))
    return CustomAnimation("Rise", keys)


def gen_rain(level=15, base=1, ms=500):
    keys = []
    for tier in range(4):
        lv = [level if ROW[i] == tier else base for i in range(10)]
        keys.append(_key(lv, lv, ms))
    return CustomAnimation("Rain", keys)


def gen_sweep(level=15, base=1, ms=700):
    xs = sorted(set(LAMP_X))
    lo, hi = min(LAMP_X) - 3, max(LAMP_X) + 3
    keys = []
    for pos in [lo + (hi - lo) * s / 5 for s in range(6)] + [hi - (hi - lo) * s / 5 for s in range(1, 5)]:
        left = [max(base, level - abs(LAMP_X[i] - 1.5 - pos) * 1.2) for i in range(10)]
        right = [max(base, level - abs(LAMP_X[i] + 1.5 - pos) * 1.2) for i in range(10)]
        keys.append(_key(left, right, ms))
    del xs
    return CustomAnimation("Sweep", keys)


def gen_alternate(level=15, base=1, ms=800):
    return CustomAnimation("Ping-pong", [_key([level] * 10, [base] * 10, ms), _key([base] * 10, [level] * 10, ms)])


def gen_pulse(level=15, base=1, ms=1500):
    return CustomAnimation("Pulse", [_key([base] * 10, [base] * 10, ms), _key([level] * 10, [level] * 10, ms)])


def gen_sparkle(level=15, base=2, ms=220, n=16, seed=7):
    import random
    rnd = random.Random(seed)
    keys = []
    for _ in range(n):
        left, right = [base] * 10, [base] * 10
        for _j in range(2):
            (left if rnd.random() < 0.5 else right)[rnd.randrange(10)] = level
        keys.append(_key(left, right, ms, LINEAR))
    return CustomAnimation("Sparkle", keys)


def gen_star(level=15, base=3, ms=400):
    star_l = [base] * 10
    star_r = [base] * 10
    star_l[0] = level
    star_r[0] = level
    return CustomAnimation("Star", [_key([base] * 10, [base] * 10, ms * 3), _key(star_l, star_r, ms), _key(star_l, star_r, ms, SMOOTH)])


GENERATORS = {
    "Chase (up the tree)": gen_chase,
    "Rise (tier by tier)": gen_rise,
    "Rain (top to bottom)": gen_rain,
    "Sweep (left - right)": gen_sweep,
    "Ping-pong (L / R electrodes)": gen_alternate,
    "Pulse (whole tree)": gen_pulse,
    "Sparkle (random)": gen_sparkle,
    "Star flash": gen_star,
}


def from_builtin(mode, params, seconds=4.0, step_ms=200, name=None):
    """Sample a built-in animation into keys (to start editing from it)."""
    from . import builtin
    keys = []
    for t in range(0, int(seconds * 1000), step_ms):
        e1, e2 = builtin.mode_frame(mode, 1000 + t, params)
        keys.append(Key([round(v * LEVELS / 4096) for v in e1], [round(v * LEVELS / 4096) for v in e2], step_ms, LINEAR))
    from .device import BUILTIN_NAMES
    return CustomAnimation(name or ("My " + BUILTIN_NAMES[mode].lower()), keys)
