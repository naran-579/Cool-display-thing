# Minimal driver for the DS3231 real-time clock (I2C address 0x68).
# Wired to the XIAO RP2040: SDA -> D4 / GPIO6, SCL -> D5 / GPIO7 (I2C bus 1).

from machine import I2C, Pin

ADDR = 0x68
_i2c = None


def _bus():
    global _i2c
    if _i2c is None:
        _i2c = I2C(1, sda=Pin(6), scl=Pin(7), freq=100_000)
    return _i2c


def present():
    try:
        return ADDR in _bus().scan()
    except Exception:
        return False


def _from_bcd(b):
    return (b >> 4) * 10 + (b & 0x0F)


def _to_bcd(n):
    return ((n // 10) << 4) | (n % 10)


def get_time():
    """Returns (year, month, day, hour, minute, second), hour in 24-hour form."""
    d = _bus().readfrom_mem(ADDR, 0, 7)
    second = _from_bcd(d[0] & 0x7F)
    minute = _from_bcd(d[1] & 0x7F)
    h = d[2]
    if h & 0x40:                                  # chip was left in 12-hour mode
        hour = _from_bcd(h & 0x1F) % 12 + (12 if h & 0x20 else 0)
    else:
        hour = _from_bcd(h & 0x3F)
    day = _from_bcd(d[4] & 0x3F)
    month = _from_bcd(d[5] & 0x1F)
    year = 2000 + _from_bcd(d[6])
    return year, month, day, hour, minute, second


def set_time(year, month, day, hour, minute, second, weekday=1):
    """Matrix Studio calls this to copy your computer's time onto the chip."""
    data = bytes([_to_bcd(second), _to_bcd(minute), _to_bcd(hour), weekday,
                  _to_bcd(day), _to_bcd(month), _to_bcd(year - 2000)])
    _bus().writeto_mem(ADDR, 0, data)
    status = _bus().readfrom_mem(ADDR, 0x0F, 1)[0]
    _bus().writeto_mem(ADDR, 0x0F, bytes([status & 0x7F]))   # clear "clock stopped" flag
