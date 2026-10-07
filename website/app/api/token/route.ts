import { randomBytes } from "crypto";
import { NextResponse } from "next/server";
import { AccessToken } from "livekit-server-sdk";

// Never cache or prerender: every call needs a fresh identity and token.
export const dynamic = "force-dynamic";
export const revalidate = 0;

// ─────────────────────────────────────────────────────────────────────────────
// ROOM NAME PREFIX
// Every call gets its own room: `support_triage_room_<random>`.
//
// Why not one fixed "support_triage_room"? The receptionist worker (agent.py)
// registers WITHOUT an agent_name, so LiveKit auto-dispatches Ava into every
// NEW room, whatever it is called; the Python workers never look at the room
// name. Ava's assistant binds to the FIRST guest who joins, so with one shared
// room a second visitor (or a quick redial) would get silence. And when a call
// ends, the backend deletes the room, so the next caller lands in a fresh room
// anyway. Change the prefix here if you ever need to.
// ─────────────────────────────────────────────────────────────────────────────
const ROOM_PREFIX = "support_triage_room";

export async function GET() {
  const apiKey = process.env.LIVEKIT_API_KEY;
  const apiSecret = process.env.LIVEKIT_API_SECRET;
  // The browser gets the server URL from this response, so one server-side
  // variable is enough. NEXT_PUBLIC_LIVEKIT_URL is accepted as a fallback.
  const serverUrl = process.env.LIVEKIT_URL ?? process.env.NEXT_PUBLIC_LIVEKIT_URL;

  const missing = [
    !apiKey && "LIVEKIT_API_KEY",
    !apiSecret && "LIVEKIT_API_SECRET",
    !serverUrl && "LIVEKIT_URL",
  ].filter(Boolean);

  if (missing.length > 0) {
    console.error(`[token] Missing environment variable(s): ${missing.join(", ")}`);
    return NextResponse.json(
      { error: `Server is missing ${missing.join(", ")}. Set it in Vercel → Settings → Environment Variables.` },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }

  const suffix = randomBytes(4).toString("hex");
  const identity = `exhibition_guest_${Math.floor(100000 + Math.random() * 900000)}`;
  const roomName = `${ROOM_PREFIX}_${suffix}`;

  try {
    const at = new AccessToken(apiKey, apiSecret, {
      identity,
      name: "Website Visitor",
      ttl: "15m",
    });
    at.addGrant({
      room: roomName,
      roomJoin: true,
      canPublish: true,
      canSubscribe: true,
      canPublishData: true,
    });

    // toJwt() is async in livekit-server-sdk v2.
    const token = await at.toJwt();

    return NextResponse.json(
      { token, serverUrl, roomName, identity },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (err) {
    console.error("[token] Failed to sign LiveKit token", err);
    return NextResponse.json(
      { error: "Could not create a call token." },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }
}
