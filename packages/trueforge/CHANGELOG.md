# @truefoundry/trueforge

## 1.0.0-rc.1

### Major Changes

- 2829e4c: Replace string creator fields (`created_by` / `triggered_by`) with a non-null `created_by_subject` JSON object on agent, session, schedule, and schedule_run. Ownership and list filters use `tenant_id` + `created_by_subject.subject_id`.

### Minor Changes

- 2829e4c: Add a slot-driven agent Metrics tab with aggregate cards, time-range filtering, and Harness-backed line charts.
- 2829e4c: Add optional mutual TLS for the HTTPS listener and schedule controller→server hop via `TRUEFORGE_MTLS_ENABLED` / `TRUEFORGE_MTLS_CERTS_DIR`. Off by default; independent of ServiceFoundry `TRUEFOUNDRY_MTLS_*`.
- 2829e4c: Adds first-class cron schedules for existing agents: persist them, manage them via /api/v1/schedules, validate cron policy at write time, and advance due runs through a single-dispatcher claim path.
- 2829e4c: Enforce external agent authorization on agent list, get, snippets, update, delete, and referenced-agent use.
- 2829e4c: Add optional `OIDC_ALLOWED_EMAILS` allowlist (exact addresses and `*` globs) so OIDC logins can be limited to approved emails or domains.
- 2829e4c: Store Postgres app tables and Kysely migration bookkeeping in a dedicated `trueforge` schema, with an automatic one-time move from `public` so existing installs keep their data and migration history.
- 2829e4c: Add a TrueFoundry-managed model registry. When `TRUEFOUNDRY_SERVICEFOUNDRY_SERVER_URL` is set, models are listed from the TrueFoundry ServiceFoundry server and turns are routed through the tenant's default AI Gateway with the caller's token. Mutually exclusive with OIDC. Supports internal mutual TLS to the ServiceFoundry server via `TRUEFOUNDRY_MTLS_ENABLED`/`TRUEFOUNDRY_MTLS_CERTS_DIR`.
- 2829e4c: Unify request-scoped RequestContext across standalone, OIDC, and TrueFoundry auth. `/auth/me` returns `{ data: { type, tenant_id, subject, roles } }` (`type` is `oidc-connected` | `default`; OpenAPI/SDK regen deferred to CI).

### Patch Changes

- 2829e4c: Persist zero-initialized metrics on agent sessions.
- 2829e4c: Add caller-scoped session metrics meters, charts, and chart-data under `/internal/metrics` via a server-owned `ISessionMetricsStore`.
- 2829e4c: Fold session metrics totals on createTurn and terminal writes.
- 2829e4c: Add persisted `agent.metadata` on Postgres and SQLite; store `updateAgent` can patch manifest and/or metadata.
- 2829e4c: Add agent `external_id` (`string | null` on create) with a tenant-scoped partial unique index (Postgres and SQLite).
- 2829e4c: Sync ServiceFoundry remote agents on create/update/delete and store the remote id in `external_id`. Filter `listAgents` by `external_ids`. Keep general ServiceFoundry HTTP at 10s and agent CRUD calls at 3s.
- 2829e4c: Drop unused `agent.metadata`; remote identity is stored in `external_id`.
- 2829e4c: Reject reserved agent names `tfg` and `trueforge` in create requests.
- 2829e4c: Use injected `db` for TrueFoundryAgentStore advisory-lock transactions.
- 2829e4c: Add GET /api/v1/agents/{agent_id}/code-snippets with TypeScript TrueForge SDK stream and non-stream samples.
- 2829e4c: Add a dedicated controller entry point (`dist/controller-main.js`) that runs the periodic control loops (schedule dispatch) as a single-replica process for distributed mode (`STANDALONE=false`). It targets the server API via the new `SERVER_URL` env (default `http://localhost:$PORT`). Standalone mode keeps running the controller inside the server process.
- 2829e4c: Report a Daytona key that cannot register snapshots as missing key permissions (403) instead of an invalid API key (422), and name the grants to add in the Daytona dashboard.
- 2829e4c: Cap Daytona status-refresh calls at 1 minute so a stalled provider cannot hang request handlers.
- 2829e4c: Make optional `VITE_BASE_PATH` apply to both the UI public path and API/auth URLs (defaults to `/`).
- 2829e4c: Move `resolveInvokeHeaders` onto `IMcpServerWithAuthStore` (not `IMcpServerStore`) so DB backends stay CRUD-only and turn/MCP invoke paths take the request-scoped with-auth store for configured headers and TrueFoundry gateway Bearer.
- 2829e4c: Split MCP server persistence (`IMcpServerStore`) from Connect UX auth (`IMcpServerWithAuthStore` / `McpServerWithAuthStore`) so DB backends stay CRUD + OAuth client columns while authorize/status/revoke compose in via a token store.
- 2829e4c: Apply `POSTGRES_SSL_MODE` as `sslmode` on the Postgres connection URL.
- 2829e4c: Accept `DATABASE_URL` for hosted mode so managed Postgres (e.g. Railway) can be wired without discrete `POSTGRES_*` vars.
- 2829e4c: Add NOT NULL `agent_id` on `schedule` (backfilled from `agent`), FK to `agent(id)` ON DELETE CASCADE (replacing the `(tenant_id, agent_name)` FK), and `(tenant_id, agent_id)` index for per-agent listing.
- 2829e4c: List schedules is token-paginated (`limit` / `page_token`) and filters by comma-separated `agent_names`.
- 2829e4c: Add GET /api/v1/schedules/{schedule_id}/runs to list a schedule's runs (newest `scheduled_for` first), with the same creator-or-admin access as other schedule routes.
- 2829e4c: Add POST /api/v1/schedules/runs to trigger an immediate schedule run
- 2829e4c: Dispatch schedule runs through the session/turn API: get-or-create a session keyed by run id, then create a turn only when that session has none.
- 2829e4c: Add tenant-unique optional session `external_id`, `Sessions.getOrCreateByExternalId`, and an idempotent `POST /internal/sessions/get-or-create-by-external-id` endpoint and SDK method.
- 2829e4c: Add caller-owned session `metadata` (`Record<string, string>` with size limits) on create, update, and read. Persist as a new `session.metadata` jsonb column; leave session `custom` unchanged.
- 2829e4c: Wire TrueFoundry MCP authorize, status, and delete through ServiceFoundry; stub list auth_status; gate oauth2 invoke mid-turn with authRequired; paginate MCP server lists. UI treats SFY consent `code`/`error` on the FE landing like local DCR success/failure.
- 2829e4c: TrueFoundry MCP invoke headers are owned by the MCP store (`resolveInvokeHeaders`), so gateway Bearer comes from the request-scoped store rather than being threaded through turn/tools APIs.
- 2829e4c: Per-MCP-server request headers via `x-tfg-mcp-headers`, merged into the invoke headers for the named server. Lets a caller that authenticates as one identity give each MCP server the identity it should actually see.
- 2829e4c: Add TrueFoundry-managed MCP list/get (SFY registry, gateway proxy URL, create/update 424).
- Updated dependencies [2829e4c]
- Updated dependencies [2829e4c]
- Updated dependencies [2829e4c]
- Updated dependencies [2829e4c]
- Updated dependencies [2829e4c]
- Updated dependencies [2829e4c]
- Updated dependencies [2829e4c]
- Updated dependencies [2829e4c]
- Updated dependencies [2829e4c]
- Updated dependencies [2829e4c]
- Updated dependencies [2829e4c]
- Updated dependencies [2829e4c]
- Updated dependencies [2829e4c]
  - @truefoundry/trueforge-sdk@0.1.4-rc.1
  - @truefoundry/trueforge-core@1.0.0-rc.1

## 0.2.0-rc.0

### Minor Changes

- 0297727: Add context-management compaction triggers with model-aware defaults and migrate persisted legacy token thresholds.

### Patch Changes

- 3539da2: Add `brand.mode` (`icon-title` | `icon-only` | `logo`) so hosts pick chrome look first; `name` always labels the mark, and `resolveBrandChrome` maps mode to layout chrome.
- 940c4e5: Prefer MCP Python SDK 2.0 snake_case tool annotation fields, with camelCase fallback for older SDKs, without changing destructive-tool detection behavior.
- a655537: Update published dependency ranges (AI SDK, Hono, MCP SDK, Redis, assistant-ui, and related packages).
- 5ccac3d: Update /healthz to return JSON status and package version
- fba6129: Require Node.js 22.14+ (`better-sqlite3` v13 is built for Node-API 10 and SIGSEGVs on 22.13 and below).
- Updated dependencies [940c4e5]
- Updated dependencies [a655537]
- Updated dependencies [0297727]
  - @truefoundry/trueforge-core@0.2.0-rc.0

## 0.1.4

### Patch Changes

- 42eee39: Enable a standalone in-memory local sandbox fallback (no settings row), persist fancy `v1:type:raw` sandbox ids, drop tenant-prefix ownership checks, keep TFY sandbox writes cwd-relative (no `/opt` / `/usr/local`), let each sandbox provider own PATH (no hardcoded Daytona tail in Sandbox), and grant only the Code Mode socket parent in SRT (not host `/tmp`).
- cc49d4a: Rename catalog, sandbox-file download, and MCP tools paths; Fern upsert becomes create_or_update. Sessions and turns default and max 25; session and turn event lists default and max 100.
- d7a640f: Align OpenAPI type names across AgentSpec, settings, catalogs, and chat pickers: Catalog/Configured/Available resource views, AgentSpec nested Model/Skill/InitialUserMessage, Put*Request → Update*Request, MCP acronym casing, GetMeResponse, and explicit names for nested AgentSpec/capabilities schemas.
- 6251d2a: Omit POST /api/v1/auth/logout from the SDK; the UI posts the cookie-clearing path directly.
- 2c3278e: Treat a replayed OIDC callback (browser Back after a successful login) as already signed-in instead of `/?error=login_failed`, and ignore that stale query when a session is still valid.
- 5e03c3d: Collapse Mintlify API Reference groups to Auth, Capabilities, Models, MCP Servers, Skills, Sandboxes, Agents, and Agent Sessions.
- Updated dependencies [42eee39]
- Updated dependencies [d7a640f]
- Updated dependencies [7ae5376]
- Updated dependencies [889caca]
- Updated dependencies [2ca7fb2]
- Updated dependencies [43d780e]
  - @truefoundry/trueforge-core@0.1.4

## 0.1.4-rc.0

### Patch Changes

- 42eee39: Enable a standalone in-memory local sandbox fallback (no settings row), persist fancy `v1:type:raw` sandbox ids, drop tenant-prefix ownership checks, keep TFY sandbox writes cwd-relative (no `/opt` / `/usr/local`), let each sandbox provider own PATH (no hardcoded Daytona tail in Sandbox), and grant only the Code Mode socket parent in SRT (not host `/tmp`).
- cc49d4a: Rename catalog, sandbox-file download, and MCP tools paths; Fern upsert becomes create_or_update. Sessions and turns default and max 25; session and turn event lists default and max 100.
- d7a640f: Align OpenAPI type names across AgentSpec, settings, catalogs, and chat pickers: Catalog/Configured/Available resource views, AgentSpec nested Model/Skill/InitialUserMessage, Put*Request → Update*Request, MCP acronym casing, GetMeResponse, and explicit names for nested AgentSpec/capabilities schemas.
- 6251d2a: Omit POST /api/v1/auth/logout from the SDK; the UI posts the cookie-clearing path directly.
- 2c3278e: Treat a replayed OIDC callback (browser Back after a successful login) as already signed-in instead of `/?error=login_failed`, and ignore that stale query when a session is still valid.
- 5e03c3d: Collapse Mintlify API Reference groups to Auth, Capabilities, Models, MCP Servers, Skills, Sandboxes, Agents, and Agent Sessions.
- Updated dependencies [42eee39]
- Updated dependencies [d7a640f]
- Updated dependencies [7ae5376]
- Updated dependencies [889caca]
- Updated dependencies [2ca7fb2]
- Updated dependencies [43d780e]
  - @truefoundry/trueforge-core@0.1.4-rc.0

## 0.1.3

### Patch Changes

- 3113aa4: Rename the MCP servers SDK method from `deleteAuthorize` to `deleteAuthorization`.
- 45dc6cd: Replace MCP authorize `redirect_url` with a same-origin `return_to` path to prevent open redirects after OAuth.
- c546350: Pass `tenantName` on `SandboxOptions` instead of injecting `TFY_TENANT_NAME` via exec env.
- Updated dependencies [08700d1]
- Updated dependencies [c546350]
  - @truefoundry/trueforge-core@0.1.3

## 0.1.2

### Patch Changes

- 9485811: Clear DCR OAuth tokens and pending authorizations when an MCP server URL changes, since the URL is the token audience.
- 5b981ab: Cancel a session even when the owning executor is gone (restart) or Redis cannot confirm abort. Freeze the running turn in the store so a new turn can start. `freezeAndGetTurn` now takes the cancellation reason (barge-in stays `cancelled-for-next-turn`; explicit cancel stays `client-cancelled`). Redis timeout and transport failures still freeze, with a warning that the cancel is not clean.
- Updated dependencies [363a522]
- Updated dependencies [5b981ab]
  - @truefoundry/trueforge-core@0.1.2

## 0.1.1

### Patch Changes

- 69237db: Await Daytona snapshot registration on sandbox provider configure so auth failures return 422 instead of a false pending status, and keep GET status refreshes persisted.
- f056973: Reject oversized HTTP request bodies with 413 via config-driven Hono bodyLimit (MAX_REQUEST_BODY_BYTES).
- 9a4d1a7: Add opt-in `withRouter` URL sync for shell places (`/`, `/agents/:agentName`, `/sessions/:sessionId`, `/settings`), with path customization via `routes` and `react-router-dom` as an optional peer. Serve the app shell for client-side deep links from the TrueForge server.
- Updated dependencies [69237db]
- Updated dependencies [7783fc0]
  - @truefoundry/trueforge-core@0.1.1

## 0.1.0

### Minor Changes

- b56c003: Initial 0.1.0-rc.1 prerelease of all public packages.

### Patch Changes

- e9bf976: Wrap settings MCP, skills, model-provider, and sandbox create/put bodies as `{ manifest }`. List/get items nest the stored document (`name` plus `manifest`, plus derived fields). Create returns 201. Chat lists and catalogs stay flat. Adapter catalogs follow the new SDK shapes.
- Updated dependencies [b56c003]
  - @truefoundry/trueforge-core@0.1.0

## 0.1.0-rc.1

### Patch Changes

- e9bf976: Wrap settings MCP, skills, model-provider, and sandbox create/put bodies as `{ manifest }`. List/get items nest the stored document (`name` plus `manifest`, plus derived fields). Create returns 201. Chat lists and catalogs stay flat. Adapter catalogs follow the new SDK shapes.

## 0.1.0-rc.0

### Minor Changes

- b56c003: Initial 0.1.0-rc.1 prerelease of all public packages.

### Patch Changes

- Updated dependencies [b56c003]
  - @truefoundry/trueforge-core@0.1.0-rc.0
