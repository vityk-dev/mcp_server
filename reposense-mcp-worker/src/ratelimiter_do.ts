import { sha256Hex } from "./util";

type CheckBody = { token: string; rpm: number };

export class RateLimiterDO {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);
    if (url.pathname !== "/check" || req.method !== "POST") return new Response("not found", { status: 404 });

    const body = (await req.json()) as CheckBody;
    const token = body.token || "";
    const rpm = Number(body.rpm || 60);

    const now = Date.now();
    const minute = Math.floor(now / 60000);
    const tokenHash = await sha256Hex(token);
    const k = `rl:v1:${tokenHash}:${minute}`;

    const current = (await this.state.storage.get<number>(k)) ?? 0;
    const next = current + 1;
    await this.state.storage.put(k, next);

    const prevKey = `rl:v1:${tokenHash}:${minute - 2}`;
    await this.state.storage.delete(prevKey);

    if (next > rpm) return new Response("rate limited", { status: 429 });
    return new Response("ok", { status: 200 });
  }
}