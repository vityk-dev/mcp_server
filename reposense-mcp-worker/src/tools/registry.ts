import type { Cache } from "../cache";
import type { RepoPolicy } from "../policy";
import type { EnvelopeMeta, ToolEnvelope } from "../envelope";

import { ping } from "./ping";
import { github_cache_clear, github_cache_stats } from "./cache";
import { github_auth_logout, github_auth_poll, github_auth_start, github_auth_status } from "./auth";
import { github_repo_snapshot, github_repo_tree } from "./repo";
import { github_read_excerpt, github_read_file } from "./file";
import { github_search_code, github_search_repos } from "./search";
import { github_list_branches } from "./branches";
import { github_rate_limit_status } from "./ratelimit";

type Env = any;

export type ToolCtx = {
  env: Env;
  ctx: ExecutionContext;
  rid: string;
  meta: EnvelopeMeta;
  policy: RepoPolicy;
  cache: Cache;
  args: unknown;
};

export type ToolFn = (ctx: ToolCtx) => Promise<ToolEnvelope>;

export const tools: Record<string, ToolFn> = {
  ping,
  github_cache_stats,
  github_cache_clear,
  github_auth_start,
  github_auth_poll,
  github_auth_status,
  github_auth_logout,
  github_repo_tree,
  github_read_file,
  github_read_excerpt,
  github_search_code,
  github_search_repos,
  github_list_branches,
  github_rate_limit_status,
  github_repo_snapshot
};

export const toolsList = [
  { name: "ping", description: "Health ping", inputSchema: { type: "object", properties: { message: { type: ["string", "null"] } } } },
  { name: "github_cache_stats", description: "Cache statistics", inputSchema: { type: "object", properties: {} } },
  { name: "github_cache_clear", description: "Clear KV cache", inputSchema: { type: "object", properties: {} } },
  { name: "github_auth_start", description: "Start GitHub device flow", inputSchema: { type: "object", properties: {} } },
  { name: "github_auth_poll", description: "Poll GitHub device flow", inputSchema: { type: "object", properties: { device_code: { type: "string" } }, required: ["device_code"] } },
  { name: "github_auth_status", description: "Auth status", inputSchema: { type: "object", properties: {} } },
  { name: "github_auth_logout", description: "Logout GitHub token", inputSchema: { type: "object", properties: {} } },
  {
    name: "github_repo_tree",
    description: "List repository tree",
    inputSchema: {
      type: "object",
      properties: {
        owner: { type: "string" },
        repo: { type: "string" },
        ref: { type: "string", default: "main" },
        max_items: { type: "number", default: 5000 },
        no_cache: { type: "boolean", default: false }
      },
      required: ["owner", "repo"]
    }
  },
  {
    name: "github_read_file",
    description: "Read file content",
    inputSchema: {
      type: "object",
      properties: {
        owner: { type: "string" },
        repo: { type: "string" },
        path: { type: "string" },
        ref: { type: "string", default: "main" },
        no_cache: { type: "boolean", default: false }
      },
      required: ["owner", "repo", "path"]
    }
  },
  {
    name: "github_read_excerpt",
    description: "Read excerpt from file",
    inputSchema: {
      type: "object",
      properties: {
        owner: { type: "string" },
        repo: { type: "string" },
        path: { type: "string" },
        ref: { type: "string", default: "main" },
        head_lines: { type: ["number", "null"] },
        tail_lines: { type: ["number", "null"] },
        start_line: { type: ["number", "null"] },
        end_line: { type: ["number", "null"] },
        no_cache: { type: "boolean", default: false }
      },
      required: ["owner", "repo", "path"]
    }
  },
  {
    name: "github_search_code",
    description: "Search code on GitHub",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string" },
        repo: { type: ["string", "null"] },
        language: { type: ["string", "null"] },
        path: { type: ["string", "null"] },
        max_results: { type: "number", default: 10 },
        no_cache: { type: "boolean", default: false }
      },
      required: ["query"]
    }
  },
  {
    name: "github_search_repos",
    description: "Search repositories on GitHub",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string" },
        language: { type: ["string", "null"] },
        stars: { type: ["string", "null"] },
        topics: { type: ["array", "null"], items: { type: "string" } },
        sort: { type: "string", default: "stars" },
        max_results: { type: "number", default: 10 },
        no_cache: { type: "boolean", default: false }
      },
      required: ["query"]
    }
  },
  {
    name: "github_list_branches",
    description: "List repository branches",
    inputSchema: {
      type: "object",
      properties: {
        owner: { type: "string" },
        repo: { type: "string" },
        per_page: { type: "number", default: 100 },
        max_pages: { type: "number", default: 10 },
        no_cache: { type: "boolean", default: false }
      },
      required: ["owner", "repo"]
    }
  },
  {
    name: "github_rate_limit_status",
    description: "Get GitHub rate limit status",
    inputSchema: { type: "object", properties: { no_cache: { type: "boolean", default: false } } }
  },
  {
    name: "github_repo_snapshot",
    description: "Snapshot key files for repo understanding",
    inputSchema: {
      type: "object",
      properties: {
        owner: { type: "string" },
        repo: { type: "string" },
        ref: { type: "string", default: "main" },
        max_files: { type: "number", default: 20 },
        max_chars_per_file: { type: "number", default: 20000 },
        no_cache: { type: "boolean", default: false }
      },
      required: ["owner", "repo"]
    }
  }
];