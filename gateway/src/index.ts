/**
 * Aetheris Core API Gateway (Fastify 5 / TypeScript)
 *
 * Responsibilities:
 *  - API-key enforcement (x-api-key) + per-IP rate limiting
 *  - Request IDs + structured access logs
 *  - SSE proxying: POST /api/query streams orchestrator telemetry straight through
 *  - JSON proxying for corpus / stats / graph / ingest / citation verification
 */
import cors from "@fastify/cors";
import rateLimit from "@fastify/rate-limit";
import Fastify, { type FastifyReply, type FastifyRequest } from "fastify";
import { Readable } from "node:stream";
import { randomUUID } from "node:crypto";
import { config } from "./env.js";

const app = Fastify({
  logger: { level: (process.env.APP_LOG_LEVEL ?? "info").trim() || "info" },
  bodyLimit: 6 * 1024 * 1024,
});

await app.register(cors, {
  origin: config.corsOrigins.length ? config.corsOrigins : true,
  credentials: true,
  methods: ["GET", "POST", "DELETE", "OPTIONS"],
});

await app.register(rateLimit, {
  max: config.rateLimit,
  timeWindow: "1 minute",
  keyGenerator: (req) => req.ip,
});

/* ------------------------------ auth hook ------------------------------ */
app.addHook("onRequest", async (req: FastifyRequest, reply: FastifyReply) => {
  const rid = (req.headers["x-request-id"] as string) || randomUUID();
  (req as unknown as { rid: string }).rid = rid;
  reply.header("x-request-id", rid);
  if (req.method === "OPTIONS") return;
  if (!config.requireAuth) return;
  if (req.url === "/api/health") return;
  const key = req.headers["x-api-key"];
  if (key !== config.apiKey) {
    await reply.code(401).send({ error: "invalid or missing x-api-key" });
  }
});

/* ------------------------------ helpers ------------------------------ */
type ProxyBody = Record<string, unknown> | undefined;

async function proxyJson(
  req: FastifyRequest,
  reply: FastifyReply,
  path: string,
  method: "GET" | "POST" | "DELETE" = "GET",
  body?: ProxyBody,
) {
  const started = Date.now();
  try {
    const res = await fetch(`${config.orchestratorUrl}${path}`, {
      method,
      headers: {
        "content-type": "application/json",
        "x-request-id": (req as unknown as { rid: string }).rid,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    const text = await res.text();
    let payload: unknown = null;
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { raw: text };
    }
    req.log.info({ path, method, status: res.status, ms: Date.now() - started },
      "orchestrator proxy");
    return reply.code(res.status).send(payload);
  } catch (err) {
    req.log.error({ err, path }, "orchestrator unreachable");
    return reply.code(502).send({
      error: "orchestrator_unreachable",
      detail: String(err),
      hint: "Start the Python orchestrator:  cd orchestrator && python run.py",
    });
  }
}

/* ------------------------------ routes ------------------------------ */
app.get("/api/health", async (_req, reply) => {
  let orchestrator: Record<string, unknown> = { reachable: false };
  try {
    const res = await fetch(`${config.orchestratorUrl}/api/v1/health`);
    orchestrator = { reachable: res.ok, ...(await res.json()) };
  } catch {
    orchestrator = { reachable: false };
  }
  return reply.send({
    status: "ok",
    service: "aetheris-gateway",
    app: config.appName,
    auth_required: config.requireAuth,
    orchestrator,
    ts: Date.now(),
  });
});

app.get("/api/config", (req, reply) => proxyJson(req, reply, "/api/v1/config"));
app.get("/api/stats", (req, reply) => proxyJson(req, reply, "/api/v1/stats"));
app.get("/api/corpus", (req, reply) => proxyJson(req, reply, "/api/v1/corpus"));
app.delete("/api/corpus", (req, reply) => proxyJson(req, reply, "/api/v1/corpus", "DELETE"));
app.get("/api/graph", (req, reply) => proxyJson(req, reply, "/api/v1/graph"));
app.get("/api/chunks/:id", (req, reply) => {
  const { id } = req.params as { id: string };
  return proxyJson(req, reply, `/api/v1/chunks/${encodeURIComponent(id)}`);
});
app.post("/api/ingest", (req, reply) =>
  proxyJson(req, reply, "/api/v1/ingest", "POST", req.body as ProxyBody),
);
app.post("/api/verify-citation", (req, reply) =>
  proxyJson(req, reply, "/api/v1/verify-citation", "POST", req.body as ProxyBody),
);

/* -------------------- SSE streaming proxy: /api/query -------------------- */
app.post("/api/query", async (req: FastifyRequest, reply: FastifyReply) => {
  const body = (req.body ?? {}) as Record<string, unknown>;
  if (!body.query || typeof body.query !== "string") {
    return reply.code(400).send({ error: "query (string) is required" });
  }
  const started = Date.now();
  let upstream: Response;
  try {
    upstream = await fetch(`${config.orchestratorUrl}/api/v1/query`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-request-id": (req as unknown as { rid: string }).rid,
      },
      body: JSON.stringify(body),
    });
  } catch (err) {
    req.log.error({ err }, "orchestrator unreachable (SSE)");
    return reply.code(502).send({
      error: "orchestrator_unreachable",
      hint: "Start the Python orchestrator:  cd orchestrator && python run.py",
    });
  }

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text().catch(() => "");
    return reply.code(upstream.status).send({ error: "upstream_error", detail: text });
  }

  // hijack the socket and pipe the SSE byte-stream straight through
  reply.hijack();
  reply.raw.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache, no-transform",
    Connection: "keep-alive",
    "X-Accel-Buffering": "no",
    "X-Request-Id": (req as unknown as { rid: string }).rid,
    "Access-Control-Allow-Origin": config.corsOrigins[0] ?? "*",
    "Access-Control-Allow-Credentials": "true",
  });

  const reader = Readable.fromWeb(
    upstream.body as Parameters<typeof Readable.fromWeb>[0],
  );
  reader.pipe(reply.raw);
  reply.raw.on("close", () => reader.destroy());
  req.log.info({ ms: Date.now() - started }, "SSE stream opened");
});

/* ------------------------------ start ------------------------------ */
const start = async () => {
  try {
    await app.listen({ host: config.gatewayHost, port: config.gatewayPort });
    console.log(
      `\n  ⚡ Aetheris Gateway  →  http://${config.gatewayHost}:${config.gatewayPort}` +
        `\n     proxying         →  ${config.orchestratorUrl}` +
        `\n     auth enforced    →  ${config.requireAuth}\n`,
    );
  } catch (err) {
    app.log.error(err);
    process.exit(1);
  }
};

void start();


