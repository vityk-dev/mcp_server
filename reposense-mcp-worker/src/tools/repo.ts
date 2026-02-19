import { buildErr, buildOk, type ToolEnvelope } from "../envelope";
import type { ToolCtx } from "./registry";
import { GitHubClient } from "../github/client";
import type { GitHubTreeResponse } from "../github/types";

function pickBucket(path: string): number {
  const p = path.toLowerCase();
  if (p === "readme.md" || p.endsWith("/readme.md")) return 100;
  if (p.includes("docs/")) return 30;
  if (p.includes("src/")) return 40;
  if (p.endsWith("package.json")) return 80;
  if (p.endsWith("pyproject.toml") || p.endsWith("requirements.txt")) return 70;
  if (p.endsWith("dockerfile") || p.includes("docker")) return 50;
  if (p.includes("config") || p.endsWith(".yaml") || p.endsWith(".yml") || p.endsWith(".toml")) return 35;
  if (p.includes("test")) return 20;
  return 10;
}

async function resolveTreeSha(gh: GitHubClient, owner: string, repo: string, ref: string): Promise<string> {
  const commit = await gh.request<any>(`/repos/${owner}/${repo}/commits/${encodeURIComponent(ref)}`, { method: "GET" });
  if (commit.status >= 400) throw new Error(`failed to resolve ref: ${commit.status}`);
  const treeSha = commit.data?.commit?.tree?.sha;
  if (!treeSha) throw new Error("missing tree sha");
  return String(treeSha);
}

export async function github_repo_tree(ctx: ToolCtx): Promise<ToolEnvelope> {
  const args = (ctx.args ?? {}) as { owner: string; repo: string; ref?: string; max_items?: number; no_cache?: boolean };
  const ref = args.ref ?? "main";
  const maxItems = Math.min(Number(args.max_items ?? 5000), ctx.policy.maxTreeItems);
  const noCache = Boolean(args.no_cache ?? false);

  const cached = await ctx.cache.get<any>("github_repo_tree", args, "tree", noCache);
  if (cached) return buildOk(ctx.meta, cached);

  const gh = new GitHubClient(ctx.env);
  const treeSha = await resolveTreeSha(gh, args.owner, args.repo, ref);
  const tree = await gh.request<GitHubTreeResponse>(`/repos/${args.owner}/${args.repo}/git/trees/${treeSha}?recursive=1`, { method: "GET" });
  if (tree.status >= 400) return buildErr(ctx.meta, `github error ${tree.status}`);

  const items = (tree.data.tree ?? [])
    .filter((t) => t.path && t.type === "blob")
    .map((t) => ({ path: t.path!, sha: t.sha ?? null, size: t.size ?? null, type: t.type }))
    .filter((t) => !ctx.policy.denyPath(t.path))
    .slice(0, maxItems);

  const out = { owner: args.owner, repo: args.repo, ref, truncated: Boolean(tree.data.truncated), count: items.length, items };
  await ctx.cache.set("github_repo_tree", args, "tree", out);
  if (items.length >= maxItems) return buildOk(ctx.meta, out, { warnings: ["tree truncated by policy/max_items"] });
  return buildOk(ctx.meta, out);
}

async function readFileText(gh: GitHubClient, owner: string, repo: string, path: string, ref: string): Promise<{ text: string; size: number }> {
  const res = await gh.request<any>(`/repos/${owner}/${repo}/contents/${encodeURIComponent(path)}?ref=${encodeURIComponent(ref)}`, { method: "GET" });
  if (res.status >= 400) throw new Error(`github error ${res.status}`);
  if (res.data?.type !== "file") throw new Error("not a file");
  const size = Number(res.data.size ?? 0);
  const content = String(res.data.content ?? "");
  const decoded = atob(content.replace(/\n/g, ""));
  return { text: decoded, size };
}

export async function github_repo_snapshot(ctx: ToolCtx): Promise<ToolEnvelope> {
  const args = (ctx.args ?? {}) as { owner: string; repo: string; ref?: string; max_files?: number; max_chars_per_file?: number; no_cache?: boolean };
  const ref = args.ref ?? "main";
  const maxFiles = Math.min(Number(args.max_files ?? 20), 50);
  const maxChars = Math.min(Number(args.max_chars_per_file ?? 20000), 50000);
  const noCache = Boolean(args.no_cache ?? false);

  const cached = await ctx.cache.get<any>("github_repo_snapshot", args, "tree", noCache);
  if (cached) return buildOk(ctx.meta, cached);

  const gh = new GitHubClient(ctx.env);
  const treeRes = await github_repo_tree({ ...ctx, args: { owner: args.owner, repo: args.repo, ref, max_items: ctx.policy.maxTreeItems, no_cache: noCache } });
  if (!treeRes.ok) return treeRes;

  const tree = (treeRes.data as any).items as { path: string; size: number | null }[];
  const ranked = tree
    .slice()
    .sort((a, b) => pickBucket(b.path) - pickBucket(a.path))
    .slice(0, maxFiles);

  const files: { path: string; size: number; content: string }[] = [];
  const warnings: string[] = [];

  for (const item of ranked) {
    if (ctx.policy.denyPath(item.path)) continue;
    try {
      const { text, size } = await readFileText(gh, args.owner, args.repo, item.path, ref);
      if (size > ctx.policy.maxFileBytes) {
        warnings.push(`skipped (too large): ${item.path} (${size} bytes)`);
        continue;
      }
      files.push({ path: item.path, size, content: text.slice(0, maxChars) });
    } catch (e) {
      warnings.push(`failed to read: ${item.path}`);
    }
  }

  const out = { owner: args.owner, repo: args.repo, ref, files, file_count: files.length };
  await ctx.cache.set("github_repo_snapshot", args, "tree", out);
  return buildOk(ctx.meta, out, warnings.length ? { warnings } : undefined);
}