from pathlib import Path

import pytest
import yaml

from careloop.models import Urgency
from careloop.packs import all_packs, get_pack
from careloop.triage import evaluate_pack_rules, max_level, scan_utterance
from careloop.triage.rules import RuleError, compile_rule, evaluate

CASES = yaml.safe_load((Path(__file__).parents[1] / "eval" / "triage_cases.yaml").read_text())


@pytest.mark.parametrize("case", CASES, ids=[f"{c['lang']}:{c['text'][:30]}" for c in CASES])
def test_lexicon_case(case):
    level = max_level(scan_utterance(case["text"]))
    assert level == Urgency.parse(case["expect"]), scan_utterance(case["text"])


def test_no_emergency_false_negatives():
    """The headline guarantee: every labelled EMERGENCY utterance is caught as EMERGENCY."""
    misses = [c["text"] for c in CASES if c["expect"] == "EMERGENCY"
              and max_level(scan_utterance(c["text"])) < Urgency.EMERGENCY]
    assert misses == []


def test_negated_emergency_is_downgraded_not_dropped():
    hits = scan_utterance("I don't have chest pain")
    assert hits and hits[0].negated and hits[0].level == Urgency.REVIEW


def test_hit_records_evidence():
    hit = scan_utterance("Doctor, I have chest pain since morning")[0]
    assert hit.rule_id == "lex_chest_pain"
    assert "chest pain" in hit.evidence


def test_rule_expressions():
    assert evaluate("swelling and fever", {"swelling": True, "fever": True})
    assert not evaluate("swelling and fever", {"swelling": True})
    assert not evaluate("pain_score >= 8", {})
    assert evaluate("wound_appearance in ['bleeding', 'opened']", {"wound_appearance": "opened"})
    assert not evaluate("not fever", {})
    with pytest.raises(RuleError):
        compile_rule("__import__('os')")


def test_all_pack_rules_compile_and_reference_real_keys():
    for pack in all_packs().values():
        for rule in pack.red_flags:
            compile_rule(rule.when)
            assert any(k in rule.when for k in pack.keys), rule.id


def test_derma_rules():
    pack = get_pack("derma_week1")
    hits = evaluate_pack_rules(pack, {"swelling": True, "fever": True, "itching_score": 9})
    assert max_level(hits) == Urgency.URGENT
    assert {h.rule_id for h in hits} >= {"derma_fever_swelling", "derma_severe_itch"}


def test_surgery_rules():
    pack = get_pack("post_surgery")
    assert max_level(evaluate_pack_rules(pack, {"pain_score": 3, "wound_appearance": "clean_dry"})) == Urgency.ROUTINE
    assert max_level(evaluate_pack_rules(pack, {"wound_appearance": "opened"})) == Urgency.URGENT


def test_recovery_score():
    pack = get_pack("derma_week1")
    good = pack.recovery_score({"redness_trend": "better", "itching_score": 0, "swelling": False, "fever": False})
    bad = pack.recovery_score({"redness_trend": "worse", "itching_score": 9, "swelling": True, "fever": True})
    assert good == 100.0 and bad < 20
