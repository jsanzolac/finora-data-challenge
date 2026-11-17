/**
 * The voice UI ships only when built with NEXT_PUBLIC_VOICE=1. Off by default, so a
 * normal production build has no voice code path and does not bundle the ElevenLabs SDK.
 */
export const VOICE_ENABLED = process.env.NEXT_PUBLIC_VOICE === "1";
