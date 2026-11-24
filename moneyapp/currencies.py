"""Currencies an account can be kept in: the Americas, plus the euro.

Amounts are always stored in hundredths of the account's own currency. There are no live
exchange rates: a transfer between accounts in different currencies records what left and
what arrived, and totals across currencies use rough rates the person types in themselves
(marked approximate wherever they're used)."""

from decimal import Decimal, InvalidOperation

# ISO 4217 codes. Names and symbols come from the browser, in the person's language.
CODES = ("USD", "CAD", "MXN", "GTQ", "HNL", "NIO", "CRC", "PAB", "DOP", "JMD", "TTD", "BSD",
         "COP", "VES", "PEN", "BOB", "CLP", "ARS", "UYU", "PYG", "BRL", "EUR")
DEFAULT = "USD"


def clean_code(code, default=DEFAULT):
    c = str(code or "").strip().upper()
    if not c:
        return default
    if c not in CODES:
        raise ValueError(f"Unknown currency {c}")
    return c


def clean_rate(value):
    """A rough rate as typed ("0.18", "5,40"): how many of the main currency one unit is worth.
    Empty means none. Returned as text so it's kept exactly as given."""
    s = str(value if value is not None else "").strip().replace(" ", "")
    if not s:
        return None
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"{value} isn't a number")
    if not d.is_finite() or d <= 0 or d > Decimal("1000000"):
        raise ValueError("A rate must be more than 0")
    return format(d.normalize(), "f")
