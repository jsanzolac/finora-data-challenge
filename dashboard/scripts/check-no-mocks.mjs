// Fails the build if the mock layer leaked into the deployable export.
// Usage: node scripts/check-no-mocks.mjs <dir>
import { readdir, readFile } from "node:fs/promises";
import { join, resolve } from "node:path";

const root = resolve(process.argv[2] ?? "out");
// Strings that only exist in dashboard/mocks/ (DQ and acquisition fixtures, the mock API).
const MARKERS = [
  "__DQ_MOCK_LAYER__",
  "dq_mock_session",
  "finora-demo-",
  // Acquisition mocks (dashboard/mocks/acq/).
  "__ACQ_MOCK_LAYER__",
  "acq_mock_rate_rows",
  "acq_mock_no_gold_run",
  "mock-fixture-not-a-real-model-hash",
  "proposal_close_045",
  "Q4 plan (typo)",
  // MRR mocks (dashboard/mocks/mrr/).
  "__MRR_MOCK_LAYER__",
  "mrr_mock_no_gold_run",
  "mrr-mock-fixture-not-a-real-model-hash",
  // Voice mocks (dashboard/mocks/voice.ts).
  "mock://finora-voice",
  "mock-agent-token-not-a-secret",
  "voice_mock_unavailable",
  "r_mock_ticket_by_industry",
  "conversation_signature=mock-signature",
];

async function* walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(full);
    else yield full;
  }
}

const hits = [];
let files = 0;
for await (const file of walk(root)) {
  if (!/\.(js|html|txt|json|css)$/.test(file)) continue;
  files += 1;
  const text = await readFile(file, "utf8");
  for (const marker of MARKERS) {
    if (text.includes(marker)) hits.push(`${file}: ${marker}`);
  }
}

if (hits.length > 0) {
  console.error(`Mock layer found in ${root}. This build must not be deployed:\n${hits.join("\n")}`);
  process.exit(1);
}
console.log(`check-no-mocks: ${files} files in ${root}, no mock code found.`);
