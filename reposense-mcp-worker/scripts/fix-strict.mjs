import fs from "node:fs";
import path from "node:path";

const repoRoot = process.cwd();

function write(rel, content) {
  const abs = path.join(repoRoot, rel);
  fs.mkdirSync(path.dirname(abs), { recursive: true });
  fs.writeFileSync(abs, content.trimStart(), "utf8");
  console.log(`wrote: ${rel}`);
}

function patch(rel, fn) {
  const abs = path.join(repoRoot, rel);
  const before = fs.readFileSync(abs, "utf8");
  const after = fn(before);
  if (before !== after) {
    fs.writeFileSync(abs, after, "utf8");
    console.log(`patched: ${rel}`);
  } else {
    console.log(`no changes: ${rel}`);
  }
}

/* 1) Fix envelope exports + exactOptionalPropertyTypes handling */
write(
  "src/envelope.ts",
  `
export const MCP_VERSION = "2024-11-05";

export type EnvelopeMeta = {
  timestamp: string;
  version: string;
  tool_name: string;
  rid: string;
  rate_limit?: { remaining: number; reset: number; limit: number };
};

export type ToolEnvelope = {
  ok: boolean;
  data?: unknown;
  error?: string;
  warnings?: string[];
  stats?: Record<string, unknown>;
  meta: EnvelopeMeta;
  _mcp_version: string;
};

export function buildOk(
  meta: EnvelopeMeta,
  data: unknown,
  extras?: { warnings?: string[]; stats?: Record<string, unknown> }
): ToolEnvelope {
  const out: ToolEnvelope = {
    ok: true,
    data,
    meta,
    _mcp_version: MCP_VERSION
  };
  if (extras?.warnings) out.warnings = extras.warnings;
  if (extras?.stats) out.stats = extras.stats;
  return out;
}

export function buildErr(
  meta: EnvelopeMeta,
  error: string,
  extras?: { warnings?: string[]; stats?: Record<string, unknown> }
): ToolEnvelope {
  const out: ToolEnvelope = {
    ok: false,
    error,
    meta,
    _mcp_version: MCP_VERSION
  };
  if (extras?.warnings) out.warnings = extras.warnings;
  if (extras?.stats) out.stats = extras.stats;
  return out;
}
`
);

/* 2) Fix KV cache strict types + cursor handling */
write(
  "src/cache.ts",
  `
import { sha256Hex } from "./util";

type CacheEntry = { v: unknown; ts: string };

const TTL: Record<string, number> = {
  tree: 300,
  file: 600,
  branches: 120,
  search: 60,
  rate_limit: 30
};

export type CacheBucket = keyof typeof TTL;

export type Cache = {
  get: <T>(tool: string, args: unknown, bucket: CacheBucket, noCache: boolean) => Promise<T | null>;
  set: (tool: string, args: unknown, bucket: CacheBucket, value: unknown) => Promise<void>;
  clearAll: () => Promise<{ deleted: number; warning?: string }>;
  stats: () => Promise<{ approx_keys: number }>;
};

function canonical(obj: unknown): string {
  if (!obj || typeof obj !== "object") return JSON.stringify(obj);
  return JSON.stringify(obj, Object.keys(obj as Record<string, unknown>).sort());
}

export function makeCache(kv: KVNamespace): Cache {
  async function key(tool: string, args: unknown): Promise<string> {
    const base = \`\${tool}:\${canonical(args ?? {})}\`;
    const h = await sha256Hex(base);
    return \`cache:v1:\${tool}:\${h}\`;
  }

  return {
    async get<T>(tool: string, args: unknown, bucket: CacheBucket, noCache: boolean): Promise<T | null> {
      if (noCache) return null;
      const k = await key(tool, args);
      const raw = await kv.get(k);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as CacheEntry;
      return parsed.v as T;
    },

    async set(tool: string, args: unknown, bucket: CacheBucket, value: unknown): Promise<void> {
      const k = await key(tool, args);
      const ttl = TTL[bucket];
      const entry: CacheEntry = { v: value, ts: new Date().toISOString() };
      await kv.put(k, JSON.stringify(entry), { expirationTtl: ttl });
    },

    async clearAll(): Promise<{ deleted: number; warning?: string }> {
      let cursor = null;
      let deleted = 0;

      for (;;) {
        const opts = cursor ? { prefix: "cache:v1:", cursor } : { prefix: "cache:v1:" };
        const res = await kv.list(opts);

        for (const k of res.keys) {
          await kv.delete(k.name);
          deleted++;
        }

        if (res.list_complete) break;

        const next = (res as unknown as { cursor?: string }).cursor;
        cursor = next ?? null;
        if (!cursor) break;
      }

      return { deleted, warning: "KV is eventually consistent; stale reads may persist briefly." };
    },

    async stats(): Promise<{ approx_keys: number }> {
      const res = await kv.list({ prefix: "cache:v1:" });
      return { approx_keys: res.keys.length };
    }
  };
}
`
);

/* 3) Fix GitHub auth optional fields */
write(
  "src/github/auth.ts",
  `
import { putStoredToken } from "./token_store";

type Env = any;

export async function deviceStart(env: Env): Promise<{ device_code: string; user_code: string; verification_uri: string; expires_in: number; interval: number }> {
  const res = await fetch("https://github.com/login/device/code", {
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      "accept": "application/json"
    },
    body: new URLSearchParams({
      client_id: env.GITHUB_CLIENT_ID,
      scope: "repo read:user"
    }).toString()
  });
  const json = (await res.json()) as any;
  if (!json.device_code) throw new Error("failed to start device flow");
  return {
    device_code: String(json.device_code),
    user_code: String(json.user_code),
    verification_uri: String(json.verification_uri),
    expires_in: Number(json.expires_in),
    interval: Number(json.interval ?? 5)
  };
}

export async function devicePoll(
  env: Env,
  device_code: string
): Promise<
  | { status: "pending"; error: string; interval?: number }
  | { status: "ok"; scope?: string }
> {
  const res = await fetch("https://github.com/login/oauth/access_token", {
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      "accept": "application/json"
    },
    body: new URLSearchParams({
      client_id: env.GITHUB_CLIENT_ID,
      client_secret: env.GITHUB_CLIENT_SECRET,
      device_code,
      grant_type: "urn:ietf:params:oauth:grant-type:device_code"
    }).toString()
  });

  const json = (await res.json()) as any;

  if (json.error) {
    const out = { status: "pending", error: String(json.error) };
    if (json.interval) out.interval = Number(json.interval);
    return out;
  }

  if (!json.access_token) throw new Error("device poll failed");

  const scope = json.scope ? String(json.scope) : undefined;

  if (scope) {
    await putStoredToken(env, { access_token: String(json.access_token), token_type: String(json.token_type), scope });
    const ok = { status: "ok" };
    ok.scope = scope;
    return ok;
  }

  await putStoredToken(env, { access_token: String(json.access_token), token_type: String(json.token_type) });
  return { status: "ok" };
}
`
);

/* 4) Fix GitHub client response type (rate optional) */
write(
  "src/github/client.ts",
  `
import type { RateLimit } from "./types";
import { getStoredToken } from "./token_store";

type Env = any;

export type GitHubResponse<T> = { data: T; rate?: RateLimit; status: number };

function parseRate(headers: Headers): RateLimit | undefined {
  const limit = headers.get("x-ratelimit-limit");
  const remaining = headers.get("x-ratelimit-remaining");
  const reset = headers.get("x-ratelimit-reset");
  if (!limit || !remaining || !reset) return undefined;
  const l = Number(limit);
  const r = Number(remaining);
  const rs = Number(reset);
  if (!Number.isFinite(l) || !Number.isFinite(r) || !Number.isFinite(rs)) return undefined;
  return { limit: l, remaining: r, reset: rs };
}

export class GitHubClient {
  private env: Env;

  constructor(env: Env) {
    this.env = env;
  }

  async request<T>(path: string, init?: RequestInit): Promise<GitHubResponse<T>> {
    const token = await getStoredToken(this.env);
    const headers = new Headers(init?.headers ?? {});
    headers.set("accept", "application/vnd.github+json");
    headers.set("user-agent", "reposense-mcp-worker");
    headers.set("x-github-api-version", "2022-11-28");
    if (token) headers.set("authorization", \`Bearer \${token}\`);

    const res = await fetch(\`https://api.github.com\${path}\`, { ...init, headers });
    const rate = parseRate(res.headers);
    const status = res.status;

    if (status === 204) return { data: undefined as T, rate, status };

    const text = await res.text();
    const json = text ? (JSON.parse(text) as T) : (undefined as T);

    return { data: json, rate, status };
  }
}
`
);

/* 5) Fix token_store BufferSource typing */
write(
  "src/github/token_store.ts",
  `
import { b64url, fromB64url } from "../util";

type Env = any;

function decodeKeyB64(keyB64: string): Uint8Array {
  const raw = fromB64url(keyB64.replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=+$/g, ""));
  if (raw.byteLength !== 32) throw new Error("CACHE_ENCRYPTION_KEY must be 32 bytes base64");
  return raw;
}

async function aesKey(env: Env): Promise<CryptoKey> {
  const raw = decodeKeyB64(env.CACHE_ENCRYPTION_KEY);
  const ab = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
  return crypto.subtle.importKey("raw", ab, { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
}

export async function putStoredToken(env: Env, token: { access_token: string; token_type: string; scope?: string }): Promise<void> {
  const key = await aesKey(env);
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const pt = new TextEncoder().encode(JSON.stringify({ ...token, obtained_at: new Date().toISOString() }));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, pt);
  const combined = new Uint8Array(nonce.byteLength + ct.byteLength);
  combined.set(nonce, 0);
  combined.set(new Uint8Array(ct), nonce.byteLength);
  await env.AUTH_KV.put("gh:token:v1", b64url(combined));
}

export async function getStoredToken(env: Env): Promise<string | null> {
  const raw = await env.AUTH_KV.get("gh:token:v1");
  if (!raw) return null;
  const key = await aesKey(env);
  const combined = fromB64url(raw);
  if (combined.byteLength < 13) return null;
  const nonce = combined.slice(0, 12);
  const ct = combined.slice(12);
  const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: nonce }, key, ct);
  const parsed = JSON.parse(new TextDecoder().decode(pt)) as { access_token: string };
  return parsed.access_token ?? null;
}

export async function clearStoredToken(env: Env): Promise<void> {
  await env.AUTH_KV.delete("gh:token:v1");
}
`
);

/* 6) Fix session BufferSource typing */
patch("src/session.ts", (s) => {
  s = s.replace(
    /const sig = await crypto\.subtle\.sign\("HMAC", key, msg\);\s*\n\s*return new Uint8Array\(sig\);/m,
    `const ab = msg.buffer.slice(msg.byteOffset, msg.byteOffset + msg.byteLength);
  const sig = await crypto.subtle.sign("HMAC", key, ab);
  return new Uint8Array(sig);`
  );
  return s;
});

/* 7) Fix tools that pass warnings: undefined */
patch("src/tools/auth.ts", (s) => {
  s = s.replace(
    /return buildErr\(ctx\.meta,\s*polled\.error,\s*\{\s*warnings:\s*polled\.interval\s*\?\s*\[`poll interval: \$\{polled\.interval\}s`\]\s*:\s*undefined\s*\}\s*\);/g,
    `if (polled.interval) return buildErr(ctx.meta, polled.error, { warnings: [\`poll interval: \${polled.interval}s\`] });
  return buildErr(ctx.meta, polled.error);`
  );
  return s;
});

patch("src/tools/cache.ts", (s) => {
  s = s.replace(
    /return buildOk\(ctx\.meta,\s*res,\s*\{\s*warnings:\s*res\.warning\s*\?\s*\[res\.warning\]\s*:\s*undefined\s*\}\s*\);/g,
    `if (res.warning) return buildOk(ctx.meta, res, { warnings: [res.warning] });
  return buildOk(ctx.meta, res);`
  );
  return s;
});