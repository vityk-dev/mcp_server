// src/oauth.ts

type Env = {
  OAUTH_KV: KVNamespace;

  OAUTH_CLIENT_ID: string;
  OAUTH_CLIENT_SECRET: string;
  OAUTH_REDIRECT_URIS: string; // comma-separated
  OAUTH_ISSUER?: string;
  CF_ACCESS_TEAM_DOMAIN?: string;
};

type OAuthTokenResponse = {
  access_token: string;
  token_type: "Bearer";
  expires_in: number;
  scope?: string;
};

const AUTHZ_CODE_TTL_SEC = 10 * 60; // 10 min
const ACCESS_TOKEN_TTL_SEC = 60 * 60; // 60 min

function issuerFromReq(req: Request, env: Env): string {
  if (env.OAUTH_ISSUER && env.OAUTH_ISSUER.trim()) return env.OAUTH_ISSUER.trim();
  const u = new URL(req.url);
  return `${u.protocol}//${u.host}`;
}

function splitRedirectUris(env: Env): string[] {
  return (env.OAUTH_REDIRECT_URIS || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function badRequest(msg: string): Response {
  return Response.json({ error: "invalid_request", error_description: msg }, { status: 400 });
}

function unauthorized(msg: string): Response {
  return Response.json({ error: "invalid_client", error_description: msg }, { status: 401 });
}

function randB64url(bytesLen = 32): string {
  const u8 = crypto.getRandomValues(new Uint8Array(bytesLen));
  let s = "";
  for (let i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]!);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function nowSec(): number {
  return Math.floor(Date.now() / 1000);
}

async function kvPutJson(env: Env, key: string, value: unknown, ttlSec: number) {
  await env.OAUTH_KV.put(key, JSON.stringify(value), { expirationTtl: ttlSec });
}

async function kvGetJson<T>(env: Env, key: string): Promise<T | null> {
  const raw = await env.OAUTH_KV.get(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function isValidRedirectUri(env: Env, uri: string): boolean {
  return splitRedirectUris(env).includes(uri);
}

type StoredAuthCode = {
  client_id: string;
  redirect_uri: string;
  scope: string;
  created_at: number;
};

type StoredAccessToken = {
  client_id: string;
  scope: string;
  exp: number; // epoch sec
};


export function isOAuthPath(pathname: string): boolean {
  return (
    pathname === "/authorize" ||
    pathname === "/token" ||
    pathname === "/revoke" ||
    pathname === "/.well-known/oauth-authorization-server" ||
    pathname === "/.well-known/openid-configuration" ||
    pathname === "/.well-known/oauth-protected-resource" ||
    pathname === "/.well-known/oauth-authorization-server/mcp" ||
    pathname === "/.well-known/openid-configuration/mcp" ||
    pathname === "/.well-known/oauth-protected-resource/mcp" ||
    pathname === "/mcp/.well-known/oauth-authorization-server" ||
    pathname === "/mcp/.well-known/openid-configuration" ||
    pathname === "/mcp/.well-known/oauth-protected-resource"
  );
}

// Cloudflare Access verification
function getCookieValue(cookieHeader: string, name: string): string | null {
  // very small cookie parser (no deps)
  const parts = cookieHeader.split(";").map((p) => p.trim());
  for (const p of parts) {
    if (!p) continue;
    const eq = p.indexOf("=");
    if (eq < 0) continue;
    const k = p.slice(0, eq).trim();
    const v = p.slice(eq + 1).trim();
    if (k === name) return v;
  }
  return null;
}

function b64urlToBytes(input: string): Uint8Array {
  // base64url -> base64
  let b64 = input.replace(/-/g, "+").replace(/_/g, "/");
  const pad = b64.length % 4;
  if (pad === 2) b64 += "==";
  else if (pad === 3) b64 += "=";
  else if (pad !== 0) throw new Error("invalid base64url length");
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function toArrayBuffer(u8: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(u8.byteLength);
  copy.set(u8);
  return copy.buffer;
}

function decodeJwtPartJson(part: string): any {
  const bytes = b64urlToBytes(part);
  const text = new TextDecoder().decode(bytes);
  return JSON.parse(text);
}

type Jwk = {
  kty: string;
  n?: string;
  e?: string;
  kid?: string;
  alg?: string;
  use?: string;
};

type Jwks = { keys: Jwk[] };

function accessJwksUrl(env: Env): string | null {
  const td = (env.CF_ACCESS_TEAM_DOMAIN || "").trim();
  if (!td) return null;
  return `https://${td}/cdn-cgi/access/certs`;
}

async function fetchAccessJwks(env: Env): Promise<Jwks | null> {
  const url = accessJwksUrl(env);
  if (!url) return null;

  const res = await fetch(url, { method: "GET" });
  if (!res.ok) return null;
  const json = (await res.json().catch(() => null)) as any;
  if (!json || !Array.isArray(json.keys)) return null;
  return json as Jwks;
}

async function importRsaJwk(jwk: Jwk): Promise<CryptoKey> {
  // Cloudflare Access certs are typically RSA keys.
  return crypto.subtle.importKey(
    "jwk",
    jwk as JsonWebKey,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"]
  );
}

async function verifyAccessJwtSignature(env: Env, jwt: string): Promise<boolean> {
  const parts = jwt.split(".");
  if (parts.length !== 3) return false;

  const [h, p, s] = parts;
  if (!h || !p || !s) return false;

  const header = decodeJwtPartJson(h);
  const kid = String(header?.kid || "");
  const alg = String(header?.alg || "");

  // Only accept RS256 here.
  if (alg && alg !== "RS256") return false;

  const jwks = await fetchAccessJwks(env);
  if (!jwks) return false;

  const jwk = jwks.keys.find((k) => (kid ? k.kid === kid : true) && k.kty === "RSA" && k.n && k.e);
  if (!jwk) return false;

  const key = await importRsaJwk(jwk);

  const data = new TextEncoder().encode(`${h}.${p}`);
  const sig = b64urlToBytes(s);

  const ok = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    key,
    toArrayBuffer(sig),
    toArrayBuffer(data)
  );

  if (!ok) return false;

  try {
    const payload = decodeJwtPartJson(p);
    const exp = Number(payload?.exp || 0);
    if (!exp) return false;
    return nowSec() < exp;
  } catch {
    return false;
  }
}

async function isAuthorizedUser(req: Request, env: Env): Promise<boolean> {
  const cookie = req.headers.get("cookie") || "";
  const cookieJwt = getCookieValue(cookie, "CF_Authorization") || "";

  const hdrJwt =
    req.headers.get("cf-access-jwt-assertion") ||
    req.headers.get("Cf-Access-Jwt-Assertion") ||
    "";

  const jwt = cookieJwt || hdrJwt;
  if (!jwt) return false;

  // Strong mode (signature verify)
  if ((env.CF_ACCESS_TEAM_DOMAIN || "").trim()) {
    return await verifyAccessJwtSignature(env, jwt);
  }

  // Lightweight mode (policy enforced in Access; just check it exists)
  return true;
}

// OAuth handler
export async function handleOAuth(req: Request, env: Env): Promise<Response> {
  const url = new URL(req.url);
  const path = url.pathname;

  if (
    path === "/.well-known/oauth-authorization-server" ||
    path === "/.well-known/oauth-authorization-server/mcp" ||
    path === "/mcp/.well-known/oauth-authorization-server"
  ) {
    const iss = issuerFromReq(req, env);
    return Response.json(
      {
        issuer: iss,
        authorization_endpoint: `${iss}/authorize`,
        token_endpoint: `${iss}/token`,
        revocation_endpoint: `${iss}/revoke`,
        response_types_supported: ["code"],
        grant_types_supported: ["authorization_code"],
        token_endpoint_auth_methods_supported: ["client_secret_post", "client_secret_basic"],
        scopes_supported: ["mcp"],
      },
      { status: 200 }
    );
  }

  if (
    path === "/.well-known/openid-configuration" ||
    path === "/.well-known/openid-configuration/mcp" ||
    path === "/mcp/.well-known/openid-configuration"
  ) {
    const iss = issuerFromReq(req, env);
    return Response.json(
      {
        issuer: iss,
        authorization_endpoint: `${iss}/authorize`,
        token_endpoint: `${iss}/token`,
        scopes_supported: ["mcp"],
        response_types_supported: ["code"],
        grant_types_supported: ["authorization_code"],
        subject_types_supported: ["public"],
        id_token_signing_alg_values_supported: ["none"],
      },
      { status: 200 }
    );
  }

  if (
    path === "/.well-known/oauth-protected-resource" ||
    path === "/.well-known/oauth-protected-resource/mcp" ||
    path === "/mcp/.well-known/oauth-protected-resource"
  ) {
    const iss = issuerFromReq(req, env);
    return Response.json(
      {
        resource: `${iss}/mcp`,
        authorization_servers: [iss],
        scopes_supported: ["mcp"],
        bearer_methods_supported: ["header"],
      },
      { status: 200 }
    );
  }

  if (path === "/authorize") {
    console.log("[oauth] /authorize url =", req.url);

    if (req.method !== "GET") return new Response("method not allowed", { status: 405 });

    const client_id = url.searchParams.get("client_id") || "";
    const redirect_uri = url.searchParams.get("redirect_uri") || "";
    const response_type = url.searchParams.get("response_type") || "";
    const scope = url.searchParams.get("scope") || "mcp";
    const state = url.searchParams.get("state") || "";

    if (!client_id) return badRequest("missing client_id");
    if (!redirect_uri) return badRequest("missing redirect_uri");
    if (response_type !== "code") return badRequest("response_type must be code");
    if (client_id !== env.OAUTH_CLIENT_ID) return badRequest("unknown client_id");
    if (!isValidRedirectUri(env, redirect_uri)) return badRequest("redirect_uri not allowed");
    const ok = await isAuthorizedUser(req, env);
    if (!ok) {
      return new Response(
        "Not authorized (Cloudflare Access). Protect /authorize with Access and ensure JWT reaches the Worker.",
        { status: 401 }
      );
    }

    const code = randB64url(32);
    const stored: StoredAuthCode = { client_id, redirect_uri, scope, created_at: nowSec() };
    await kvPutJson(env, `code:${code}`, stored, AUTHZ_CODE_TTL_SEC);

    const cb = new URL(redirect_uri);
    cb.searchParams.set("code", code);
    if (state) cb.searchParams.set("state", state);

    return Response.redirect(cb.toString(), 302);
  }

  if (path === "/token") {
    if (req.method !== "POST") return new Response("method not allowed", { status: 405 });

    // Support both client_secret_basic and client_secret_post
    let client_id = "";
    let client_secret = "";

    const auth = req.headers.get("authorization") || "";
    if (auth.startsWith("Basic ")) {
      const raw = atob(auth.slice("Basic ".length));
      const idx = raw.indexOf(":");
      if (idx >= 0) {
        client_id = raw.slice(0, idx);
        client_secret = raw.slice(idx + 1);
      }
    }

    const form = await req.formData().catch(() => null);
    if (!form) return badRequest("token endpoint expects form data");

    if (!client_id) client_id = String(form.get("client_id") || "");
    if (!client_secret) client_secret = String(form.get("client_secret") || "");

    const grant_type = String(form.get("grant_type") || "");
    const code = String(form.get("code") || "");
    const redirect_uri = String(form.get("redirect_uri") || "");

    if (grant_type !== "authorization_code") return badRequest("grant_type must be authorization_code");
    if (!code) return badRequest("missing code");
    if (!redirect_uri) return badRequest("missing redirect_uri");

    if (client_id !== env.OAUTH_CLIENT_ID) return unauthorized("invalid client_id");
    if (client_secret !== env.OAUTH_CLIENT_SECRET) return unauthorized("invalid client_secret");

    const stored = await kvGetJson<StoredAuthCode>(env, `code:${code}`);
    if (!stored) return badRequest("invalid or expired code");
    if (stored.client_id !== client_id) return badRequest("code client mismatch");
    if (stored.redirect_uri !== redirect_uri) return badRequest("redirect_uri mismatch");

    await env.OAUTH_KV.delete(`code:${code}`);

    const access_token = randB64url(32);
    const exp = nowSec() + ACCESS_TOKEN_TTL_SEC;

    const tokenStored: StoredAccessToken = { client_id, scope: stored.scope || "mcp", exp };
    await kvPutJson(env, `token:${access_token}`, tokenStored, ACCESS_TOKEN_TTL_SEC);

    const resp: OAuthTokenResponse = {
      access_token,
      token_type: "Bearer",
      expires_in: ACCESS_TOKEN_TTL_SEC,
      scope: tokenStored.scope,
    };
    return Response.json(resp, { status: 200 });
  }

  if (path === "/revoke") {
    if (req.method !== "POST") return new Response("method not allowed", { status: 405 });
    const form = await req.formData().catch(() => null);
    if (!form) return badRequest("revoke endpoint expects form data");
    const token = String(form.get("token") || "");
    if (token) await env.OAUTH_KV.delete(`token:${token}`);
    return new Response("", { status: 200 });
  }

  return new Response("not found", { status: 404 });
}

// Validate access token for /mcp
export async function verifyAccessToken(env: Env, bearer: string, requiredScope = "mcp"): Promise<boolean> {
  if (!bearer) return false;
  const tok = await kvGetJson<StoredAccessToken>(env, `token:${bearer}`);
  if (!tok) return false;
  if (typeof tok.exp !== "number" || nowSec() > tok.exp) return false;

  const scopes = (tok.scope || "").split(/\s+/).filter(Boolean);
  return scopes.includes(requiredScope);
}