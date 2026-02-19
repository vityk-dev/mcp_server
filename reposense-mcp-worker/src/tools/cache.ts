import { buildOk, type ToolEnvelope } from "../envelope";
import type { ToolCtx } from "./registry";

export async function github_cache_stats(ctx: ToolCtx): Promise<ToolEnvelope> {
  const st = await ctx.cache.stats();
  return buildOk(ctx.meta, st);
}

export async function github_cache_clear(ctx: ToolCtx): Promise<ToolEnvelope> {
  const res = await ctx.cache.clearAll();
  if (res.warning) return buildOk(ctx.meta, res, { warnings: [res.warning] });
  return buildOk(ctx.meta, res);
}