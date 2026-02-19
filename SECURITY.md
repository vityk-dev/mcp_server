# Security

## Secrets and config files

Track only templates:
- `reposense-mcp-worker/wrangler.example.toml`
- `tokenstore.example.json`

Keep real files local-only (ignored):
- `reposense-mcp-worker/wrangler.toml`
- `reposense-mcp-worker/.dev.vars`
- `tokenstore.json`

## Deny patterns (policy)

Both runtimes enforce deny patterns to prevent reading secrets:
- `.env`
- private keys (`*.pem`, `*.key`, `id_rsa`, `id_ed25519`)
- credentials (`.npmrc`, `.pypirc`)

Tune policy via env vars (Worker) or settings (Python).

## Incident response: secret committed

1) Revoke/rotate immediately.
2) Remove from branch tip.
3) Rewrite history with `git filter-repo`.
4) Force-push + ask collaborators to re-clone.

Mirror rewrite example:

```bash
git clone --mirror https://github.com/<owner>/<repo>.git repo_mirror.git
cd repo_mirror.git
git filter-repo --path tokenstore.json --invert-paths --force
git push --force --mirror
```
