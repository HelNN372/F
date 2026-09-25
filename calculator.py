"""Калькулятор на tkinter. Без зависимостей: python calculator.py"""
import ast
import math
import operator
import re
import sys
import tkinter as tk
from tkinter import font as tkfont

# ── палитра ─────────────────────────────────────────────
BG = "#1B1F2B"
KEY = "#262B3B"
KEY_HOVER = "#30364A"
FUNC = "#343B52"
FUNC_HOVER = "#3F4763"
ACCENT = "#F2B84B"
ACCENT_HOVER = "#F7C96E"
TEXT = "#E9EBF3"
MUTED = "#7F87A0"
ERROR = "#F07A7A"

LAYOUT = [
    ["(", ")", "√", "x²"],
    ["AC", "⌫", "%", "÷"],
    ["7", "8", "9", "×"],
    ["4", "5", "6", "−"],
    ["1", "2", "3", "+"],
    ["±", "0", ".", "="],
]
DIGITS = set("0123456789")
OPS = "+−×÷^"
KEYMAP = {"*": "×", "/": "÷", "-": "−", "+": "+", ",": ".", ".": ".",
          "%": "%", "(": "(", ")": ")", "^": "^"}


# ── безопасное вычисление (без eval) ────────────────────
BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.Pow: operator.pow}
UN = {ast.UAdd: operator.pos, ast.USub: operator.neg}
FUNCS = {"sqrt": math.sqrt}


def safe_eval(src):
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in BIN:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 1000:
                raise OverflowError
            return BIN[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in UN:
            return UN[type(n.op)](ev(n.operand))
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id in FUNCS and len(n.args) == 1 and not n.keywords):
            return FUNCS[n.func.id](ev(n.args[0]))
        raise SyntaxError
    return ev(ast.parse(src, mode="eval"))


def to_python(expr):
    s = (expr.replace("÷", "/").replace("×", "*").replace("−", "-")
             .replace("^", "**").replace("√", "sqrt").replace("%", "/100"))
    return s + ")" * (s.count("(") - s.count(")"))


def fmt_raw(x):
    if isinstance(x, complex):
        raise ValueError
    x = float(x)
    if math.isinf(x) or math.isnan(x):
        raise OverflowError
    if x == 0:
        return "0"
    if abs(x) >= 1e15 or abs(x) < 1e-9:
        m, e = f"{x:.8e}".split("e")
        s = f"{m.rstrip('0').rstrip('.')}e{int(e)}"
    elif x.is_integer():
        s = str(int(x))
    else:
        s = f"{x:.10f}".rstrip("0").rstrip(".")
    return s.replace("-", "−")


def _group(m):
    whole, dot, frac = m.group(0).partition(".")
    if whole:
        whole = f"{int(whole):,}".replace(",", " ")
    return whole + dot + frac


def pretty(expr):
    return re.sub(r"\d+(?:\.\d*)?|\.\d+", _group, expr)


def pick_family(root):
    have = set(tkfont.families(root))
    for f in ("Segoe UI Variable Display", "Segoe UI", "SF Pro Display",
              "Helvetica Neue", "Inter", "Ubuntu", "DejaVu Sans"):
        if f in have:
            return f
    return "Helvetica"


# ── скруглённая кнопка на Canvas ────────────────────────
class RoundButton(tk.Canvas):
    def __init__(self, master, text, command, bg, hover, fg, font, w, h, r):
        super().__init__(master, width=w, height=h, bg=BG,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.bg, self.hover, self.command = bg, hover, command
        self.inside = False
        self.shape = self._round_rect(1, 1, w - 1, h - 1, r, fill=bg, outline="")
        self.label = self.create_text(w / 2, h / 2, text=text, fill=fg, font=font)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1,
               x2, y1 + r, x2, y1 + r, x2, y2 - r, x2, y2 - r, x2, y2,
               x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2, x1, y2,
               x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]
        return self.create_polygon(pts, smooth=True, **kw)

    def _fill(self, c):
        self.itemconfig(self.shape, fill=c)

    def _enter(self, _):
        self.inside = True
        self._fill(self.hover)

    def _leave(self, _):
        self.inside = False
        self._fill(self.bg)

    def _press(self, _):
        self._fill(self.bg)
        self.move(self.label, 0, 1)

    def _release(self, e):
        self.move(self.label, 0, -1)
        self._fill(self.hover if self.inside else self.bg)
        if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.command()

    def flash(self):
        self._fill(self.hover)
        self.after(90, lambda: self._fill(self.hover if self.inside else self.bg))


# ── приложение ──────────────────────────────────────────
class Calculator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Калькулятор")
        self.configure(bg=BG)
        self.resizable(False, False)

        s = self.winfo_fpixels("1i") / 96  # масштаб под DPI
        self.bw, self.bh = int(76 * s), int(62 * s)
        self.gap, self.pad, self.radius = int(10 * s), int(22 * s), int(20 * s)

        fam = pick_family(self)
        self.big_size = 44
        self.f_big = tkfont.Font(family=fam, size=self.big_size)
        self.f_small = tkfont.Font(family=fam, size=12)
        self.f_prev = tkfont.Font(family=fam, size=18)
        self.f_key = tkfont.Font(family=fam, size=19)
        self.f_fn = tkfont.Font(family=fam, size=15)

        self.expr = ""
        self.done = False  # только что нажали «=»
        self.buttons = {}

        self._build()
        self.bind("<Key>", self._on_key)
        self._render()

        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 3
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.maxw = w - 2 * self.pad
        self._render()
        self._dark_titlebar()

    # интерфейс
    def _build(self):
        disp = tk.Frame(self, bg=BG)
        disp.pack(fill="x", padx=self.pad, pady=(self.pad + 8, 14))

        self.l_hist = tk.Label(disp, bg=BG, fg=MUTED, font=self.f_small, anchor="e")
        self.l_hist.pack(fill="x")

        box = tk.Frame(disp, bg=BG, height=self.f_big.metrics("linespace") + 6)
        box.pack(fill="x")
        box.pack_propagate(False)
        self.l_expr = tk.Label(box, bg=BG, fg=TEXT, font=self.f_big, anchor="e")
        self.l_expr.pack(fill="both", expand=True)

        self.l_prev = tk.Label(disp, bg=BG, fg=MUTED, font=self.f_prev, anchor="e")
        self.l_prev.pack(fill="x")

        pad = tk.Frame(self, bg=BG)
        pad.pack(padx=self.pad, pady=(0, self.pad))
        for r, row in enumerate(LAYOUT):
            for c, t in enumerate(row):
                bg, hov, fg, f = self._style(t)
                b = RoundButton(pad, t, lambda t=t: self.press(t), bg, hov, fg, f,
                                self.bw, self.bh, self.radius)
                b.grid(row=r, column=c,
                       padx=(0 if c == 0 else self.gap, 0),
                       pady=(0 if r == 0 else self.gap, 0))
                self.buttons[t] = b

    def _style(self, t):
        if t == "=":
            return ACCENT, ACCENT_HOVER, BG, self.f_key
        if t in ("÷", "×", "−", "+"):
            return FUNC, FUNC_HOVER, ACCENT, self.f_key
        if t in DIGITS or t in (".", "±"):
            return KEY, KEY_HOVER, TEXT, self.f_key
        return FUNC, FUNC_HOVER, TEXT, self.f_fn

    def _dark_titlebar(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            v = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(v), ctypes.sizeof(v))
        except Exception:
            pass

    # ввод
    def _on_key(self, e):
        ks, ch = e.keysym, e.char
        if ks in ("Return", "KP_Enter") or ch == "=":
            t = "="
        elif ks == "BackSpace":
            t = "⌫"
        elif ks in ("Escape", "Delete"):
            t = "AC"
        elif ch in DIGITS:
            t = ch
        elif ch in KEYMAP:
            t = KEYMAP[ch]
        else:
            return
        if t in self.buttons:
            self.buttons[t].flash()
        self.press(t)

    def press(self, t):
        if t == "AC":
            self.expr, self.done = "", False
            self.l_hist.config(text="")
            return self._render()
        if t == "=":
            return self._equals()

        e = self.expr
        if self.done and (t in DIGITS or t in (".", "(", "√")):
            e = ""
        self.done = False
        last = e[-1:]
        num = re.search(r"[\d.]+$", e)

        if t in DIGITS:
            if num and num.group() == "0":
                e = e[:-1]
            elif last in (")", "%"):
                e += "×"
            e += t
        elif t == ".":
            if num and "." in num.group():
                return
            if not num:
                if last in (")", "%"):
                    e += "×"
                e += "0"
            e += "."
        elif t in OPS:
            if t == "−" and (not e or last in "(×÷^"):
                e += t
            else:
                base = e.rstrip(OPS)
                if not base or base[-1] == "(":
                    return
                e = base + t
        elif t in ("(", "√"):
            if last and (last.isdigit() or last in ").%"):
                e += "×"
            e += "(" if t == "(" else "√("
        elif t == ")":
            if e.count("(") <= e.count(")") or not last or last in OPS + "(":
                return
            e += ")"
        elif t in ("%", "x²"):
            if not last or not (last.isdigit() or last == ")"):
                return
            e += "%" if t == "%" else "^2"
        elif t == "±":
            if not num:
                return
            i = num.start()
            if e[:i].endswith("(−"):
                e = e[:i - 2] + e[i:]
            elif e[:i] == "−":
                e = e[i:]
            else:
                e = e[:i] + "(−" + e[i:]
        elif t == "⌫":
            e = e[:-2] if e.endswith("√(") else e[:-1]

        self.expr = e
        self._render()

    # вычисление и отрисовка
    def _calc(self, expr):
        return fmt_raw(safe_eval(to_python(expr)))

    def _equals(self):
        if not self.expr or self.done:
            return
        try:
            res = self._calc(self.expr)
        except ZeroDivisionError:
            return self._error("Деление на ноль")
        except OverflowError:
            return self._error("Слишком большое число")
        except ValueError:
            return self._error("Недопустимое значение")
        except Exception:
            return self._error("Выражение не закончено")
        closed = self.expr + ")" * (self.expr.count("(") - self.expr.count(")"))
        self.l_hist.config(text=pretty(closed) + " =")
        self.expr, self.done = res, True
        self._render()

    def _preview(self):
        if re.fullmatch(r"−?[\d.]*(?:e−?\d+)?", self.expr):
            return ""
        try:
            return "= " + pretty(self._calc(self.expr))
        except Exception:
            return ""

    def _render(self):
        self._fit(pretty(self.expr) or "0")
        self.l_prev.config(text=self._preview(), fg=MUTED)

    def _fit(self, text):
        maxw = getattr(self, "maxw", 10_000)
        size = self.big_size
        self.f_big.configure(size=size)
        while self.f_big.measure(text) > maxw and size > 22:
            size -= 2
            self.f_big.configure(size=size)
        shown, i = text, 0
        while self.f_big.measure(shown) > maxw and i < len(text) - 1:
            i += 1
            shown = "…" + text[i:]
        self.l_expr.config(text=shown)

    def _error(self, msg):
        self.l_prev.config(text=msg, fg=ERROR)
        self._shake((12, 0, 8, 0, 4, 0))

    def _shake(self, seq):
        if seq:
            self.l_expr.pack_configure(padx=(0, seq[0]))
            self.after(35, self._shake, seq[1:])


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    Calculator().mainloop()
