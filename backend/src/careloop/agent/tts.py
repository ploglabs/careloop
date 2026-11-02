"""Gnani streaming TTS that speaks every sentence of a reply.

Pipecat sends each sentence of an LLM reply to the TTS as its own request, all under the
reply's one audio context. The stock `GnaniTTSService` closes that context when the *first*
request completes, so audio for the second sentence lands behind the close marker and is
dropped: the patient hears "Got it, five out of ten." and never the next question.

This subclass keeps the context open until its reply has ended and its last request has
completed. Requests go out one at a time, since the socket's audio carries no request id
to tell two overlapping streams apart.
"""

import asyncio
from collections import deque
from collections.abc import AsyncGenerator

from loguru import logger
from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame, TTSStoppedFrame
from pipecat_gnani import GnaniTTSService
from pipecat_gnani.tts import _resolved_tts_sample_rate

# Longest wait for the previous sentence's audio before sending the next one anyway.
REQUEST_TIMEOUT_SECONDS = 15.0


class SentenceSafeGnaniTTS(GnaniTTSService):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._in_flight: deque[str] = deque()  # context id of each sent request, oldest first
        self._idle = asyncio.Event()
        self._idle.set()

    def _reset_requests(self) -> None:
        self._in_flight.clear()
        self._idle.set()

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        try:
            await asyncio.wait_for(self._idle.wait(), REQUEST_TIMEOUT_SECONDS)
        except TimeoutError:
            logger.warning("Gnani TTS: previous sentence never completed, sending the next one")
            self._reset_requests()
        self._idle.clear()
        self._in_flight.append(context_id)
        async for frame in super().run_tts(text, context_id):
            if isinstance(frame, ErrorFrame):
                self._reset_requests()
            yield frame

    async def _receive_messages(self):
        try:
            await super()._receive_messages()
        finally:
            # The socket closed (interruption reconnect, network drop): nothing more will complete.
            self._reset_requests()

    async def _handle_audio_chunk(self, audio_bytes: bytes):
        audio_bytes = self._pcm_processor.process(audio_bytes)
        if not audio_bytes:
            return
        if self._awaiting_first_chunk:
            self._awaiting_first_chunk = False
            await self.stop_ttfb_metrics()
        context_id = self._in_flight[0] if self._in_flight else self.get_active_audio_context_id()
        await self.append_to_audio_context(
            context_id,
            TTSAudioRawFrame(
                audio=audio_bytes, sample_rate=_resolved_tts_sample_rate(self), num_channels=1, context_id=context_id,
            ),
        )

    async def _finish_audio_context(self):
        """One request completed: close its context only if its reply is over and nothing else is pending."""
        context_id = self._in_flight.popleft() if self._in_flight else None
        self._idle.set()
        if context_id and context_id not in self._in_flight and context_id != self._turn_context_id:
            await self._close_context(context_id)

    async def flush_audio(self, context_id: str | None = None):
        """The reply ended: close its context now, or once its last request completes."""
        if context_id and context_id not in self._in_flight:
            await self._close_context(context_id)

    async def _close_context(self, context_id: str) -> None:
        if self.audio_context_available(context_id):
            await self.append_to_audio_context(context_id, TTSStoppedFrame(context_id=context_id))
            await self.remove_audio_context(context_id)
