import fs from "node:fs";
import path from "node:path";
import type { NextConfig } from "next";

/** Walk up from the frontend dir to the repo root and load the master .env. */
function loadRootEnv(): Record<string, string> {
  let dir = process.cwd();
  for (let i = 0; i < 8; i++) {
    const candidate = path.join(dir, ".env");
    if (fs.existsSync(candidate)) {
      const out: Record<string, string> = {};
      for (const raw of fs.readFileSync(candidate, "utf-8").split(/\r?\n/)) {
        const line = raw.trim();
        if (!line || line.startsWith("#")) continue;
        const eq = line.indexOf("=");
        if (eq === -1) continue;
        out[line.slice(0, eq).trim()] = line.slice(eq + 1).trim();
      }
      return out;
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return {};
}

const rootEnv = loadRootEnv();

const nextConfig: NextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_BASE_URL:
      rootEnv.NEXT_PUBLIC_API_BASE_URL || "http://localhost:4000",
    NEXT_PUBLIC_GATEWAY_API_KEY: rootEnv.NEXT_PUBLIC_GATEWAY_API_KEY || "",
    NEXT_PUBLIC_APP_NAME: rootEnv.NEXT_PUBLIC_APP_NAME || "Aetheris Core",
  },
};

export default nextConfig;
