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

The **notifications** domain (`notification-service.yaml` 2.1.0 in `barber-saas-docs`): the in-app
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
| `AppointmentReminderDue` | `payload.clientId` | `REMINDER` |
| `StickerGranted`, `RewardRedeemed` | `payload.clientId` | `SYSTEM` |
| `PasswordResetRequested` | `payload.userId` | `SYSTEM` |

A null `clientId` (walk-in) answers `IGNORED`, a redelivered event `DUPLICATE`, another type `422`.

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
