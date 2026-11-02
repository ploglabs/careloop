"""A deterministic, rule-based brain for running calls without an LLM key.

It asks the pack questions in English, parses short answers with keyword rules and drives
the same session tools as the LLM. Good enough for local development, tests and a fallback
demo; the real multilingual experience needs the LLM brain.
"""

import re
from typing import Any

from careloop.agent.session import CallSession
from careloop.models import Urgency

YES = {"yes", "yeah", "yep", "ok", "okay", "sure", "haan", "han", "ha", "ji", "हाँ", "हां", "जी", "ಹೌದು", "ஆமா",
       "ஆம்", "అవును", "ഉവ്വ്", "হ্যাঁ", "હા", "ਹਾਂ", "हो", "little", "slight", "bit"}
NO = {"no", "nope", "nahi", "nahin", "not", "never", "नहीं", "ना", "ಇಲ್ಲ", "இல்லை", "లేదు", "ഇല്ല", "না", "ના", "ਨਹੀਂ", "नाही", "none"}

NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten".split())}

ENUM_SYNONYMS: dict[str, list[str]] = {
    "worse": ["worse", "more", "increased", "badh", "zyada", "spreading"],
    "better": ["better", "improved", "improving", "less", "reduced", "kam", "good", "fine"],
    "same": ["same", "no change", "unchanged", "waisa", "similar"],
    "none": ["none", "not taking", "stopped", "not using", "no"],
    "some": ["some", "sometimes", "missed", "few", "kabhi", "partly", "forgot"],
    "all": ["all", "every", "regularly", "yes", "sab", "daily"],
    "opened": ["opened", "open"],
    "bleeding": ["bleeding", "blood"],
    "discharge": ["discharge", "pus", "oozing", "fluid"],
    "swollen": ["swollen", "swelling"],
    "red": ["red", "redness"],
    "clean_dry": ["clean", "dry", "fine", "good", "healing"],
    "bedbound": ["bed", "can't walk", "cannot walk", "bedbound"],
    "limited": ["little", "limited", "slowly", "some"],
    "normal": ["normal", "walking", "fine", "yes"],
    "poor": ["poor", "not much", "not really", "no"],
    "partial": ["partly", "partial", "somewhat", "some"],
    "good": ["good", "well", "yes", "strictly"],
}

ORDINALS = {"first": 0, "1": 0, "one": 0, "second": 1, "2": 1, "two": 1, "third": 2, "3": 2, "three": 2}


def _words(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


def parse_bool(text: str) -> bool | None:
    words = set(_words(text))
    if words & NO:
        return False
    if words & YES:
        return True
    return None


def parse_number(text: str) -> float | None:
    if m := re.search(r"\d+(?:\.\d+)?", text):
        return float(m.group())
    for w in _words(text):
        if w in NUMBER_WORDS:
            return float(NUMBER_WORDS[w])
    return None


def parse_enum(text: str, options: tuple[str, ...]) -> str | None:
    low = text.lower()
    for option, words in ENUM_SYNONYMS.items():
        if option in options and any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", low) for w in words):
            return option
    return None


class OfflineBrain:
    def __init__(self, s: CallSession, opening: str):
        self.phase = "consent"
        self.q_index = 0
        self.offered: list[dict[str, Any]] = []

    def _ask_current(self, s: CallSession) -> str:
        return s.pack.questions[self.q_index].ask

    async def reply(self, s: CallSession, user_text: str, notes: list[str]) -> list[str]:
        if s.level == Urgency.EMERGENCY:
            result = s.tool_end_call("emergency")
            return [result["closing_line"]] if result.get("closing_line") else []

        if self.phase == "consent":
            granted = parse_bool(user_text)
            if granted is None:
                return ["Sorry, may I continue with a few quick questions? Please say yes or no."]
            s.tool_record_consent(granted)
            if not granted:
                return [s.tool_end_call("consent_declined")["closing_line"]]
            self.phase = "questions"
            return ["Thank you. " + self._ask_current(s)]

        if self.phase == "questions":
            q = s.pack.questions[self.q_index]
            value: Any
            if q.type == "bool":
                value = parse_bool(user_text)
            elif q.type in ("scale", "number"):
                value = parse_number(user_text)
            elif q.type == "enum":
                value = parse_enum(user_text, q.options)
            else:
                value = user_text
            if value is None:
                status = "unclear" if getattr(self, "_retried", False) else None
                if status is None:
                    self._retried = True
                    return ["Sorry, I didn't catch that. " + q.ask]
                result = s.tool_record_answer(q.key, None, status="unclear", evidence_quote=user_text)
            else:
                result = s.tool_record_answer(q.key, value, evidence_quote=user_text)
            self._retried = False
            out = []
            if not result.get("ok"):
                return ["Sorry, could you say that again? " + q.ask]
            if result.get("say_exactly"):
                out.append(result["say_exactly"])
            self.q_index += 1
            if self.q_index < len(s.pack.questions):
                out.append(self._ask_current(s))
                return out
            if s.answers.get("wants_appointment") or s.level >= Urgency.URGENT:
                slots = s.tool_check_slots().get("slots", [])
                if slots:
                    self.offered = slots
                    self.phase = "booking"
                    options = "; ".join(f"option {i + 1}, {sl['when']}" for i, sl in enumerate(slots))
                    out.append(f"I can book {options}. Which one works for you?")
                    return out
            self.phase = "anything_else"
            out.append("Is there anything else you would like to tell your doctor?")
            return out

        if self.phase == "booking":
            choice = next((ORDINALS[w] for w in _words(user_text) if w in ORDINALS), None)
            if choice is None or choice >= len(self.offered):
                if parse_bool(user_text) is False:
                    self.phase = "anything_else"
                    return ["No problem. Is there anything else you would like to tell your doctor?"]
                return ["Please say option one, two or three."]
            booked = s.tool_book_slot(self.offered[choice]["slot_id"])
            self.phase = "anything_else"
            if booked.get("ok"):
                return [f"Booked for {booked['confirmed']}. Is there anything else you would like to tell your doctor?"]
            return ["That slot was just taken, sorry. The clinic will call you to fix a time. Anything else?"]

        # anything_else
        result = s.tool_end_call("completed")
        if not result.get("ok"):
            for key in s.unanswered:
                s.tool_record_answer(key, None, status="declined", evidence_quote="")
            result = s.tool_end_call("completed")
        return [result["closing_line"]]
