import dataclasses
from datetime import date, timedelta

import pytest

from careloop import dates
from careloop.agent import session as session_mod
from careloop.agent.prompts import system_prompt
from careloop.agent.session import CallSession
from careloop.agent.simulate import open_call
from careloop.languages import line, pick_voice
from careloop.models import to_ist, utcnow

from tests.test_calls import _plan

MONDAY = date(2026, 11, 2)


@pytest.mark.parametrize("text,expected", [
    ("tomorrow", MONDAY + timedelta(days=1)),
    ("can I come tmrw?", MONDAY + timedelta(days=1)),
    ("day after tomorrow", MONDAY + timedelta(days=2)),
    ("kal", MONDAY + timedelta(days=1)),
    ("ਕੱਲ੍ਹ ਦਾ ਟਾਈਮ ਦੇ ਦਿਓ", MONDAY + timedelta(days=1)),
    ("ਪਰਸੋਂ", MONDAY + timedelta(days=2)),
    ("परसों सुबह", MONDAY + timedelta(days=2)),
    ("நாளை", MONDAY + timedelta(days=1)),
    ("ఎల్లుండి", MONDAY + timedelta(days=2)),
    ("in 3 days", MONDAY + timedelta(days=3)),
    ("two weeks from now", MONDAY + timedelta(days=14)),
    ("friday", date(2026, 11, 6)),
    ("next Friday", date(2026, 11, 6)),
    ("friday next week", date(2026, 11, 13)),
    ("अगले हफ्ते शुक्रवार", date(2026, 11, 13)),
    ("monday", date(2026, 11, 9)),  # said on a Monday: next week's
    ("ਸ਼ੁੱਕਰਵਾਰ", date(2026, 11, 6)),
    ("next week", date(2026, 11, 9)),
    ("this weekend", date(2026, 11, 7)),
    ("5 November", date(2026, 11, 5)),
    ("nov 10th", date(2026, 11, 10)),
    ("1 January", date(2027, 1, 1)),
    ("2026-11-07", date(2026, 11, 7)),
    ("whenever suits", None),
    ("", None),
])
def test_resolve_day(text, expected):
    assert dates.resolve_day(text, MONDAY) == expected


def test_calendar_labels_relative_days():
    cal = dates.calendar_lines(3, MONDAY).splitlines()
    assert cal == [
        "- 2026-11-02 Monday 02 November (today)",
        "- 2026-11-03 Tuesday 03 November (tomorrow)",
        "- 2026-11-04 Wednesday 04 November (day after tomorrow)",
    ]


def _session(pack="post_surgery") -> CallSession:
    s = CallSession(open_call(_plan(pack)))
    s.start("text")
    s.tool_record_consent(True)
    return s


def test_check_slots_tomorrow_returns_only_tomorrow():
    s = _session()
    tomorrow = dates.today_ist() + timedelta(days=1)
    for words in ("tomorrow", tomorrow.isoformat()):
        result = s.tool_check_slots(preferred_date=words)
        assert result["slots"], result
        assert "requested day" in result["date_note"]
        assert all(sl["when"].startswith("tomorrow, ") for sl in result["slots"])


def test_check_slots_past_or_unknown_date_falls_back_to_earliest():
    s = _session()
    earliest = s.tool_check_slots()["slots"]
    past = s.tool_check_slots(preferred_date="2024-11-03")
    assert past["slots"] == earliest and "past" in past["date_note"]
    vague = s.tool_check_slots(preferred_date="whenever")
    assert vague["slots"] == earliest and "Could not work out" in vague["date_note"]


def test_prompt_has_calendar_and_gender():
    s = _session()
    prompt = system_prompt(s)
    tomorrow = dates.today_ist() + timedelta(days=1)
    assert f"{tomorrow.isoformat()} {tomorrow:%A %d %B} (tomorrow)" in prompt
    assert f"TODAY (IST): {to_ist(utcnow()):%A %d %B %Y}" in prompt
    assert f"YOUR VOICE is {s.agent_gender}" in prompt


def test_pick_voice_by_gender():
    assert pick_voice("pa-IN", gender="female") == ("Mehuli", "female")
    assert pick_voice("pa-IN", gender="male") == ("Zayan", "male")
    assert pick_voice("en-IN") == ("Kaveri", "female")
    # No male v2.5 voice for Tamil: falls back, and says so.
    assert pick_voice("ta-IN", gender="male") == ("Asmita", "female")
    assert pick_voice("hi-IN", codemix=True) == ("Poorvi", "female")
    assert pick_voice("ta-IN", gender="male", model="timbre-v3.0") == ("Avinash", "male")


def test_match_voice_follows_patient_gender(monkeypatch):
    monkeypatch.setattr(session_mod, "settings", dataclasses.replace(session_mod.settings, agent_voice="match"))
    s = _session()
    expected = s.patient_gender or "female"
    voice, gender = pick_voice(s.language, s.codemix, expected)
    assert (s.voice, s.agent_gender) == (voice, gender)


def test_female_patient_hindi_emergency_line():
    assert "बता रही हैं" in line("hi-IN", "emergency", patient_gender="female")
    assert "बता रहे हैं" in line("hi-IN", "emergency", patient_gender="male")
    assert line("en-IN", "emergency", patient_gender="female") == line("en-IN", "emergency")


def test_check_slots_beyond_schedule_offers_nearest():
    s = _session()
    far = (dates.today_ist() + timedelta(days=300)).isoformat()
    result = s.tool_check_slots(preferred_date=far)
    assert result["slots"] and "No free slots" in result["date_note"]
