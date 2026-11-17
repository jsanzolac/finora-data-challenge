// Self-hosts the audio worklets the ElevenLabs SDK needs, so the CSP can stay at
// script-src 'self' (no blob:, data: or public CDN). Copied from the installed, pinned
// packages into public/voice/ only for voice builds (NEXT_PUBLIC_VOICE=1); removed otherwise,
// so a default build ships none of them.
import { copyFileSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const target = join(root, "public", "voice");
const files = [
  ["node_modules/@elevenlabs/client/worklets/rawAudioProcessor.js", "rawAudioProcessor.js"],
  ["node_modules/@elevenlabs/client/worklets/audioConcatProcessor.js", "audioConcatProcessor.js"],
  ["node_modules/@alexanderolsen/libsamplerate-js/dist/libsamplerate.worklet.js", "libsamplerate.worklet.js"],
];

rmSync(target, { recursive: true, force: true });
if (process.env.NEXT_PUBLIC_VOICE === "1") {
  mkdirSync(target, { recursive: true });
  for (const [from, to] of files) copyFileSync(join(root, from), join(target, to));
  console.log(`voice-assets: ${files.length} worklets in public/voice/`);
} else {
  console.log("voice-assets: voice off, public/voice/ removed");
}
