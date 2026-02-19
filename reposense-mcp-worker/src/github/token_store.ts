import { b64url, fromB64url } from "../util";

type Env = any;

function decodeKeyB64(keyB64: string): Uint8Array {
  const raw = fromB64url(keyB64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, ""));
  if (raw.byteLength !== 32) throw new Error("CACHE_ENCRYPTION_KEY must be 32 bytes base64");
  return raw;
}

async function aesKey(env: Env): Promise<CryptoKey> {
  const raw = decodeKeyB64(env.CACHE_ENCRYPTION_KEY);
  const copy = new Uint8Array(raw);
  const ab: ArrayBuffer = copy.buffer;
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
