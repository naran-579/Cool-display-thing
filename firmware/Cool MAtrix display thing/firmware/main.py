# Desk matrix firmware (MicroPython, Seeed XIAO RP2040 + FC-16 4-in-1 MAX7219 module)
#
# The module stands upright: 8 pixels wide, 32 tall, with its input end (DIN)
# plugged into the socket at the bottom.
#
# Wiring (matches the schematic):
#   MTX_DIN -> D10 / GPIO3     MTX_CLK -> D8 / GPIO2     MTX_CS -> D7 / GPIO1
#   BTN     -> D3  / GPIO29 (other side of button to GND)
#
# Everything you customise lives in config.json, which Matrix Studio writes.
# The button skips to the next message or animation.

import json
import time
import framebuf
from machine import Pin, SPI
import max7219

MODULES = 4
WIDTH = 8                 # upright: 8 pixels across
HEIGHT = MODULES * 8      # and 32 pixels tall

spi = SPI(0, baudrate=10_000_000, polarity=0, phase=0, sck=Pin(2), mosi=Pin(3))
display = max7219.Matrix8x8(spi, Pin(1), MODULES)
button = Pin(29, Pin.IN, Pin.PULL_UP)

DEFAULT_CONFIG = {
    "brightness": 2,
    "scroll_speed": 50,
    "mirror": False,
    "flip": False,
    "reverse_modules": False,
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

# ---------- button: an interrupt sets a flag so presses are never missed ----------
skip_requested = False
last_press = 0


def on_button(pin):
    global skip_requested, last_press
    now = time.ticks_ms()
    if time.ticks_diff(now, last_press) > 250:   # debounce
        skip_requested = True
        last_press = now


button.irq(trigger=Pin.IRQ_FALLING, handler=on_button)


def wait(ms):
    """Sleep for ms, but return True straight away if the button was pressed."""
    global skip_requested
    end = time.ticks_add(time.ticks_ms(), ms)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        if skip_requested:
            skip_requested = False
            return True
        time.sleep_ms(5)
    return False


# ---------- turning an upright picture into what the chips expect ----------
# A picture is 32 numbers, one per row from top to bottom.
# Each number is 0-255; its highest bit is the leftmost pixel.

def _reverse_bits(b):
    r = 0
    for i in range(8):
        r = (r << 1) | ((b >> i) & 1)
    return r


REVERSED = bytearray([_reverse_bits(i) for i in range(256)])


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


def play_text(item):
    strip = text_strip(item.get("text", ""), item.get("style", "stacked"))
    if item.get("static"):
        show(window(strip, (HEIGHT - len(strip)) // 2))
        wait(int(item.get("duration", 3) * 1000))
        return
    delay = cfg["scroll_speed"]
    top = HEIGHT                      # start just below the bottom edge
    while top > -len(strip):          # scroll up until it's gone off the top
        show(window(strip, top))
        if wait(delay):
            return
        top -= 1


# ---------- animations ----------
def play_animation(item):
    frames = item.get("frames", [])
    if not frames:
        return
    delay = max(1, 1000 // max(1, item.get("fps", 4)))
    for _ in range(max(1, item.get("loops", 1))):
        for rows in frames:
            show(rows)
            if wait(delay):
                return


# ---------- main loop ----------
display.brightness(max(0, min(15, cfg["brightness"])))

while True:
    for item in cfg["items"]:
        if item.get("type") == "animation":
            play_animation(item)
        else:
            play_text(item)
