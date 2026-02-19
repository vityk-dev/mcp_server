export class RateLimiterDO {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);
    if (url.pathname !== "/check" || req.method !== "POST") return new Response("not found", { status: 404 });

    const body = (await req.json().catch(() => null)) as null | { token?: string; rpm?: number };
    const token = typeof body?.token === "string" ? body.token : "";
    const rpm = Number.isFinite(body?.rpm) ? Number(body?.rpm) : 60;

    if (!token) return new Response("missing token", { status: 400 });

    const now = Date.now();
    const cutoff = now - 60_000;

    const db = this.state.storage.sql;

    db.exec("CREATE TABLE IF NOT EXISTS rl (token TEXT NOT NULL, ts INTEGER NOT NULL)");
    db.exec("CREATE INDEX IF NOT EXISTS rl_token_ts ON rl(token, ts)");

    db.exec("DELETE FROM rl WHERE token = ? AND ts < ?", token, cutoff);

    let count = 0;
    for (const row of db.exec<{ c: number }>("SELECT COUNT(1) AS c FROM rl WHERE token = ?", token)) {
      count = row.c || 0;
      break;
    }

    if (count >= rpm) return new Response("rate limited", { status: 429 });

    db.exec("INSERT INTO rl(token, ts) VALUES(?, ?)", token, now);

    return Response.json({ ok: true, remaining: Math.max(0, rpm - (count + 1)) }, { status: 200 });
  }
}