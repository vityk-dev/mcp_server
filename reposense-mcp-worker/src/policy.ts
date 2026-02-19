type EnvLike = {
  POLICY_DENY_PATTERNS: string;
  POLICY_MAX_FILE_BYTES: string;
  POLICY_MAX_TREE_ITEMS: string;
};

export type RepoPolicy = {
  denyPatterns: string[];
  maxFileBytes: number;
  maxTreeItems: number;
  denyPath: (path: string) => boolean;
};

function globToRegExp(glob: string): RegExp {
  const escaped = glob.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  const re = escaped
    .replace(/\*\*/g, "§§DOUBLESTAR§§")
    .replace(/\*/g, "[^/]*")
    .replace(/§§DOUBLESTAR§§/g, ".*")
    .replace(/\?/g, ".");
  return new RegExp(`^${re}$`);
}

export function loadPolicy(env: EnvLike): RepoPolicy {
  let denyPatterns: string[] = [];
  try {
    denyPatterns = JSON.parse(env.POLICY_DENY_PATTERNS || "[]") as string[];
  } catch {
    denyPatterns = [];
  }
  const compiled = denyPatterns.map(globToRegExp);

  const maxFileBytes = Number(env.POLICY_MAX_FILE_BYTES || "1000000");
  const maxTreeItems = Number(env.POLICY_MAX_TREE_ITEMS || "5000");

  return {
    denyPatterns,
    maxFileBytes,
    maxTreeItems,
    denyPath(path: string) {
      return compiled.some((r) => r.test(path));
    }
  };
}