"""Triage: three layers that can only ever raise urgency.

1. Lexicon: red-flag phrases on every final transcript, during the call.
2. Pack rules: deterministic expressions over the structured answers.
3. LLM review: end-of-call second opinion (see careloop.agent.review). Raise-only.

Every hit records which rule fired and the patient's words that triggered it.
"""

import re
from dataclasses import dataclass
from typing import Any

from careloop.models import Urgency
from careloop.packs import Pack
from careloop.triage.lexicon import CLAUSE_BREAKS, NEGATIONS, RED_FLAGS
from careloop.triage.rules import evaluate

NEGATION_WINDOW_TOKENS = 4


@dataclass(frozen=True)
class Hit:
    level: Urgency
    source: str  # lexicon | rule | llm_review | adherence | routing
    rule_id: str
    reason: str
    evidence: str = ""
    negated: bool = False


def _is_latin(term: str) -> bool:
    return all(ord(c) < 0x250 for c in term)


def _normalise(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text).strip().lower()


_BREAK_RE = re.compile(
    r"[.,;!?।|\n]+|\s(?:" + "|".join(re.escape(b) for b in CLAUSE_BREAKS) + r")\s",
    flags=re.IGNORECASE,
)


def _clauses(text: str) -> list[str]:
    padded = f" {text} "
    return [c.strip() for c in _BREAK_RE.split(padded) if c and c.strip()]


_ALL_NEGATIONS = tuple({cue for cues in NEGATIONS.values() for cue in cues})


def _is_negation(token: str) -> bool:
    token = token.strip("'\"")
    for cue in _ALL_NEGATIONS:
        if token == cue:
            return True
        # Indic negation is often a verb suffix (வரவில்லை, ಬಂದಿಲ್ಲ, రాలేదు).
        if not _is_latin(cue) and len(cue) >= 3 and token.endswith(cue):
            return True
    return False


def _find(term: str, clause: str) -> list[tuple[int, int]]:
    if _is_latin(term):
        pattern = r"(?<![\w'])" + re.escape(term) + r"(?![\w'])"
        return [m.span() for m in re.finditer(pattern, clause)]
    spans, start = [], 0
    while (i := clause.find(term, start)) != -1:
        spans.append((i, i + len(term)))
        start = i + 1
    return spans


def _negated(clause: str, span: tuple[int, int]) -> bool:
    tokens = [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", clause)]
    inside = [i for i, (s, e, _) in enumerate(tokens) if s < span[1] and e > span[0]]
    if not inside:
        return False
    lo, hi = inside[0], inside[-1]
    for i in range(max(0, lo - NEGATION_WINDOW_TOKENS), min(len(tokens), hi + NEGATION_WINDOW_TOKENS + 1)):
        if lo <= i <= hi:
            continue
        if _is_negation(tokens[i][2]):
            return True
    return False


def scan_utterance(text: str) -> list[Hit]:
    """Scan one patient utterance for red flags in any supported language.

    All languages are scanned on every call, which tolerates language-ID mistakes and
    code-mixing. A negated emergency phrase is not dropped: it becomes a REVIEW hit,
    so a misheard negation can never silently hide an emergency.
    """
    norm = _normalise(text)
    if not norm:
        return []
    best: dict[str, Hit] = {}
    for clause in _clauses(norm):
        for flag in RED_FLAGS:
            for terms in flag.terms.values():
                for term in terms:
                    for span in _find(term.lower(), clause):
                        if _negated(clause, span):
                            if flag.level < Urgency.EMERGENCY:
                                continue
                            hit = Hit(
                                Urgency.REVIEW, "lexicon", flag.id,
                                f"{flag.reason} mentioned with a negation; verify", clause, negated=True,
                            )
                        else:
                            hit = Hit(flag.level, "lexicon", flag.id, flag.reason, clause)
                        prev = best.get(flag.id)
                        if prev is None or hit.level > prev.level:
                            best[flag.id] = hit
    return sorted(best.values(), key=lambda h: -h.level)


def evaluate_pack_rules(pack: Pack, answers: dict[str, Any], evidence: dict[str, str] | None = None) -> list[Hit]:
    evidence = evidence or {}
    hits = []
    for rule in pack.red_flags:
        if evaluate(rule.when, answers):
            quotes = [evidence[k] for k in answers if k in rule.when and evidence.get(k)]
            hits.append(Hit(Urgency.parse(rule.level), "rule", rule.id, rule.reason, " | ".join(quotes)))
    return sorted(hits, key=lambda h: -h.level)


def max_level(hits: list[Hit], floor: Urgency = Urgency.ROUTINE) -> Urgency:
    return max([floor, *(h.level for h in hits)])
