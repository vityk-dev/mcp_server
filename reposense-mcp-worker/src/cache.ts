import { sha256Hex } from "./util";

type CacheEntry = { v: unknown; ts: string };

const TTL = {
  tree: 300,
  file: 600,
  branches: 120,
  search: 60,
  rate_limit: 30
} as const;

export type CacheBucket = keyof typeof TTL;

export type Cache = {
  get: <T>(tool: string, args: unknown, bucket: CacheBucket, noCache: boolean) => Promise<T | null>;
  set: (tool: string, args: unknown, bucket: CacheBucket, value: unknown) => Promise<void>;
  clearAll: () => Promise<{ deleted: number; warning?: string }>;
  stats: () => Promise<{ approx_keys: number }>;
};

function canonical(obj: unknown): string {
  if (!obj || typeof obj !== "object") return JSON.stringify(obj);
  return JSON.stringify(obj, Object.keys(obj as Record<string, unknown>).sort());
}

export function makeCache(kv: KVNamespace): Cache {
  async function key(tool: string, args: unknown): Promise<string> {
    const base = `${tool}:${canonical(args ?? {})}`;
    const h = await sha256Hex(base);
    return `cache:v1:${tool}:${h}`;
  }

  return {
    async get<T>(tool: string, args: unknown, bucket: CacheBucket, noCache: boolean): Promise<T | null> {
      if (noCache) return null;
      const k = await key(tool, args);
      const raw = await kv.get(k);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as CacheEntry;
      return parsed.v as T;
    },

    async set(tool: string, args: unknown, bucket: CacheBucket, value: unknown): Promise<void> {
      const k = await key(tool, args);
      const ttl: number = TTL[bucket];
      const entry: CacheEntry = { v: value, ts: new Date().toISOString() };
      await kv.put(k, JSON.stringify(entry), { expirationTtl: ttl });
    },

    async clearAll(): Promise<{ deleted: number; warning?: string }> {
      let cursor: string | null = null;
      let deleted = 0;

      for (;;) {
        const opts: KVNamespaceListOptions = cursor ? { prefix: "cache:v1:", cursor } : { prefix: "cache:v1:" };
        const res = await kv.list(opts);

        for (const k of res.keys) {
          await kv.delete(k.name);
          deleted++;
        }

        if (res.list_complete) break;

        const next: string | undefined = (res as unknown as { cursor?: string }).cursor;
        cursor = next ?? null;
        if (!cursor) break;
      }

      return { deleted, warning: "KV is eventually consistent; stale reads may persist briefly." };
    },

    async stats(): Promise<{ approx_keys: number }> {
      const res = await kv.list({ prefix: "cache:v1:" });
      return { approx_keys: res.keys.length };
    }
  };
}
