"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ConnectionState, MediaDeviceFailure } from "livekit-client";
import {
  BarVisualizer,
  LiveKitRoom,
  RoomAudioRenderer,
  StartAudio,
  VoiceAssistantControlBar,
  useConnectionState,
  useRoomContext,
  useVoiceAssistant,
} from "@livekit/components-react";
import "@livekit/components-styles";
import { Headset, LoaderCircle, PhoneOff, ShieldCheck, X } from "lucide-react";

type Props = {
  isOpen: boolean;
  onClose: () => void;
};

type TokenResponse = {
  token: string;
  serverUrl: string;
  roomName: string;
  identity: string;
};

// The backend renames each agent's participant to one of these.
const PERSONAS = [
  { name: "Ava", role: "Reception" },
  { name: "Jordan", role: "Sales" },
  { name: "Taylor", role: "Emergency" },
];

// How long the "Call ended" screen stays up before the modal closes itself.
const ENDED_SCREEN_MS = 2200;

export default function AICallModal({ isOpen, onClose }: Props) {
  // Each opening gets a new key, so every call starts from a clean slate
  // (new token, new room, no leftover error or "ended" state).
  const [callKey, setCallKey] = useState(0);
  const [wasOpen, setWasOpen] = useState(isOpen);
  if (isOpen !== wasOpen) {
    setWasOpen(isOpen);
    if (isOpen) setCallKey((k) => k + 1);
  }

  // Esc closes the modal; the page behind it does not scroll while open.
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = overflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [isOpen, onClose]);

  // Autoplay compliance: nothing is fetched and no room is mounted until the
  // visitor has clicked a Call button (isOpen === true).
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-md animate-[fade-in_200ms_ease-out]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ai-call-title"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-lg overflow-hidden rounded-3xl border border-white/10 bg-slate-900/75 text-white shadow-[0_30px_120px_-20px_rgba(220,38,38,0.45)] backdrop-blur-2xl animate-[pop-in_260ms_cubic-bezier(0.2,0.9,0.3,1.2)]"
      >
        {/* Glass sheen + red glow */}
        <div aria-hidden className="pointer-events-none absolute inset-0">
          <div className="absolute -top-24 left-1/2 h-56 w-[28rem] -translate-x-1/2 rounded-full bg-red-600/25 blur-3xl" />
          <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/40 to-transparent" />
        </div>

        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute right-4 top-4 z-10 rounded-full p-2 text-slate-400 transition hover:bg-white/10 hover:text-white"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="relative px-6 pb-7 pt-7 sm:px-8">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-red-600 shadow-lg shadow-red-600/40">
              <Headset className="h-5 w-5" />
            </span>
            <div>
              <p id="ai-call-title" className="text-lg font-semibold leading-tight">
                Summit 24/7 AI Dispatch
              </p>
              <p className="text-xs text-slate-400">Live voice call in your browser, no phone needed</p>
            </div>
          </div>

          <CallSession key={callKey} onClose={onClose} />

          <p className="mt-6 flex items-center justify-center gap-1.5 text-center text-[11px] text-slate-500">
            <ShieldCheck className="h-3.5 w-3.5" />
            You are speaking with an AI assistant. Allow microphone access when asked.
          </p>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// One call: fetch a token, join the room, show the live UI.
// ─────────────────────────────────────────────────────────────────────────────
function CallSession({ onClose }: { onClose: () => void }) {
  const [details, setDetails] = useState<TokenResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ended, setEnded] = useState(false);
  // Distinguishes "the call ended" from "the call never connected".
  const connectedOnce = useRef(false);
  // Set when the visitor pressed End Call, so the modal closes at once.
  const endedByUser = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const res = await fetch("/api/token", { cache: "no-store", signal: controller.signal });
        const body = await res.json();
        if (!res.ok) throw new Error(body?.error ?? `Token request failed (${res.status})`);
        setDetails(body as TokenResponse);
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Could not start the call.");
      }
    })();
    return () => controller.abort();
  }, []);

  // When the agent hangs up (the backend deletes the room after a booking or
  // ticket), show a short "Call ended" screen, then close the modal by itself.
  useEffect(() => {
    if (!ended) return;
    const t = setTimeout(onClose, ENDED_SCREEN_MS);
    return () => clearTimeout(t);
  }, [ended, onClose]);

  const handleMediaFailure = useCallback((failure?: MediaDeviceFailure) => {
    if (failure === MediaDeviceFailure.PermissionDenied) {
      setError("Microphone access was blocked. Allow it from the browser's address bar and try again.");
    } else if (failure === MediaDeviceFailure.NotFound) {
      setError("No microphone was found. Plug one in and try again.");
    } else {
      setError("The microphone could not be started.");
    }
  }, []);

  const endCall = useCallback(() => {
    endedByUser.current = true;
    onClose();
  }, [onClose]);

  if (error) {
    return (
      <div className="mt-8 flex flex-col items-center gap-5 text-center">
        <p className="max-w-sm rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </p>
        <button
          type="button"
          onClick={onClose}
          className="rounded-full border border-white/15 px-6 py-2.5 text-sm font-medium text-slate-200 transition hover:bg-white/10"
        >
          Close
        </button>
      </div>
    );
  }

  if (ended) {
    return (
      <div className="mt-8 flex flex-col items-center gap-3 py-8 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-white/10">
          <PhoneOff className="h-6 w-6 text-slate-300" />
        </span>
        <p className="text-lg font-semibold">Call ended</p>
        <p className="text-sm text-slate-400">Thanks for calling Summit Roofing &amp; Plumbing.</p>
      </div>
    );
  }

  if (!details) {
    return (
      <div className="mt-8 flex flex-col items-center gap-4 py-10">
        <LoaderCircle className="h-8 w-8 animate-spin text-red-500" />
        <StatusLine label="Securing a line..." tone="amber" pulse />
      </div>
    );
  }

  return (
    <LiveKitRoom
      token={details.token}
      serverUrl={details.serverUrl}
      connect={true}
      audio={true}
      video={false}
      onConnected={() => {
        connectedOnce.current = true;
      }}
      onDisconnected={() => {
        if (endedByUser.current) return;
        if (connectedOnce.current) setEnded(true);
        else setError(`Could not reach the voice server at ${details.serverUrl}. Check LIVEKIT_URL and the network.`);
      }}
      onMediaDeviceFailure={handleMediaFailure}
      onError={(e) => setError(e.message)}
      data-lk-theme="default"
      className="!bg-transparent"
    >
      <LiveCall onEnd={endCall} />
      {/* Invisible: plays every remote audio track, i.e. the AI's voice. */}
      <RoomAudioRenderer />
      {/* Only appears if a strict autoplay policy (e.g. Safari) still blocks audio. */}
      <StartAudio
        label="Tap to enable audio"
        className="mx-auto mt-4 block rounded-full bg-amber-400 px-5 py-2 text-sm font-semibold text-slate-950"
      />
    </LiveKitRoom>
  );
}

function LiveCall({ onEnd }: { onEnd: () => void }) {
  const room = useRoomContext();
  const connectionState = useConnectionState();
  const { state, audioTrack, agent } = useVoiceAssistant();

  const activeName = agent?.name || agent?.identity;
  const active = PERSONAS.find((p) => p.name.toLowerCase() === activeName?.toLowerCase());

  // During a transfer the current agent leaves before the next one joins.
  // Remember that an agent was here so that gap reads as a transfer, not a stall.
  const [hadAgent, setHadAgent] = useState(false);
  if (agent && !hadAgent) setHadAgent(true);

  const status = describeStatus(connectionState, state, !!agent, hadAgent, active?.name);

  const hangUp = () => {
    room.disconnect();
    onEnd();
  };

  return (
    <div className="mt-6 flex flex-col items-center gap-6">
      <StatusLine {...status} />

      {/* The waveform: the centrepiece the audience watches. */}
      <div className="relative flex h-40 w-full items-center justify-center overflow-hidden rounded-2xl border border-white/10 bg-black/30 px-6">
        <div
          aria-hidden
          className={`absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(220,38,38,0.35),transparent_70%)] transition-opacity duration-500 ${
            state === "speaking" ? "opacity-100" : "opacity-0"
          }`}
        />
        <BarVisualizer
          state={state}
          track={audioTrack}
          barCount={7}
          options={{ minHeight: 10 }}
          className="summit-visualizer relative h-full w-full"
        />
      </div>

      {/* Who is on the line: lights up as Ava transfers to Jordan or Taylor. */}
      <div className="grid w-full grid-cols-3 gap-2">
        {PERSONAS.map((p) => {
          const on = active?.name === p.name;
          return (
            <div
              key={p.name}
              className={`rounded-xl border px-3 py-2 text-center transition-all duration-300 ${
                on ? "border-red-500/60 bg-red-600/15 shadow-[0_0_24px_-6px_rgba(220,38,38,0.8)]" : "border-white/5 bg-white/[0.03] opacity-50"
              }`}
            >
              <p className="text-[10px] font-medium uppercase tracking-widest text-slate-400">{p.role}</p>
              <p className="text-sm font-semibold">{p.name}</p>
            </div>
          );
        })}
      </div>

      <div className="flex w-full flex-col items-center gap-3 sm:flex-row sm:justify-center">
        {/* Mic mute + device picker only. */}
        <VoiceAssistantControlBar controls={{ microphone: true, leave: false }} />
        <button
          type="button"
          onClick={hangUp}
          className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-red-600 px-7 py-3 text-sm font-bold text-white shadow-lg shadow-red-600/40 transition hover:bg-red-500 active:scale-[0.98] sm:w-auto"
        >
          <PhoneOff className="h-4 w-4" />
          End Call
        </button>
      </div>
    </div>
  );
}

type Tone = "amber" | "green" | "sky" | "slate";

function describeStatus(
  connection: ConnectionState,
  agentState: ReturnType<typeof useVoiceAssistant>["state"],
  hasAgent: boolean,
  hadAgent: boolean,
  agentName?: string,
): { label: string; tone: Tone; pulse?: boolean } {
  if (connection === ConnectionState.Connecting) return { label: "Connecting...", tone: "amber", pulse: true };
  if (connection === ConnectionState.Reconnecting || connection === ConnectionState.SignalReconnecting)
    return { label: "Reconnecting...", tone: "amber", pulse: true };
  if (connection === ConnectionState.Disconnected) return { label: "Call ended", tone: "slate" };

  if (!hasAgent) {
    return hadAgent
      ? { label: "Transferring your call...", tone: "sky", pulse: true }
      : { label: "Connected · Ringing dispatch...", tone: "amber", pulse: true };
  }

  const who = agentName ?? "Dispatcher";
  switch (agentState) {
    case "speaking":
      return { label: `${who} is speaking`, tone: "amber", pulse: true };
    case "thinking":
      return { label: `${who} is thinking...`, tone: "sky", pulse: true };
    case "listening":
      return { label: "Listening to you", tone: "green" };
    case "initializing":
    case "connecting":
    case "pre-connect-buffering":
      return { label: `${who} is picking up...`, tone: "amber", pulse: true };
    default:
      return { label: "Connected", tone: "green" };
  }
}

const TONES: Record<Tone, string> = {
  amber: "border-amber-400/30 bg-amber-400/10 text-amber-200 [--dot:var(--color-amber-400)]",
  green: "border-emerald-400/30 bg-emerald-400/10 text-emerald-200 [--dot:var(--color-emerald-400)]",
  sky: "border-sky-400/30 bg-sky-400/10 text-sky-200 [--dot:var(--color-sky-400)]",
  slate: "border-white/10 bg-white/5 text-slate-300 [--dot:var(--color-slate-400)]",
};

function StatusLine({ label, tone, pulse }: { label: string; tone: Tone; pulse?: boolean }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`inline-flex items-center gap-2.5 rounded-full border px-4 py-1.5 text-sm font-medium ${TONES[tone]}`}
    >
      <span className="relative flex h-2 w-2">
        {pulse && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--dot)] opacity-75" />}
        <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--dot)]" />
      </span>
      {label}
    </div>
  );
}
