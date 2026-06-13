# 05 — Auth (email magic-link + sessions)

Passwordless. A leader enters their email, gets a one-time link, clicks it, and
has a session. No passwords stored. OAuth is a later add behind the same session
abstraction. Parent: [`../SPEC.md`](../SPEC.md). Depends on data model (04), SMTP.

## Flow

```
POST /v1/auth/magic-link {email}
  → upsert user(email)
  → create magic_link(token=urlsafe(32), user_id, expires=+15min, used=false)
  → email a link: {APP_URL}/v1/auth/callback?token=…
  → 202 (always 202 even if email unknown — no account enumeration)

GET /v1/auth/callback?token=…
  → validate (exists, unused, unexpired); mark used
  → create session; set httpOnly Secure SameSite=Lax cookie (sid)
  → 303 → {APP_URL}/   (PWA reads /v1/auth/me)
```

## Tables

```
magic_links: id, user_id→users, token_hash, expires_at, used_at, created_at
sessions:    id, user_id→users, token_hash, expires_at(+30d sliding),
             user_agent, created_at, last_seen_at
```
Store **hashes** of tokens (`sha256`), compare in constant time. The cookie holds
the raw session token; rotate `last_seen_at`, slide expiry.

## Email

- Dev: **MailHog** in compose (`smtp://mailhog:1025`), view at :8025.
- Prod: operator-supplied SMTP (`SMTP_URL`, `MAIL_FROM`). Plain text + a tiny
  HTML. Subject "Your Convoy sign-in link". Link valid 15 min, single use.
- If SMTP is unconfigured, log the link at WARN in dev (never in prod).

## Sessions & guards

- `current_user` FastAPI dependency reads the cookie → session → user, or `401`.
- `require_owner(plan_id)` / `require_editor(plan_id)` check `plan_members`.
- Public share routes use **no** session; they validate the `share_token`
  (constant-time, against `plans.share_token`) and that `share_enabled`.

## Co-lead invites

`POST /v1/plans/{id}/members {email, role:editor}` (owner only):
- upsert user(email), create `plan_members(editor, invited_at)`,
- email an invite linking to the plan (recipient still signs in via magic-link).
- Editor can edit plan + stops + bailouts; **cannot** delete the plan, toggle
  share, or manage members (owner-only — see API authz matrix).

## Security notes

- Rate-limit `/auth/magic-link` per email + per IP (reuse a limiter like the old
  service).
- Tokens: 256-bit magic-link, 256-bit session; url-safe; hashed at rest.
- No enumeration: magic-link request always 202; invalid callback → generic 400.
- CSRF: SameSite=Lax + a custom header check on state-changing requests (the SPA
  sends `X-Convoy: 1`; share GETs are safe).

## Acceptance criteria

- Request link → email arrives in MailHog → callback sets a session → `/auth/me`
  returns the user.
- Expired/used token → 400, no session.
- Editor invited to a plan can edit it but is 403 on delete/share/members.
- Share routes work with zero auth and ignore sessions.
