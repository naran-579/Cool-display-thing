# Desk matrix firmware (MicroPython, Seeed XIAO RP2040 + FC-16 4-in-1 MAX7219 module)
#
# Wiring (matches the schematic):
#   MTX_DIN -> D10 / GPIO3     MTX_CLK -> D8 / GPIO2     MTX_CS -> D7 / GPIO1
#   BTN     -> D3  / GPIO29 (other side of button to GND)
#
# Everything you customise lives in config.json, which Matrix Studio writes.
# The button skips to the next message or animation.

import json
import time
from machine import Pin, SPI
import max7219

MODULES = 4            # four 8x8 blocks = 32 x 8 pixels
WIDTH = MODULES * 8

spi = SPI(0, baudrate=10_000_000, polarity=0, phase=0, sck=Pin(2), mosi=Pin(3))
display = max7219.Matrix8x8(spi, Pin(1), MODULES)
button = Pin(29, Pin.IN, Pin.PULL_UP)

DEFAULT_CONFIG = {
    "brightness": 2,
    "scroll_speed": 40,
    "mirror": False,
    "flip": False,
    "reverse_modules": False,
    "items": [{"type": "text", "text": "NO CONFIG", "static": False, "duration": 3}],
}


def load_config():
    try:
        with open("config.json") as f:
            cfg = json.load(f)
        for key, value in DEFAULT_CONFIG.items():
            cfg.setdefault(key, value)
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


# ---------- orientation fixes for modules that come out mirrored or upside down ----------
def _reverse_bits(b):
    r = 0
    for i in range(8):
        r = (r << 1) | ((b >> i) & 1)
    return r


REVERSED = bytearray([_reverse_bits(i) for i in range(256)])

flip = cfg["flip"]
swap_modules = cfg["mirror"] != cfg["reverse_modules"]   # mirroring also swaps module order
reverse_bits = cfg["mirror"]


def push():
    """Apply any orientation fixes to the drawing buffer, then send it to the display."""
    buf = display.buffer
    if flip:
        for y in range(4):
            for m in range(MODULES):
                a = y * MODULES + m
                b = (7 - y) * MODULES + m
                buf[a], buf[b] = buf[b], buf[a]
    if swap_modules:
        for y in range(8):
            start = y * MODULES
            for m in range(MODULES // 2):
                a = start + m
                b = start + MODULES - 1 - m
                buf[a], buf[b] = buf[b], buf[a]
    if reverse_bits:
        for i in range(len(buf)):
            buf[i] = REVERSED[buf[i]]
    display.show()


# ---------- drawing ----------
def draw_frame(rows):
    """rows: 8 numbers, one per row. The highest bit of each is the leftmost pixel."""
    buf = display.buffer
    for y in range(8):
        r = rows[y]
        for m in range(MODULES):
            buf[y * MODULES + m] = (r >> (8 * (MODULES - 1 - m))) & 0xFF


def play_text(item):
    text = item.get("text", "")
    width = len(text) * 8
    if item.get("static"):
        display.fill(0)
        display.text(text, (WIDTH - width) // 2, 0, 1)
        push()
        wait(int(item.get("duration", 3) * 1000))
        return
    x = WIDTH
    delay = cfg["scroll_speed"]
    while x > -width:
        display.fill(0)
        display.text(text, x, 0, 1)
        push()
        if wait(delay):
            return
        x -= 1


def play_animation(item):
    frames = item.get("frames", [])
    if not frames:
        return
    delay = max(1, 1000 // max(1, item.get("fps", 4)))
    for _ in range(max(1, item.get("loops", 1))):
        for rows in frames:
            draw_frame(rows)
            push()
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
