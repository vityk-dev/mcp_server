import fs from "node:fs";
import path from "node:path";

const repoRoot = process.cwd();

const roots = [
  path.join(repoRoot, "src"),
  path.join(repoRoot, "tests")
];

const exts = new Set([".ts"]);

function walk(dir) {
  const out = [];
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) out.push(...walk(p));
    else if (exts.has(path.extname(ent.name))) out.push(p);
  }
  return out;
}

function collectAll() {
  const out = [];
  for (const r of roots) {
    if (fs.existsSync(r)) out.push(...walk(r));
  }
  return out;
}

function rewrite(content) {
  let out = content;

  out = out.replace(
    /from\s+["']\/Users\/vityk\/mcp_server\/reposense-mcp-worker\/(src\/)?/g,
    'from "'
  );

  out = out.replace(/from\s+["'](\.{1,2}\/[^"']+)\.ts["']/g, 'from "$1"');

  out = out.replace(/from\s+["']([^"']+)["']/g, (m, p1) => {
    const norm = p1.replace(/\\/g, "/");
    return `from "${norm}"`;
  });

  out = out.replace(/from\s+["'](\.{1,2}\/)+src\//g, (m) => m.replace("src/", ""));

  return out;
}

const files = collectAll();
let changed = 0;

for (const file of files) {
  const before = fs.readFileSync(file, "utf8");
  const after = rewrite(before);
  if (before !== after) {
    fs.writeFileSync(file, after, "utf8");
    changed++;
    console.log(`rewrote: ${path.relative(repoRoot, file)}`);
  }
}

console.log(`done. files changed: ${changed}/${files.length}`);