"""
support_agent.py
================
"Taylor" — Tier-1 Technical Support Specialist for a home-services
(roofing & plumbing) company.

Part of the Receptionist -> Sales -> Support multi-agent triad.

Stack (pre-1.0 LiveKit Agents API, pinned to livekit-agents==0.12.21):
    * Pipeline : livekit.agents.voice_assistant.VoiceAssistant
                 (in 0.12.x this is an alias of pipeline.VoicePipelineAgent)
    * LLM      : openai/gpt-oss-20b     via Groq  (openai plugin + custom AsyncOpenAI client)
    * STT      : whisper-large-v3       via Groq  (openai plugin + same client)
    * TTS      : Cartesia               (model names live in common.py)
    * VAD      : Silero
    * Tools    : llm.FunctionContext + @llm.ai_callable

Required environment variables (.env):
    LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
    GROQ_API_KEY
    CARTESIA_API_KEY
    N8N_TICKET_WEBHOOK_URL        optional; e.g. http://localhost:5678/webhook/support-ticket
                                  If unset, tickets are printed to the terminal (mock mode).
Optional:
    SUPPORT_VOICE_ID              a Cartesia voice for Taylor (distinct voices make
                                  each handoff audible on stage).

This worker registers with agent_name "support-agent" (explicit dispatch), so it
only joins a room when the Receptionist or Sales transfers a caller here.

Auto-hangup: once create_support_ticket succeeds, Taylor says one goodbye line
and then the call is ended for everyone (see SupportFunctions._hang_up).

Run:
    python support_agent.py download-files   # one-time: fetch Silero model weights
    python support_agent.py dev              # connect to your LiveKit server
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
    SUPPORT_VOICE_ID,
    GROQ_LLM_MODEL,
    GROQ_STT_MODEL,
    SUPPORT_AGENT_NAME,
    handoff_prompt_block,
    make_groq_client,
    read_handoff,
)

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
load_dotenv()

logger = logging.getLogger("support-agent")
logger.setLevel(logging.INFO)

N8N_TICKET_WEBHOOK_URL = os.getenv("N8N_TICKET_WEBHOOK_URL", "")

# Webhook must never stall a live call: cap the whole request at 8 seconds.
WEBHOOK_TIMEOUT = aiohttp.ClientTimeout(total=8)

VALID_URGENCY = ["EMERGENCY", "URGENT", "ROUTINE"]

# Auto-hangup timing. The goodbye line must START within HANGUP_DELAY seconds
# of the ticket being created (LLM + Cartesia latency); if it doesn't, Taylor
# says the goodbye directly through TTS instead of waiting on the LLM forever.
HANGUP_DELAY = 6.0
GOODBYE_MAX_SECONDS = 20.0  # cap on how long the goodbye itself may play
HANGUP_GRACE = 0.8          # let the last audio frames reach the browser


# ---------------------------------------------------------------------------
# System prompt — persona + guardrails
# ---------------------------------------------------------------------------
# Kept short and imperative: an 8B model follows a tight rule list far more
# reliably than long prose. Spoken-output rules matter because every token
# the LLM writes is read aloud by the TTS.
SYSTEM_PROMPT = """
You are Taylor, a Tier-1 Technical Support Specialist for a home-services company
that handles roofing and plumbing (Summit Roofing and Plumbing). You are on a live
phone call.

TONE: Calm, competent, efficient. Short sentences. One question at a time.
This is a voice call: never use lists, markdown, emojis, or special symbols.

YOUR JOB, IN ORDER:
1. Find out what is wrong (plumbing or roofing) and how bad it is.
2. Decide urgency:
   - EMERGENCY: active flooding, burst pipe, sewage backup, water near electrical,
     gas smell, roof collapse or large open hole during rain.
   - URGENT: active leak that is contained, no hot water, roof leak into a room.
   - ROUTINE: slow drip, running toilet, missing shingles, inspection or quote.
3. If EMERGENCY, give safety mitigation FIRST, before collecting details.
4. Collect: full name, callback phone number, service address.
   Read the phone number and address back to confirm them.
5. Call create_support_ticket exactly once, when you have all five fields.
6. Tell the caller their ticket number and that a technician will contact them.

ALLOWED SAFETY ADVICE (the only guidance you may give):
- Shut off the main water valve, or the local valve under the fixture.
- Switch off electricity to affected areas only if it is safe to reach the breaker
  without standing in water.
- If they smell gas: leave the house now, do not use switches or flames,
  and call the gas company or emergency services from outside.
- Move valuables away from water; put a bucket under a drip.
- Stay off the roof. Stay out of rooms with a sagging ceiling.

STRICT RULES:
- Never diagnose the root cause. Say a technician will assess it on site.
- Never give repair or DIY instructions beyond the safety list above.
- Never quote prices or promise arrival times.
- If the caller wants a quote or a new installation, say you will note it on the
  ticket and the sales team will follow up.
- Never invent a ticket number. Only use the one returned by the tool.
""".strip()

GREETING = (
    "Hi, this is Taylor from technical support. "
    "I'm here to help. Can you tell me what's going on?"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _generate_ticket_id() -> str:
    """Short, speakable ticket ID, e.g. 'TK-4827'.

    Four digits are easy to hear and repeat back on a phone call. It's
    generated locally so the caller still gets a reference even if n8n is
    down; if n8n returns its own ID, that one wins.
    """
    return "TK-" + "".join(random.choices(string.digits, k=4))


def _spoken_ticket(ticket_id: str) -> str:
    """'TK-4827' -> 'T K 4 8 2 7' so the TTS reads it character by character."""
    return " ".join(ch for ch in ticket_id if ch != "-")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
class SupportFunctions(llm.FunctionContext):
    """Tools exposed to Taylor's LLM."""

    def __init__(self, room: rtc.Room) -> None:
        super().__init__()
        self.room = room
        # Guard against the 8B model calling the tool twice for the same caller.
        self._ticket_created: str | None = None
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

        room.disconnect() only removes Taylor; the browser guest would stay in an
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

    @llm.ai_callable(
        description=(
            "Log a support ticket for the caller. Call this only once, after you "
            "have collected and confirmed the customer's name, phone number, "
            "service address, a description of the issue, and the urgency level."
        )
    )
    async def create_support_ticket(
        self,
        customer_name: Annotated[
            str, llm.TypeInfo(description="Customer's full name")
        ],
        phone_number: Annotated[
            str, llm.TypeInfo(description="Callback phone number, digits only")
        ],
        service_address: Annotated[
            str, llm.TypeInfo(description="Full address where service is needed")
        ],
        issue_description: Annotated[
            str,
            llm.TypeInfo(
                description=(
                    "Short factual description of the problem as the caller "
                    "described it, including whether it is plumbing or roofing"
                )
            ),
        ],
        urgency_level: Annotated[
            str,
            llm.TypeInfo(
                description="How urgent the issue is",
                # Passed as a LIST, per the project's constraint.
                choices=["EMERGENCY", "URGENT", "ROUTINE"],
            ),
        ],
    ) -> str:
        # --- Idempotency: don't create a second ticket on the same call -----
        if self._ticket_created:
            return (
                f"A ticket was already created on this call: "
                f"{_spoken_ticket(self._ticket_created)}. Do not create another. "
                f"Just remind the caller of this ticket number."
            )

        # --- Normalise inputs (small models drift on casing/format) --------
        urgency = urgency_level.strip().upper()
        if urgency not in VALID_URGENCY:
            urgency = "URGENT"  # safest middle ground if the model goes off-script
        phone_clean = "".join(ch for ch in phone_number if ch.isdigit() or ch == "+")

        ticket_id = _generate_ticket_id()
        payload = {
            "ticket_id": ticket_id,
            "customer_name": customer_name.strip(),
            "phone_number": phone_clean,
            "service_address": service_address.strip(),
            "issue_description": issue_description.strip(),
            "urgency_level": urgency,
            "source_agent": "support_agent",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("Creating support ticket: %s", payload)

        # --- POST to n8n ----------------------------------------------------
        webhook_ok = False
        if not N8N_TICKET_WEBHOOK_URL:
            # Mock mode: no n8n configured. Print the payload that WOULD be sent,
            # with a banner that's easy to show on screen, and treat it as a success
            # so Taylor confirms the ticket normally on the call.
            print("\n" + "=" * 60)
            print("  [MOCK TICKET WEBHOOK]  POST /n8n/support-ticket")
            print("=" * 60)
            print(json.dumps(payload, indent=2))
            print("=" * 60 + "\n", flush=True)
            webhook_ok = True
        else:
            try:
                async with aiohttp.ClientSession(timeout=WEBHOOK_TIMEOUT) as session:
                    async with session.post(N8N_TICKET_WEBHOOK_URL, json=payload) as resp:
                        if 200 <= resp.status < 300:
                            webhook_ok = True
                            # If n8n responds with its own ticket_id, prefer it.
                            try:
                                data = await resp.json(content_type=None)
                                if isinstance(data, dict) and data.get("ticket_id"):
                                    ticket_id = str(data["ticket_id"])
                            except (aiohttp.ContentTypeError, ValueError):
                                pass  # non-JSON body is fine
                            logger.info("Ticket %s accepted by n8n", ticket_id)
                        else:
                            body = await resp.text()
                            logger.error("n8n returned HTTP %s: %s", resp.status, body[:300])
            except asyncio.TimeoutError:
                logger.error("n8n webhook timed out")
            except aiohttp.ClientError as e:
                logger.error("n8n webhook unreachable: %s", e)

        self._ticket_created = ticket_id
        spoken = _spoken_ticket(ticket_id)

        # --- Tell the LLM what to say, then hang up --------------------------
        # The return string becomes the tool result; the LLM turns it into speech.
        # The same goodbye is the fallback if the LLM says nothing.
        if webhook_ok:
            goodbye = (
                f"Your ticket is logged. Your ticket number is {spoken}. "
                f"A technician will call you back at the number you gave. Goodbye!"
            )
            status = f"SUCCESS. Ticket number: {spoken}. Urgency: {urgency}."
        else:
            goodbye = (
                f"Your details are recorded under reference {spoken}. "
                f"Our dispatch team will call you back at the number you gave. "
                f"Please stay safe. Goodbye!"
            )
            status = (
                f"RECORDED. The ticketing system did not confirm, but the details "
                f"were recorded under reference {spoken}."
            )
        if urgency == "EMERGENCY" and webhook_ok:
            goodbye = goodbye.replace("Goodbye!", "Please stay safe. Goodbye!")

        self._schedule_hangup(goodbye)
        return (
            f"{status} The call ends automatically in a few seconds. "
            f"You MUST say exactly this, and nothing else: '{goodbye}' "
            f"Then stop talking. Do not ask any question."
        )


# ---------------------------------------------------------------------------
# Worker lifecycle
# ---------------------------------------------------------------------------
def prewarm(proc: JobProcess) -> None:
    """Load Silero once per worker process, not once per call."""
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext) -> None:
    logger.info("Support agent joining room %s", ctx.room.name)

    # Audio only — the agent doesn't need video tracks.
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    await announce_persona(ctx, "Taylor")  # lets the web UI show who is speaking
    participant = await ctx.wait_for_participant()  # ignores other agents by default
    logger.info("Caller connected: %s", participant.identity)

    # Note left by Ava or Jordan when they transferred the call (empty if direct).
    note = read_handoff(ctx)
    logger.info("Handoff note: %s", note)

    name = note.get("caller_name", "").strip()
    if note:
        # Transferred call: skip "what's going on?" and go straight to safety.
        greeting = (
            f"Hi{' ' + name if name else ''}, this is Taylor in technical support. "
            "I've got the basics. First, are you safe right now, "
            "and is the problem still happening?"
        )
    else:
        greeting = GREETING

    groq_client = make_groq_client()
    initial_ctx = llm.ChatContext().append(
        role="system", text=SYSTEM_PROMPT + handoff_prompt_block(note)
    )
    fnc_ctx = SupportFunctions(room=ctx.room)

    assistant = VoiceAssistant(
        vad=ctx.proc.userdata["vad"],
        stt=openai.STT(
            model=GROQ_STT_MODEL,
            language="en",
            client=groq_client,
        ),
        llm=openai.LLM(
            model=GROQ_LLM_MODEL,
            client=groq_client,
            temperature=0.3,  # low temperature = steadier tool arguments
        ),
        tts=cartesia.TTS(
            model=CARTESIA_TTS_MODEL,
            voice=os.getenv("SUPPORT_VOICE_ID") or SUPPORT_VOICE_ID,
        ),
        chat_ctx=initial_ctx,
        fnc_ctx=fnc_ctx,
        allow_interruptions=True,
        # Callers describing a leak pause mid-sentence; give them a little room.
        min_endpointing_delay=0.6,
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
            # Explicit dispatch: only joins when Ava or Jordan transfers a call here.
            # Health-check HTTP port. Each worker needs its own when all three run in
            # one container (they'd all default to 8081 in "start" mode and clash).
            port=int(os.getenv("WORKER_PORT", "8083")),
            agent_name=SUPPORT_AGENT_NAME,
        )
    )
