"""Орбита — аркада на одну кнопку. Запуск: python orbit.py

Точка сама летит по орбите вокруг ядра. Пробел или клик — прыжок
между внутренней и внешней орбитой. Собирай искры, не задевай красные дуги.
Дуга сначала появляется тусклой — это предупреждение.
"""
import math
import random
import sys
import time
import tkinter as tk
from pathlib import Path

# ── палитра ─────────────────────────────────────────────
BG = "#15122B"
RING = "#2A2550"
CORE = "#3B3470"
PLAYER = "#FFF1DC"
SPARK = "#7FE3D4"
HAZARD = "#FF5D84"
WARN = "#6A3560"
TEXT = "#EDE9FF"
MUTED = "#8C86B3"

WARN_TIME = 0.9     # сколько дуга предупреждает, прежде чем стать опасной
FADE_TIME = 0.3
TAU = 2 * math.pi
BEST_FILE = Path.home() / ".orbit_best"


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def blend(a, b, t):
    t = max(0.0, min(1.0, t))
    ra, rb = rgb(a), rgb(b)
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(ra, rb))


def angdiff(a, b):
    d = (a - b) % TAU
    return min(d, TAU - d)


def pick_family(root):
    from tkinter import font as tkfont
    have = set(tkfont.families(root))
    for f in ("Segoe UI Variable Display", "Segoe UI", "SF Pro Display",
              "Helvetica Neue", "Inter", "Ubuntu", "DejaVu Sans"):
        if f in have:
            return f
    return "Helvetica"


class Game(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Орбита")
        self.configure(bg=BG)
        self.resizable(False, False)

        s = self.s = self.winfo_fpixels("1i") / 96
        self.W, self.H = int(520 * s), int(660 * s)
        self.cx, self.cy = self.W / 2, self.H / 2 + 10 * s
        self.R = [110 * s, 185 * s]
        self.pr = 9 * s          # радиус игрока
        self.orb_r = 6 * s
        self.fam = pick_family(self)

        self.cv = tk.Canvas(self, width=self.W, height=self.H, bg=BG,
                            highlightthickness=0, bd=0)
        self.cv.pack()
        self.bind("<space>", lambda e: self.action())
        self.bind("<Up>", lambda e: self.action())
        self.bind("<Down>", lambda e: self.action())
        self.cv.bind("<Button-1>", lambda e: self.action())

        self.best = self._load_best()
        self.new_best = False
        self.state = "menu"
        self.particles = []
        self.shake = 0.0
        self.clock = 0.0
        self.reset()

        x = (self.winfo_screenwidth() - self.W) // 2
        y = (self.winfo_screenheight() - self.H) // 3
        self.geometry(f"+{x}+{y}")
        self._dark_titlebar()

        self.last = time.perf_counter()
        self.loop()

    # ── состояние ───────────────────────────────────────
    def reset(self):
        self.a = -math.pi / 2
        self.ring = 1
        self.r_vis = self.R[1]
        self.t = 0.0
        self.score = 0
        self.obs = []
        self.orbs = []
        self.trail = []
        self.spawn_timer = 1.2
        self.core_pulse = 0.0
        self.new_best = False

    def omega(self):
        return min(1.5 + 0.035 * self.t, 3.2)

    def spawn_interval(self):
        return max(0.42, 1.25 - 0.018 * self.t)

    def pos(self, a, r):
        return self.cx + r * math.cos(a), self.cy - r * math.sin(a)

    # ── ввод ────────────────────────────────────────────
    def action(self):
        if self.state == "menu":
            self.reset()
            self.state = "play"
        elif self.state == "play":
            self.ring = 1 - self.ring
            x, y = self.pos(self.a, self.r_vis)
            self.burst(x, y, PLAYER, 5, 90)
        elif self.state == "over" and time.perf_counter() - self.over_at > 0.6:
            self.reset()
            self.state = "play"

    # ── спавн ───────────────────────────────────────────
    def try_spawn(self):
        w = self.omega()
        for _ in range(15):
            k = random.randint(0, 1)
            span = random.uniform(0.35, 0.8) * (1.35 if k == 0 else 1.0)
            ang = random.uniform(0, TAU)
            ahead = (ang - self.a) % TAU
            # не спавнить прямо перед носом и прямо на игроке
            if ahead < w * WARN_TIME * 1.1 + span / 2 or ahead > TAU - span / 2 - 0.3:
                continue
            ok = True
            for o in self.obs:
                gap = angdiff(ang, o["ang"]) - (span + o["span"]) / 2
                if o["ring"] != k and gap < 0.35 + w * 0.2:   # всегда оставлять проход
                    ok = False
                if o["ring"] == k and gap < 0.1:
                    ok = False
            for orb in self.orbs:
                if orb["ring"] == k and angdiff(ang, orb["ang"]) < span / 2 + 0.15:
                    ok = False
            if ok:
                self.obs.append({"ring": k, "ang": ang, "span": span, "age": 0.0,
                                 "life": random.uniform(3.2, 4.6)})
                return

    def spawn_orb(self):
        for _ in range(20):
            k = random.randint(0, 1)
            ang = (self.a + random.uniform(1.2, 5.0)) % TAU
            if all(o["ring"] != k or angdiff(ang, o["ang"]) > o["span"] / 2 + 0.25
                   for o in self.obs):
                self.orbs.append({"ring": k, "ang": ang, "born": self.clock})
                return

    def burst(self, x, y, color, n, speed):
        for _ in range(n):
            a = random.uniform(0, TAU)
            v = random.uniform(0.3, 1.0) * speed * self.s
            self.particles.append({"x": x, "y": y, "vx": math.cos(a) * v,
                                   "vy": math.sin(a) * v, "life": 1.0,
                                   "color": color, "size": random.uniform(1.5, 3.5) * self.s})

    # ── логика ──────────────────────────────────────────
    def loop(self):
        now = time.perf_counter()
        dt = min(now - self.last, 0.05)
        self.last = now
        self.update_game(dt)
        self.draw()
        self.after(16, self.loop)

    def update_game(self, dt):
        self.clock += dt
        self.shake = max(0.0, self.shake - dt * 2.5)
        self.core_pulse = max(0.0, self.core_pulse - dt * 2.5)

        drag = 0.9 ** (dt * 60)
        for p in self.particles:
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["vx"] *= drag
            p["vy"] *= drag
            p["life"] -= dt * 1.4
        self.particles = [p for p in self.particles if p["life"] > 0]

        if self.state == "over":
            return

        speed = self.omega() if self.state == "play" else 1.0
        self.a = (self.a + speed * dt) % TAU
        self.r_vis += (self.R[self.ring] - self.r_vis) * min(1.0, dt * 14)
        self.trail.append((self.a, self.r_vis))
        self.trail = self.trail[-16:]

        if self.state != "play":
            return

        self.t += dt
        for o in self.obs:
            o["age"] += dt
        self.obs = [o for o in self.obs if o["age"] < o["life"]]

        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            self.try_spawn()
            self.spawn_timer = self.spawn_interval()
        if len(self.orbs) < 2:
            self.spawn_orb()

        on = next((k for k in (0, 1) if abs(self.r_vis - self.R[k]) < 12 * self.s), None)
        if on is None:
            return
        r = self.R[on]
        x, y = self.pos(self.a, self.r_vis)

        for o in self.obs:
            live = WARN_TIME <= o["age"] < o["life"] - FADE_TIME * 0.5
            if o["ring"] == on and live and \
                    angdiff(self.a, o["ang"]) < o["span"] / 2 + self.pr / r * 0.8:
                return self.die(x, y)

        for orb in self.orbs[:]:
            if orb["ring"] == on and angdiff(self.a, orb["ang"]) < (self.pr + self.orb_r) / r:
                self.orbs.remove(orb)
                self.score += 1
                self.core_pulse = 1.0
                self.burst(x, y, SPARK, 14, 160)

    def die(self, x, y):
        self.state = "over"
        self.over_at = time.perf_counter()
        self.shake = 1.0
        self.burst(x, y, PLAYER, 35, 260)
        self.burst(x, y, HAZARD, 20, 200)
        if self.score > self.best:
            self.best, self.new_best = self.score, True
            try:
                BEST_FILE.write_text(str(self.best))
            except OSError:
                pass

    # ── отрисовка ───────────────────────────────────────
    def draw(self):
        c, s = self.cv, self.s
        c.delete("all")
        ox = random.uniform(-1, 1) * self.shake * 10 * s
        oy = random.uniform(-1, 1) * self.shake * 10 * s
        cx, cy = self.cx + ox, self.cy + oy

        for r in self.R:
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=RING, width=2 * s)

        # ядро
        pulse = 0.5 + 0.5 * math.sin(self.clock * 2.2)
        cr = (24 + 3 * pulse + 10 * self.core_pulse) * s
        for i in range(4, 0, -1):
            rr = cr + i * 7 * s
            c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline="",
                          fill=blend(BG, CORE, 0.25 * (5 - i) / 4 + 0.3 * self.core_pulse))
        c.create_oval(cx - cr, cy - cr, cx + cr, cy + cr, outline="",
                      fill=blend(CORE, SPARK, self.core_pulse * 0.7))

        # дуги
        for o in self.obs:
            r = self.R[o["ring"]]
            if o["age"] < WARN_TIME:
                p = o["age"] / WARN_TIME
                blink = 0.75 + 0.25 * math.sin(o["age"] * 30)
                color, width = blend(BG, WARN, (0.4 + 0.6 * p) * blink), 5 * s
            else:
                fade = min(1.0, (o["life"] - o["age"]) / FADE_TIME)
                color, width = blend(BG, HAZARD, fade), 13 * s
            c.create_arc(cx - r, cy - r, cx + r, cy + r, style="arc",
                         start=math.degrees(o["ang"] - o["span"] / 2),
                         extent=math.degrees(o["span"]), outline=color, width=width)

        # искры
        for orb in self.orbs:
            x, y = self.pos(orb["ang"], self.R[orb["ring"]])
            x, y = x + ox, y + oy
            grow = min(1.0, (self.clock - orb["born"]) * 4)
            g = (self.orb_r + 5 * s * (0.5 + 0.5 * math.sin(self.clock * 5))) * grow
            c.create_oval(x - g, y - g, x + g, y + g, outline=blend(BG, SPARK, 0.4), width=2 * s)
            rr = self.orb_r * grow
            c.create_oval(x - rr, y - rr, x + rr, y + rr, fill=SPARK, outline="")

        # игрок
        if self.state != "over":
            n = len(self.trail)
            for i, (ta, tr) in enumerate(self.trail):
                k = (i + 1) / n
                x, y = self.pos(ta, tr)
                rr = self.pr * k * 0.75
                c.create_oval(x - rr + ox, y - rr + oy, x + rr + ox, y + rr + oy,
                              fill=blend(BG, PLAYER, k * 0.45), outline="")
            x, y = self.pos(self.a, self.r_vis)
            x, y = x + ox, y + oy
            for i in range(3, 0, -1):
                rr = self.pr + i * 4 * s
                c.create_oval(x - rr, y - rr, x + rr, y + rr, outline="",
                              fill=blend(BG, PLAYER, 0.12 * (4 - i)))
            c.create_oval(x - self.pr, y - self.pr, x + self.pr, y + self.pr,
                          fill=PLAYER, outline="")

        for p in self.particles:
            rr = p["size"] * p["life"]
            c.create_oval(p["x"] - rr + ox, p["y"] - rr + oy, p["x"] + rr + ox, p["y"] + rr + oy,
                          fill=blend(BG, p["color"], p["life"]), outline="")

        self.draw_text()

    def draw_text(self):
        c, s, f = self.cv, self.s, self.fam
        top, bottom = 72 * s, self.H - 52 * s
        mid = self.W / 2
        if self.state == "menu":
            c.create_text(mid, top, text="Орбита", fill=TEXT, font=(f, 38, "bold"))
            c.create_text(mid, top + 44 * s, text="Собирай искры, не задевай красные дуги",
                          fill=MUTED, font=(f, 12))
            c.create_text(mid, bottom, text="Пробел или клик — сменить орбиту и начать",
                          fill=TEXT, font=(f, 13))
            if self.best:
                c.create_text(mid, bottom + 26 * s, text=f"Рекорд {self.best}",
                              fill=MUTED, font=(f, 11))
        elif self.state == "play":
            c.create_text(mid, top, text=str(self.score), fill=TEXT, font=(f, 40, "bold"))
            c.create_text(mid, top + 40 * s, text=f"Рекорд {self.best}",
                          fill=MUTED, font=(f, 11))
        else:
            c.create_text(mid, top, text=str(self.score), fill=TEXT, font=(f, 40, "bold"))
            label = "Новый рекорд" if self.new_best else f"Рекорд {self.best}"
            c.create_text(mid, top + 40 * s, text=label,
                          fill=SPARK if self.new_best else MUTED, font=(f, 12))
            c.create_text(mid, bottom, text="Пробел — ещё раз", fill=TEXT, font=(f, 13))

    # ── прочее ──────────────────────────────────────────
    def _load_best(self):
        try:
            return int(BEST_FILE.read_text())
        except (OSError, ValueError):
            return 0

    def _dark_titlebar(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            self.update()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            v = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(v), ctypes.sizeof(v))
        except Exception:
            pass


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    Game().mainloop()
