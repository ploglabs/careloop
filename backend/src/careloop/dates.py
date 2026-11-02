"""Turning what a patient says about a day ("tomorrow", "day after tomorrow", "next Monday",
"in 3 days", "5 November", "ਕੱਲ੍ਹ", "परसों") into a calendar date, relative to today in IST.

The LLM is asked to pass YYYY-MM-DD, but models slip on date arithmetic and on the Indian words
for tomorrow and the day after, so the booking tool also accepts the patient's own words and
resolves them here. Only future days make sense for booking, so "kal" (which can also mean
yesterday) is read as tomorrow.
"""

import re
from datetime import date, datetime, timedelta, timezone

from careloop.models import IST, to_ist, utcnow

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december")

# Checked before TOMORROW, since most "day after tomorrow" phrases contain the word for tomorrow.
DAY_AFTER_TOMORROW = (
    "day after tomorrow", "day after tmrw", "day after tmr", "overmorrow",
    "parso", "parson", "parsoon", "parsun", "परसों", "परसो", "ਪਰਸੋਂ", "ਪਰਸੋ", "ਪਰਸੋਂ",
    "परवा", "पर्वा",                     # Marathi
    "પરમ દિવસે", "પરમદિવસે", "પરમ દિવસ", "પરમ",  # Gujarati
    "পরশু", "parshu", "porshu",           # Bengali
    "நாளை மறுநாள்", "நாளைமறுநாள்", "மறுநாள்", "naalai marunaal",  # Tamil
    "ఎల్లుండి", "ellundi",                # Telugu
    "ನಾಡಿದ್ದು", "naadiddu", "nadiddu",     # Kannada
    "മറ്റന്നാൾ", "mattannal",              # Malayalam
)
TOMORROW = (
    "tomorrow", "tommorow", "tomorow", "tmrw", "tmr", "next day",
    "kal", "kaal", "kall", "कल", "ਕੱਲ੍ਹ", "ਕੱਲ", "ਕਲ", "ਭਲਕੇ", "bhalke",
    "उद्या", "udya",                       # Marathi
    "આવતીકાલે", "આવતી કાલે", "કાલે", "kale",  # Gujarati
    "আগামীকাল", "কাল", "kalke", "agamikal",  # Bengali
    "நாளை", "naalai", "nalai",            # Tamil
    "రేపు", "repu",                        # Telugu
    "ನಾಳೆ", "naale", "nale",               # Kannada
    "നാളെ", "naale",                       # Malayalam
)
TODAY = ("today", "aaj", "aj", "आज", "ਅੱਜ", "ਅਜ", "आज", "આજે", "আজ", "இன்று", "ఈరోజు", "ఈ రోజు", "ಇಂದು", "ഇന്ന്")
NEXT_WEEK = ("next week", "agle hafte", "अगले हफ्ते", "अगले हफ़्ते", "ਅਗਲੇ ਹਫ਼ਤੇ", "ਅਗਲੇ ਹਫਤੇ")

# Hindi/Marathi (Devanagari) and Punjabi (Gurmukhi) weekday names, Monday first.
NATIVE_WEEKDAYS = (
    ("सोमवार", "ਸੋਮਵਾਰ", "somvar"),
    ("मंगलवार", "मंगळवार", "ਮੰਗਲਵਾਰ", "mangalvar"),
    ("बुधवार", "ਬੁੱਧਵਾਰ", "ਬੁਧਵਾਰ", "budhvar"),
    ("गुरुवार", "ਵੀਰਵਾਰ", "veervar", "guruvar"),
    ("शुक्रवार", "ਸ਼ੁੱਕਰਵਾਰ", "ਸ਼ੁਕਰਵਾਰ", "shukravar"),
    ("शनिवार", "ਸ਼ਨੀਵਾਰ", "ਸ਼ਨਿੱਚਰਵਾਰ", "shanivar"),
    ("रविवार", "ਐਤਵਾਰ", "aitvar", "ravivar"),
)

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ten": 10, "a": 1}


def today_ist() -> date:
    return to_ist(utcnow()).date()


def _has(text: str, words: tuple[str, ...]) -> bool:
    for w in words:
        if w.isascii():
            if re.search(rf"\b{re.escape(w)}\b", text):
                return True
        elif w in text:
            return True
    return False


def resolve_day(text: str | None, today: date | None = None) -> date | None:
    """The date the words refer to, or None if they don't name a day."""
    if not text or not text.strip():
        return None
    today = today or today_ist()
    raw = text.strip()
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        pass
    t = raw.lower()

    if _has(t, DAY_AFTER_TOMORROW):
        return today + timedelta(days=2)
    if _has(t, TOMORROW):
        return today + timedelta(days=1)
    if _has(t, TODAY):
        return today

    m = re.search(r"\bin\s+(\d+|one|two|three|four|five|six|seven|ten|a)\s+(day|days|week|weeks)\b", t) or \
        re.search(r"\b(\d+|one|two|three|four|five|six|seven|ten|a)\s+(day|days|week|weeks)\s+(from now|later)\b", t)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else _NUMBER_WORDS[m.group(1)]
        return today + timedelta(days=n * (7 if m.group(2).startswith("week") else 1))

    for i, name in enumerate(WEEKDAYS):
        native = NATIVE_WEEKDAYS[i]
        if re.search(rf"\b{name}\b|\b{name[:3]}\b", t) or any(w in t for w in native):
            if _has(t, NEXT_WEEK) or re.search(r"\bnext week\b", t):  # "Friday next week"
                return today + timedelta(days=7 - today.weekday() + i)
            # The coming one ("Friday", "next Friday"); a weekday named on that same day means a week from today.
            return today + timedelta(days=(i - today.weekday()) % 7 or 7)

    if _has(t, NEXT_WEEK):
        return today + timedelta(days=7 - today.weekday())  # next Monday
    if re.search(r"\bweekend\b", t):
        return today if today.weekday() >= 5 else today + timedelta(days=5 - today.weekday())

    # "5 November", "November 5", "5th Nov", "5/11"
    for i, month in enumerate(MONTHS, start=1):
        pat = rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{month[:3]}\w*|{month[:3]}\w*\s+(\d{{1,2}})(?:st|nd|rd|th)?"
        m = re.search(pat, t)
        if m:
            day = int(m.group(1) or m.group(2))
            return _next_occurrence(today, i, day)
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})", t)
    if m:
        return _next_occurrence(today, int(m.group(2)), int(m.group(1)))
    m = re.fullmatch(r"(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)", t)
    if m:  # "the 5th": this month, or next month if it has passed
        day = int(m.group(1))
        for months_ahead in (0, 1):
            y, mo = today.year + (today.month + months_ahead - 1) // 12, (today.month + months_ahead - 1) % 12 + 1
            try:
                d = date(y, mo, day)
            except ValueError:
                continue
            if d >= today:
                return d
    return None


def _next_occurrence(today: date, month: int, day: int) -> date | None:
    for year in (today.year, today.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        if d >= today:
            return d
    return None


def relative_label(d: date, today: date | None = None) -> str | None:
    today = today or today_ist()
    return {0: "today", 1: "tomorrow", 2: "day after tomorrow"}.get((d - today).days)


def calendar_lines(days: int = 14, today: date | None = None) -> str:
    """Upcoming dates for the system prompt, so the model never has to do date arithmetic."""
    today = today or today_ist()
    out = []
    for i in range(days):
        d = today + timedelta(days=i)
        label = relative_label(d, today)
        if label is None:
            label = f"the coming {d:%A}" if i < 7 else f"{d:%A} next week"
        out.append(f"- {d.isoformat()} {d:%A %d %B} ({label})")
    return "\n".join(out)


def ist_midnight_utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=IST).astimezone(timezone.utc)
