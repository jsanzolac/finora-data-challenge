// Minimal static file server for a Next.js static export.
// It applies the same clean-URL rewrite the CloudFront Function must apply:
//   /            -> /index.html
//   /login/      -> /login/index.html
//   /login       -> /login/index.html
// Anything else that is missing gets 404.html with status 404.
// Usage: node scripts/serve-static.mjs <dir> <port>
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, normalize, resolve, sep } from "node:path";

const root = resolve(process.argv[2] ?? "out");
const port = Number(process.argv[3] ?? 4173);

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".png": "image/png",
  ".woff2": "font/woff2",
  ".map": "application/json",
};

export function rewrite(uri) {
  if (uri.endsWith("/")) return `${uri}index.html`;
  if (!uri.split("/").pop().includes(".")) return `${uri}/index.html`;
  return uri;
}

async function exists(file) {
  try {
    return (await stat(file)).isFile();
  } catch {
    return false;
  }
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", "http://localhost");
  if (url.pathname.startsWith("/api/")) {
    // There is no API behind this server. In mock mode the browser never gets here.
    res.writeHead(502, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { code: "no_api", message: "No API behind the static server." } }));
    return;
  }
  const rel = normalize(decodeURIComponent(rewrite(url.pathname)));
  let file = join(root, rel);
  if (file !== root && !file.startsWith(root + sep)) {
    res.writeHead(400);
    res.end();
    return;
  }
  let status = 200;
  if (!(await exists(file))) {
    file = join(root, "404.html");
    status = 404;
  }
  try {
    const body = await readFile(file);
    res.writeHead(status, {
      "content-type": TYPES[extname(file)] ?? "application/octet-stream",
      "cache-control": "no-store",
    });
    res.end(body);
  } catch {
    res.writeHead(404);
    res.end("Not found");
  }
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Serving ${root} at http://127.0.0.1:${port}`);
});
