"""Small, pure functions that clean one value at a time.

Each function returns the cleaned value, or None if the input is invalid.
They never touch the database, which makes them easy to test.
"""
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

# India time = UTC + 5:30. A fixed offset avoids needing the tzdata package on Windows.
IST = timezone(timedelta(hours=5, minutes=30))

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def normalise_header(text: str) -> str:
    """lower-case, trim, and turn every run of _ or spaces into one space."""
    return re.sub(r"[_\s]+", " ", text.lower().strip())


def normalise_phone(raw) -> str | None:
    """Return '+91XXXXXXXXXX' for a valid Indian mobile number, else None."""
    digits = re.sub(r"[^0-9]", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        return "+91" + digits
    return None


def parse_date(raw) -> date | None:
    """Accept YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, DD-Mon-YYYY (day first)."""
    s = (raw or "").strip()
    try:
        if m := re.fullmatch(r"([0-9]{4})-([0-9]{2})-([0-9]{2})", s):
            y, mo, d = int(m[1]), int(m[2]), int(m[3])
        elif m := re.fullmatch(r"([0-9]{2})([/-])([0-9]{2})\2([0-9]{4})", s):
            d, mo, y = int(m[1]), int(m[3]), int(m[4])
        elif m := re.fullmatch(r"([0-9]{2})-([A-Za-z]{3})-([0-9]{4})", s):
            d, y = int(m[1]), int(m[3])
            mo = _MONTHS.get(m[2].lower())
            if mo is None:
                return None
        else:
            return None
        return date(y, mo, d)  # raises ValueError for impossible dates like 31/02
    except ValueError:
        return None


_CURRENCY_PREFIX = re.compile(r"(?:₹|rs\.?|inr)\s*", re.IGNORECASE)


def parse_decimal(raw) -> Decimal | None:
    """Money like '₹1,200.5' -> Decimal('1200.50'). Must be >= 0."""
    s = (raw or "").strip()
    s = _CURRENCY_PREFIX.sub("", s, count=1) if _CURRENCY_PREFIX.match(s) else s
    s = s.replace(",", "")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", s):
        return None  # also rejects negatives
    return Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_enum(raw, allowed) -> str | None:
    """Case-insensitive match against the allowed values; stored lower-case."""
    v = (raw or "").strip().lower()
    return v if v in {a.lower() for a in allowed} else None


def parse_timestamp(raw) -> datetime | None:
    """Read Z / +05:30 / naive timestamps and return an IST-aware datetime.
    Naive (no timezone) means IST."""
    try:
        dt = datetime.fromisoformat(raw.strip())
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(IST)