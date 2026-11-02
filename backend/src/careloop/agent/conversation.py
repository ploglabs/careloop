"""Text conversation: session + brain + safety interjections, one patient turn at a time."""

import asyncio

from careloop.agent.brain import LLMBrain, review_call
from careloop.agent.offline import OfflineBrain
from careloop.agent.session import CallSession
from careloop.config import settings


class TextConversation:
    def __init__(self, call_id: int, *, offline: bool | None = None):
        self.session = CallSession(call_id)
        self.offline = (not settings.llm_enabled) if offline is None else offline
        self.brain: LLMBrain | OfflineBrain | None = None

    def start(self) -> list[str]:
        opening = self.session.start(mode="text")
        self.brain = OfflineBrain(self.session, opening) if self.offline else LLMBrain(self.session, opening)
        return [opening]

    @property
    def ended(self) -> bool:
        return self.session.ended

    async def user(self, text: str) -> list[str]:
        assert self.brain is not None, "call start() first"
        turn = self.session.on_user_text(text)
        replies = await self.brain.reply(self.session, text, turn.llm_notes)
        for r in replies:
            if r not in turn.speak_now:
                self.session.add_assistant_text(r)
        # Safety lines come first and verbatim; drop exact duplicates from the brain.
        return turn.speak_now + [r for r in replies if r not in turn.speak_now]

    async def finish(self):
        review = None if self.offline else review_call
        return await asyncio.to_thread(self.session.finalize, review)
