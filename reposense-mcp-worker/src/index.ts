import { buildErr, buildOk, type EnvelopeMeta, MCP_VERSION, type ToolEnvelope } from "./envelope";
import { loadPolicy } from "./policy";
import { makeCache } from "./cache";
import { createSession, verifySession } from "./session";
import { nanoid8, readJson, sseResponse, type JsonRpcRequest, type JsonRpcResponse } from "./util";
import { tools, toolsList } from "./tools/registry";
import { promptsList, promptsGet } from "./prompts";
import { RateLimiterDO } from "./ratelimiter_do";

export { RateLimiterDO };

type Env = {
  VERSION: string;
  MCP_PROTOCOL_VERSION: string;
  MCP_BEARER: string;
  SESSION_HMAC_SECRET: string;

  CACHE_ENCRYPTION_KEY: string;

  GITHUB_CLIENT_ID: string;
  GITHUB_CLIENT_SECRET: string;

  CACHE_KV: KVNamespace;
  AUTH_KV: KVNamespace;

  RATE_LIMITER: DurableObjectNamespace;

  RATE_LIMIT_RPM: string;
  POLICY_DENY_PATTERNS: string;
  POLICY_MAX_FILE_BYTES: string;
  POLICY_MAX_TREE_ITEMS: string;
};

function unauthorized(): Response {
  return new Response("unauthorized", { status: 401 });
}

function forbidden(msg: string): Response {
  return new Response(msg, { status: 403 });
}

function jsonError(id: JsonRpcRequest["id"], code: number, message: string): JsonRpcResponse {
  return { jsonrpc: "2.0", id: id ?? null, error: { code, message } };
}

function jsonResult(id: JsonRpcRequest["id"], result: unknown): JsonRpcResponse {
  return { jsonrpc: "2.0", id: id ?? null, result };
}

function routesMatch(pathname: string): boolean {
  return pathname === "/mcp" || pathname === "/mcp/";
}

async function rateLimitOrThrow(req: Request, env: Env): Promise<void> {
  const auth = req.headers.get("Authorization") ?? "";
  const token = auth.startsWith("Bearer ") ? auth.slice("Bearer ".length) : "";
  const doId = env.RATE_LIMITER.idFromName("global");
  const stub = env.RATE_LIMITER.get(doId);
  const res = await stub.fetch("https://ratelimiter.local/check", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ token, rpm: Number(env.RATE_LIMIT_RPM || "60") })
  });
  if (res.status === 429) {
    throw new Error("rate_limit_exceeded");
  }
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === "/health" && req.method === "GET") {
      return Response.json({ ok: true, version: env.VERSION, ts: new Date().toISOString() }, { status: 200 });
    }

    if (!routesMatch(url.pathname)) {
      return new Response("not found", { status: 404 });
    }

    if (req.method !== "POST") {
      return new Response("method not allowed", { status: 405 });
    }

    const auth = req.headers.get("Authorization");
    if (!auth || !auth.startsWith("Bearer ")) return unauthorized();
    const bearer = auth.slice("Bearer ".length);
    if (bearer !== env.MCP_BEARER) return forbidden("invalid bearer");

    try {
      await rateLimitOrThrow(req, env);
    } catch (e) {
      if (String(e).includes("rate_limit_exceeded")) {
        const rid = nanoid8();
        const meta: EnvelopeMeta = {
          timestamp: new Date().toISOString(),
          version: env.VERSION,
          tool_name: "rate_limit",
          rid
        };
        const inner: ToolEnvelope = buildErr(meta, "rate limit exceeded", undefined);
        const rpc = jsonError(1, -32029, "rate limit exceeded");
        return sseResponse(rpc, { extraHeaders: {} });
      }
      return new Response("rate limit error", { status: 500 });
    }

    const rid = nanoid8();
    const policy = loadPolicy(env);
    const cache = makeCache(env.CACHE_KV);

    const body = await readJson<JsonRpcRequest>(req);
    if (!body) {
      return sseResponse(jsonError(null, -32700, "parse error"));
    }

    const method = body.method;
    const id = body.id ?? null;

    if (method === "initialize") {
      const sid = await createSession(env.SESSION_HMAC_SECRET, 60 * 60);
      const result = {
        protocolVersion: env.MCP_PROTOCOL_VERSION,
        capabilities: {
          tools: { listChanged: false },
          prompts: { listChanged: false }
        },
        serverInfo: { name: "RepoSense MCP", version: env.VERSION }
      };
      const rpc = jsonResult(id, result);
      return sseResponse(rpc, {
        extraHeaders: {
          "mcp-session-id": sid,
          "access-control-expose-headers": "mcp-session-id"
        }
      });
    }

    const sid = req.headers.get("mcp-session-id");
    if (!sid) return forbidden("missing mcp-session-id");
    const okSid = await verifySession(env.SESSION_HMAC_SECRET, sid);
    if (!okSid) return forbidden("invalid mcp-session-id");

    if (method === "tools/list") {
      const rpc = jsonResult(id, { tools: toolsList });
      return sseResponse(rpc);
    }

    if (method === "tools/call") {
      const params = (body.params ?? {}) as { name?: string; arguments?: unknown };
      const name = params.name;
      if (!name || typeof name !== "string") {
        return sseResponse(jsonError(id, -32602, "invalid params"));
      }
      const fn = tools[name];
      if (!fn) {
        return sseResponse(jsonError(id, -32601, "method not found"));
      }

      const meta: EnvelopeMeta = {
        timestamp: new Date().toISOString(),
        version: env.VERSION,
        tool_name: name,
        rid
      };

      try {
        const inner = await fn({
          env,
          ctx,
          rid,
          meta,
          policy,
          cache,
          args: params.arguments
        });
        const rpc = jsonResult(id, inner);
        return sseResponse(rpc);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "unknown error";
        if (msg === "rate_limit_exceeded") {
          return sseResponse(jsonError(id, -32029, "rate limit exceeded"));
        }
        return sseResponse(jsonResult(id, buildErr(meta, msg, undefined)));
      }
    }

    if (method === "prompts/list") {
      const rpc = jsonResult(id, { prompts: promptsList(env) });
      return sseResponse(rpc);
    }

    if (method === "prompts/get") {
      const params = (body.params ?? {}) as { name?: string; arguments?: unknown };
      if (!params.name || typeof params.name !== "string") return sseResponse(jsonError(id, -32602, "invalid params"));
      const p = promptsGet(env, params.name, params.arguments);
      if (!p) return sseResponse(jsonError(id, -32601, "method not found"));
      const rpc = jsonResult(id, p);
      return sseResponse(rpc);
    }

    return sseResponse(jsonError(id, -32601, "method not found"));
  }
};