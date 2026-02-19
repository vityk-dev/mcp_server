import { buildErr, buildOk, type ToolEnvelope } from "../envelope";
import type { ToolCtx } from "./registry";
import { devicePoll, deviceStart } from "../github/auth";
import { clearStoredToken, getStoredToken } from "../github/token_store";

export async function github_auth_start(ctx: ToolCtx): Promise<ToolEnvelope> {
  const started = await deviceStart(ctx.env);
  return buildOk(ctx.meta, started);
}

export async function github_auth_poll(ctx: ToolCtx): Promise<ToolEnvelope> {
  const args = (ctx.args ?? {}) as { device_code?: string };
  if (!args.device_code) return buildErr(ctx.meta, "device_code is required");
  const polled = await devicePoll(ctx.env, args.device_code);
  if (polled.status === "pending") {
    if (polled.interval) return buildErr(ctx.meta, polled.error, { warnings: [`poll interval: ${polled.interval}s`] });
  return buildErr(ctx.meta, polled.error);
  }
  return buildOk(ctx.meta, { authenticated: true, scope: polled.scope ?? null });
}

export async function github_auth_status(ctx: ToolCtx): Promise<ToolEnvelope> {
  const token = await getStoredToken(ctx.env);
  return buildOk(ctx.meta, { authenticated: Boolean(token) });
}

export async function github_auth_logout(ctx: ToolCtx): Promise<ToolEnvelope> {
  await clearStoredToken(ctx.env);
  return buildOk(ctx.meta, { authenticated: false });
}