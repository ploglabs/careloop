"""Condition packs: per-specialty question scripts and red-flag rules, stored as YAML."""

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import yaml

PACK_DIR = Path(__file__).parent


class AnswerError(ValueError):
    pass


@dataclass(frozen=True)
class Question:
    key: str
    type: str  # enum | scale | number | bool | text
    ask: str
    options: tuple[str, ...] = ()
    min: float | None = None
    max: float | None = None
    unit: str | None = None
    medication: bool = False
    score: dict[str, Any] = field(default_factory=dict)

    def normalise(self, value: Any) -> Any:
        """Coerce an LLM-supplied value to this question's type, or raise AnswerError."""
        if self.type == "enum":
            v = str(value).strip().lower().replace(" ", "_")
            if v not in self.options:
                raise AnswerError(f"{self.key} must be one of {list(self.options)}, got {value!r}")
            return v
        if self.type in ("scale", "number"):
            try:
                v = float(value)
            except (TypeError, ValueError):
                raise AnswerError(f"{self.key} must be a number, got {value!r}") from None
            if (self.min is not None and v < self.min) or (self.max is not None and v > self.max):
                raise AnswerError(f"{self.key} must be between {self.min} and {self.max}, got {v}")
            return int(v) if v.is_integer() else v
        if self.type == "bool":
            if isinstance(value, bool):
                return value
            v = str(value).strip().lower()
            if v in {"true", "yes", "y", "1"}:
                return True
            if v in {"false", "no", "n", "0"}:
                return False
            raise AnswerError(f"{self.key} must be true or false, got {value!r}")
        return str(value).strip()

    def item_score(self, value: Any) -> float | None:
        """0 (bad) to 1 (good) contribution to the recovery score, or None if unscored."""
        if not self.score or value is None:
            return None
        if self.type == "enum":
            return self.score.get(value)
        if self.type == "bool":
            return 0.0 if value == self.score.get("bad_when", True) else 1.0
        if self.type == "scale" and self.max:
            frac = (float(value) - (self.min or 0)) / (self.max - (self.min or 0))
            return 1 - frac if self.score.get("invert") else frac
        return None


@dataclass(frozen=True)
class RedFlagRule:
    id: str
    when: str
    level: str
    reason: str


@dataclass(frozen=True)
class Pack:
    id: str
    name: str
    specialty: str
    procedure_types: tuple[str, ...]
    offset_days: tuple[int, ...]
    context: str
    questions: tuple[Question, ...]
    red_flags: tuple[RedFlagRule, ...]

    def question(self, key: str) -> Question:
        for q in self.questions:
            if q.key == key:
                return q
        raise AnswerError(f"Unknown question key {key!r}. Valid keys: {[q.key for q in self.questions]}")

    @property
    def keys(self) -> list[str]:
        return [q.key for q in self.questions]

    def recovery_score(self, answers: dict[str, Any]) -> float | None:
        scores = [s for q in self.questions if (s := q.item_score(answers.get(q.key))) is not None]
        return round(100 * sum(scores) / len(scores), 1) if scores else None


def _load(path: Path) -> Pack:
    raw = yaml.safe_load(path.read_text())
    questions = tuple(
        Question(
            key=q["key"],
            type=q["type"],
            ask=q["ask"],
            options=tuple(q.get("options", ())),
            min=q.get("min"),
            max=q.get("max"),
            unit=q.get("unit"),
            medication=q.get("medication", False),
            score=q.get("score", {}),
        )
        for q in raw["questions"]
    )
    rules = tuple(RedFlagRule(**r) for r in raw.get("red_flags", ()))
    return Pack(
        id=raw["id"],
        name=raw["name"],
        specialty=raw["specialty"],
        procedure_types=tuple(raw.get("procedure_types", ())),
        offset_days=tuple(raw.get("offset_days", (7,))),
        context=raw.get("context", "").strip(),
        questions=questions,
        red_flags=rules,
    )


@cache
def all_packs() -> dict[str, Pack]:
    packs = {}
    for path in sorted(PACK_DIR.glob("*.yaml")):
        pack = _load(path)
        packs[pack.id] = pack
    return packs


def get_pack(pack_id: str) -> Pack:
    try:
        return all_packs()[pack_id]
    except KeyError:
        raise KeyError(f"No condition pack {pack_id!r}") from None


def pack_for_procedure(procedure_type: str) -> Pack | None:
    for pack in all_packs().values():
        if procedure_type in pack.procedure_types:
            return pack
    return None
