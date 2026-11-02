"""Deterministic FAA-style phraseology (JO 7110.65 number conventions)."""
from __future__ import annotations

import re

DIGITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "niner"]
ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
TEENS = ["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
NATO = {
    "A": "alpha", "B": "bravo", "C": "charlie", "D": "delta", "E": "echo", "F": "foxtrot", "G": "golf",
    "H": "hotel", "I": "india", "J": "juliett", "K": "kilo", "L": "lima", "M": "mike", "N": "november",
    "O": "oscar", "P": "papa", "Q": "quebec", "R": "romeo", "S": "sierra", "T": "tango", "U": "uniform",
    "V": "victor", "W": "whiskey", "X": "x-ray", "Y": "yankee", "Z": "zulu",
}
TELEPHONY = {
    "DAL": "Delta", "SWA": "Southwest", "AAL": "American", "UAL": "United", "EDV": "Endeavor",
    "JBU": "JetBlue", "ASA": "Alaska", "FFT": "Frontier", "NKS": "Spirit", "SKW": "SkyWest", "RPA": "Brickyard",
}


def _pair(n: int) -> str:
    """Two-digit group as spoken in a flight number: 23 -> twenty-three, 05 -> zero five."""
    if n < 10:
        return f"zero {ONES[n] or 'zero'}" if n else "hundred"
    if n < 20:
        return TEENS[n - 10]
    return TENS[n // 10] + (f"-{ONES[n % 10]}" if n % 10 else "")


def flight_number(num: str) -> str:
    n = int(num)
    if len(num) <= 2:
        return _pair(n) if n >= 10 else ONES[n] or "zero"
    if len(num) == 3:
        rest = n % 100
        return f"{ONES[n // 100]} {_pair(rest)}" if rest else f"{ONES[n // 100]} hundred"
    if len(num) == 4:
        return f"{_pair(n // 100)} {_pair(n % 100)}"
    return " ".join(DIGITS[int(d)] for d in num)


def callsign(cs: str) -> str:
    m = re.fullmatch(r"([A-Z]{3})(\d{1,4})([A-Z]{0,2})", cs)
    if m and m.group(1) in TELEPHONY:
        out = f"{TELEPHONY[m.group(1)]} {flight_number(m.group(2))}"
        return out + "".join(f" {NATO[c]}" for c in m.group(3))
    # N-number or unknown: spell it out
    return " ".join(NATO[c] if c.isalpha() else DIGITS[int(c)] for c in cs.upper() if c.isalnum()).capitalize()


def digits(n: int, width: int = 0) -> str:
    return " ".join(DIGITS[int(d)] for d in str(n).zfill(width))


def altitude(ft: float) -> str:
    ft = int(round(ft / 100.0) * 100)
    if ft >= 18000:
        return f"flight level {digits(ft // 100)}"
    thousands, hundreds = divmod(ft, 1000)
    parts = []
    if thousands:
        parts.append(f"{digits(thousands)} thousand")
    if hundreds:
        parts.append(f"{DIGITS[hundreds // 100]} hundred")
    return " ".join(parts) or "zero"


def instruction(cs: str, action: str, value: float, current_heading: float | None = None,
                current_alt: float | None = None, current_gs: float | None = None) -> str:
    who = callsign(cs)
    if action in ("climb", "descend"):
        return f"{who}, {action} and maintain {altitude(value)}."
    if action == "turn":
        hdg = int(round(value)) % 360 or 360
        side = ""
        if current_heading is not None:
            d = (hdg - current_heading + 540) % 360 - 180
            side = "right " if d > 0 else "left "
        return f"{who}, turn {side}heading {digits(hdg, 3)}."
    if action == "speed":
        verb = "reduce" if current_gs is not None and value < current_gs else "increase" if current_gs is not None else "maintain"
        return f"{who}, {verb} speed to {digits(int(round(value)))}."
    raise ValueError(action)
