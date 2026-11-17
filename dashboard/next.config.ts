import type { NextConfig } from "next";
import { resolve } from "node:path";
import { PHASE_PRODUCTION_BUILD } from "next/constants";

/**
 * Static export: the build is uploaded to S3 and served through CloudFront.
 * No server, no middleware, no route handlers. State travels in the query string.
 *
 * Mock mode (NEXT_PUBLIC_DQ_MOCKS=1) is for local development and the e2e smoke
 * test only. A mock build is refused unless DQ_MOCK_EXPORT=1 is also set, and it
 * is written to out-mock/, never to out/ (the directory that gets deployed).
 */
export default function config(phase: string): NextConfig {
  const mocks = process.env.NEXT_PUBLIC_DQ_MOCKS === "1";
  const mockExport = process.env.DQ_MOCK_EXPORT === "1";

  if (phase === PHASE_PRODUCTION_BUILD && mocks && !mockExport) {
    throw new Error(
      "NEXT_PUBLIC_DQ_MOCKS=1 is set for a production build. Unset it, or use `npm run build:mock` (writes to out-mock/).",
    );
  }
  if (phase === PHASE_PRODUCTION_BUILD && mockExport && !mocks) {
    throw new Error("DQ_MOCK_EXPORT=1 needs NEXT_PUBLIC_DQ_MOCKS=1. Use `npm run build:mock`.");
  }

  // The only door into dashboard/mocks/. Without the flag it leads to a stub.
  const mockInstall = mocks ? "./mocks/install.ts" : "./src/lib/mock-switch/disabled.ts";
  // The only door into the voice UI (and the ElevenLabs SDK). Off unless NEXT_PUBLIC_VOICE=1.
  const voice = process.env.NEXT_PUBLIC_VOICE === "1" ? "./src/components/voice/index.ts" : "./src/lib/voice/disabled.tsx";

  return {
    output: "export",
    turbopack: { resolveAlias: { "@dq/mock-install": mockInstall, "@finora/voice": voice } },
    webpack: (webpackConfig: { resolve: { alias: Record<string, string> } }) => {
      webpackConfig.resolve.alias["@dq/mock-install"] = resolve(process.cwd(), mockInstall);
      webpackConfig.resolve.alias["@finora/voice"] = resolve(process.cwd(), voice);
      return webpackConfig;
    },
    trailingSlash: true,
    distDir: mocks && mockExport ? "out-mock" : "out",
    images: { unoptimized: true },
    devIndicators: false,
    reactStrictMode: true,
  };
}
