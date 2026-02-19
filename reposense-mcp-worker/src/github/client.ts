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
    if (token) headers.set("authorization", `Bearer ${token}`);

    const res = await fetch(`https://api.github.com${path}`, { ...init, headers });
    const rate = parseRate(res.headers);
    const status = res.status;

    if (status === 204) {
      const out: GitHubResponse<T> = { data: undefined as T, status };
      if (rate) out.rate = rate;
      return out;
    }

    const text = await res.text();
    const json = text ? (JSON.parse(text) as T) : (undefined as T);

    const out: GitHubResponse<T> = { data: json, status };
    if (rate) out.rate = rate;
    return out;
  }
}
