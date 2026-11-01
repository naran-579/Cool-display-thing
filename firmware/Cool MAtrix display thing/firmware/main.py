# Desk matrix firmware (MicroPython, Seeed XIAO RP2040 + FC-16 4-in-1 MAX7219 module)
#
# The module stands upright: 8 pixels wide, 32 tall, with its input end (DIN)
# plugged into the socket at the bottom.
#
# Wiring (matches the schematic):
#   MTX_DIN -> D10 / GPIO3     MTX_CLK -> D8 / GPIO2     MTX_CS -> D7 / GPIO1
#   BTN     -> D3  / GPIO29 (other side of button to GND)
#   DS3231 clock module: SDA -> D4 / GPIO6, SCL -> D5 / GPIO7, VCC -> 3V3
#
# Everything you customise lives in config.json, which Matrix Studio writes.
#
# The button:
#   Hold (about 1 second)  switch mode: playlist -> timer -> stopwatch -> playlist
#   Press                  playlist: skip to the next item
#                          timer / stopwatch: start or pause
#   Double-press           timer / stopwatch: reset
#   When the timer finishes, the display flashes until you press the button.

import json
import time
import framebuf
from machine import Pin, SPI
import max7219
import ds3231

MODULES = 4
WIDTH = 8                 # upright: 8 pixels across
HEIGHT = MODULES * 8      # and 32 pixels tall

HOLD_MS = 800             # how long counts as a hold
DOUBLE_MS = 350           # max gap between the two presses of a double-press
DEBOUNCE_MS = 30

spi = SPI(0, baudrate=10_000_000, polarity=0, phase=0, sck=Pin(2), mosi=Pin(3))
display = max7219.Matrix8x8(spi, Pin(1), MODULES)
button = Pin(29, Pin.IN, Pin.PULL_UP)

DEFAULT_CONFIG = {
    "brightness": 2,
    "scroll_speed": 50,
    "mirror": False,
    "flip": False,
    "reverse_modules": False,
    "timer": {"enabled": True, "minutes": 5, "seconds": 0},
    "stopwatch": {"enabled": True},
    "items": [{"type": "text", "text": "NO CONFIG", "style": "stacked",
               "static": False, "duration": 3}],
}


def load_config():
    try:
        with open("config.json") as f:
            cfg = json.load(f)
        for key, value in DEFAULT_CONFIG.items():
            if key not in cfg:
                cfg[key] = value
        if not cfg["items"]:
            cfg["items"] = DEFAULT_CONFIG["items"]
        return cfg
    except Exception as e:
        print("Could not read config.json:", e)
        return DEFAULT_CONFIG


cfg = load_config()


# ---------- the button ----------
# Checked every few milliseconds inside wait(), which every mode calls constantly.
class Button:
    def __init__(self, pin):
        self.pin = pin
        self.down_at = None       # when the current press started
        self.held = False         # a hold already fired for this press
        self.click_at = None      # a single press waiting to see if a second one follows

    def poll(self, allow_double):
        now = time.ticks_ms()
        pressed = self.pin.value() == 0
        if pressed:
            if self.down_at is None:
                self.down_at = now
            elif not self.held and time.ticks_diff(now, self.down_at) >= HOLD_MS:
                self.held = True
                self.click_at = None
                return "hold"
        elif self.down_at is not None:
            length = time.ticks_diff(now, self.down_at)
            was_held = self.held
            self.down_at = None
            self.held = False
            if not was_held and length >= DEBOUNCE_MS:
                if not allow_double:
                    return "press"
                if self.click_at is not None:
                    self.click_at = None
                    return "double"
                self.click_at = now
        if self.click_at is not None and self.down_at is None and \
                time.ticks_diff(now, self.click_at) > DOUBLE_MS:
            self.click_at = None
            return "press"
        return None


btn = Button(button)
current_mode = "playlist"


def wait(ms, allow_double=False):
    """Waits up to ms. Returns a button event ("press", "double", "hold"),
    "timer_done" if the timer runs out while you're in another mode, or None."""
    end = time.ticks_add(time.ticks_ms(), ms)
    while True:
        event = btn.poll(allow_double)
        if event:
            return event
        if current_mode != "timer" and timer.finished():
            return "timer_done"
        if time.ticks_diff(end, time.ticks_ms()) <= 0:
            return None
        time.sleep_ms(5)


# ---------- turning an upright picture into what the chips expect ----------
# A picture is 32 numbers, one per row from top to bottom.
# Each number is 0-255; its highest bit is the leftmost pixel.

def _reverse_bits(b):
    r = 0
    for i in range(8):
        r = (r << 1) | ((b >> i) & 1)
    return r


REVERSED = bytearray([_reverse_bits(i) for i in range(256)])
BLANK = [0] * HEIGHT


def show(rows):
    # Orientation fixes, in case the real display comes out wrong.
    if cfg["mirror"]:
        rows = [REVERSED[r] for r in rows]
    if cfg["flip"]:
        rows = rows[::-1]
    if cfg["reverse_modules"]:
        rows = [rows[(MODULES - 1 - i // 8) * 8 + i % 8] for i in range(HEIGHT)]
    # The chips think of the module as lying on its side, so each 8x8 block
    # gets turned a quarter turn as it's copied into the display buffer.
    buf = display.buffer
    for m in range(MODULES):
        block = rows[m * 8:m * 8 + 8]
        for ny in range(8):
            b = 0
            for k in range(8):
                b = (b << 1) | ((block[k] >> ny) & 1)
            buf[ny * MODULES + m] = b
    display.show()


# ---------- text ----------
def text_strip(text, style):
    """Draws the text as one tall strip of rows, which then scrolls up the display."""
    if style == "sideways":
        # Normal left-to-right text, turned so it reads from top to bottom.
        width = len(text) * 8
        tmp = bytearray(len(text) * 8)
        fb = framebuf.FrameBuffer(tmp, width, 8, framebuf.MONO_HLSB)
        fb.text(text, 0, 0, 1)
        strip = bytearray(width)
        for x in range(width):
            col = 0
            for y in range(8):
                if fb.pixel(x, y):
                    col |= 1 << y
            strip[x] = col
        return strip
    # "stacked": upright letters, one above the next
    strip = bytearray(len(text) * 8)
    tmp = bytearray(8)
    fb = framebuf.FrameBuffer(tmp, 8, 8, framebuf.MONO_HLSB)
    for i, ch in enumerate(text):
        fb.fill(0)
        fb.text(ch, 0, 0, 1)
        strip[i * 8:i * 8 + 8] = tmp
    return strip


def window(strip, top):
    """The 32 rows of the strip visible when its first row sits at row `top`."""
    rows = []
    n = len(strip)
    for y in range(HEIGHT):
        i = y - top
        rows.append(strip[i] if 0 <= i < n else 0)
    return rows


def four_digits(text):
    return window(text_strip(text, "stacked"), 0)


def time_rows(seconds):
    """Minutes over seconds. From one hour on: hours over minutes, with a dot
    on the right edge between them so you can tell the difference."""
    if seconds >= 3600:
        rows = four_digits("%02d%02d" % (min(99, seconds // 3600), seconds // 60 % 60))
        rows[15] |= 0x01
        return rows
    return four_digits("%02d%02d" % (seconds // 60, seconds % 60))


# ---------- playlist items ----------
def play_text(item):
    strip = text_strip(item.get("text", ""), item.get("style", "stacked"))
    if item.get("static"):
        show(window(strip, (HEIGHT - len(strip)) // 2))
        return wait(int(item.get("duration", 3) * 1000))
    delay = cfg["scroll_speed"]
    top = HEIGHT                      # start just below the bottom edge
    while top > -len(strip):          # scroll up until it's gone off the top
        show(window(strip, top))
        event = wait(delay)
        if event:
            return event
        top -= 1
    return None


has_clock_chip = ds3231.present()
if not has_clock_chip:
    print("No DS3231 found, using the XIAO's own clock (resets when unplugged)")


def current_hour_minute():
    if has_clock_chip:
        try:
            t = ds3231.get_time()
            return t[3], t[4]
        except Exception:
            pass
    t = time.localtime()
    return t[3], t[4]


def play_clock(item):
    """Hours on top, minutes below: four upright digits fill the display exactly."""
    end = time.ticks_add(time.ticks_ms(), int(item.get("duration", 5) * 1000))
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        hour, minute = current_hour_minute()
        if item.get("format") == "12h":
            hour = hour % 12 or 12
        show(four_digits("%02d%02d" % (hour, minute)))
        event = wait(min(1000, max(1, time.ticks_diff(end, time.ticks_ms()))))
        if event:
            return event
    return None


def play_animation(item):
    frames = item.get("frames", [])
    if not frames:
        return None
    delay = max(1, 1000 // max(1, item.get("fps", 4)))
    for _ in range(max(1, item.get("loops", 1))):
        for rows in frames:
            show(rows)
            event = wait(delay)
            if event:
                return event
    return None


def run_playlist(can_switch):
    """Plays the playlist until a hold (switch mode) or the timer finishing."""
    while True:
        for item in cfg["items"]:
            kind = item.get("type")
            if kind == "animation":
                event = play_animation(item)
            elif kind == "clock":
                event = play_clock(item)
            else:
                event = play_text(item)
            if event == "timer_done" or (event == "hold" and can_switch):
                return event
            # a press (or a hold with nowhere to switch to) moves on to the next item


# ---------- timer ----------
class Timer:
    def __init__(self, seconds):
        self.length_ms = max(1, seconds) * 1000
        self.reset()

    def reset(self):
        self.running = False
        self.left_ms = self.length_ms
        self.ends_at = 0

    def remaining_ms(self):
        if self.running:
            return max(0, time.ticks_diff(self.ends_at, time.ticks_ms()))
        return self.left_ms

    def finished(self):
        return self.running and self.remaining_ms() == 0

    def toggle(self):
        if self.running:
            self.left_ms = self.remaining_ms()
            self.running = False
        else:
            self.ends_at = time.ticks_add(time.ticks_ms(), self.left_ms)
            self.running = True

    def at_start(self):
        return not self.running and self.left_ms == self.length_ms


class Stopwatch:
    def __init__(self):
        self.reset()

    def reset(self):
        self.running = False
        self.total_ms = 0
        self.started_at = 0

    def elapsed_ms(self):
        if self.running:
            return self.total_ms + time.ticks_diff(time.ticks_ms(), self.started_at)
        return self.total_ms

    def toggle(self):
        if self.running:
            self.total_ms = self.elapsed_ms()
            self.running = False
        else:
            self.started_at = time.ticks_ms()
            self.running = True


tcfg = cfg["timer"]
timer = Timer(int(tcfg.get("minutes", 5)) * 60 + int(tcfg.get("seconds", 0)))
stopwatch = Stopwatch()

HOURGLASS = [0xFF, 0x42, 0x24, 0x18, 0x18, 0x24, 0x42, 0xFF]
STOPWATCH_ICON = [0x18, 0x3C, 0x42, 0x89, 0x91, 0x81, 0x42, 0x3C]


def show_icon(icon):
    show([0] * 12 + icon + [0] * 12)
    return wait(700)


def blink_on():
    return (time.ticks_ms() // 500) % 2 == 0


def flash_until_pressed():
    """The timer ran out: flash until someone presses the button."""
    zero = time_rows(0)
    full = [0xFF] * HEIGHT
    flip_frame = False
    while True:
        show(full if flip_frame else zero)
        flip_frame = not flip_frame
        event = wait(250)
        if event:
            timer.reset()
            return event


def run_timer(announce):
    if announce:
        event = show_icon(HOURGLASS)
        if event == "hold":
            return event
    while True:
        if timer.finished():
            if flash_until_pressed() == "hold":
                return "hold"
            continue
        seconds = (timer.remaining_ms() + 999) // 1000      # round up, like a kitchen timer
        paused = not timer.running and not timer.at_start()
        show(BLANK if paused and not blink_on() else time_rows(seconds))
        event = wait(100, allow_double=True)
        if event == "press":
            timer.toggle()
        elif event == "double":
            timer.reset()
        elif event == "hold":
            return event


def run_stopwatch():
    event = show_icon(STOPWATCH_ICON)
    if event in ("hold", "timer_done"):
        return event
    while True:
        elapsed = stopwatch.elapsed_ms()
        paused = not stopwatch.running and elapsed > 0
        show(BLANK if paused and not blink_on() else time_rows(elapsed // 1000))
        event = wait(100, allow_double=True)
        if event == "press":
            stopwatch.toggle()
        elif event == "double":
            stopwatch.reset()
        elif event in ("hold", "timer_done"):
            return event


# ---------- main loop ----------
display.brightness(max(0, min(15, cfg["brightness"])))

modes = ["playlist"]
if tcfg.get("enabled"):
    modes.append("timer")
if cfg["stopwatch"].get("enabled"):
    modes.append("stopwatch")

announce = True
while True:
    if current_mode == "playlist":
        event = run_playlist(len(modes) > 1)
    elif current_mode == "timer":
        event = run_timer(announce)
    else:
        event = run_stopwatch()
    if event == "timer_done":
        current_mode, announce = "timer", False      # jump straight to the flashing timer
    else:
        current_mode = modes[(modes.index(current_mode) + 1) % len(modes)]
        announce = True
