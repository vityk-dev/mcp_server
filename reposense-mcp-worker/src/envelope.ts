export const MCP_VERSION = "2024-11-05";

export type EnvelopeMeta = {
  timestamp: string;
  version: string;
  tool_name: string;
  rid: string;
  rate_limit?: { remaining: number; reset: number; limit: number };
};

export type ToolEnvelope = {
  ok: boolean;
  data?: unknown;
  error?: string;
  warnings?: string[];
  stats?: Record<string, unknown>;
  meta: EnvelopeMeta;
  _mcp_version: string;
};

export function buildOk(
  meta: EnvelopeMeta,
  data: unknown,
  extras?: { warnings?: string[]; stats?: Record<string, unknown> }
): ToolEnvelope {
  const out: ToolEnvelope = {
    ok: true,
    data,
    meta,
    _mcp_version: MCP_VERSION
  };
  if (extras?.warnings) out.warnings = extras.warnings;
  if (extras?.stats) out.stats = extras.stats;
  return out;
}

export function buildErr(
  meta: EnvelopeMeta,
  error: string,
  extras?: { warnings?: string[]; stats?: Record<string, unknown> }
): ToolEnvelope {
  const out: ToolEnvelope = {
    ok: false,
    error,
    meta,
    _mcp_version: MCP_VERSION
  };
  if (extras?.warnings) out.warnings = extras.warnings;
  if (extras?.stats) out.stats = extras.stats;
  return out;
}
