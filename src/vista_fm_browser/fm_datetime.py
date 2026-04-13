"""
FileMan date/time conversion utilities.

FileMan stores dates and times as a number in the format YYYMMDD.HHMMSS:

    YYY = actual_year - 1700  (e.g. 316 = 2016, 245 = 1945)
    MM  = month (01-12)
    DD  = day (01-31)

The time component is optional.  Because YottaDB stores dates as floating-
point numbers, trailing zeros in the time fraction are dropped:

    14:30:00 → stored as .143  (not .1430)
    08:00:00 → stored as .08   (not .080000)

This module right-pads the fractional part to six digits before parsing as
HHMMSS, so both forms are handled correctly.

Special values:
    ""  or  "0"  → no date (returns None)

Partial dates (month=0 or day=0) are normalized to month=1, day=1.

Public API::

    fm_to_dt("3160101")          → datetime(2016, 1, 1)
    fm_to_dt("3160101.143")      → datetime(2016, 1, 1, 14, 30, 0)
    dt_to_fm(datetime(2016,1,1)) → "3160101"
    fm_date_display("3160101")   → "Jan 01, 2016"
"""

from __future__ import annotations

from datetime import datetime

__all__ = ["fm_to_dt", "dt_to_fm", "fm_date_display"]

_MONTH_ABBR = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]


def fm_to_dt(fm_date: str) -> datetime | None:
    """Convert a FileMan internal date/time string to a Python datetime.

    Parameters
    ----------
    fm_date:
        FileMan internal date string, e.g. "3160101", "3160101.143",
        "2450101.083015".  Empty string or "0" returns None.

    Returns None for empty, "0", whitespace-only, or unparseable input.
    Partial dates (month or day = 0) are normalised to 1.
    """
    if not fm_date or fm_date.strip() in ("", "0"):
        return None
    fm_date = fm_date.strip()
    try:
        if "." in fm_date:
            date_str, time_str = fm_date.split(".", 1)
        else:
            date_str, time_str = fm_date, ""

        date_str = date_str.zfill(7)  # pad short dates to YYYMMDD
        fm_year = int(date_str[:3])
        month = int(date_str[3:5]) or 1  # month 00 → 01 (partial date)
        day = int(date_str[5:7]) or 1  # day   00 → 01 (partial date)
        year = fm_year + 1700

        if time_str:
            # Right-pad fractional part to 6 digits → parse as HHMMSS
            ts = time_str.ljust(6, "0")[:6]
            hour, minute, second = int(ts[0:2]), int(ts[2:4]), int(ts[4:6])
        else:
            hour = minute = second = 0

        return datetime(year, month, day, hour, minute, second)
    except (ValueError, IndexError):
        return None


def dt_to_fm(dt: datetime) -> str:
    """Convert a Python datetime to a FileMan internal date string.

    The time component is omitted when midnight.  Trailing zeros in the time
    fraction are stripped to match how YottaDB stores numeric values.

    Parameters
    ----------
    dt:
        Python datetime (timezone-naive).

    Examples
    --------
    >>> dt_to_fm(datetime(2016, 1, 1))
    '3160101'
    >>> dt_to_fm(datetime(2016, 1, 1, 14, 30, 0))
    '3160101.143'
    """
    fm_year = dt.year - 1700
    date_part = f"{fm_year}{dt.month:02d}{dt.day:02d}"
    if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
        return date_part
    # Build HHMMSS, strip trailing zeros (mirroring float storage)
    time_part = f"{dt.hour:02d}{dt.minute:02d}{dt.second:02d}".rstrip("0")
    return f"{date_part}.{time_part}"


def fm_date_display(fm_date: str, *, include_time: bool = True) -> str:
    """Format a FileMan internal date as a human-readable string.

    Parameters
    ----------
    fm_date:
        FileMan internal date string.
    include_time:
        If True and the date has a non-midnight time component, append the
        time as HH:MM:SS.

    Returns empty string for empty, "0", or unparseable input.

    Examples
    --------
    >>> fm_date_display("3160101")
    'Jan 01, 2016'
    >>> fm_date_display("3160101.143")
    'Jan 01, 2016 14:30:00'
    >>> fm_date_display("3160101.143", include_time=False)
    'Jan 01, 2016'
    """
    dt = fm_to_dt(fm_date)
    if dt is None:
        return ""
    month_abbr = _MONTH_ABBR[dt.month - 1]
    date_str = f"{month_abbr} {dt.day:02d}, {dt.year}"
    if include_time and (dt.hour or dt.minute or dt.second):
        return f"{date_str} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"
    return date_str
