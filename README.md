# barber-saas-notifications-api

> notifications bounded context: service API

Part of the **Barber Saas** distributed system — team `barber-saas`, Grupo 2.
Governance and documentation live in [`barber-saas-docs`](https://github.com/code-corhuila/barber-saas-docs).

## Branching

Three permanent branches. **None of them accepts a direct commit** — you enter through a child
branch and leave through a Pull Request.

```
develop  <--PR--  feat/... fix/... chore/...
qa       <--PR--  qa/...
main     <--PR--  release/...  hotfix/...
```

Promotion happens **by re-application** (`git cherry-pick -x`), never by merging one permanent
branch into another: `merge develop -> qa` and `merge qa -> main` do not exist in this model.

`main` requires **1 approval from `ariel5253`**. On `develop` and `qa` the team sets its own review
rule.

Full policy: `00-governance/branching-policy.md` in `barber-saas-docs`.

## What this service does

The **notifications** domain (`notification-service.yaml` 2.3.0 in `barber-saas-docs`): the in-app
inbox of each user and the device tokens for push delivery. No public endpoint creates a
notification: `barber-saas-worker` delivers each domain event to `POST /internal/v1/events`
(ADR-016), and each event produces at most one notification.

| Operation | Who |
|---|---|
| `GET /health` | anyone (internal probe) |
| `GET /api/v1/notifications` | any user — only their own, paged `{data, meta}`, filter `read` |
| `POST /api/v1/notifications/{id}/read` | any user — another user's answers `404` |
| `POST /api/v1/device-tokens` | any user, with `Idempotency-Key` |
| `POST /internal/v1/events` | only the service token of `barber-saas-worker` |

| Event | Notifies | `type` |
|---|---|---|
| `AppointmentConfirmed` | `payload.clientId` | `APPOINTMENT_CONFIRMATION` |
| `AppointmentCancelled`, `AppointmentCompleted` | `payload.clientId` | `SYSTEM` |
| `AppointmentReminderDue` | `payload.clientId` — **also by e-mail**, by `window` (`DAY_BEFORE`, `HOUR_BEFORE`) | `REMINDER` |
| `StickerGranted`, `RewardRedeemed` | `payload.clientId` | `SYSTEM` |
| `PlanExpiringSoon`, `BarbershopSuspended` | each of `payload.owners` — **also by e-mail** | `SYSTEM` |
| `PasswordResetRequested`, `EmailVerificationRequested` | `payload.email` — **an e-mail with the code, no inbox notification** | — |

A null `clientId` (walk-in) answers `IGNORED`, a redelivered event `DUPLICATE`, another type `422`.
Each handled event writes one JSON log line (`event <id> of type <type>: <outcome>`) with the
worker's `X-Correlation-Id` as `correlationId`; never its payload, an address or a code.

**Code e-mails (`DEC-NOTIF-01`, `DEC-NOTIF-02`).** `PasswordResetRequested` and
`EmailVerificationRequested` send the 6-digit code to
`payload.email` through SMTP (`SMTP_*`, standard library) and creates no inbox notification: a user
who cannot sign in never reads one. The e-mail is sent first and then the event id alone is written
to `processed_event` — never the code — so a redelivery answers `DUPLICATE` without a second e-mail.
Without `SMTP_HOST`, or when the server refuses the message, the event answers `503` and the worker
retries it (ADR-016); a crash between sending and recording may send it twice, which at-least-once
delivery accepts. `SMTP_PASSWORD` is a secret of the environment and is **never** versioned.

**Notices by e-mail (`DEC-NOTIF-02`).** `PlanExpiringSoon` and `BarbershopSuspended` are also e-mailed
to each owner's `email`, after the push. That e-mail is best effort, like the push: a failure is kept
in `deliveryAttempts` (`EMAIL`, `FAILED`) and the event is still `PROCESSED`. Only the codes answer `503`.
`AppointmentReminderDue` is e-mailed too: its payload has no address, so the client's one is read from
identity-auth's `GET /internal/v1/users/{id}/contact` (`DEC-AUTH-10`) with `SERVICE_TOKEN`. If identity-auth
does not answer (`IDENTITY_AUTH_TIMEOUT_S`), the reminder is still `PROCESSED` without the e-mail. A
version 1 reminder has no `window` and is the day-before one.

**Push (FCM).** A new notification is also pushed to every device its user registered
(`POST /api/v1/device-tokens`), through the FCM HTTP v1 API. Each try is kept in the notification's
`deliveryAttempts` (the last 10); a token FCM no longer knows (`UNREGISTERED`) is removed. The push is
best effort: if FCM fails or is slow (`FCM_TIMEOUT_S`), the event is still `PROCESSED` and the
notification stays in the inbox; a redelivered event never pushes twice. Without
`FCM_SERVICE_ACCOUNT_JSON` nothing is pushed. That credential is a secret of the environment and is
**never** versioned.

## Structure (ADR-012, annex C)

```
src/notifications/
  domain/model/            Notification, DeviceToken, which notice each event produces, typed errors
  application/port/        inbound use cases and outbound ports (repositories, clock, ids)
  application/usecase/     one service per group of operations
  adapter/inbound/http/    FastAPI: RS256, envelope, correlation, routes
  adapter/outbound/        persistence: MongoDB (pymongo) and in memory
apps/api/__main__.py       composition root and explicit limits
```

`import-linter` (in `pyproject.toml`) enforces the layers in CI: the domain and the application
import no FastAPI, pydantic, pymongo or jwt.

## Depends on

- `barber-saas-identity-auth-api`: its public key (`JWT_PUBLIC_KEY`) to validate every token.
- `barber-saas-worker`: delivers the events.
- `barber-saas-notifications-db` and `barber-saas-infra-mongo`: the MongoDB collections, their
  validators and unique indexes. The service connects as `notifications_app` (`MONGO_URL`) and never
  migrates. Without `MONGO_URL` the repositories are in memory and nothing survives a restart.
  The unique `sourceEventId` index, not the code, makes a redelivered event notify once; a device
  token and its Idempotency-Key are written in one transaction (the instance is a replica set).

## Run it

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e '.[dev]'
lint-imports && pytest
# the MongoDB adapters too, against an instance migrated by barber-saas-notifications-db:
TEST_MONGO_URL="mongodb://localhost:27017/?directConnection=true" pytest
JWT_PUBLIC_KEY="$(cat ../barber-saas-infra-postgres/keys/jwt-public.pem)" python -m apps.api
```

As part of the platform: `./scripts/up.sh dev` in `barber-saas-infra-postgres`, which includes
`deploy/compose.yml`. The service listens on `notifications-api:8080` inside the `platform`
network; the gateway routes `/api/v1/notifications` and `/api/v1/device-tokens`, never `/internal`.
