# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] - 2026-11-05

User stories: code-corhuila/barber-saas-docs#6, code-corhuila/barber-saas-docs#123, code-corhuila/barber-saas-docs#128, code-corhuila/barber-saas-docs#131

### Added

- **events:** e-mail the verification code like the reset code
- **domain:** word the plan notices for each owner of the barbershop
- **application:** e-mail a notice as a second channel without blocking the event
- **domain:** word the hour-before reminder and mark reminders to be e-mailed
- **application:** e-mail reminders to the client's address read from identity-auth
- **identity:** read a user's contact from identity-auth with the service token
- **app:** compose the identity-auth contact reader with its own service token
- **application:** log every handled event with its id, type and outcome
- **domain:** name the plan and the barbershop in the notices when the event carries them
- **email:** send every e-mail as HTML too

### Fixed

- **events:** ignore a password-reset event whose code already expired
- **device-tokens:** answer 200, not 500, when one device registers its token twice at once

### Documentation

- **readme:** list the verification code with the reset code
- **readme:** explain the notices e-mailed to the owners and when smtp is missing
- **readme:** explain the reminder windows and their e-mail
- **readme:** explain the log line of each handled event

### Tests

- **events:** specify that an expired reset code is ignored and not e-mailed
- **events:** specify the e-mail verification code like the reset code
- **events:** specify the plan notices to the owners by inbox, push and e-mail
- **events:** specify both reminder windows and their e-mail to the client
- **app:** specify the identity-auth settings of the composition root
- **events:** specify one info line per handled event, without the payload
- **events:** specify the plan and barbershop names in the notices, with the text without them as fallback
- **device-tokens:** specify one document and no error when a device signs in twice at once

## [2.0.0] - 2026-10-08

User stories: code-corhuila/barber-saas-docs#5, code-corhuila/barber-saas-docs#6, code-corhuila/barber-saas-docs#21, code-corhuila/barber-saas-docs#23, code-corhuila/barber-saas-docs#59

### Added

- **domain:** add the notification aggregate and its typed errors
- **application:** list my notifications and mark one as read
- **http:** answer every error in the single envelope with the correlation id
- **http:** validate the rs256 token in the service itself
- **http:** serve the health check, my notifications and mark as read
- **domain:** decide which notification each domain event produces
- **application:** receive an event and notify at most once
- **http:** accept events from the worker at /internal/v1/events
- **domain:** add the device token, unique by token
- **application:** register a device token idempotently by key
- **http:** serve POST /api/v1/device-tokens with Idempotency-Key
- **app:** compose the service with its limits declared
- **deploy:** build the image and compose the service for the platform
- **persistence:** keep notifications and device tokens in mongodb
- **app:** use mongodb when MONGO_URL is set
- **deploy:** connect to the single mongodb instance as notifications_app
- **application:** push a new notification to the devices of its user
- **persistence:** record delivery attempts and find the devices of a user
- **push:** send through the fcm http v1 api with a service account
- **app:** push only when FCM_SERVICE_ACCOUNT_JSON is set
- **domain:** build the password-reset e-mail instead of an inbox notice
- **events:** e-mail the reset code once and answer 503 when it cannot
- **email:** send through smtp with the standard library
- **persistence:** keep processed events in mongodb
- **app:** wire the password-reset e-mail from SMTP_* settings

### Fixed

- **events:** finish a sent reset even when its record fails
- **email:** refuse smtp credentials when SMTP_SECURITY is none

### Documentation

- **readme:** point the header to Barber Saas and barber-saas-docs
- **readme:** explain the service, its structure, dependencies and how to run it

### Tests

- **notifications:** specify the inbox of each user and marking as read
- **http:** specify the annex c checks of the inbox
- **http:** specify that an unexpected failure hides its detail
- **events:** specify one notification per delivered event
- **device-tokens:** specify idempotent registration of a device token
- **app:** specify the composition root and its declared limits
- **persistence:** specify the mongodb repositories against the real collections
- **app:** specify the service on mongodb end to end and its declared limits
- **push:** specify pushing a new notification to the devices of its user
- **push:** specify the delivery attempts in mongodb and the push settings
- **events:** cover the password-reset e-mail
- **events:** specify that a sent code whose record fails is not retried
- **email:** specify that credentials over an unencrypted connection are refused
- **app:** specify the service without smtp and with cleartext credentials

### Maintenance

- set up the python project, its ci and the pull request template

[3.0.0]: https://github.com/code-corhuila/barber-saas-notifications-api/releases/tag/v3.0.0
[2.0.0]: https://github.com/code-corhuila/barber-saas-notifications-api/releases/tag/v2.0.0
