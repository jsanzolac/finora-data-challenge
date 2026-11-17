"use client";

/**
 * The real voice session: @elevenlabs/react `useConversation`, started with the signed
 * URL from POST /api/agent-session (contracts/agent_api_contract.md). Loaded lazily, so
 * the SDK only downloads when a user starts talking. Websocket transport (signed URL).
 */
import { useEffect, useRef } from "react";
import { ConversationProvider, useConversation } from "@elevenlabs/react";
import type { SessionEvents, SessionStart } from "./session";

type Tools = Record<string, (parameters: unknown) => Promise<string>>;

function Session({ takeStart, clientTools, events }: { takeStart: () => SessionStart | null; clientTools: Tools; events: SessionEvents }) {
  const conversation = useConversation({
    clientTools: clientTools as Record<string, (parameters: Record<string, unknown>) => Promise<string>>,
    onStatusChange: ({ status }) => {
      if (status === "connecting" || status === "connected" || status === "disconnected") events.onStatus(status);
    },
    onModeChange: ({ mode }) => events.onMode(mode),
    onMessage: ({ role, message }) => events.onMessage(role === "user" ? "user" : "agent", message),
    onError: (message) => events.onError(String(message)),
    onDisconnect: () => events.onStatus("disconnected"),
  });
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const config = takeStart();
    if (!config) {
      events.onError("no session config");
      return;
    }
    events.onStatus("connecting");
    events.registerEnd(() => conversation.endSession());
    try {
      conversation.startSession({
        signedUrl: config.signedUrl,
        dynamicVariables: config.dynamicVariables,
        connectionType: "websocket",
        // Self-hosted (scripts/voice-assets.mjs), so the CSP needs no blob:, data: or CDN in script-src.
        workletPaths: { rawAudioProcessor: "/voice/rawAudioProcessor.js", audioConcatProcessor: "/voice/audioConcatProcessor.js" },
        libsampleratePath: "/voice/libsamplerate.worklet.js",
      });
    } catch (error) {
      events.onError(error instanceof Error ? error.message : "start failed");
    }
    // The provider ends the session explicitly (stop), so React's dev double-mount can't end it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}

export default function ElevenLabsHost(props: { takeStart: () => SessionStart | null; clientTools: Tools; events: SessionEvents }) {
  return (
    <ConversationProvider>
      <Session {...props} />
    </ConversationProvider>
  );
}
