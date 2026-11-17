"use client";

import { createContext, lazy, Suspense, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, getAgentResult, postAgentSession } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/store";
import { kpiEntry } from "@/lib/voice/kpis";
import { createClientTools, pageOfPath } from "@/lib/voice/tools";
import type { AgentResult } from "@/lib/voice/types";
import type { SessionEvents, SessionStart } from "./session";
import { AgentChartPanel, VoiceCaptions } from "./AgentChartPanel";

const MOCKS_ENABLED = process.env.NEXT_PUBLIC_DQ_MOCKS === "1";
const ElevenLabsHost = lazy(() => import("./ElevenLabsHost"));
const HISTORY = 5;
const TURNS = 3;
const HIGHLIGHT_MS = 2600;

export type VoiceState = "idle" | "permission" | "connecting" | "listening" | "speaking" | "ended" | "unavailable";

export interface Turn {
  id: number;
  role: "user" | "agent";
  text: string;
}

interface VoiceContextValue {
  state: VoiceState;
  /** Why the voice is unavailable, in Spanish. */
  reason: string | null;
  start: () => void;
  confirmPermission: () => void;
  cancelPermission: () => void;
  stop: () => void;
  turns: Turn[];
  captions: boolean;
  setCaptions: (on: boolean) => void;
  charts: AgentResult[];
  activeChartId: string | null;
  panelOpen: boolean;
  selectChart: (id: string) => void;
  closePanel: () => void;
  announcement: string;
}

const VoiceContext = createContext<VoiceContextValue | null>(null);

export function useVoice(): VoiceContextValue {
  const value = useContext(VoiceContext);
  if (!value) throw new Error("useVoice must be used inside <VoiceProvider>");
  return value;
}

const UNAVAILABLE = "La voz no está disponible ahora.";
const NO_MIC = "Necesitamos permiso para usar el micrófono. Puedes activarlo en la configuración del navegador.";
const NO_MIC_API = "Este navegador no permite usar el micrófono aquí.";

async function microphoneGranted(): Promise<boolean> {
  try {
    const status = await navigator.permissions?.query({ name: "microphone" as PermissionName });
    return status?.state === "granted";
  } catch {
    return false;
  }
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/**
 * The voice session for the whole app (it lives above the pages, so client-side
 * navigation keeps it). The ElevenLabs SDK is loaded only when a session starts.
 * The agent token is handed to the session host through a ref and cleared as soon as
 * the host takes it: it is never in React state, storage or logs.
 */
export function VoiceProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { status: authStatus } = useAuth();
  const [state, setState] = useState<VoiceState>("idle");
  const [reason, setReason] = useState<string | null>(null);
  const [sessionKey, setSessionKey] = useState(0);
  const [hostKind, setHostKind] = useState<"elevenlabs" | "mock" | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [captions, setCaptions] = useState(true);
  const [charts, setCharts] = useState<AgentResult[]>([]);
  const [activeChartId, setActiveChartId] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const startRef = useRef<SessionStart | null>(null);
  const endRef = useRef<(() => void) | null>(null);
  const connectedRef = useRef(false);
  const turnId = useRef(0);

  // ------------------------------------------------------------ client tools
  const tools = useMemo(
    () =>
      createClientTools({
        fetchResult: (id) => getAgentResult(id),
        openChart: (result) => {
          setCharts((current) => [result, ...current.filter((entry) => entry.result_id !== result.result_id)].slice(0, HISTORY));
          setActiveChartId(result.result_id);
          setPanelOpen(true);
          setAnnouncement(`Gráfico del analista: ${result.title_es}`);
        },
        currentPage: () => pageOfPath(window.location.pathname),
        navigate: (href) => router.push(href),
        waitForKpi: (kpiId) =>
          new Promise((resolve) => {
            const started = Date.now();
            const look = () => {
              // The visible match (a rule cell exists in the table and in the narrow-screen list),
              // or one inside a closed Details panel, which highlight() opens.
              const matches = [...document.querySelectorAll<HTMLElement>(`[data-kpi-id="${CSS.escape(kpiId)}"]`)];
              const element = matches.find((match) => match.getClientRects().length > 0) ?? matches.find((match) => match.closest("details:not([open])"));
              if (element) return resolve(element);
              if (Date.now() - started > 5000) return resolve(null);
              window.setTimeout(look, 100);
            };
            look();
          }),
        highlight: (element, kpiId) => {
          for (let details = element.closest("details"); details; details = details.parentElement?.closest("details") ?? null) details.open = true;
          element.scrollIntoView({ block: "center", behavior: prefersReducedMotion() ? "auto" : "smooth" });
          element.removeAttribute("data-highlighted");
          void element.offsetWidth; // restart the animation
          element.setAttribute("data-highlighted", "true");
          window.setTimeout(() => element.removeAttribute("data-highlighted"), HIGHLIGHT_MS);
          setAnnouncement(`Resaltado: ${kpiEntry(kpiId)?.label_es ?? kpiId}`);
        },
      }),
    [router],
  );

  // ---------------------------------------------------------- session events
  const events: SessionEvents = useMemo(
    () => ({
      onStatus: (status) => {
        if (status === "connecting") setState("connecting");
        else if (status === "connected") {
          connectedRef.current = true;
          setState((current) => (current === "speaking" ? current : "listening"));
        } else if (status === "disconnected") {
          setHostKind(null);
          endRef.current = null;
          setState((current) => (current === "unavailable" ? current : connectedRef.current ? "ended" : "unavailable"));
          if (!connectedRef.current) setReason((current) => current ?? UNAVAILABLE);
          connectedRef.current = false;
        }
      },
      onMode: (mode) => {
        if (!connectedRef.current) return;
        setState(mode === "speaking" ? "speaking" : "listening");
      },
      onMessage: (role, text) => {
        turnId.current += 1;
        const id = turnId.current;
        setTurns((current) => [...current, { id, role, text }].slice(-TURNS));
      },
      onError: () => {
        setReason(UNAVAILABLE);
        setState("unavailable");
        endRef.current?.();
        endRef.current = null;
        setHostKind(null);
      },
      registerEnd: (end) => {
        endRef.current = end;
      },
    }),
    [],
  );

  /** Hands the session config to the host once, then forgets it (the token included). */
  const takeStart = useCallback((): SessionStart | null => {
    const config = startRef.current;
    startRef.current = null;
    return config;
  }, []);

  // ------------------------------------------------------------ start / stop
  const connect = useCallback(async () => {
    setReason(null);
    setTurns([]);
    setState("connecting");
    if (!navigator.mediaDevices?.getUserMedia) {
      setReason(NO_MIC_API);
      setState("unavailable");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
    } catch {
      setReason(NO_MIC);
      setState("unavailable");
      return;
    }
    try {
      const session = await postAgentSession();
      startRef.current = {
        signedUrl: session.signed_url,
        dynamicVariables: { ...session.dynamic_variables, secret__agent_token: session.agent_token },
      };
      const mock = MOCKS_ENABLED && session.signed_url.startsWith("mock://");
      connectedRef.current = false;
      setHostKind(mock ? "mock" : "elevenlabs");
      setSessionKey((key) => key + 1);
    } catch (error) {
      // 401 and a pending password change are handled by the API client.
      if (error instanceof ApiError && (error.status === 401 || error.code === "password_change_required")) {
        setState("idle");
        return;
      }
      setReason(UNAVAILABLE);
      setState("unavailable");
    }
  }, []);

  const start = useCallback(() => {
    if (state === "connecting" || state === "listening" || state === "speaking" || state === "permission") return;
    void microphoneGranted().then((granted) => {
      if (granted) void connect();
      else setState("permission");
    });
  }, [state, connect]);

  const stop = useCallback(() => {
    endRef.current?.();
    endRef.current = null;
    startRef.current = null;
    setHostKind(null);
    if (connectedRef.current) setState("ended");
    else setState("idle");
    connectedRef.current = false;
  }, []);

  // A signed-out user has no voice session: end it; the host's disconnect updates the state.
  useEffect(() => {
    if (authStatus !== "signedOut") return;
    endRef.current?.();
    endRef.current = null;
    startRef.current = null;
  }, [authStatus]);

  const value: VoiceContextValue = {
    state,
    reason,
    start,
    confirmPermission: () => void connect(),
    cancelPermission: () => setState("idle"),
    stop,
    turns,
    captions,
    setCaptions,
    charts,
    activeChartId,
    panelOpen,
    selectChart: (id) => {
      setActiveChartId(id);
      setPanelOpen(true);
    },
    closePanel: () => setPanelOpen(false),
    announcement,
  };

  return (
    <VoiceContext.Provider value={value}>
      {children}
      <AgentChartPanel />
      <VoiceCaptions />
      {hostKind === "elevenlabs" ? (
        <Suspense fallback={null}>
          <ElevenLabsHost key={sessionKey} takeStart={takeStart} clientTools={tools} events={events} />
        </Suspense>
      ) : null}
      {MOCKS_ENABLED && hostKind === "mock" ? <MockHost key={sessionKey} takeStart={takeStart} clientTools={tools} events={events} /> : null}
    </VoiceContext.Provider>
  );
}

/**
 * Mock builds only: drives a scripted session from dashboard/mocks/voice.ts (installed
 * on window by the mock layer). In a real build MOCKS_ENABLED is false and this never renders.
 */
function MockHost({ takeStart, clientTools, events }: { takeStart: () => SessionStart | null; clientTools: ReturnType<typeof createClientTools>; events: SessionEvents }) {
  useEffect(() => {
    const config = takeStart();
    const driver = (window as unknown as { __FINORA_VOICE_MOCK__?: { start: (tools: typeof clientTools, events: SessionEvents) => () => void } }).__FINORA_VOICE_MOCK__;
    if (!config || !driver) {
      events.onError("mock voice driver missing");
      return;
    }
    const end = driver.start(clientTools, events);
    events.registerEnd(end);
    // The provider ends the session explicitly (stop); nothing to do on unmount.
  }, [takeStart, clientTools, events]);
  return null;
}
