import { b64url, fromB64url } from "./util";

type SessionPayload = {
  jti: string;
  iat: number;
  exp: number;
};

function encJson(obj: unknown): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(obj));
}

function decJson(u8: Uint8Array): unknown {
  return JSON.parse(new TextDecoder().decode(u8));
}

async function hmacSign(secret: string, msg: Uint8Array): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const ab: ArrayBuffer = new Uint8Array(msg).buffer;
  const sig = await crypto.subtle.sign("HMAC", key, ab);
  return new Uint8Array(sig);
}

function timingSafeEq(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  let v = 0;
  for (let i = 0; i < a.length; i++) v |= a[i]! ^ b[i]!;
  return v === 0;
}

export async function createSession(secret: string, ttlSeconds: number): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const payload: SessionPayload = {
    jti: crypto.randomUUID(),
    iat: now,
    exp: now + ttlSeconds
  };
  const base = b64url(encJson(payload));
  const sig = await hmacSign(secret, new TextEncoder().encode(base));
  return `${base}.${b64url(sig)}`;
}

export async function verifySession(secret: string, sid: string): Promise<boolean> {
  try {
    if (!secret) return false;

    const parts = sid.split(".");
    if (parts.length !== 2) return false;

    const [base, sig] = parts as [string, string];
    if (!base || !sig) return false;

    const expected = await hmacSign(secret, new TextEncoder().encode(base));
    const got = fromB64url(sig);
    if (!timingSafeEq(expected, got)) return false;

    const payload = decJson(fromB64url(base)) as SessionPayload;
    if (!payload || typeof payload.exp !== "number") return false;

    const now = Math.floor(Date.now() / 1000);
    return now <= payload.exp;
  } catch {
    return false;
  }
}