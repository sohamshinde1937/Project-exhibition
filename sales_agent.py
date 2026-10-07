"""
sales_agent.py — Sales Representative "Jordan"
===============================================
Qualifies roofing/plumbing upgrade leads, gives rough price ranges, and books a
free on-site consultation. If the caller has an active emergency, Jordan stops
selling and transfers them straight to Support ("Taylor").

Stack (livekit-agents==0.12.21, pre-1.0 API):
    VoiceAssistant + Silero VAD + Groq (whisper-large-v3 STT, gpt-oss-20b LLM)
    + Cartesia TTS. Model names live in common.py.

This worker registers with agent_name "sales-agent" (explicit dispatch), so it
only joins a room when the Receptionist transfers a caller here.

Auto-hangup: once book_consultation succeeds, Jordan says one goodbye line and
then the call is ended for everyone (see SalesFunctions._hang_up).

Run:  python sales_agent.py download-files   (once)
      python sales_agent.py dev
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import random
import string
from datetime import datetime, timezone
from typing import Annotated

import aiohttp
from dotenv import load_dotenv

from livekit import api, rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
)
from livekit.agents.pipeline import AgentCallContext
from livekit.agents.voice_assistant import VoiceAssistant
from livekit.plugins import cartesia, openai, silero

from common import (
    announce_persona,
    CARTESIA_TTS_MODEL,
    SALES_VOICE_ID,
    GROQ_LLM_MODEL,
    GROQ_STT_MODEL,
    SALES_AGENT_NAME,
    SUPPORT_AGENT_NAME,
    Handoff,
    handoff_prompt_block,
    make_groq_client,
    read_handoff,
)

load_dotenv()

logger = logging.getLogger("sales-agent")
logger.setLevel(logging.INFO)

VALID_URGENCY = ["HIGH", "MEDIUM", "LOW"]

# Optional n8n webhook for sales leads, e.g.
# http://localhost:5678/webhook/sales-lead . If unset, leads are only printed.
N8N_LEAD_WEBHOOK_URL = os.getenv("N8N_LEAD_WEBHOOK_URL", "")
WEBHOOK_TIMEOUT = aiohttp.ClientTimeout(total=8)  # never stall a live call

# Auto-hangup timing. The goodbye line must START within HANGUP_DELAY seconds
# of the booking (LLM + Cartesia latency); if it doesn't, Jordan says the
# goodbye directly through TTS instead of waiting on the LLM forever.
HANGUP_DELAY = 6.0
GOODBYE_MAX_SECONDS = 20.0  # cap on how long the goodbye itself may play
HANGUP_GRACE = 0.8          # let the last audio frames reach the browser

# ---------------------------------------------------------------------------
# Rough price table (placeholder demo values for a fictional company)
# ---------------------------------------------------------------------------
# Prices live in code, not in the LLM: a small model asked to "estimate" invents
# a different number each time. Edit these to whatever you want to show.
CURRENCY = "rupees"
PRICE_RANGES: dict[str, tuple[int, int, str]] = {
    # key                  (low,    high,   unit spoken to caller)
    "roof_replacement":    (180,    350,    "per square foot"),
    "roof_repair":         (15000,  60000,  "per job"),
    "roof_inspection":     (0,      0,      "free"),
    "roof_waterproofing":  (60,     120,    "per square foot"),
    "gutter_installation": (400,    900,    "per running foot"),
    "water_heater":        (12000,  45000,  "installed"),
    "drain_inspection":    (1500,   5000,   "per visit"),
    "bathroom_replumb":    (40000,  150000, "per bathroom"),
    "plumbing_repipe":     (150000, 500000, "for a typical home"),
    "water_filtration":    (15000,  60000,  "installed"),
}
SERVICE_KEYS = list(PRICE_RANGES.keys())


def _spoken_number(n: int) -> str:
    """Phrase a number the way a person says it on the phone (Indian units)."""
    if n >= 100000:
        return f"{n / 100000:g} lakh"
    if n >= 1000:
        return f"{n // 1000} thousand"
    return str(n)


# ---------------------------------------------------------------------------
# System prompt (compact: Groq free plan ~8K tokens/min for gpt-oss-20b)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are Jordan, a Sales Representative for Summit Roofing and Plumbing, on a live
phone call.

RULE ZERO: If the caller has an active emergency (burst pipe, flooding, water
coming through the ceiling now, sewage backup, gas smell, roof collapse), stop
selling immediately and call transfer_to_support. If they smell gas, first tell
them to leave the house and call the gas company from outside.

STYLE: Upbeat, consultative, professional, and brief. One or two short spoken
sentences, then one question. No lists, markdown, or symbols.

FLOW:
1. Learn what they want: roofing or plumbing, and what exactly.
2. Qualify: property type, age of the current roof or plumbing, size or scope
   (roof area, number of bathrooms), budget in mind, and preferred timing.
3. Once you know the service, call get_rough_estimate and share the range.
   Always say it is a rough, non-binding estimate; the final price comes after
   the free on-site inspection.
4. Briefly pitch the value, then offer a free on-site consultation.
5. If they agree, confirm their full name and phone number (read the number
   back), and ask for a preferred date.
6. Call book_consultation once, then confirm the booking reference.

NEVER: offer discounts or deals, give an exact or final price, invent prices
the tool did not give, or invent a booking reference.
""".strip()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
class SalesFunctions(llm.FunctionContext):
    """Tools exposed to Jordan's LLM."""

    def __init__(self, handoff: Handoff, room: rtc.Room) -> None:
        super().__init__()
        self._handoff = handoff
        self.room = room
        self._booking_ref: str | None = None  # blocks double bookings on one call
        # Kept referenced so it isn't garbage-collected mid-run, and so the job
        # shutdown can cancel it instead of leaving a "Task was destroyed" error.
        self._hangup_task: asyncio.Task | None = None
        self._ending_call = False

    # -- Auto-hangup ---------------------------------------------------------
    def _schedule_hangup(self, goodbye: str) -> None:
        """Start the hangup in the background. Must run inside an ai_callable."""
        if self._hangup_task is not None:
            return
        assistant = AgentCallContext.get_current().agent
        self._hangup_task = asyncio.create_task(self._hang_up(assistant, goodbye))

    async def _hang_up(self, assistant: VoiceAssistant, goodbye: str) -> None:
        # Register both listeners now: the goodbye can start before we'd get to
        # a second registration.
        started, stopped = asyncio.Event(), asyncio.Event()
        assistant.once("agent_started_speaking", lambda *_: started.set())
        assistant.once("agent_stopped_speaking", lambda *_: stopped.set())
        try:
            await asyncio.wait_for(started.wait(), timeout=HANGUP_DELAY)
            await asyncio.wait_for(stopped.wait(), timeout=GOODBYE_MAX_SECONDS)
        except asyncio.TimeoutError:
            if not started.is_set():
                # The LLM produced no speech after the tool result: this is the
                # "stuck in thinking" case. Say the goodbye directly via TTS.
                logger.warning("No goodbye from the LLM; speaking it directly")
                try:
                    handle = await assistant.say(
                        goodbye, allow_interruptions=False, add_to_chat_ctx=False
                    )
                    await asyncio.wait_for(
                        asyncio.shield(handle.join()), timeout=GOODBYE_MAX_SECONDS
                    )
                except asyncio.TimeoutError:
                    logger.warning("Fallback goodbye did not finish; hanging up anyway")
            else:
                logger.warning("Goodbye ran long; hanging up anyway")

        await asyncio.sleep(HANGUP_GRACE)
        self._ending_call = True
        await self._end_call()

    async def _end_call(self) -> None:
        """End the call for EVERYONE in the room, not just this agent.

        room.disconnect() only removes Jordan; the browser guest would stay in an
        empty room (the UI shows "Transferring your call..."). Deleting the room
        on the server disconnects every participant, so the browser gets a
        normal Disconnected event, and this job shuts down on "room disconnected".
        """
        lkapi = api.LiveKitAPI()  # reads LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET
        try:
            await lkapi.room.delete_room(api.DeleteRoomRequest(room=self.room.name))
            logger.info("Call ended: room %s deleted", self.room.name)
        except Exception:
            logger.exception("Could not delete room %s; leaving it instead", self.room.name)
            await self.room.disconnect()
        finally:
            await lkapi.aclose()

    async def aclose(self) -> None:
        """Job shutdown hook: don't leave the hangup task pending."""
        task = self._hangup_task
        if task is None or task.done():
            return
        if not self._ending_call:
            task.cancel()  # caller left before the goodbye finished
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await asyncio.wait_for(task, timeout=5)


    # -- Emergency escape hatch ----------------------------------------------
    @llm.ai_callable(
        description=(
            "Transfer the caller to Taylor in technical support. Use immediately "
            "if the caller has an active leak, flood, burst pipe, or other emergency."
        )
    )
    async def transfer_to_support(
        self,
        caller_name: Annotated[str, llm.TypeInfo(description="Caller's name, if known")],
        summary: Annotated[
            str, llm.TypeInfo(description="One sentence describing the emergency")
        ],
    ) -> str:
        if self._hangup_task is not None:
            return "The call is already ending. Say nothing more."
        if not self._handoff.begin(SUPPORT_AGENT_NAME, caller_name, summary):
            return "A transfer is already in progress. Say nothing more."
        return (
            "Transfer started. In ONE short, calm sentence, tell the caller you are "
            "connecting them to Taylor in support right now. Say nothing else."
        )

    # -- Deterministic rough estimate ----------------------------------------
    @llm.ai_callable(
        description=(
            "Get a rough price range for a roofing or plumbing service. "
            "Use this before quoting any number to the caller."
        )
    )
    async def get_rough_estimate(
        self,
        service_type: Annotated[
            str,
            llm.TypeInfo(
                description="The service the caller is interested in",
                choices=SERVICE_KEYS,  # a list, per the project's schema rule
            ),
        ],
    ) -> str:
        key = service_type.strip().lower()
        if key not in PRICE_RANGES:
            return (
                "No estimate is available for that service. Tell the caller the "
                "technician will quote it during the free on-site consultation."
            )
        low, high, unit = PRICE_RANGES[key]
        logger.info("Estimate requested: %s", key)
        if high == 0:
            return f"{key.replace('_', ' ')} is free. Tell the caller it costs nothing."
        return (
            f"Rough range for {key.replace('_', ' ')}: about {_spoken_number(low)} "
            f"to {_spoken_number(high)} {CURRENCY} {unit}. Say this is only a rough, "
            f"non-binding estimate, confirmed after the free on-site inspection."
        )

    # -- Required tool: book the consultation --------------------------------
    @llm.ai_callable(
        description=(
            "Book a free on-site consultation. Call only once, after the caller "
            "agrees and you have confirmed their name and phone number. "
            "Never use this for an active emergency."
        )
    )
    async def book_consultation(
        self,
        customer_name: Annotated[str, llm.TypeInfo(description="Customer's full name")],
        phone_number: Annotated[
            str, llm.TypeInfo(description="Callback phone number, digits only")
        ],
        service_interest: Annotated[
            str,
            llm.TypeInfo(
                description=(
                    "What the customer wants, with scope details, e.g. "
                    "'roof replacement, about 1500 square feet'"
                )
            ),
        ],
        urgency: Annotated[
            str,
            llm.TypeInfo(
                description="How soon the customer wants the work done",
                # Passed as a LIST, per the project's constraint.
                choices=["HIGH", "MEDIUM", "LOW"],
            ),
        ],
        estimated_budget: Annotated[
            str,
            llm.TypeInfo(description="Budget the caller mentioned, or 'not stated'"),
        ] = "not stated",
        preferred_date: Annotated[
            str,
            llm.TypeInfo(description="Preferred consultation date or day, or 'flexible'"),
        ] = "flexible",
    ) -> str:
        if self._handoff.started:
            return "The caller is being transferred to support. Say nothing more."
        if self._booking_ref:
            return (
                f"A consultation is already booked with reference {self._booking_ref}. "
                f"Do not book another; just remind the caller."
            )

        urgency_norm = urgency.strip().upper()
        if urgency_norm not in VALID_URGENCY:
            urgency_norm = "MEDIUM"
        phone_clean = "".join(ch for ch in phone_number if ch.isdigit() or ch == "+")
        ref = "SL-" + "".join(random.choices(string.digits, k=4))

        # Matches the "Sales Consultation Payload Contract" in the project spec,
        # plus booking_ref and urgency.
        payload = {
            "booking_ref": ref,
            "customer_name": customer_name.strip(),
            "phone_number": phone_clean,
            "service_interest": service_interest.strip(),
            "urgency": urgency_norm,
            "estimated_budget": estimated_budget.strip(),
            "preferred_date": preferred_date.strip(),
            "source_agent": "sales_agent",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # --- Send the lead to n8n (or print it in mock mode) -----------------
        # Always printed, so it can be shown on the projector either way.
        print("\n" + "=" * 60)
        print("  [CRM LEAD]  " + ("POST " + N8N_LEAD_WEBHOOK_URL if N8N_LEAD_WEBHOOK_URL else "mock mode (no webhook set)"))
        print("=" * 60)
        print(json.dumps(payload, indent=2))
        print("=" * 60 + "\n", flush=True)

        if N8N_LEAD_WEBHOOK_URL:
            try:
                async with aiohttp.ClientSession(timeout=WEBHOOK_TIMEOUT) as session:
                    async with session.post(N8N_LEAD_WEBHOOK_URL, json=payload) as resp:
                        if 200 <= resp.status < 300:
                            logger.info("Lead %s accepted by n8n", ref)
                        else:
                            body = await resp.text()
                            logger.error("n8n returned HTTP %s: %s", resp.status, body[:300])
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                # The booking still stands on the call; the lead is in this log.
                logger.error("n8n lead webhook unreachable: %s", e)
        logger.info("Consultation booked: %s", ref)

        self._booking_ref = ref
        spoken_ref = " ".join(ch for ch in ref if ch != "-")  # "S L 4 8 2 7"
        first_name = customer_name.strip().split(" ")[0] if customer_name.strip() else ""
        goodbye = (
            f"Thank you{' ' + first_name if first_name else ''}! Your free consultation "
            f"is booked. Your booking reference is {spoken_ref}. A specialist will "
            f"call you to confirm the visit time. Goodbye!"
        )
        self._schedule_hangup(goodbye)
        return (
            f"SUCCESS. Consultation booked. Booking reference: {spoken_ref}. The call "
            f"ends automatically in a few seconds. You MUST say exactly this, and "
            f"nothing else: '{goodbye}' Then stop talking. Do not ask any question."
        )


# ---------------------------------------------------------------------------
# Worker lifecycle
# ---------------------------------------------------------------------------
def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    await announce_persona(ctx, "Jordan")  # lets the web UI show who is speaking
    participant = await ctx.wait_for_participant()  # ignores other agents by default

    note = read_handoff(ctx)
    logger.info("Sales agent in room %s, handoff note: %s", ctx.room.name, note)

    name = note.get("caller_name", "").strip()
    greeting = (
        f"Hi {name}, this is Jordan from sales. " if name else "Hi, this is Jordan from sales. "
    ) + (
        "I hear you're interested in some work on your home. Tell me a bit more?"
        if note.get("summary")
        else "Are you looking at a roofing or a plumbing upgrade today?"
    )

    groq_client = make_groq_client()
    initial_ctx = llm.ChatContext().append(
        role="system", text=SYSTEM_PROMPT + handoff_prompt_block(note)
    )
    fnc_ctx = SalesFunctions(
        handoff=Handoff(ctx, from_agent="Jordan in sales"), room=ctx.room
    )

    assistant = VoiceAssistant(
        vad=ctx.proc.userdata["vad"],
        stt=openai.STT(model=GROQ_STT_MODEL, language="en", client=groq_client),
        llm=openai.LLM(model=GROQ_LLM_MODEL, client=groq_client, temperature=0.5),
        tts=cartesia.TTS(
            model=CARTESIA_TTS_MODEL,
            # Jordan's own voice (male); Ava and Taylor use different ones.
            voice=os.getenv("SALES_VOICE_ID") or SALES_VOICE_ID,
        ),
        chat_ctx=initial_ctx,
        fnc_ctx=fnc_ctx,
        allow_interruptions=True,
        # Lets an estimate lookup be followed by a booking in the same exchange.
        max_nested_fnc_calls=2,
    )

    # Clean shutdown paths, so the job never ends with work still pending.
    ctx.add_shutdown_callback(fnc_ctx.aclose)
    ctx.add_shutdown_callback(assistant.aclose)

    @ctx.room.on("participant_disconnected")
    def _on_participant_disconnected(p: rtc.RemoteParticipant) -> None:
        # Caller closed the tab: leave now instead of idling in the room until
        # LiveKit's departure timeout closes it underneath us.
        if p.identity == participant.identity:
            ctx.shutdown(reason="caller disconnected")

    assistant.start(ctx.room, participant)
    await assistant.say(greeting, allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            # Explicit dispatch: only joins when transferred to.
            # Health-check HTTP port. Each worker needs its own when all three run in
            # one container (they'd all default to 8081 in "start" mode and clash).
            port=int(os.getenv("WORKER_PORT", "8082")),
            agent_name=SALES_AGENT_NAME,
        )
    )
