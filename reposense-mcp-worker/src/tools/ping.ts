import { buildOk, type ToolEnvelope } from "../envelope";
import type { ToolCtx } from "./registry";

export async function ping(ctx: ToolCtx): Promise<ToolEnvelope> {
  const args = (ctx.args ?? {}) as { message?: string | null };
  return buildOk(ctx.meta, { message: args.message ?? "pong" });
}