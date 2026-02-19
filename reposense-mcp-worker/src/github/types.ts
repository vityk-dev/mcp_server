export type RateLimit = { limit: number; remaining: number; reset: number };

export type GitHubTreeItem = {
  path?: string;
  mode?: string;
  type?: "blob" | "tree" | "commit";
  sha?: string;
  size?: number;
  url?: string;
};

export type GitHubTreeResponse = {
  sha: string;
  truncated: boolean;
  tree: GitHubTreeItem[];
};

export type GitHubContentFile = {
  type: "file";
  encoding: "base64";
  size: number;
  name: string;
  path: string;
  content?: string;
  sha: string;
};

export type GitHubBranch = {
  name: string;
  commit: { sha: string };
  protected?: boolean;
};

export type GitHubSearchCodeItem = {
  name: string;
  path: string;
  sha: string;
  html_url: string;
  repository: { full_name: string };
  score?: number;
};

export type GitHubSearchRepoItem = {
  full_name: string;
  description?: string | null;
  language?: string | null;
  stargazers_count: number;
  forks_count: number;
  html_url: string;
  topics?: string[];
  updated_at: string;
  score?: number;
};