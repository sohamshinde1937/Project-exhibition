"""
agent.py — Receptionist "Ava"
==============================
Front desk for Summit Roofing & Plumbing. Answers FAQs, learns why the caller
is calling, gets their name, and hands them to the right specialist:

    Sales   "Jordan"  (sales_agent.py)   quotes, upgrades, inspections, new installs
    Support "Taylor"  (support_agent.py) active leaks, repairs, emergencies

Stack (livekit-agents==0.12.21, pre-1.0 API):
    VAD  Silero (300 ms sustained speech)   STT  whisper-large-v3 via Groq
    LLM  openai/gpt-oss-20b via Groq        TTS  Cartesia (see common.py)

This worker registers with NO agent_name, so LiveKit auto-dispatches it into
every new room. Sales and Support register with names and only join when Ava
transfers a call to them (see common.py for how the handoff works).

Run:  python agent.py download-files   (once)
      python agent.py dev
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

from dotenv import load_dotenv

from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
)
from livekit.agents.voice_assistant import VoiceAssistant
from livekit.plugins import cartesia, openai, silero

from common import (
    announce_persona,
    CARTESIA_TTS_MODEL,
    RECEPTIONIST_VOICE_ID,
    GROQ_LLM_MODEL,
    GROQ_STT_MODEL,
    SALES_AGENT_NAME,
    SUPPORT_AGENT_NAME,
    Handoff,
    make_groq_client,
)

load_dotenv()

logger = logging.getLogger("voice-receptionist")
logging.basicConfig(level=logging.INFO)

REQUIRED_ENV_VARS = [
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "GROQ_API_KEY",
    "CARTESIA_API_KEY",
]


def _validate_env() -> None:
    """Fail fast if any required credentials are missing."""
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        raise RuntimeError(f"Missing required environment variable(s): {', '.join(missing)}")


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
# Deliberately compact: Groq's free plan allows ~8K tokens per minute for
# gpt-oss-20b, and the full prompt is re-sent on every turn.
SYSTEM_PROMPT = """
You are Ava, the AI voice receptionist for Summit Roofing and Plumbing, a local
home-services company for residential and light-commercial roofing and plumbing.
You answer the phone 24/7.

STYLE: Warm, professional, efficient. Short, natural spoken sentences. No lists,
markdown, or symbols. Never claim to be human; if asked, say you are the
company's AI receptionist.

YOUR JOB:
1. Greet the caller and find out why they are calling.
2. Answer general questions from the FAQ below.
3. Get the caller's first name before any transfer.
4. Route the call:
   - Active leak, water coming in, burst pipe, flooding, sewage backup, no water,
     storm damage exposing the roof, gas smell, or any repair problem:
     call transfer_to_support. For an active emergency, transfer at once; if you
     don't have their name yet, ask for it in the same breath, but do not delay.
   - Quotes, estimates, inspections, upgrades, replacements, new installs:
     call transfer_to_sales.
   - Only FAQ questions: answer them yourself, no transfer.
5. Never book appointments, quote prices, or give repair advice yourself.

GAS SAFETY: If the caller smells gas, first tell them to leave the house now and
call the gas company or emergency services from outside, then transfer to support.

FAQ:
- Hours: office 8am to 6pm Monday to Saturday. Emergency dispatch 24/7.
- Service area: about 40 miles around the city centre; farther away, a team
  member will confirm.
- Estimates: roofing estimates are free and in person. Plumbing visits have a
  diagnostic fee that is waived if the customer goes ahead with the repair.
- Payment: cash, cheque, all major cards, and financing for large roofing jobs.
- Fully licensed and insured; documents available on request.
""".strip()

GREETING = "Hi, thank you for calling Summit Roofing and Plumbing. How can I help you today?"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
class ReceptionistFunctions(llm.FunctionContext):
    def __init__(self, handoff: Handoff) -> None:
        super().__init__()
        self._handoff = handoff

    def _transfer(self, target: str, who: str, caller_name: str, summary: str) -> str:
        if not self._handoff.begin(target, caller_name, summary):
            return "A transfer is already in progress. Say nothing more."
        return (
            f"Transfer started. Say ONE short sentence telling the caller you are "
            f"connecting them to {who} now. Say nothing else after that."
        )

    @llm.ai_callable(
        description=(
            "Transfer the caller to Taylor in technical support. Use for active "
            "leaks, emergencies, repairs, or anything broken right now."
        )
    )
    async def transfer_to_support(
        self,
        caller_name: Annotated[
            str, llm.TypeInfo(description="Caller's first name, or empty if unknown")
        ],
        summary: Annotated[
            str, llm.TypeInfo(description="One sentence: what the caller said is wrong")
        ],
    ) -> str:
        return self._transfer(SUPPORT_AGENT_NAME, "Taylor in our support team", caller_name, summary)

    @llm.ai_callable(
        description=(
            "Transfer the caller to Jordan in sales. Use for quotes, estimates, "
            "inspections, upgrades, replacements, or new installations."
        )
    )
    async def transfer_to_sales(
        self,
        caller_name: Annotated[str, llm.TypeInfo(description="Caller's first name")],
        summary: Annotated[
            str, llm.TypeInfo(description="One sentence: what the caller is interested in")
        ],
    ) -> str:
        return self._transfer(SALES_AGENT_NAME, "Jordan on our sales team", caller_name, summary)


# ---------------------------------------------------------------------------
# Worker lifecycle
# ---------------------------------------------------------------------------
def prewarm(proc: JobProcess) -> None:
    """Load Silero VAD once per worker process."""
    proc.userdata["vad"] = silero.VAD.load(
        # ~300 ms of continuous speech before it counts as speech, so short
        # background noises don't trigger false turns or interruptions.
        min_speech_duration=0.3,
        min_silence_duration=0.55,
        activation_threshold=0.5,
    )


async def entrypoint(ctx: JobContext) -> None:
    _validate_env()

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    await announce_persona(ctx, "Ava")  # lets the web UI show who is speaking
    participant = await ctx.wait_for_participant()
    logger.info("Starting receptionist for participant: %s", participant.identity)

    groq_client = make_groq_client()
    initial_ctx = llm.ChatContext().append(role="system", text=SYSTEM_PROMPT)

    assistant = VoiceAssistant(
        vad=ctx.proc.userdata["vad"],
        stt=openai.STT(model=GROQ_STT_MODEL, language="en", client=groq_client),
        llm=openai.LLM(model=GROQ_LLM_MODEL, client=groq_client, temperature=0.4),
        tts=cartesia.TTS(
            model=CARTESIA_TTS_MODEL,
            voice=os.getenv("RECEPTIONIST_VOICE_ID") or RECEPTIONIST_VOICE_ID,
        ),
        chat_ctx=initial_ctx,
        fnc_ctx=ReceptionistFunctions(Handoff(ctx, from_agent="Ava the receptionist")),
        # Barge-in: caller speech stops Ava mid-sentence, but only after 300 ms
        # and at least one transcribed word, so noise blips don't cut her off.
        allow_interruptions=True,
        interrupt_speech_duration=0.3,
        interrupt_min_words=1,
        min_endpointing_delay=0.5,
    )

    assistant.start(ctx.room, participant)
    await assistant.say(GREETING, allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            # No agent_name: Ava is auto-dispatched into every new room.
            # Health-check HTTP port. Each worker needs its own when all three run in
            # one container (they'd all default to 8081 in "start" mode and clash).
            port=int(os.getenv("WORKER_PORT", "8081")),
        )
    )
