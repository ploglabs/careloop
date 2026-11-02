"""Text-mode conversation driver.

Used by the browser text call, the synthetic-patient simulator and tests. Voice calls use
the Pipecat pipeline in careloop.agent.voice, which shares the same session, prompt and tools.
"""

import json
from typing import Any, Protocol

from loguru import logger
from openai import AsyncOpenAI, OpenAI

from careloop.agent.prompts import system_prompt
from careloop.agent.session import CallSession
from careloop.agent.tools import openai_tools
from careloop.config import settings
from careloop.models import Urgency

MAX_TOOL_ROUNDS = 6


class Brain(Protocol):
    async def reply(self, s: CallSession, user_text: str, notes: list[str]) -> list[str]: ...


class LLMBrain:
    """Drives the call with any OpenAI-compatible chat model that supports tool calls."""

    def __init__(self, s: CallSession, opening: str):
        self.client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt(s)},
            {"role": "assistant", "content": opening},
        ]

    async def reply(self, s: CallSession, user_text: str, notes: list[str]) -> list[str]:
        for note in notes:
            self.messages.append({"role": "system", "content": note})
        self.messages.append({"role": "user", "content": user_text})
        out: list[str] = []
        for _ in range(MAX_TOOL_ROUNDS):
            resp = await self.client.chat.completions.create(
                model=settings.llm_model, messages=self.messages, tools=openai_tools(), temperature=0.3,
                extra_body=settings.llm_extra_body,
            )
            msg = resp.choices[0].message
            if msg.content and msg.content.strip():
                out.append(msg.content.strip())
            if not msg.tool_calls:
                self.messages.append({"role": "assistant", "content": msg.content or ""})
                break
            self.messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = s.dispatch(tc.function.name, args)
                logger.debug(f"tool {tc.function.name}({args}) -> {result}")
                self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)})
                if tc.function.name == "end_call" and result.get("ok"):
                    if result.get("closing_line"):
                        out.append(result["closing_line"])
                    return out
                if result.get("say_exactly"):
                    out.append(result["say_exactly"])
        return out


def review_call(s: CallSession) -> dict[str, Any] | None:
    """End-of-call LLM pass: clinician summary plus a second opinion on urgency (raise-only)."""
    if not (settings.llm_enabled and settings.llm_review_enabled):
        return None
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    transcript = "\n".join(f"{t['role']}: {t['text']}" for t in s.transcript)
    prompt = f"""You review a post-discharge follow-up call for a clinician.
Context: {json.dumps(s.patient_context())}
Pack: {s.pack.name}
Structured answers: {json.dumps(s.answers)}
Current urgency from rules: {s.level.name}
Transcript (may be in an Indian language):
{transcript}

Return JSON with keys:
- "summary": 2-4 sentence clinical summary in English for the doctor. Facts only, no advice.
- "level": one of ROUTINE, REVIEW, URGENT, EMERGENCY. The level you think this call needs.
- "reason": short reason if level is above ROUTINE, else "".
- "evidence": the patient's exact words supporting the level, else "".
Be conservative: if anything suggests a dangerous symptom, choose the higher level."""
    resp = client.chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
        extra_body=settings.llm_extra_body,
    )
    data = json.loads(resp.choices[0].message.content or "{}")
    if data.get("level", "ROUTINE").upper() not in Urgency.__members__:
        data["level"] = "ROUTINE"
    return data
