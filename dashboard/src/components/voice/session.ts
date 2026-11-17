/** What a session host (ElevenLabs or the mock) receives and reports back. */
export interface SessionStart {
  signedUrl: string;
  /** Includes `secret__agent_token`. Read once by the host, then dropped. */
  dynamicVariables: Record<string, string | number | boolean>;
}

export interface SessionEvents {
  onStatus: (status: "connecting" | "connected" | "disconnected") => void;
  onMode: (mode: "speaking" | "listening") => void;
  onMessage: (role: "user" | "agent", text: string) => void;
  onError: (message: string) => void;
  /** The host registers how to end its session; the provider calls it on stop. */
  registerEnd: (end: () => void) => void;
}
