"""Renders what the tree shows right now, from its status: the same animation code as the firmware, on the
tree's own clock (status uptime), with crossfades, drift, custom animations, live frames and brightness."""
import time

from . import builtin
from .device import N_BASIC, SHOW_CUSTOM0, SHOW_LIVE, Config

Q = 4096


def now_ms():
    return time.monotonic() * 1000.0


class Mirror:
    def __init__(self):
        self.cfg = Config()
        self.customs = []
        self.status = None
        self.offset = None
        self.show = 0
        self.prev = 0
        self.t_change = -1e12
        self.cur_t0 = 0
        self.prev_t0 = 0
        self.live = None  # the frame the app streams: (left[10], right[10]) 0-255

    def reset(self):
        self.status = None
        self.offset = None

    def update_status(self, st):
        off = st.uptime_ms - now_ms()
        if self.offset is None or abs(off - self.offset) > 300:
            self.offset = off
        else:
            self.offset += (off - self.offset) * 0.05
        if self.status is None:
            self.show = self.prev = st.show
        elif st.show != self.show:
            t = self.tree_now()
            self.prev, self.show = self.show, st.show
            self.t_change = t
            self.prev_t0, self.cur_t0 = self.cur_t0, t
        self.status = st

    def tree_now(self):
        return now_ms() + (self.offset or 0)

    # -- frames in Q12, like anim.c

    def _entries(self, m, w, t0, t, out):
        if w <= 0:
            return
        n_custom = len(self.customs)
        if m == 7 or (m >= 8 and m != SHOW_LIVE and m - SHOW_CUSTOM0 >= n_custom) or (8 <= m < SHOW_LIVE):
            m = 0
        if m == 6:
            for sub, ws, ts in builtin.drift_entries(t, self.cfg, n_custom):
                self._entries(sub, w * ws >> 12, ts, t, out)
            return
        out.append((m, w, t0))

    def anim_frame(self, cur, prev, k, t):
        ents = []
        self._entries(prev, Q - k, self.prev_t0, t, ents)
        self._entries(cur, k, self.cur_t0, t, ents)
        e1, e2, rail = [0] * 10, [0] * 10, 0
        for m, w, t0 in ents:
            if m >= SHOW_CUSTOM0:
                a, b = self.customs[m - SHOW_CUSTOM0].frame(max(0, t - t0))
                r = Q
            elif m == SHOW_LIVE:
                lv = self.live or ([0] * 10, [0] * 10)
                a = [v * 16 + (v >> 4) for v in lv[0]]
                b = [v * 16 + (v >> 4) for v in lv[1]]
                r = Q
            else:
                a, b = builtin.mode_frame(m, t, self.cfg.params[:N_BASIC], self.status is not None and self.status.style == 1)
                r = builtin.rail(m, t, self.cfg.params)
            for i in range(10):
                e1[i] += a[i] * w >> 12
                e2[i] += b[i] * w >> 12
            rail += r * w >> 12
        return e1, e2, rail

    def frame(self):
        """Display brightness per electrode, 0..1."""
        st = self.status
        if st is None or not st.is_on or st.daylight_off or st.fault or not st.boost_on:
            return [0.0] * 10, [0.0] * 10
        if 8 <= st.show <= 10 or st.mode == 2:  # bring-up shows / manual: lamp states + level
            lv = (st.level / 255.0) ** 2
            bits = [st.lamp_bits(i) for i in range(10)]
            return ([lv if b & 1 else 0.0 for b in bits], [lv if b & 2 else 0.0 for b in bits])
        t = int(self.tree_now())
        fade = self.cfg.fade_ds * 100 or 1
        k = builtin.smooth(int(min(fade, max(0, t - self.t_change)) * Q // fade))
        e1, e2, _rail = self.anim_frame(self.show, self.prev, k, t)
        return self.display(e1, e2, st)

    @staticmethod
    def display(e1, e2, st=None, level=None):
        """Q12 duty requests -> perceived brightness, like publish_lamp(): share(), then the brightness
        factor (status.level = anim_L / 16) on top of the strike minimum (400 us of 7 ms)."""
        lvl = (st.level if st else 255) / 255.0 if level is None else level
        mn = 400 / 7000
        left, right = [], []
        for i in range(10):
            a, b = builtin.share(e1[i], e2[i])
            left.append(0.0 if a <= 0 else mn + (1 - mn) * a / Q * lvl)
            right.append(0.0 if b <= 0 else mn + (1 - mn) * b / Q * lvl)
        return left, right
