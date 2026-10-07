"""
common.py
=========
Shared config and the call-handoff mechanism for the
Receptionist -> Sales -> Support triad (livekit-agents==0.12.21).

HOW A HANDOFF WORKS
-------------------
Every agent is its own worker process:

    python agent.py dev          # Receptionist "Ava"  -> auto-joins every new room
    python sales_agent.py dev    # Sales "Jordan"      -> joins only when dispatched
    python support_agent.py dev  # Support "Taylor"    -> joins only when dispatched

Ava registers with NO agent_name, so LiveKit sends her into every new room.
Jordan and Taylor register WITH an agent_name, which switches them to
"explicit dispatch": they only join a room when someone asks for them.

When an agent calls a transfer tool:
    1. The tool returns immediately, telling the LLM to say one handoff sentence.
    2. A background task waits for that sentence to finish playing.
    3. It asks the LiveKit server to dispatch the target agent into the SAME room,
       attaching a small JSON note (caller name, reason, summary) as job metadata.
    4. The current agent leaves the room (ctx.shutdown()).
The caller never disconnects; they just hear a new voice pick up.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from openai import AsyncOpenAI

from livekit import api
from livekit.agents import JobContext
from livekit.agents.pipeline import AgentCallContext

logger = logging.getLogger("handoff")

# ---------------------------------------------------------------------------
# Shared model config — change a model in ONE place for all three agents
# ---------------------------------------------------------------------------
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Groq shut down llama-3.1-8b-instant on 16 Aug 2026; its listed replacement
# is openai/gpt-oss-20b, which is also on Groq's free plan.
GROQ_LLM_MODEL = os.getenv("GROQ_LLM_MODEL", "openai/gpt-oss-20b")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3")

# Cartesia sunset the original "sonic" family (which sonic-english belonged to).
# sonic-2 works with this 0.12-era plugin but Cartesia retires it on 20 Oct 2026;
# after that, try CARTESIA_TTS_MODEL=sonic-3.5 and test it before going on stage.
CARTESIA_TTS_MODEL = os.getenv("CARTESIA_TTS_MODEL", "sonic-2")
DEFAULT_VOICE_ID = "c2ac25f9-ecc4-4f56-9095-651354df60c0"

# One clearly different Cartesia voice per agent, so each handoff is audible.
# Override any of them with RECEPTIONIST_VOICE_ID / SALES_VOICE_ID /
# SUPPORT_VOICE_ID in .env (an env value always wins over these defaults).
RECEPTIONIST_VOICE_ID = DEFAULT_VOICE_ID                   # Ava:    "Commercial Lady" (female, American)
SALES_VOICE_ID = "a0e99841-438c-4a64-b679-ae501e7d6091"    # Jordan: "Barbershop Man" (male, American)
SUPPORT_VOICE_ID = "79a125e8-cd45-4c13-8a67-188112f4dd22"  # Taylor: "British Lady" (female, British)

# agent_name values used for explicit dispatch. Must match between the
# worker that registers the name and the agent that dispatches it.
SALES_AGENT_NAME = os.getenv("SALES_AGENT_NAME", "sales-agent")
SUPPORT_AGENT_NAME = os.getenv("SUPPORT_AGENT_NAME", "support-agent")


def make_groq_client() -> AsyncOpenAI:
    """One OpenAI-compatible client pointed at Groq, shared by STT and LLM."""
    return AsyncOpenAI(api_key=os.environ["GROQ_API_KEY"], base_url=GROQ_BASE_URL)


# ---------------------------------------------------------------------------
# Tell the frontend which persona is on the line
# ---------------------------------------------------------------------------
async def announce_persona(ctx: JobContext, name: str) -> None:
    """Set this agent's participant name ("Ava", "Jordan", "Taylor").

    The web frontend reads the agent participant's name to light up the right
    card and label transcript lines. Agents have permission to update their own
    name; if it fails, the call still works and the UI falls back gracefully.
    """
    try:
        await ctx.room.local_participant.set_name(name)
    except Exception:
        logger.warning("Could not set participant name to %s", name, exc_info=True)


# ---------------------------------------------------------------------------
# Receiving side: read the note left by the previous agent
# ---------------------------------------------------------------------------
def read_handoff(ctx: JobContext) -> dict:
    """Return the handoff note from job metadata, or {} if this is a direct call."""
    raw = ctx.job.metadata or ""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        logger.warning("Job metadata is not JSON: %r", raw[:200])
        return {}


def handoff_prompt_block(note: dict) -> str:
    """Turn the handoff note into a line appended to the system prompt."""
    if not note:
        return ""
    parts = [f"You are taking over this call from {note.get('from_agent', 'a colleague')}."]
    if note.get("caller_name"):
        parts.append(f"The caller's name is {note['caller_name']}.")
    if note.get("summary"):
        parts.append(f"What they said so far: {note['summary']}")
    parts.append("Do not ask them to repeat what they already told us.")
    return "\n\nHANDOFF CONTEXT: " + " ".join(parts)


# ---------------------------------------------------------------------------
# Sending side: transfer the caller to another agent
# ---------------------------------------------------------------------------
class Handoff:
    """Performs at most one transfer per call."""

    def __init__(self, ctx: JobContext, from_agent: str) -> None:
        self._ctx = ctx
        self._from_agent = from_agent
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    def begin(self, target_agent_name: str, caller_name: str, summary: str) -> bool:
        """Start a transfer in the background. Returns False if one already started.

        Must be called from inside an @llm.ai_callable, because it uses the
        current AgentCallContext to find the running VoiceAssistant.
        """
        if self._started:
            return False
        self._started = True

        assistant = AgentCallContext.get_current().agent
        note = {
            "from_agent": self._from_agent,
            "caller_name": caller_name.strip(),
            "summary": summary.strip(),
        }
        asyncio.create_task(self._run(assistant, target_agent_name, note))
        return True

    async def _run(self, assistant, target: str, note: dict) -> None:
        # In 0.12.x, tools run AFTER any text spoken before the tool call, and
        # the LLM's reply to the tool result is spoken next. So: wait for that
        # next utterance (the handoff sentence) to start and then finish.
        started, stopped = asyncio.Event(), asyncio.Event()
        assistant.once("agent_started_speaking", lambda *_: started.set())
        try:
            await asyncio.wait_for(started.wait(), timeout=6)
            assistant.once("agent_stopped_speaking", lambda *_: stopped.set())
            await asyncio.wait_for(stopped.wait(), timeout=15)
        except asyncio.TimeoutError:
            # Model said nothing, or speech ran long: transfer anyway.
            logger.warning("Handoff sentence not detected; transferring anyway")

        room = self._ctx.room.name
        lkapi = api.LiveKitAPI()  # reads LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET
        try:
            await lkapi.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name=target,
                    room=room,
                    metadata=json.dumps(note),
                )
            )
            logger.info("Dispatched %s into room %s with %s", target, room, note)
        except Exception:
            # Don't leave the caller alone with nobody: stay on the line.
            logger.exception("Dispatch to %s failed; staying on the call", target)
            self._started = False
            await assistant.say(
                "Sorry, I couldn't connect you just now. Let's keep going together.",
                allow_interruptions=True,
            )
            return
        finally:
            await lkapi.aclose()

        # Leave the room so the caller only hears the new agent.
        self._ctx.shutdown(reason=f"transferred to {target}")
