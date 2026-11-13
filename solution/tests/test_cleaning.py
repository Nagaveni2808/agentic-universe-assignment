from datetime import date
from decimal import Decimal

import pytest

from ledger.cleaning import (
    normalise_header, normalise_phone, parse_date,
    parse_decimal, parse_enum, parse_timestamp,
)


def test_header():
    assert normalise_header(" Mobile_No ") == "mobile no"
    assert normalise_header("POLICY__NO") == "policy no"
    assert normalise_header("Policy   No") == "policy no"


@pytest.mark.parametrize("raw", [
    "9876543210", "+91 98765 43210", "98765-43210",
    "098765 43210", "919876543210", "91-98765-43210",
])
def test_phone_valid_formats(raw):
    assert normalise_phone(raw) == "+919876543210"


@pytest.mark.parametrize("raw", [
    "", None, "98765", "1234567890", "5876543210", "+91 12345 67890",
])
def test_phone_invalid(raw):
    assert normalise_phone(raw) is None


def test_dates():
    assert parse_date("2026-12-01") == date(2026, 12, 1)
    assert parse_date("01/12/2026") == date(2026, 12, 1)   # day first
    assert parse_date("01-12-2026") == date(2026, 12, 1)
    assert parse_date("01-Dec-2026") == date(2026, 12, 1)
    assert parse_date("01-dEc-2026") == date(2026, 12, 1)  # case-insensitive


@pytest.mark.parametrize("raw", ["31/02/2026", "2026-13-01", "abc", "", None, "01-Xyz-2026"])
def test_dates_invalid(raw):
    assert parse_date(raw) is None


def test_decimal():
    assert parse_decimal("₹1,23,456.789") == Decimal("123456.79")
    assert parse_decimal("Rs. 500") == Decimal("500.00")
    assert parse_decimal("inr 99.5") == Decimal("99.50")
    assert parse_decimal("Rs1,200") == Decimal("1200.00")
    assert parse_decimal("0") == Decimal("0.00")
    assert parse_decimal("-5") is None
    assert parse_decimal("abc") is None
    assert parse_decimal("") is None


def test_enum():
    assert parse_enum(" HI ", ["en", "hi"]) == "hi"
    assert parse_enum("fr", ["en", "hi"]) is None


def test_timestamps_all_become_ist():
    assert parse_timestamp("2026-10-05T13:20:21Z").isoformat() == "2026-10-05T18:50:21+05:30"
    assert parse_timestamp("2026-10-05T18:50:21+05:30").isoformat() == "2026-10-05T18:50:21+05:30"
    assert parse_timestamp("2026-10-03 10:01:00").isoformat() == "2026-10-03T10:01:00+05:30"
    assert parse_timestamp("garbage") is None