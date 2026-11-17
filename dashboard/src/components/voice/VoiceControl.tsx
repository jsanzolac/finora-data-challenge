"use client";

import * as Dialog from "@radix-ui/react-dialog";
import clsx from "clsx";
import { AudioLines, Captions, CaptionsOff, Mic, MicOff, PhoneOff } from "lucide-react";
import { useVoice, type VoiceState } from "./VoiceProvider";

const TEXT: Record<VoiceState, string> = {
  idle: "Hablar con el analista",
  permission: "Hablar con el analista",
  connecting: "Conectando…",
  listening: "Escuchando…",
  speaking: "El analista está hablando…",
  ended: "Conversación terminada",
  unavailable: "La voz no está disponible ahora",
};

/** What a click does, after the visible text (the accessible name starts with the visible label, WCAG 2.5.3). */
const ACTION: Record<VoiceState, string> = {
  idle: "",
  permission: "",
  connecting: "Cancelar",
  listening: "Terminar la conversación",
  speaking: "Terminar la conversación",
  ended: "Hablar de nuevo",
  unavailable: "Intentar de nuevo",
};

function accessibleName(state: VoiceState): string {
  return ACTION[state] ? `${TEXT[state]} ${ACTION[state]}` : TEXT[state];
}

/** The mic button in the header, the microphone explanation, and the captions toggle. */
export function VoiceControl() {
  const voice = useVoice();
  const active = voice.state === "listening" || voice.state === "speaking";
  const Icon = voice.state === "unavailable" ? MicOff : voice.state === "speaking" ? AudioLines : active ? PhoneOff : Mic;

  return (
    <div lang="es" className="flex items-center gap-1" data-testid="voice-control" data-state={voice.state}>
      <button
        type="button"
        onClick={() => (active || voice.state === "connecting" ? voice.stop() : voice.start())}
        aria-label={accessibleName(voice.state)}
        title={voice.reason ?? accessibleName(voice.state)}
        className={clsx(
          "flex min-h-10 items-center gap-2 rounded-full border px-3 text-[0.9375rem] whitespace-nowrap",
          active ? "border-accent bg-surface-2 text-ink" : "border-line-strong text-ink-2 hover:bg-surface-3 hover:text-ink",
        )}
        data-testid="voice-button"
      >
        {voice.state === "connecting" ? (
          <span aria-hidden="true" className="size-4 rounded-full border-2 border-line-strong border-t-accent motion-safe:animate-spin" />
        ) : active ? (
          <span aria-hidden="true" className="relative flex size-4 items-center justify-center">
            <span className="absolute inline-flex size-3 rounded-full bg-accent opacity-60 motion-safe:animate-ping" />
            <Icon size={16} className="relative" />
          </span>
        ) : (
          <Icon aria-hidden="true" size={16} />
        )}
        <span className="hidden lg:inline" data-testid="voice-text">
          {TEXT[voice.state]}
        </span>
      </button>
      {active ? (
        <button
          type="button"
          aria-pressed={voice.captions}
          aria-label={voice.captions ? "Ocultar subtítulos" : "Mostrar subtítulos"}
          onClick={() => voice.setCaptions(!voice.captions)}
          className="flex size-10 items-center justify-center rounded-full text-ink-2 hover:bg-surface-3 hover:text-ink"
          data-testid="captions-toggle"
        >
          {voice.captions ? <Captions aria-hidden="true" size={18} /> : <CaptionsOff aria-hidden="true" size={18} />}
        </button>
      ) : null}
      <p className="sr-only" aria-live="polite" data-testid="voice-status">
        {voice.state === "unavailable" ? voice.reason ?? TEXT.unavailable : TEXT[voice.state]}
        {voice.announcement ? `. ${voice.announcement}` : ""}
      </p>

      <Dialog.Root open={voice.state === "permission"} onOpenChange={(open) => (open ? null : voice.cancelPermission())}>
        <Dialog.Portal>
          <Dialog.Overlay className="overlay-enter fixed inset-0 z-40 bg-overlay" />
          <Dialog.Content
            lang="es"
            className="overlay-enter fixed top-1/2 left-1/2 z-50 flex w-[calc(100vw-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 flex-col gap-4 rounded-xl border border-line-strong bg-bg p-6 shadow-panel"
            data-testid="mic-dialog"
          >
            <Dialog.Title className="text-xl font-semibold">Usar el micrófono</Dialog.Title>
            <Dialog.Description className="text-[0.9375rem] leading-relaxed text-ink-2">
              Para hablar con el analista necesitamos tu micrófono. Solo se usa mientras dura la conversación y puedes terminarla cuando quieras. El
              analista responde con los datos del tablero y nunca ve tu contraseña.
            </Dialog.Description>
            <div className="flex flex-wrap justify-end gap-2">
              <Dialog.Close className="btn-secondary">Cancelar</Dialog.Close>
              <button type="button" className="btn-primary" onClick={voice.confirmPermission} data-testid="mic-allow">
                <Mic aria-hidden="true" size={16} />
                Permitir micrófono
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
