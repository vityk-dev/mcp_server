import { buildErr, buildOk, type ToolEnvelope } from "../envelope";
import type { ToolCtx } from "./registry";
import { GitHubClient } from "../github/client";
import type { GitHubSearchCodeItem, GitHubSearchRepoItem } from "../github/types";

export async function github_search_code(ctx: ToolCtx): Promise<ToolEnvelope> {
  const args = (ctx.args ?? {}) as { query: string; repo?: string | null; language?: string | null; path?: string | null; max_results?: number; no_cache?: boolean };
  const maxResults = Math.min(Number(args.max_results ?? 10), 100);
  const noCache = Boolean(args.no_cache ?? false);

  const cached = await ctx.cache.get<any>("github_search_code", args, "search", noCache);
  if (cached) return buildOk(ctx.meta, cached);

  const parts = [args.query];
  if (args.repo) parts.push(`repo:${args.repo}`);
  if (args.language) parts.push(`language:${args.language}`);
  if (args.path) parts.push(`path:${args.path}`);
  const q = parts.join(" ");

  const gh = new GitHubClient(ctx.env);
  const res = await gh.request<{ total_count: number; items: GitHubSearchCodeItem[] }>(
    `/search/code?q=${encodeURIComponent(q)}&per_page=${encodeURIComponent(String(Math.min(maxResults, 100)))}`,
    { method: "GET" }
  );
  if (res.status >= 400) return buildErr(ctx.meta, `github error ${res.status}`);

  const out = {
    query: q,
    total_count: res.data.total_count,
    items: (res.data.items ?? []).slice(0, maxResults).map((i) => ({
      repository: i.repository.full_name,
      path: i.path,
      sha: i.sha,
      url: i.html_url,
      score: i.score ?? 0
    }))
  };
  await ctx.cache.set("github_search_code", args, "search", out);
  return buildOk(ctx.meta, out);
}

export async function github_search_repos(ctx: ToolCtx): Promise<ToolEnvelope> {
  const args = (ctx.args ?? {}) as { query: string; language?: string | null; stars?: string | null; topics?: string[] | null; sort?: string; max_results?: number; no_cache?: boolean };
  const maxResults = Math.min(Number(args.max_results ?? 10), 100);
  const sort = args.sort ?? "stars";
  const noCache = Boolean(args.no_cache ?? false);

  const cached = await ctx.cache.get<any>("github_search_repos", args, "search", noCache);
  if (cached) return buildOk(ctx.meta, cached);

  const parts = [args.query];
  if (args.language) parts.push(`language:${args.language}`);
  if (args.stars) parts.push(`stars:${args.stars}`);
  if (args.topics) for (const t of args.topics) parts.push(`topic:${t}`);
  const q = parts.join(" ");

  const gh = new GitHubClient(ctx.env);
  const res = await gh.request<{ total_count: number; items: GitHubSearchRepoItem[] }>(
    `/search/repositories?q=${encodeURIComponent(q)}&sort=${encodeURIComponent(sort)}&per_page=${encodeURIComponent(String(Math.min(maxResults, 100)))}`,
    { method: "GET" }
  );
  if (res.status >= 400) return buildErr(ctx.meta, `github error ${res.status}`);

  const out = {
    query: q,
    total_count: res.data.total_count,
    items: (res.data.items ?? []).slice(0, maxResults).map((i) => ({
      full_name: i.full_name,
      description: i.description ?? "",
      language: i.language ?? null,
      stars: i.stargazers_count,
      forks: i.forks_count,
      url: i.html_url,
      topics: i.topics ?? [],
      updated_at: i.updated_at,
      score: i.score ?? 0
    }))
  };
  await ctx.cache.set("github_search_repos", args, "search", out);
  return buildOk(ctx.meta, out);
}