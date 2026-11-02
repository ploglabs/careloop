"""Voice call pipeline: browser WebRTC ↔ Gnani Prisma STT ↔ LLM (tools) ↔ Gnani Timbre TTS.

    transport.in → Prisma STT → TriageTap → user aggregator → LLM → AssistantTap → Timbre TTS → transport.out

TriageTap runs the red-flag lexicon on each final transcript. On an URGENT/EMERGENCY hit it
speaks the scripted safety line straight to TTS (no LLM in the loop) and adds a SAFETY note
to the LLM context before the patient's words reach it.
"""

import asyncio
import os
from typing import Any

from loguru import logger

from careloop.agent.brain import asks_patient, review_call
from careloop.agent.prompts import system_prompt
from careloop.agent.session import CallSession
from careloop.agent.tools import TOOL_SPECS, pipecat_tools
from careloop.config import settings
from careloop.languages import line, voice_for


def _stt_settings(s: CallSession):
    from pipecat_gnani import GnaniSTTService

    keywords = [s.doctor.name, s.clinic.name, *s.encounter.medications]
    if s.codemix or settings.stt_model == "prisma-v3.0":
        # Code-mixed callers: multilingual model with a hint, since bare indic-auto can
        # mis-detect when an utterance ends in silence.
        return GnaniSTTService.Settings(
            model="prisma-v3.0",
            language="indic-auto",
            language_candidates=[s.language, "en-IN"] if s.language != "en-IN" else ["en-IN", "hi-IN"],
            keywords=keywords,
        )
    return GnaniSTTService.Settings(language=s.language)


def _tts_settings(s: CallSession, language: str | None = None):
    from pipecat_gnani import GnaniTTSService

    language = language or s.language
    return GnaniTTSService.Settings(
        model=settings.tts_model,
        voice=voice_for(language, s.codemix),
        language=language,
        # Slightly slower for older patients.
        speed=0.92 if (s.patient.age or 0) >= 60 else 1.0,
    )


async def run_voice_call(call_id: int, webrtc_connection) -> None:
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADParams
    from pipecat.frames.frames import (
        EndWorkerFrame,
        Frame,
        LLMFullResponseEndFrame,
        LLMFullResponseStartFrame,
        LLMMessagesAppendFrame,
        LLMTextFrame,
        STTUpdateSettingsFrame,
        TranscriptionFrame,
        TTSSpeakFrame,
        TTSUpdateSettingsFrame,
    )
    from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.worker import PipelineWorker
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import (
        LLMContextAggregatorPair,
        LLMUserAggregatorParams,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
    from pipecat.services.llm_service import FunctionCallParams
    from pipecat.services.openai.llm import OpenAILLMService
    from pipecat.transports.base_transport import TransportParams
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
    from pipecat.workers.runner import WorkerRunner
    from pipecat_gnani import GnaniSTTService

    from pipecat.frames.frames import FunctionCallResultProperties

    from careloop.agent.tts import SentenceSafeGnaniTTS

    s = CallSession(call_id)
    older = (s.patient.age or 0) >= 60
    vad = SileroVADAnalyzer(params=VADParams(stop_secs=1.0 if older else 0.7))

    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )
    stt = GnaniSTTService(api_key=settings.gnani_api_key, settings=_stt_settings(s))
    tts = SentenceSafeGnaniTTS(api_key=settings.gnani_api_key, settings=_tts_settings(s))
    llm = OpenAILLMService(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        settings=OpenAILLMService.Settings(
            model=settings.llm_model, temperature=0.3, extra={"extra_body": settings.llm_extra_body},
        ),
    )

    opening = s.start(mode="voice")
    context = LLMContext(
        messages=[
            {"role": "system", "content": system_prompt(s)},
            {"role": "assistant", "content": opening},
        ],
        tools=pipecat_tools(),
    )
    aggregators = LLMContextAggregatorPair(context, user_params=LLMUserAggregatorParams(vad_analyzer=vad))

    class TriageTap(FrameProcessor):
        async def process_frame(self, frame: Frame, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if isinstance(frame, TranscriptionFrame) and direction == FrameDirection.DOWNSTREAM:
                lang_code = str(frame.language.value) if getattr(frame, "language", None) else None
                turn = s.on_user_text(frame.text, lang_code)
                for text in turn.speak_now:
                    await self.push_frame(TTSSpeakFrame(text))
                if turn.llm_notes:
                    await self.push_frame(LLMMessagesAppendFrame(
                        messages=[{"role": "system", "content": n} for n in turn.llm_notes], run_llm=False,
                    ))
            await self.push_frame(frame, direction)

    class AssistantTap(FrameProcessor):
        def __init__(self):
            super().__init__()
            self.buf: list[str] = []

        async def process_frame(self, frame: Frame, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if isinstance(frame, LLMFullResponseStartFrame):
                self.buf = []
            elif isinstance(frame, LLMTextFrame):
                self.buf.append(frame.text)
            elif isinstance(frame, LLMFullResponseEndFrame):
                s.add_assistant_text("".join(self.buf))
                self.buf = []
            await self.push_frame(frame, direction)

    pipeline = Pipeline([
        transport.input(), stt, TriageTap(), aggregators.user(), llm, AssistantTap(), tts,
        transport.output(), aggregators.assistant(),
    ])

    latency = UserBotLatencyObserver()

    @latency.event_handler("on_latency_measured")
    async def _on_latency(_observer, seconds: float):
        s.latencies_ms.append(round(seconds * 1000))

    worker = PipelineWorker(pipeline, observers=[latency], idle_timeout_secs=60)

    async def end_call(closing: str | None) -> None:
        frames: list[Any] = [TTSSpeakFrame(closing)] if closing else []
        await worker.queue_frames([*frames, EndWorkerFrame(reason="call ended")])

    def make_handler(name: str):
        async def handler(params: FunctionCallParams):
            result = await asyncio.to_thread(s.dispatch, name, dict(params.arguments or {}))
            run_llm = True
            if result.get("say_exactly"):
                await params.llm.push_frame(TTSSpeakFrame(result["say_exactly"]))
            if name == "end_call" and result.get("ok"):
                run_llm = False
                await end_call(result.get("closing_line"))
            elif s.transcript and s.transcript[-1]["role"] == "assistant" and asks_patient(s.transcript[-1]["text"]):
                # The bot just asked the patient something; wait for the answer before speaking again.
                run_llm = False
            await params.result_callback(result, properties=FunctionCallResultProperties(run_llm=run_llm))

        return handler

    for name in TOOL_SPECS:
        llm.register_function(name, make_handler(name))

    def on_language_change(code: str) -> None:
        from pipecat_gnani import GnaniSTTSettings, GnaniTTSSettings

        frames = [TTSUpdateSettingsFrame(delta=GnaniTTSSettings(language=code, voice=voice_for(code, s.codemix)))]
        if not s.codemix:
            frames.append(STTUpdateSettingsFrame(delta=GnaniSTTSettings(language=code)))
        asyncio.get_running_loop().create_task(worker.queue_frames(frames))

    s.on_language_change = on_language_change

    async def call_timer() -> None:
        await asyncio.sleep(settings.max_call_seconds)
        if not s.ended:
            logger.info(f"call {call_id}: max length reached")
            s.ended, s.end_reason = True, "max_length"
            await end_call(line(s.language, "closing"))

    timer: asyncio.Task | None = None

    @transport.event_handler("on_client_connected")
    async def on_connected(_transport, _client):
        nonlocal timer
        logger.info(f"call {call_id}: patient connected")
        timer = asyncio.create_task(call_timer())
        # The consent line is spoken verbatim; the LLM takes over from the patient's reply.
        await worker.queue_frames([TTSSpeakFrame(opening)])

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(_transport, _client):
        logger.info(f"call {call_id}: patient disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    try:
        await runner.run()
    finally:
        if timer:
            timer.cancel()
        await asyncio.to_thread(s.finalize, review_call)
        logger.info(f"call {call_id}: finalised")


def voice_ready() -> tuple[bool, str]:
    if not settings.gnani_api_key:
        return False, "GNANI_API_KEY is not set"
    if not settings.llm_api_key:
        return False, "LLM_API_KEY (or DEEPINFRA_API_KEY) is not set"
    os.environ.setdefault("GNANI_API_KEY", settings.gnani_api_key)
    return True, "ok"
