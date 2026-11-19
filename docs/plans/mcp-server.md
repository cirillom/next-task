# Remote MCP server implementation plan

Planning only. Application baseline: v2.12.2 (f90d43c); revised 2026-11-17.

Release clients: **Claude and ChatGPT**. Endpoint:

**https://next.studas.com.br/mcp**. Keep the existing FastAPI process,

accounts, SQLite database, Docker image and Cloudflare Tunnel.

## 1. Decisions that keep this small

- Use stable **Python MCP SDK v2**, importing `MCPServer` from `mcp.server`, over

  Streamable HTTP. Pin the tested release and lockfile. Support the current

  2026-07-28 protocol and let the SDK handle legacy clients; do not implement

  negotiation or initialization yourself. [SDK v2](https://py.sdk.modelcontextprotocol.io/whats-new/),

  [legacy compatibility](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/legacy-clients.md).

- Use a maintained OAuth implementation in the **same FastAPI deployment**.

  Start with **Authlib's framework-independent authorization-server core**,

  grants, PKCE and revocation endpoints. Add only the thin ASGI

  request/response bridge and Next Task persistence, login, consent and policy

  hooks. Its FastAPI client integration is not an authorization server; prove

  the server adapter before full persistence or consent UI. Do not implement

  OAuth parsing, grant exchange or PKCE algorithms manually. [Authlib](https://docs.authlib.org/en/stable/oauth2/authorization-server/),

  [server core](https://github.com/authlib/authlib/blob/main/authlib/oauth2/rfc6749/authorization_server.py).

- Configure MCP as a resource server using `TokenVerifier` and `AuthSettings`;

  explicitly enable resource/audience validation. The OAuth library issues

  tokens; the SDK verifies them through the application callback. Do not start

  with the SDK's embedded `auth_server_provider`: current documentation advises

  against it for new servers. AS/RS separation is logical, with both hosted in

  this application. [SDK authorization](https://py.sdk.modelcontextprotocol.io/run/authorization/).

- Use **CIMD-only public clients** initially, with

  `token_endpoint_auth_method=none` and mandatory PKCE S256. Advertise

  `client_id_metadata_document_supported: true`. No DCR endpoint, registered-client

  table or client-secret infrastructure. Add DCR only after a recorded failure

  in a target client demonstrates a compatibility need; do not build a fallback

  preemptively. CIMD removes dynamic registration, not authorization, consent,

  grants, tokens or revocation. [MCP client identification](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/client-registration).

- Choose **fully authenticated MCP** for v1. Every tool handles private data,

  so this uses the SDK's existing HTTP auth boundary. ChatGPT also supports

  anonymous discovery/mixed authentication, but that is a different mode;

  do not build both. Select OAuth in both clients and prove this mode first.

  Diagnose an actual failure before changing the design.

  [ChatGPT authentication modes](https://developers.openai.com/api/docs/guides/custom-mcp-server).

- Ship eight tools. Defer `get_profile`: account identity is shown during consent

  and in authorized connections. Add a read-only profile tool only if milestone

  1 demonstrates an account-identification problem; it must not introduce

  another permission or expose additional personal data.

- Skip extra services, databases, generic service frameworks, configurable

  auth modes, provider-specific protocols, task/tag updates or deletion,

  draft/Pomodoro tools, resources, prompts and marketplace publication.

## 2. Milestone 1: prove one complete client workflow

**1a — small feasibility test, before full storage/UI:** use an isolated

FastAPI/SDK v2 HTTP harness, fixture identity and ephemeral credentials to prove

Authlib's code exchange with S256, CIMD validation, public-client `none`

handling, resource binding, token issuance/refresh and issuer identification.

Exercise the metadata-fetch security boundaries with controlled fixtures.

This is a focused test of reusable integration code, not a second server or

an authentication bypass to ship. Do not implement OAuth parsing, PKCE or grant

exchange manually. If the adapter requires substantial custom protocol logic,

stop and reevaluate the library; document the gap before building further.

**1b — durable end-to-end workflow:** add the required SQLite grant/token

persistence, existing-account login, minimal explicit consent/disconnect

support and **only `list_tasks`**. Extract only the shared listing logic needed

for this tool. Use isolated SQLite locally and a disposable invited account

externally; never use production task data as fixtures.

Connect Claude web/Desktop as a custom remote connector and ChatGPT as a custom

MCP server with **OAuth and CIMD** (Claude's published identity; ChatGPT's CIMD

choice). Verify both supply public-client metadata and support `none`; do not

fall back to secrets or DCR silently. Test through

https://next.studas.com.br/mcp and the current tunnel. Account/workspace

permissions still govern who can add custom connections. [Claude setup](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp),

[ChatGPT setup](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt).

**Gate before implementing the other seven tools:** both clients must complete

MCP/issuer discovery, CIMD identification, login, explicit consent, scoped

access/refresh token issuance, tool listing, unfiltered/filtered list_tasks,

access-token expiry/refresh, app restart and disconnect. Revoked credentials

must fail immediately and two users must remain isolated. Verify modern and

legacy SDK HTTP clients return equivalent results. Record client surface,

SDK/OAuth-library versions, protocol, CIMD URL/auth method, issuer behavior

and outcomes.

An Inspector or in-memory SDK test alone does not pass this gate.

No other tools until this gate passes in both clients. A public client's

`client_id` identifies the software, not an authenticated person or a secret;

PKCE binds code redemption to the initiating flow. Do not add a client-secret

authentication scheme or an authentication service to satisfy this milestone.

## 3. Authentication, permissions and security boundaries

**Public protocol metadata is not public task access.** With fully authenticated

MCP, a valid request to /mcp without a valid Bearer token returns 401 and a

WWW-Authenticate discovery challenge, including legacy initialization and tool

discovery. Health, OAuth entry points and well-known metadata have their own

behavior; there is no blanket requirement that all unauthenticated HTTP

requests return 401. Reject cookie-only MCP authentication and tokens in URLs.

Use NEXT_TASK_PUBLIC_APP_URL=https://next.studas.com.br as the fixed issuer

origin and https://next.studas.com.br/mcp as the resource. Never derive these

from Host/forwarded headers. With the origin unset, retain ordinary application

access, show setup unavailable and refuse MCP/OAuth use. Local tests may use

localhost HTTP under the existing origin validator.

| Required endpoint | Behavior |

| --- | --- |

| /.well-known/oauth-protected-resource/mcp and its root alias | Public JSON advertising this resource and issuer; use SDK metadata where provided. |

| /.well-known/oauth-authorization-server | Public JSON with the fixed issuer, code/refresh grants, S256, scopes, CIMD support and token_endpoint_auth_methods_supported=["none"]. No registration_endpoint. |

| /oauth/authorize, /oauth/token, /oauth/revoke | Authlib-backed authorization-code + PKCE S256, refresh and revocation; application hooks supply persistence, secure CIMD resolution and policy. No implicit/password grants. |

| /api/mcp/authorizations/{request_id} (GET/POST) | Existing cookie-authenticated browser reads consent details and explicitly allows/denies. Bind to the session with CSRF/origin checks. |

| /api/settings/mcp (GET), /api/settings/mcp/connections/{grant_id} (DELETE) | Current user's setup/connections and explicit revocation; ownership and CSRF/origin checks apply. |

**CIMD resolution:** use maintained library validation/fetching where it meets

these requirements; otherwise one narrowly scoped resolver using existing

HTTP/standard-library facilities, proven in 1a. Do not build a general fetcher.

- Accept HTTPS client-ID URLs with a path; reject userinfo/fragments and

  unsupported ports/schemes. Require 200 JSON with the specified field types,

  `client_id`, `client_name`, `redirect_uris`, and public-client `none` handling

  under the specification's metadata/default rules. The document's `client_id`

  must equal its URL exactly. Validate

  the callback against its HTTPS redirect list by exact string comparison.

- Reject private, loopback, link-local, reserved and internal destinations,

  including IPv4-mapped IPv6 and mixed public/private DNS answers. Enforce this

  on the **actual connection**, not only a DNS precheck: prevent rebinding and

  resolution-to-connect races while preserving hostname TLS validation/SNI.

  Do not inherit an environment proxy that bypasses destination validation,

  and send no browser cookies or OAuth credentials to metadata hosts.

- Reject metadata HTTP redirects initially. Use TLS verification, a five-second

  total deadline and a 64 KiB decoded-body cap enforced while streaming. Fetch

  no logos, client_uri pages, JWKS or other metadata-linked URLs for this public

  client mode. Fail closed on malformed metadata, fetch failure or limit breach.

- Keep only a bounded validated metadata cache (initial limits: 128 entries,

  TTL no longer than five minutes, shortened by HTTP cache directives; honor

  no-store). No unbounded/permanent registry or stale-on-error trust. Refresh

  metadata as required by the CIMD specification; bind the validated client-ID

  URL and exact callback to the pending code/grant so metadata changes cannot

  alter an in-flight exchange. Cached metadata never authorizes user access.

These are initial implementation limits, not user-facing configuration options.

Rate-limit metadata resolution and OAuth attempts to bound outbound work.

[CIMD security](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations#client-id-metadata-document-security),

[OpenAI OAuth contract](https://developers.openai.com/plugins/build/auth).

**Issuer identification:** use Authlib's RFC 9207 `IssuerParameter` extension

if the pinned version integrates cleanly. Return the fixed

`iss=https://next.studas.com.br` on successful authorization callbacks and valid

error callbacks, consistent with discovery metadata. Do not redirect invalid

callback requests just to return `iss`. Advertise

`authorization_response_iss_parameter_supported: true` only after tests cover

both response paths. SDK client tests must reject mismatched/missing issuer

when support is advertised; observe both real clients in milestone 1. Next Task

is the issuer/resource server, not a new OAuth client: validation belongs in

the client/test side. If library support is inadequate, record the limitation

and do not advertise support. Never derive issuer from request headers.

[Authlib RFC 9207](https://docs.authlib.org/en/stable/oauth2/specs/rfc9207.html).

Keep four scopes and enforce **one relevant scope per tool**:

| Scope | Tools |

| --- | --- |

| tasks:read | list_tasks, get_task, get_next_task, list_next_tasks |

| tasks:create | create_task |

| tags:read | list_tags, get_tag |

| tags:create | create_tag |

`AuthSettings.required_scopes` must not require all four scopes globally. The

transport validates credentials; dispatch/handlers check the tool's scope

before accessing data. Publish matching per-tool OAuth securitySchemes metadata

through the SDK, including the ChatGPT-compatible _meta declaration. Metadata

is advisory, never the enforcement mechanism. For insufficient scope, use the

supported auth error/challenge, including _meta["mcp/www_authenticate"] on tool

errors where needed for ChatGPT reauthorization. Verify the wire response

rather than assuming FastAPI's HTTP exception handler runs inside MCP calls.

A token with only tasks:read tags:read must use every reading tool and fail both

creates. [Tool auth metadata/challenges](https://developers.openai.com/plugins/build/auth#triggering-authentication-ui).

Persist only pending authorization/code state, consent/grants and access/refresh

credentials in additive SQLite tables. Retain the CIMD client-ID URL and the

validated callback/policy fields needed by each transaction/grant; no

registered-client tables or client secrets. Use random opaque tokens and the

existing SHA-256 hashing helper for stored credentials; retain user, client,

resource, scopes, expiry and revocation. Codes expire after five minutes,

access tokens after one hour and refresh tokens after 30 days. Consume codes

and rotate refresh credentials atomically; replay revokes the grant. Preserve

state across restarts. Never accept credentials from obsolete OAuth tables

that an upgraded installation might retain.

Validate exact metadata-declared HTTPS redirects, PKCE, client identity, resource,

scope, expiry and grant/user existence through library/application hooks.

Reject wildcard callbacks and arbitrary post-login return URLs. Preserve

OAuth state through a short-lived server-side transaction; the request ID

alone cannot approve access. Show the signed-in account, unverified client

name/redirect host and requested permissions; require explicit Allow/Deny and

return the effective granted scopes. No approval on page load or dismissal.

Revocation invalidates every credential for that grant immediately. Extend

shared replace_password to revoke grants for password changes, recovery and

operator resets in the existing transaction. Browser logout retains external

connections, which users disconnect explicitly in Settings. Apply existing

rate-limit machinery to metadata/authorization/token attempts and tool calls; bound

request sizes, search and filter arrays. Log identifiers/statuses, never tokens,

OAuth query strings, passwords or task bodies. Treat descriptions as user data.

**User binding:** the token verifier resolves a live persisted grant and its

existing Next Task user, then sets `AccessToken.subject` to that user's stable

identity (the persisted User.id represented as a string). Keep OAuth client_id

as the client identity; never use it as the owner or a client-to-user mapping.

Tools resolve ownership exclusively from this authenticated subject/current

grant. Reject missing/deleted users and expired/revoked/mismatched grants.

Never trust a caller-supplied user ID, subject, session ID or user-name claim.

Validate the same owner for direct lookups, filters, tag attachments and parent

relationships; creation always assigns the authenticated owner.

## 4. Eight tools and application semantics

| Tool | Contract |

| --- | --- |

| create_tag | Existing TagCreate: name, optional description, color, score_value, parent_tag_id; return TagRead. Preserve scoped duplicate-name rules and relationship validation. |

| get_tag | Owned tag_id; return TagRead with disambiguated display name, parents, children and ancestors. |

| list_tags | Optional case-insensitive search over name/description, direct parent_tag_id, offset, limit. Combine filters with AND; no filters lists all owned tags, ordered by existing name/ID rules. |

| create_task | Existing TaskCreate: title, optional description, priority (default/minimum 1), due_date, last_worked_at, parent_task_id, tag_ids; return TaskRead. Preserve date/UTC validation. |

| get_task | Owned task_id; return TaskRead. Drafts (priority=0) are outside this surface, including direct ID lookup. |

| list_tasks | Existing finished (false by default, null for either), abandoned (exclude/only/include), search, blocked, actionable, include_tag_ids, exclude_tag_ids and tag_match (all/any), plus pagination. Keep existing filter/ranking defaults. |

| get_next_task | Optional tag scope; return {task: TaskRead or null} for the first shared Next result. This is a recommendation read with no task mutation. |

| list_next_tasks | Same tag scope plus pagination; return the ranked actionable list, including its first recommendation. |

Tool/parameter descriptions must say that **tag IDs identify unique tags**,

even when names repeat or one tag has multiple hierarchical paths. Included

and excluded task scopes expand through descendants; exclusions take

precedence, and NextScope rejects an explicitly overlapping ID. Omitted scope

means all tags, not the browser's locally saved filter.

Reuse the Next page's exact query: priority>0, unfinished, not abandoned,

blocked=false, actionable=true, requested scope. Preserve scheduled blockers,

unfinished descendants, inherited abandonment, scoring fallback, ancestor

boosts and ties. Reads never update last_worked_at or start timers.

Use {items, next_offset: integer or null} for lists: offset 0, default limit

50 (10 for Next), maximum 100; search maximum 300 characters. Return fixed

compact summaries with identity, task status/parent/tag identities, blocking

and ranking metadata/warnings; get/create return full existing read schemas.

Page only after full filtering/ranking. Pages reflect live data and can shift;

defer snapshot cursors and performance redesign until measured need.

Use SDK-generated schemas/structured results and equivalent JSON text content.

Annotate reads readOnlyHint=true; creates readOnlyHint=false,

destructiveHint=false, idempotentHint=false; openWorldHint=false throughout.

Create descriptions must warn against blind retries: a lost response may hide

a successful creation, so retrieve/check before retrying. Return safe business

error codes/messages without stack traces. There is no user_id input; derive

ownership from the authenticated token. Foreign/missing IDs are

indistinguishable; check every filter/parent/tag relation before traversal.

## 5. Minimal change surface

| Existing surface | Required work only |

| --- | --- |

| routes/tasks.py, services/tasks.py | Extract listing for milestone 1; subsequently extract only shared get/create/ranking helpers needed by the remaining tools. |

| routes/tags.py, services/tags.py, schemas.py | Reuse creation, lookup, serialization, scoped name checks, SQLite write locking and relationship validation; add filtered tag listing. No unused GET-by-ID REST route. |

| main.py, config.py | Mount MCPServer.streamable_http_app() at exactly /mcp, own SDK lifespan, register OAuth/metadata before the SPA catch-all. Reuse configured public origin. |

| Auth, models and Alembic | Thin Authlib integration, additive persistence, consent and grant revocation through shared password replacement. |

| Settings, App.svelte, frontend API/types, locales | Minimal consent/login continuation and feature panel, connection management, English/Brazilian Portuguese strings. |

| Dependency/lock files, tests, README | Add only mcp and the selected maintained OAuth library; document client connection and validation. |

Search every caller before moving helpers, including routes/drafts.py's

imports of task_read/apply_task_relations. Preserve transactions, locking,

validation and error handling. Do not redesign task/tag architecture, scoring,

REST defaults/array responses or the database. Do not internally call REST over

HTTP or pass FastAPI Depends/Query defaults into MCP. Prove REST/MCP result

equivalence after the documented MCP list-summary projection with regression

tests; do not change REST to match that projection. Leave unrelated

Dockerfile/Compose cleanup out of this work.

**Exact ASGI routing:** retain the SDK's internal `/mcp` path and attach its

complete ASGI application to an exact `/mcp` ASGI route in FastAPI, preserving

the original path. Do not combine a `/mcp` mount prefix with the SDK's default

`/mcp`, extract routes in a way that drops SDK auth middleware, or use a root

mount that shadows the existing SPA. Delegate advertised discovery paths to

the SDK application where provided; keep the root metadata alias consistent.

Configure stateless HTTP/JSON responses on the SDK app, construct it before

entering its session-manager lifespan, and start/stop that manager from the

parent FastAPI lifespan. Do not start another server.

Require production-ASGI integration tests showing `POST /mcp` reaches the SDK

without 301/302/307/308 responses, authenticated and unauthenticated requests

follow the chosen auth mode, and `/mcp/mcp` is not a second MCP endpoint.

Verify lifecycle startup/shutdown, an existing REST endpoint, normal SPA

fallback, and OAuth/discovery JSON or protocol responses rather than frontend

HTML. Test modern and legacy HTTP clients through this exact routing.

Keep Host/Origin validation enabled for the actual public hostname, allow

absent Origin for server clients and reject untrusted supplied Origins.

Preserve normal frontend/API routing and prevent SPA HTML from intercepting

MCP/discovery. Add CORS only if a demonstrated browser flow requires it.

[SDK mounting guidance](https://py.sdk.modelcontextprotocol.io/run/asgi/).

In Settings, add one **Connect your AI assistant** panel using house components:

explanation, copyable endpoint, concise Claude/ChatGPT OAuth instructions,

example prompts, authorized connections and Disconnect. Include account and

requested permissions in consent; explain data sharing and creation rights.

Call grants “Authorized connections”, not live client status. Include loading,

unavailable/error/empty states and accessible keyboard behavior. No provider

API keys, token-copy UI, global toggle or automatic linking.

## 6. vmstudas: verify deployment, change only proven problems

Use **https://next.studas.com.br/mcp and the existing tunnel unchanged**.

No new hostname, tunnel, listener or published app port is planned. Live VM

inspection previously failed because the vmstudas SSH alias did not resolve;

do not treat historical paths as current deployment facts.

1. Confirm the existing app's Compose project, data mount and healthy origin.

   Verify the application origin remains private.

   Verify NEXT_TASK_PUBLIC_APP_URL=https://next.studas.com.br, secure cookies

   and retained credential secret. Back up SQLite consistently before the

   additive migration. Use the established reviewed-image deployment process.

2. From outside LAN/Tailscale, check the app and metadata documents. Confirm

   /mcp, /oauth/*, /.well-known/*, login/consent/assets and new APIs reach

   FastAPI without prefix stripping, slash redirects or SPA interception.

   Metadata returns 200 JSON; valid unauthenticated MCP requests return the

   selected mode's 401 challenge. Browser GET alone is not an MCP test.

3. Complete milestone 1 through the existing route. Before release, verify the

   trusted immediate-proxy configuration and actual client-IP resolution; test

   that spoofed forwarding headers cannot bypass rate limits. Check that

   Authorization/protocol headers and the external HTTPS scheme survive the

   tunnel, Access/WAF challenges do not intercept protocol traffic, and caching

   cannot serve OAuth or user data across requests/users. These are read-only

   checks/tests, not planned configuration changes. On a specific failure,

   record the request and change only the responsible rule/header. Do not

   preemptively disable protections or reconfigure Cloudflare/proxies.

4. If origin connectivity is the demonstrated failure, inspect cloudflared's

   actual network namespace/upstream. A container's localhost is itself;

   separate rootless Docker daemons do not share DNS. Preserve the private-origin

   boundary when correcting connectivity.

   Tunnel traffic is outbound; do not add router forwarding or expose Docker,

   Portainer, SSH or unrelated routes. [Tunnel guidance](https://developers.cloudflare.com/tunnel/).

5. After deployment, repeat refresh, restart and immediate-revocation checks.

   On rollback retain additive tables and current task data; revert the image

   rather than discarding the database. This planning task performs no deployment.

## 7. Remaining milestones and acceptance

After milestone 1 passes in **both clients**, add the other seven tools in

small changes, extracting shared logic only when needed. Then finish the

Settings panel/docs and run repository CI: Ruff, backend/root pytest,

frontend check/tests/build, language browser tests and production image build.

Recheck all eight tools externally before release; record evidence rather

than inferring compatibility from SDK conformance.

Focused acceptance coverage:

- OAuth: CIMD discovery/identification and public-client `none`, statuses for

  the chosen fully authenticated mode, explicit Allow/Deny and login

  continuation, CSRF, exact redirect/client/resource

  binding, PKCE, expiry, concurrent code redemption, refresh rotation/replay,

  restart, revoke and every password-reset/change path. RFC 9207 success/error

  callbacks and client rejection of mismatched/missing issuer when advertised.

- Metadata fetch: exact client-ID match, malformed/missing fields, wrong auth

  method, private/internal and IPv6 destinations, mixed DNS answers, rebinding,

  redirect rejection, TLS failure, timeout/body limits, cache bounds/expiry and

  no-store. Failures must create no grant and disclose no internal response.

- Permissions: every tool with its required scope alone and without it;

  both read scopes together enable all six reads and neither create. No

  global create-scope requirement. Metadata matches actual enforcement.

- Ownership: two users cannot read, filter, parent, attach tags or revoke each

  other's objects/grants, including when both use the same CIMD client ID.

  Subject remains stable through refresh/restart and differs by user;

  injected caller IDs cannot change it. Deleted-user/revoked-grant tokens fail.

  Invalid requests reveal no foreign-object existence.

- Semantics: create/get/list/filter round trips, empty/paginated results, tag

  disambiguation/multiple paths, scoped duplicates, date/UTC input and REST

  equivalence. Freeze time to compare complete Next ordering, parent boosts,

  ties, scheduled blockers, abandonment, descendants and warnings.

- Persistence/UI: fresh/upgrade migrations preserve existing data and reject

  obsolete credentials; production ASGI startup/shutdown works. Both languages,

  copy, connection listing/disconnect, consent errors and client create

  confirmations work without accidental approval or duplicate creation.

- Deployment: exact POST route/lifecycle and REST/SPA preservation, public

  OAuth/MCP requests through the unchanged tunnel, trusted/spoofed proxy-header

  cases and private-origin checks. Record configuration edits only for a

  reproduced failure.

Trade-offs: one auth mode, one client-identification mechanism and two libraries

avoid a custom protocol stack. CIMD replaces registration state with a small,

security-critical metadata resolver; it does not remove the OAuth integration.

Eight tools and offset pagination keep the feature small. The first external

workflow is the feasibility gate, not a promise of verified compatibility.

New services, abstractions or deployment changes require demonstrated need

and are outside this implementation plan.

## 8. Remaining technical uncertainties

- Whether the pinned Authlib release supports the FastAPI bridge, public CIMD

  clients, resource binding and refresh rotation with only small policy/storage

  hooks. Its server-side CIMD support is not assumed; milestone 1a decides.

- Whether maintained fetching facilities meet the required DNS-to-connection

  SSRF guarantees without a large custom transport. A DNS precheck followed by

  an unrestricted HTTP request is not an acceptable shortcut.

- The actual CIMD documents, public-client auth methods, callback URLs and

  fully authenticated connection behavior of the user's Claude/ChatGPT

  surfaces. Prove them in milestone 1b; DCR is absent unless a specific

  incompatibility later justifies revising the plan.

- RFC 9207 behavior in the pinned Authlib version and both clients, including

  error callbacks; advertise only demonstrated support. The library documents

  an extension, but integration has not been exercised here.

- Exact FastAPI/SDK mount behavior and the current vmstudas proxy/Cloudflare

  configuration. The routing/proxy acceptance tests are required evidence;

  no live deployment or client test has been performed by this planning task.