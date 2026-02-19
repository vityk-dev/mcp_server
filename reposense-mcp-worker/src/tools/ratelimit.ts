import { buildErr, buildOk, type ToolEnvelope } from "../envelope";
import type { ToolCtx } from "./registry";
import { GitHubClient } from "../github/client";

export async function github_rate_limit_status(ctx: ToolCtx): Promise<ToolEnvelope> {
  const args = (ctx.args ?? {}) as { no_cache?: boolean };
  const noCache = Boolean(args.no_cache ?? false);

  const cached = await ctx.cache.get<any>("github_rate_limit_status", args, "rate_limit", noCache);
  if (cached) return buildOk(ctx.meta, cached);

  const gh = new GitHubClient(ctx.env);
  const res = await gh.request<any>(`/rate_limit`, { method: "GET" });
  if (res.status >= 400) return buildErr(ctx.meta, `github error ${res.status}`);

  const out = res.data;
  await ctx.cache.set("github_rate_limit_status", args, "rate_limit", out);
  return buildOk(ctx.meta, out);
}