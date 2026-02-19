type Env = { VERSION: string };

export function promptsList(env: Env) {
  return [
    {
      name: "project_overview",
      description: "High-level overview workflow for a repository"
    }
  ];
}

export function promptsGet(env: Env, name: string, args: unknown) {
  if (name !== "project_overview") return null;
  const a = (args ?? {}) as { owner?: string; repo?: string; ref?: string };
  const owner = a.owner ?? "<owner>";
  const repo = a.repo ?? "<repo>";
  const ref = a.ref ?? "main";

  return {
    description: "Repo overview workflow",
    messages: [
      {
        role: "user",
        content: {
          type: "text",
          text: `Analyze ${owner}/${repo} at ref ${ref}.\n\n1) Call github_repo_snapshot\n2) If needed call github_repo_tree\n3) Read key files via github_read_file\n4) Summarize architecture, entry points, risks, and next steps.`
        }
      }
    ]
  };
}