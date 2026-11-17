/**
 * What `@finora/voice` resolves to in every build without NEXT_PUBLIC_VOICE=1 (see
 * next.config.ts): no voice control, no provider, and no ElevenLabs SDK in the bundle.
 */
export function VoiceProvider({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

export function VoiceControl() {
  return null;
}
