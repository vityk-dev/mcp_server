# OAuth (Worker)

The Worker runtime implements an OAuth Authorization Server for issuing MCP bearer tokens.

---

## Endpoints

Discovery:
- `/.well-known/oauth-authorization-server`
- `/.well-known/openid-configuration`
- `/.well-known/oauth-protected-resource`

Authorization server:
- `GET /authorize`
- `POST /token`
- `POST /revoke`

Resource:
- `POST /mcp` (requires `Authorization: Bearer <access_token>`)

---

## Flow

1) Client starts authorization code flow.
2) User visits `/authorize` and is authenticated by Cloudflare Access.
3) Worker issues an auth code (KV, TTL ~10 min).
4) Client exchanges at `/token`.
5) Worker returns an access token (KV, TTL ~60 min).
6) Client calls `/mcp` with `Authorization: Bearer <token>`.

No refresh tokens are issued; clients re-run auth when tokens expire.
