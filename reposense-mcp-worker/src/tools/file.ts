import { buildErr, buildOk, type ToolEnvelope } from "../envelope";
import type { ToolCtx } from "./registry";
import { GitHubClient } from "../github/client";

function decodeBase64Utf8(content: string): string {
  const clean = content.replace(/\n/g, "").trim();
  if (!clean) return "";
  const bin = atob(clean);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder("utf-8", { fatal: false }).decode(bytes);
}

export async function github_read_file(ctx: ToolCtx): Promise<ToolEnvelope> {
  const args = (ctx.args ?? {}) as { owner: string; repo: string; path: string; ref?: string; no_cache?: boolean };
  const ref = args.ref ?? "main";
  const noCache = Boolean(args.no_cache ?? false);

  if (ctx.policy.denyPath(args.path)) return buildErr(ctx.meta, "path denied by policy");

  const cached = await ctx.cache.get<any>("github_read_file", args, "file", noCache);
  if (cached) return buildOk(ctx.meta, cached);

  const gh = new GitHubClient(ctx.env);
  const res = await gh.request<any>(`/repos/${args.owner}/${args.repo}/contents/${encodeURIComponent(args.path)}?ref=${encodeURIComponent(ref)}`, {
    method: "GET"
  });

  if (res.status >= 400) return buildErr(ctx.meta, `github error ${res.status}`);
  if (res.data?.type !== "file") return buildErr(ctx.meta, "not a file");

  if (res.data?.encoding && String(res.data.encoding) !== "base64") {
    return buildErr(ctx.meta, `unexpected encoding: ${String(res.data.encoding)}`);
  }

  const size = Number(res.data.size ?? 0);
  if (size > ctx.policy.maxFileBytes) return buildErr(ctx.meta, `file too large: ${size} bytes (max ${ctx.policy.maxFileBytes})`);

  const content = decodeBase64Utf8(String(res.data.content ?? ""));
  const out = { owner: args.owner, repo: args.repo, ref, path: args.path, size, content };

  await ctx.cache.set("github_read_file", args, "file", out);
  return buildOk(ctx.meta, out);
}

export async function github_read_excerpt(ctx: ToolCtx): Promise<ToolEnvelope> {
  const args = (ctx.args ?? {}) as {
    owner: string;
    repo: string;
    path: string;
    ref?: string;
    head_lines?: number | null;
    tail_lines?: number | null;
    start_line?: number | null;
    end_line?: number | null;
    no_cache?: boolean;
  };

  const fileRes = await github_read_file({
    ...ctx,
    args: { owner: args.owner, repo: args.repo, path: args.path, ref: args.ref, no_cache: args.no_cache }
  });
  if (!fileRes.ok) return fileRes;

  const content = (fileRes.data as any).content as string;
  const lines = content.split("\n");

  const head = args.head_lines ?? null;
  const tail = args.tail_lines ?? null;
  const start = args.start_line ?? null;
  const end = args.end_line ?? null;

  let selected: string[] = [];

  if (start !== null || end !== null) {
    const s = Math.max(1, start ?? 1);
    const e = Math.min(lines.length, end ?? lines.length);
    selected = lines.slice(s - 1, e);
  } else if (head !== null) {
    selected = lines.slice(0, Math.max(0, head));
  } else if (tail !== null) {
    selected = lines.slice(Math.max(0, lines.length - Math.max(0, tail)));
  } else {
    selected = lines.slice(0, Math.min(200, lines.length));
  }

  return buildOk(ctx.meta, {
    owner: (fileRes.data as any).owner,
    repo: (fileRes.data as any).repo,
    ref: (fileRes.data as any).ref,
    path: (fileRes.data as any).path,
    total_lines: lines.length,
    excerpt: selected.join("\n")
  });
}