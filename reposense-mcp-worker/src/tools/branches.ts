import { buildErr, buildOk, type ToolEnvelope } from "../envelope";
import type { ToolCtx } from "./registry";
import { GitHubClient } from "../github/client";
import type { GitHubBranch } from "../github/types";

export async function github_list_branches(ctx: ToolCtx): Promise<ToolEnvelope> {
  const args = (ctx.args ?? {}) as { owner: string; repo: string; per_page?: number; max_pages?: number; no_cache?: boolean };
  const perPage = Math.min(Number(args.per_page ?? 100), 100);
  const maxPages = Math.min(Number(args.max_pages ?? 10), 50);
  const noCache = Boolean(args.no_cache ?? false);

  const cached = await ctx.cache.get<any>("github_list_branches", args, "branches", noCache);
  if (cached) return buildOk(ctx.meta, cached);

  const gh = new GitHubClient(ctx.env);
  const branches: { name: string; sha: string; protected: boolean }[] = [];

  for (let page = 1; page <= maxPages; page++) {
    const res = await gh.request<GitHubBranch[]>(
      `/repos/${args.owner}/${args.repo}/branches?per_page=${encodeURIComponent(String(perPage))}&page=${encodeURIComponent(String(page))}`,
      { method: "GET" }
    );
    if (res.status >= 400) return buildErr(ctx.meta, `github error ${res.status}`);
    const items = res.data ?? [];
    for (const b of items) {
      branches.push({ name: b.name, sha: b.commit.sha, protected: Boolean(b.protected) });
    }
    if (items.length < perPage) break;
  }

  const out = { owner: args.owner, repo: args.repo, count: branches.length, branches };
  await ctx.cache.set("github_list_branches", args, "branches", out);
  return buildOk(ctx.meta, out);
}