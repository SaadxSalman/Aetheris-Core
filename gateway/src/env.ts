/**
 * Loads the single root .env shared by the whole Aetheris Core monorepo.
 * Walks upward from cwd and from this module until it finds ".env".
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

function parseEnvFile(content: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    out[key] = value;
  }
  return out;
}

function findRootEnv(startDir: string): Record<string, string> | null {
  let dir = startDir;
  for (let i = 0; i < 8; i++) {
    const candidate = path.join(dir, ".env");
    if (fs.existsSync(candidate)) {
      return parseEnvFile(fs.readFileSync(candidate, "utf-8"));
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

const fileEnv = findRootEnv(process.cwd()) ?? findRootEnv(here) ?? {};
/** Root .env values merged over process.env (process.env wins for overrides). */
export const env: Record<string, string> = { ...fileEnv };

export function str(key: string, fallback = ""): string {
  return (process.env[key] ?? env[key] ?? fallback).trim() || fallback;
}
export function int(key: string, fallback: number): number {
  const raw = process.env[key] ?? env[key];
  const n = Number(raw);
  return Number.isFinite(n) ? n : fallback;
}
export function bool(key: string, fallback: boolean): boolean {
  const raw = (process.env[key] ?? env[key] ?? "").toLowerCase();
  if (!raw) return fallback;
  return ["1", "true", "yes", "on"].includes(raw);
}

export const config = {
  gatewayHost: str("GATEWAY_HOST", "127.0.0.1"),
  gatewayPort: int("GATEWAY_PORT", 4000),
  orchestratorUrl: str("ORCHESTRATOR_URL", "http://127.0.0.1:8000").replace(/\/+$/, ""),
  corsOrigins: str("CORS_ORIGINS", "http://localhost:3000")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean),
  apiKey: str("GATEWAY_API_KEY"),
  requireAuth: bool("GATEWAY_REQUIRE_AUTH", false),
  rateLimit: int("GATEWAY_RATE_LIMIT_PER_MIN", 120),
  appName: str("APP_NAME", "Aetheris Core"),
};
