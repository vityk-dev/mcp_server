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
      client_id: String(env.GITHUB_CLIENT_ID || ""),
      scope: "repo read:user"
    }).toString()
  });

  const text = await res.text();
  if (!res.ok) throw new Error(`device start failed: ${res.status} ${text}`);

  const json = JSON.parse(text) as any;
  if (!json.device_code) throw new Error(`device start missing device_code: ${text}`);

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
  const text = await res.text();
  if (!res.ok) throw new Error(`device poll failed: ${res.status} ${text}`);
  const json = JSON.parse(text) as any;

  if (json.error) {
    const out: { status: "pending"; error: string; interval?: number } = {
      status: "pending",
      error: String(json.error)
    };
    if (json.interval) out.interval = Number(json.interval);
    return out;
  }

  if (!json.access_token) throw new Error("device poll failed");

  const scope = json.scope ? String(json.scope) : undefined;

  if (scope) {
    await putStoredToken(env, { access_token: String(json.access_token), token_type: String(json.token_type), scope });
    const ok: { status: "ok"; scope?: string } = { status: "ok", scope };
    return ok;
  }

  await putStoredToken(env, { access_token: String(json.access_token), token_type: String(json.token_type) });
  return { status: "ok" };
}
