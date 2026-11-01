"""
Matrix Studio: design messages and frame-by-frame animations for the desk matrix,
preview them, and send them to the display over USB.

Run:     python matrix_studio.py
Needs:   Python 3.8+ (tkinter is built in). For sending to the display: pip install mpremote
"""

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

WIDTH, HEIGHT = 32, 8
MODULES = 4
FULL = (1 << WIDTH) - 1
HERE = Path(__file__).resolve().parent
FIRMWARE_DIR = HERE / "firmware"

# ---------- look ----------
PCB_BLUE = "#1f4e79"       # the module's circuit board
MODULE_BLACK = "#121212"   # the 8x8 LED blocks
LED_OFF = "#3b1a17"
LED_ONION = "#7d3329"
LED_ON_DIM = (150, 40, 30)
LED_ON_BRIGHT = (255, 72, 48)
CHROME = "#e8ebee"
INK = "#1c2430"
MUTED = "#5d6875"

# MicroPython's built-in 8x8 font (font_petme128_8x8), characters 32-127.
# Each character is 8 column bytes, lowest bit at the top. Same font the display uses.
FONT_HEX = (
    "00000000000000000000004f4f0000000007070000070700147f7f14147f7f1400242e6b6b3a1200006333180c666300"
    "00327f4d4d777250000000040603010000001c3e63410000000041633e1c0000082a3e1c1c3e2a080008083e3e080800"
    "000080e0600000000008080808080800000000606000000000406030180c0602003e7f49457f3e000040447f7f404000"
    "00627351494f460000226349497f360000181814167f7f1000276745457d3900003e7f49497b3200000303797d070300"
    "00367f49497f360000266f49497f3e000000002424000000000080e46400000000081c36634141000014141414141400"
    "00414163361c080000020351590f0600003e7f414d4f2e00007c7e0b0b7e7c00007f7f49497f3600003e7f4141632200"
    "007f7f41633e1c00007f7f4949414100007f7f0909010100003e7f41497b3a00007f7f08087f7f000000417f7f410000"
    "002060417f3f0100007f7f1c36634100007f7f4040404000007f7f060c067f7f007f7f0e1c7f7f00003e7f41417f3e00"
    "007f7f09090f0600001e3f21617f5e00007f7f19396f460000266f49497b32000001017f7f010100003f7f40407f3f00"
    "001f3f60603f1f00007f7f3018307f7f0063771c1c77630000070f78780f0700006171594d47430000007f7f41410000"
    "0002060c18306040000041417f7f000000080c06060c0800c0c0c0c0c0c0c0c0000001030604000000207454547c7800"
    "007f7f44447c380000387c44446c280000387c44447f7f0000387c54545c580000087e7f090302000098bca4a4fc7c00"
    "007f7f04047c78000000007d7d0000000040c08080fd7d00007f7f30386c44000000417f7f400000007c7c1830187c7c"
    "007c7c04047c780000387c44447c380000fcfc24243c180000183c2424fcfc00007c7c04040c080000485c5454742000"
    "04043f7f44642000003c7c40407c3c00001c3c60603c1c00001c7c3018307c1c00446c38386c4400009cbca0a0fc7c00"
    "004464745c4c44000008083e77414100000000ffff000000004141773e0808000002030103020301aa55aa55aa55aa55"
)
FONT = bytes.fromhex(FONT_HEX)


def text_columns(text):
    cols = []
    for ch in text:
        code = ord(ch)
        if code < 32 or code > 127:
            code = 127
        start = (code - 32) * 8
        cols.extend(FONT[start:start + 8])
    return cols


def render_text(text, x):
    """Draw text with its left edge at pixel x. Returns 8 row numbers."""
    rows = [0] * HEIGHT
    for i, col in enumerate(text_columns(text)):
        px = x + i
        if 0 <= px < WIDTH:
            for y in range(HEIGHT):
                if (col >> y) & 1:
                    rows[y] |= 1 << (WIDTH - 1 - px)
    return rows


def get_px(rows, x, y):
    return (rows[y] >> (WIDTH - 1 - x)) & 1


def set_px(rows, x, y, on):
    bit = 1 << (WIDTH - 1 - x)
    rows[y] = rows[y] | bit if on else rows[y] & ~bit


def item_frames(item, cfg):
    """Yields (rows, milliseconds) exactly the way the firmware plays an item."""
    if item["type"] == "text":
        text = item.get("text", "")
        width = len(text) * 8
        if item.get("static"):
            yield render_text(text, (WIDTH - width) // 2), int(item.get("duration", 3) * 1000)
            return
        x = WIDTH
        while x > -width:
            yield render_text(text, x), cfg["scroll_speed"]
            x -= 1
    else:
        frames = item.get("frames") or []
        delay = max(1, 1000 // max(1, item.get("fps", 4)))
        for _ in range(max(1, item.get("loops", 1))):
            for rows in frames:
                yield rows, delay


def face(eyes_row):
    rows = [0x3C, 0x42, eyes_row, 0x81, 0xA5, 0x99, 0x42, 0x3C]
    return [r << 12 for r in rows]


DEFAULT_CONFIG = {
    "brightness": 2,
    "scroll_speed": 40,
    "mirror": False,
    "flip": False,
    "reverse_modules": False,
    "items": [
        {"type": "text", "text": "HELLO!", "static": False, "duration": 3},
        {"type": "animation", "name": "Blink", "fps": 3, "loops": 3,
         "frames": [face(0xA5), face(0xA5), face(0xE7)]},
        {"type": "text", "text": "HI :)", "static": True, "duration": 3},
    ],
}


# ---------- the LED panel: preview and drawing surface ----------
class LedPanel(tk.Canvas):
    CELL = 22
    GAP = 5       # space between the four 8x8 blocks
    MARGIN = 18

    def __init__(self, master, on_paint):
        w = self.MARGIN * 2 + WIDTH * self.CELL + (MODULES - 1) * self.GAP
        h = self.MARGIN * 2 + HEIGHT * self.CELL
        super().__init__(master, width=w, height=h, bg=PCB_BLUE, highlightthickness=0)
        self.on_paint = on_paint
        self.editable = False
        self.paint_value = 1
        self.on_color = "#ff4830"
        self.leds = [[None] * WIDTH for _ in range(HEIGHT)]
        for m in range(MODULES):
            x0 = self.MARGIN + m * (8 * self.CELL + self.GAP) - 4
            self.create_rectangle(x0, self.MARGIN - 4, x0 + 8 * self.CELL + 8,
                                  self.MARGIN + HEIGHT * self.CELL + 4,
                                  fill=MODULE_BLACK, outline="")
        pad = 3
        for y in range(HEIGHT):
            for x in range(WIDTH):
                cx, cy = self.cell_origin(x, y)
                self.leds[y][x] = self.create_oval(cx + pad, cy + pad, cx + self.CELL - pad,
                                                   cy + self.CELL - pad, fill=LED_OFF, outline="")
        self.bind("<Button-1>", lambda e: self._press(e, None))
        self.bind("<B1-Motion>", self._drag)
        self.bind("<Button-3>", lambda e: self._press(e, 0))
        self.bind("<B3-Motion>", self._drag)
        self.bind("<Button-2>", lambda e: self._press(e, 0))   # right click on some Macs
        self.bind("<B2-Motion>", self._drag)

    def cell_origin(self, x, y):
        return (self.MARGIN + x * self.CELL + (x // 8) * self.GAP, self.MARGIN + y * self.CELL)

    def cell_at(self, px, py):
        for x in range(WIDTH):
            cx, _ = self.cell_origin(x, 0)
            if cx <= px < cx + self.CELL:
                y = int((py - self.MARGIN) // self.CELL)
                if 0 <= y < HEIGHT:
                    return x, y
        return None

    def set_brightness(self, level):
        t = level / 15
        rgb = [int(a + (b - a) * t) for a, b in zip(LED_ON_DIM, LED_ON_BRIGHT)]
        self.on_color = "#%02x%02x%02x" % tuple(rgb)

    def show(self, rows, onion=None):
        for y in range(HEIGHT):
            for x in range(WIDTH):
                if get_px(rows, x, y):
                    color = self.on_color
                elif onion and get_px(onion, x, y):
                    color = LED_ONION
                else:
                    color = LED_OFF
                self.itemconfigure(self.leds[y][x], fill=color)

    def _press(self, event, value):
        if not self.editable:
            return
        cell = self.cell_at(event.x, event.y)
        if cell:
            self.paint_value = value if value is not None else None
            self.on_paint(cell[0], cell[1], self.paint_value, start=True)

    def _drag(self, event):
        if not self.editable:
            return
        cell = self.cell_at(event.x, event.y)
        if cell:
            self.on_paint(cell[0], cell[1], self.paint_value, start=False)


# ---------- the app ----------
class Studio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Matrix Studio")
        self.configure(bg=CHROME)
        self.minsize(900, 640)
        self.cfg = copy.deepcopy(DEFAULT_CONFIG)
        self.path = None
        self.sel = 0
        self.frame_idx = 0
        self.player = None
        self.player_job = None
        self.loading = False
        self.stroke_value = 1

        self._style()
        self._build()
        self.load_into_ui()

    # ----- layout -----
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        base = ("TkDefaultFont", 10)
        s.configure(".", background=CHROME, foreground=INK, font=base)
        s.configure("TFrame", background=CHROME)
        s.configure("TLabel", background=CHROME, foreground=INK)
        s.configure("Muted.TLabel", foreground=MUTED)
        s.configure("Head.TLabel", font=("TkDefaultFont", 12, "bold"))
        s.configure("TCheckbutton", background=CHROME)
        s.configure("TButton", padding=(10, 5))
        s.configure("Primary.TButton", background=PCB_BLUE, foreground="white")
        s.map("Primary.TButton", background=[("active", "#2a6299"), ("disabled", "#8aa1b8")])
        s.configure("TLabelframe", background=CHROME)
        s.configure("TLabelframe.Label", background=CHROME, foreground=INK,
                    font=("TkDefaultFont", 10, "bold"))

    def _build(self):
        top = ttk.Frame(self, padding=(16, 16, 16, 8))
        top.pack(fill="x")
        self.panel = LedPanel(top, self.on_paint)
        self.panel.pack(side="left")
        side = ttk.Frame(top, padding=(16, 0, 0, 0))
        side.pack(side="left", fill="y")
        self.play_btn = ttk.Button(side, text="Play this", command=self.play_selected)
        self.play_btn.pack(fill="x")
        self.play_all_btn = ttk.Button(side, text="Play all", command=self.play_all)
        self.play_all_btn.pack(fill="x", pady=(6, 0))
        self.hint = ttk.Label(side, style="Muted.TLabel", wraplength=170, justify="left")
        self.hint.pack(fill="x", pady=(14, 0))

        mid = ttk.Frame(self, padding=(16, 4))
        mid.pack(fill="both", expand=True)

        # playlist
        left = ttk.Frame(mid)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Playlist", style="Head.TLabel").pack(anchor="w")
        ttk.Label(left, text="Plays top to bottom, then repeats.\nThe button skips ahead.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 6))
        self.listbox = tk.Listbox(left, width=30, height=12, activestyle="none",
                                  selectbackground=PCB_BLUE, selectforeground="white",
                                  relief="flat", highlightthickness=1,
                                  highlightbackground="#c5ccd3", exportselection=False)
        self.listbox.pack(fill="y", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        row = ttk.Frame(left)
        row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="Add message", command=self.add_text).pack(side="left", expand=True, fill="x")
        ttk.Button(row, text="Add animation", command=self.add_anim).pack(side="left", expand=True, fill="x", padx=(4, 0))
        row = ttk.Frame(left)
        row.pack(fill="x", pady=(4, 0))
        for label, cmd in (("Up", lambda: self.move_item(-1)), ("Down", lambda: self.move_item(1)),
                           ("Copy", self.dup_item), ("Delete", self.del_item)):
            ttk.Button(row, text=label, command=cmd, width=6).pack(side="left", expand=True, fill="x", padx=(0, 2))

        # editors
        self.editor_host = ttk.Frame(mid, padding=(20, 0, 0, 0))
        self.editor_host.pack(side="left", fill="both", expand=True)
        self._build_text_editor()
        self._build_anim_editor()

        # settings + actions
        bottom = ttk.Frame(self, padding=(16, 8, 16, 16))
        bottom.pack(fill="x")
        settings = ttk.LabelFrame(bottom, text="Display settings", padding=10)
        settings.pack(fill="x")
        self.bright_var = tk.IntVar()
        self.speed_var = tk.IntVar()
        ttk.Label(settings, text="Brightness").grid(row=0, column=0, sticky="w")
        ttk.Scale(settings, from_=0, to=15, variable=self.bright_var, length=160,
                  command=lambda v: self.on_setting()).grid(row=0, column=1, padx=6)
        self.bright_lbl = ttk.Label(settings, width=3)
        self.bright_lbl.grid(row=0, column=2, sticky="w")
        ttk.Label(settings, text="Scroll speed").grid(row=0, column=3, sticky="w", padx=(16, 0))
        ttk.Scale(settings, from_=120, to=10, variable=self.speed_var, length=160,
                  command=lambda v: self.on_setting()).grid(row=0, column=4, padx=6)
        self.speed_lbl = ttk.Label(settings, width=18, style="Muted.TLabel")
        self.speed_lbl.grid(row=0, column=5, sticky="w")
        ttk.Label(settings, text="If the picture looks wrong on the real display:",
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.mirror_var = tk.BooleanVar()
        self.flip_var = tk.BooleanVar()
        self.revmod_var = tk.BooleanVar()
        fixes = ttk.Frame(settings)
        fixes.grid(row=1, column=3, columnspan=3, sticky="w", pady=(8, 0), padx=(16, 0))
        for text, var in (("Mirrored", self.mirror_var), ("Upside down", self.flip_var),
                          ("Blocks in wrong order", self.revmod_var)):
            ttk.Checkbutton(fixes, text=text, variable=var, command=self.on_setting).pack(side="left", padx=(0, 12))

        actions = ttk.Frame(bottom, padding=(0, 10, 0, 0))
        actions.pack(fill="x")
        ttk.Button(actions, text="Open…", command=self.open_file).pack(side="left")
        ttk.Button(actions, text="Save", command=self.save_file).pack(side="left", padx=(4, 0))
        self.send_btn = ttk.Button(actions, text="Send to display", style="Primary.TButton",
                                   command=self.send_to_display)
        self.send_btn.pack(side="right")
        self.install_btn = ttk.Button(actions, text="Install firmware", command=self.install_firmware)
        self.install_btn.pack(side="right", padx=(0, 6))
        self.status = ttk.Label(actions, style="Muted.TLabel")
        self.status.pack(side="left", padx=(16, 0), fill="x", expand=True)

    def _build_text_editor(self):
        f = self.text_editor = ttk.Frame(self.editor_host)
        ttk.Label(f, text="Message", style="Head.TLabel").pack(anchor="w")
        self.text_var = tk.StringVar()
        entry = ttk.Entry(f, textvariable=self.text_var, font=("TkDefaultFont", 13), width=36)
        entry.pack(anchor="w", pady=(6, 4), fill="x")
        self.text_var.trace_add("write", lambda *a: self.on_text_change())
        self.text_note = ttk.Label(f, style="Muted.TLabel", wraplength=420, justify="left")
        self.text_note.pack(anchor="w")
        opts = ttk.Frame(f)
        opts.pack(anchor="w", pady=(12, 0))
        self.static_var = tk.BooleanVar()
        ttk.Checkbutton(opts, text="Hold still instead of scrolling", variable=self.static_var,
                        command=self.on_text_change).pack(side="left")
        ttk.Label(opts, text="for").pack(side="left", padx=(12, 4))
        self.duration_var = tk.StringVar()
        ttk.Spinbox(opts, from_=1, to=60, width=4, textvariable=self.duration_var,
                    command=self.on_text_change).pack(side="left")
        self.duration_var.trace_add("write", lambda *a: self.on_text_change())
        ttk.Label(opts, text="seconds").pack(side="left", padx=(4, 0))

    def _build_anim_editor(self):
        f = self.anim_editor = ttk.Frame(self.editor_host)
        head = ttk.Frame(f)
        head.pack(fill="x")
        ttk.Label(head, text="Animation", style="Head.TLabel").pack(side="left")
        self.name_var = tk.StringVar()
        ttk.Entry(head, textvariable=self.name_var, width=18).pack(side="left", padx=(10, 0))
        self.name_var.trace_add("write", lambda *a: self.on_anim_settings())
        self.fps_var = tk.StringVar()
        self.loops_var = tk.StringVar()
        ttk.Label(head, text="Frames per second").pack(side="left", padx=(16, 4))
        ttk.Spinbox(head, from_=1, to=30, width=4, textvariable=self.fps_var,
                    command=self.on_anim_settings).pack(side="left")
        ttk.Label(head, text="Repeat").pack(side="left", padx=(12, 4))
        ttk.Spinbox(head, from_=1, to=99, width=4, textvariable=self.loops_var,
                    command=self.on_anim_settings).pack(side="left")
        self.fps_var.trace_add("write", lambda *a: self.on_anim_settings())
        self.loops_var.trace_add("write", lambda *a: self.on_anim_settings())

        strip_box = ttk.Frame(f)
        strip_box.pack(fill="x", pady=(10, 0))
        self.strip = tk.Canvas(strip_box, height=58, bg="white", highlightthickness=1,
                               highlightbackground="#c5ccd3")
        self.strip.pack(fill="x")
        sb = ttk.Scrollbar(strip_box, orient="horizontal", command=self.strip.xview)
        sb.pack(fill="x")
        self.strip.configure(xscrollcommand=sb.set)
        self.strip.bind("<Button-1>", self.on_strip_click)

        row = ttk.Frame(f)
        row.pack(fill="x", pady=(8, 0))
        for label, cmd in (("New frame", self.add_frame), ("Copy frame", self.dup_frame),
                           ("Delete frame", self.del_frame), ("Move earlier", lambda: self.move_frame(-1)),
                           ("Move later", lambda: self.move_frame(1))):
            ttk.Button(row, text=label, command=cmd).pack(side="left", padx=(0, 4))
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(6, 0))
        for label, cmd in (("Clear", self.clear_frame), ("Invert", self.invert_frame),
                           ("Shift ←", lambda: self.shift(-1, 0)), ("Shift →", lambda: self.shift(1, 0)),
                           ("Shift ↑", lambda: self.shift(0, -1)), ("Shift ↓", lambda: self.shift(0, 1))):
            ttk.Button(row, text=label, command=cmd, width=8).pack(side="left", padx=(0, 4))
        self.onion_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Show previous frame faintly while drawing", variable=self.onion_var,
                        command=self.refresh_canvas).pack(anchor="w", pady=(8, 0))

    # ----- state helpers -----
    @property
    def item(self):
        items = self.cfg["items"]
        return items[self.sel] if 0 <= self.sel < len(items) else None

    def label_for(self, item):
        if item["type"] == "text":
            mode = "hold" if item.get("static") else "scroll"
            return f"Message ({mode}): {item.get('text', '') or '(empty)'}"
        n = len(item.get("frames", []))
        return f"Animation: {item.get('name') or 'Untitled'} ({n} frame{'s' if n != 1 else ''})"

    def refresh_list(self):
        self.listbox.delete(0, "end")
        for it in self.cfg["items"]:
            self.listbox.insert("end", self.label_for(it))
        if self.item:
            self.listbox.selection_set(self.sel)
            self.listbox.see(self.sel)

    def refresh_list_row(self):
        if self.item:
            self.listbox.delete(self.sel)
            self.listbox.insert(self.sel, self.label_for(self.item))
            self.listbox.selection_set(self.sel)

    def load_into_ui(self):
        self.loading = True
        self.bright_var.set(self.cfg["brightness"])
        self.speed_var.set(self.cfg["scroll_speed"])
        self.mirror_var.set(self.cfg["mirror"])
        self.flip_var.set(self.cfg["flip"])
        self.revmod_var.set(self.cfg["reverse_modules"])
        self.loading = False
        self.on_setting()
        self.sel = 0 if self.cfg["items"] else -1
        self.refresh_list()
        self.show_editor()
        self.title(f"Matrix Studio: {self.path.name}" if self.path else "Matrix Studio")

    def show_editor(self):
        self.stop()
        self.text_editor.pack_forget()
        self.anim_editor.pack_forget()
        it = self.item
        self.loading = True
        if it is None:
            self.panel.editable = False
            self.panel.show([0] * HEIGHT)
            self.hint.configure(text="Add a message or an animation to get started.")
        elif it["type"] == "text":
            self.text_var.set(it.get("text", ""))
            self.static_var.set(bool(it.get("static")))
            self.duration_var.set(str(it.get("duration", 3)))
            self.text_editor.pack(fill="both", expand=True)
            self.panel.editable = False
            self.hint.configure(text="Type your message below. Press Play this to watch it scroll.")
        else:
            if not it.get("frames"):
                it["frames"] = [[0] * HEIGHT]
            self.name_var.set(it.get("name", ""))
            self.fps_var.set(str(it.get("fps", 4)))
            self.loops_var.set(str(it.get("loops", 1)))
            self.frame_idx = min(self.frame_idx, len(it["frames"]) - 1)
            self.anim_editor.pack(fill="both", expand=True)
            self.panel.editable = True
            self.hint.configure(text="Click or drag on the display to draw.\nRight-click to erase.")
        self.loading = False
        self.refresh_canvas()
        self.refresh_strip()
        self.update_text_note()

    def refresh_canvas(self):
        it = self.item
        if it is None:
            return
        if it["type"] == "text":
            text = it.get("text", "")
            x = (WIDTH - len(text) * 8) // 2 if it.get("static") else 0
            self.panel.show(render_text(text, x))
        else:
            frames = it["frames"]
            onion = frames[self.frame_idx - 1] if self.onion_var.get() and self.frame_idx > 0 else None
            self.panel.show(frames[self.frame_idx], onion)

    def refresh_strip(self):
        self.strip.delete("all")
        it = self.item
        if not it or it["type"] != "animation":
            return
        scale, pad = 3, 8
        tw = WIDTH * scale
        for i, rows in enumerate(it["frames"]):
            x0 = pad + i * (tw + pad + 6)
            selected = i == self.frame_idx
            self.strip.create_rectangle(x0 - 3, 4, x0 + tw + 3, 8 + HEIGHT * scale + 3,
                                        fill=MODULE_BLACK,
                                        outline=PCB_BLUE if selected else "#c5ccd3",
                                        width=3 if selected else 1)
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    if get_px(rows, x, y):
                        px, py = x0 + x * scale, 7 + y * scale
                        self.strip.create_rectangle(px, py, px + scale - 1, py + scale - 1,
                                                    fill="#ff4830", outline="")
            self.strip.create_text(x0 + tw / 2, 44, text=str(i + 1), fill=MUTED)
        total = pad + len(it["frames"]) * (tw + pad + 6)
        self.strip.configure(scrollregion=(0, 0, total, 58))

    def set_status(self, text):
        self.status.configure(text=text)

    # ----- settings -----
    def on_setting(self):
        if self.loading:
            return
        self.cfg["brightness"] = int(round(self.bright_var.get()))
        self.cfg["scroll_speed"] = int(round(self.speed_var.get()))
        self.cfg["mirror"] = self.mirror_var.get()
        self.cfg["flip"] = self.flip_var.get()
        self.cfg["reverse_modules"] = self.revmod_var.get()
        self.bright_lbl.configure(text=str(self.cfg["brightness"]))
        sp = self.cfg["scroll_speed"]
        self.speed_lbl.configure(text=f"{sp} ms per step")
        self.panel.set_brightness(self.cfg["brightness"])
        self.refresh_canvas()

    # ----- text editing -----
    def update_text_note(self):
        it = self.item
        if not it or it["type"] != "text":
            return
        text = it.get("text", "")
        notes = []
        if any(ord(c) < 32 or ord(c) > 127 for c in text):
            notes.append("Some characters aren't in the display's font and will show as a block.")
        if it.get("static") and len(text) > 4:
            notes.append("Only 4 characters fit when holding still. Longer text gets cut off, so let it scroll.")
        if not notes:
            notes.append("Each character is 8 pixels wide, so 4 fit on the display at once.")
        self.text_note.configure(text=" ".join(notes))

    def on_text_change(self):
        if self.loading or not self.item or self.item["type"] != "text":
            return
        self.stop()
        it = self.item
        it["text"] = self.text_var.get()
        it["static"] = self.static_var.get()
        try:
            it["duration"] = max(1, int(self.duration_var.get()))
        except ValueError:
            pass
        self.refresh_list_row()
        self.update_text_note()
        self.refresh_canvas()

    # ----- animation editing -----
    def on_anim_settings(self):
        if self.loading or not self.item or self.item["type"] != "animation":
            return
        it = self.item
        it["name"] = self.name_var.get()
        for key, var, lo, hi in (("fps", self.fps_var, 1, 30), ("loops", self.loops_var, 1, 99)):
            try:
                it[key] = max(lo, min(hi, int(var.get())))
            except ValueError:
                pass
        self.refresh_list_row()

    def current_frame(self):
        return self.item["frames"][self.frame_idx]

    def on_paint(self, x, y, value, start):
        if not self.item or self.item["type"] != "animation":
            return
        self.stop()
        rows = self.current_frame()
        if start:
            self.stroke_value = (0 if get_px(rows, x, y) else 1) if value is None else value
        set_px(rows, x, y, self.stroke_value)
        self.refresh_canvas()
        self.after_idle(self.refresh_strip)

    def edit_frames(self, fn):
        if not self.item or self.item["type"] != "animation":
            return
        self.stop()
        fn(self.item["frames"])
        self.frame_idx = max(0, min(self.frame_idx, len(self.item["frames"]) - 1))
        self.refresh_canvas()
        self.refresh_strip()
        self.refresh_list_row()

    def add_frame(self):
        def fn(frames):
            frames.insert(self.frame_idx + 1, [0] * HEIGHT)
            self.frame_idx += 1
        self.edit_frames(fn)

    def dup_frame(self):
        def fn(frames):
            frames.insert(self.frame_idx + 1, list(frames[self.frame_idx]))
            self.frame_idx += 1
        self.edit_frames(fn)

    def del_frame(self):
        def fn(frames):
            if len(frames) == 1:
                frames[0] = [0] * HEIGHT
            else:
                frames.pop(self.frame_idx)
        self.edit_frames(fn)

    def move_frame(self, d):
        def fn(frames):
            j = self.frame_idx + d
            if 0 <= j < len(frames):
                frames[self.frame_idx], frames[j] = frames[j], frames[self.frame_idx]
                self.frame_idx = j
        self.edit_frames(fn)

    def clear_frame(self):
        self.edit_frames(lambda frames: frames.__setitem__(self.frame_idx, [0] * HEIGHT))

    def invert_frame(self):
        self.edit_frames(lambda frames: frames.__setitem__(
            self.frame_idx, [(~r) & FULL for r in frames[self.frame_idx]]))

    def shift(self, dx, dy):
        def fn(frames):
            rows = frames[self.frame_idx]
            if dx < 0:
                rows = [(r << 1) & FULL for r in rows]
            elif dx > 0:
                rows = [r >> 1 for r in rows]
            if dy < 0:
                rows = rows[1:] + [0]
            elif dy > 0:
                rows = [0] + rows[:-1]
            frames[self.frame_idx] = rows
        self.edit_frames(fn)

    def on_strip_click(self, event):
        if not self.item or self.item["type"] != "animation":
            return
        x = self.strip.canvasx(event.x)
        i = int((x - 8) // (WIDTH * 3 + 14))
        if 0 <= i < len(self.item["frames"]):
            self.stop()
            self.frame_idx = i
            self.refresh_canvas()
            self.refresh_strip()

    # ----- playlist -----
    def on_select(self, _event=None):
        picked = self.listbox.curselection()
        if picked and picked[0] != self.sel:
            self.sel = picked[0]
            self.frame_idx = 0
            self.show_editor()

    def insert_item(self, item):
        self.stop()
        pos = self.sel + 1 if self.item else len(self.cfg["items"])
        self.cfg["items"].insert(pos, item)
        self.sel = pos
        self.frame_idx = 0
        self.refresh_list()
        self.show_editor()

    def add_text(self):
        self.insert_item({"type": "text", "text": "NEW MESSAGE", "static": False, "duration": 3})

    def add_anim(self):
        n = sum(1 for i in self.cfg["items"] if i["type"] == "animation") + 1
        self.insert_item({"type": "animation", "name": f"Animation {n}", "fps": 4, "loops": 2,
                          "frames": [[0] * HEIGHT]})

    def dup_item(self):
        if self.item:
            self.insert_item(copy.deepcopy(self.item))

    def del_item(self):
        if not self.item:
            return
        self.stop()
        self.cfg["items"].pop(self.sel)
        self.sel = min(self.sel, len(self.cfg["items"]) - 1)
        self.frame_idx = 0
        self.refresh_list()
        self.show_editor()

    def move_item(self, d):
        items = self.cfg["items"]
        j = self.sel + d
        if self.item and 0 <= j < len(items):
            items[self.sel], items[j] = items[j], items[self.sel]
            self.sel = j
            self.refresh_list()

    # ----- preview playback -----
    def _play(self, frames_iter, button):
        if self.player is not None:
            self.stop()
            return
        self.player = frames_iter
        self.panel.editable = False
        button.configure(text="Stop")
        self._tick()

    def _tick(self):
        try:
            rows, ms = next(self.player)
        except StopIteration:
            self.stop()
            return
        self.panel.show(rows)
        self.player_job = self.after(max(1, ms), self._tick)

    def play_selected(self):
        if self.item:
            self._play(item_frames(self.item, self.cfg), self.play_btn)

    def play_all(self):
        def all_items():
            while True:
                if not self.cfg["items"]:
                    return
                for it in list(self.cfg["items"]):
                    yield from item_frames(it, self.cfg)
        self._play(all_items(), self.play_all_btn)

    def stop(self):
        if self.player_job:
            self.after_cancel(self.player_job)
        was_playing = self.player is not None
        self.player = None
        self.player_job = None
        self.play_btn.configure(text="Play this")
        self.play_all_btn.configure(text="Play all")
        if was_playing:
            self.panel.editable = bool(self.item and self.item["type"] == "animation")
            self.refresh_canvas()

    # ----- files -----
    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[("Display settings", "*.json")])
        if not path:
            return
        try:
            with open(path) as f:
                cfg = json.load(f)
            merged = copy.deepcopy(DEFAULT_CONFIG)
            merged.update(cfg)
            merged["items"] = cfg.get("items", [])
            self.cfg = merged
            self.path = Path(path)
            self.load_into_ui()
            self.set_status(f"Opened {self.path.name}")
        except Exception as e:
            messagebox.showerror("Couldn't open that file", f"{path}\n\n{e}")

    def save_file(self):
        if self.path is None:
            path = filedialog.asksaveasfilename(defaultextension=".json",
                                                initialfile="config.json",
                                                filetypes=[("Display settings", "*.json")])
            if not path:
                return
            self.path = Path(path)
        with open(self.path, "w") as f:
            json.dump(self.cfg, f, indent=1)
        self.title(f"Matrix Studio: {self.path.name}")
        self.set_status(f"Saved {self.path.name}")

    # ----- talking to the board -----
    def _mpremote_ready(self):
        if importlib.util.find_spec("mpremote") is None:
            messagebox.showinfo(
                "One more thing to install",
                "Sending to the display uses a small tool called mpremote.\n\n"
                "Install it by running this in a terminal, then try again:\n\n"
                f"    {Path(sys.executable).name} -m pip install mpremote")
            return False
        return True

    def _run_mpremote(self, steps, done_message):
        """steps: list of (local_path, board_name) files to copy, then the board restarts."""
        cmd = [sys.executable, "-m", "mpremote"]
        for local, remote in steps:
            cmd += ["cp", str(local), f":{remote}", "+"]
        cmd += ["reset"]
        self.send_btn.state(["disabled"])
        self.install_btn.state(["disabled"])
        self.set_status("Sending… keep the display plugged in.")

        def work():
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                ok = r.returncode == 0
                detail = (r.stderr or r.stdout).strip()
            except subprocess.TimeoutExpired:
                ok, detail = False, "It took too long to respond."
            self.after(0, lambda: finish(ok, detail))

        def finish(ok, detail):
            self.send_btn.state(["!disabled"])
            self.install_btn.state(["!disabled"])
            if ok:
                self.set_status(done_message)
            else:
                self.set_status("Sending failed.")
                messagebox.showerror(
                    "Couldn't reach the display",
                    "Check that the display is plugged in over USB, that MicroPython is on it, "
                    "and that nothing else (like Thonny) has it open.\n\nDetails:\n" + detail[-800:])

        threading.Thread(target=work, daemon=True).start()

    def _temp_config(self):
        tmp = Path(tempfile.mkdtemp()) / "config.json"
        with open(tmp, "w") as f:
            json.dump(self.cfg, f, separators=(",", ":"))
        return tmp

    def send_to_display(self):
        self.stop()
        if not self.cfg["items"]:
            messagebox.showinfo("Nothing to send", "Add a message or an animation first.")
            return
        if self._mpremote_ready():
            self._run_mpremote([(self._temp_config(), "config.json")],
                               "Sent. The display restarted with your playlist.")

    def install_firmware(self):
        self.stop()
        main, driver = FIRMWARE_DIR / "main.py", FIRMWARE_DIR / "max7219.py"
        if not (main.exists() and driver.exists()):
            messagebox.showerror("Firmware files not found",
                                 f"Expected main.py and max7219.py in:\n{FIRMWARE_DIR}")
            return
        if self._mpremote_ready():
            self._run_mpremote([(driver, "max7219.py"), (main, "main.py"),
                                (self._temp_config(), "config.json")],
                               "Firmware installed. The display restarted.")


if __name__ == "__main__":
    Studio().mainloop()
