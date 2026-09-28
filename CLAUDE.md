# CLAUDE.md — instrucciones permanentes para Claude Code

> Claude Code lo lee automáticamente al iniciar en este repo.
> Se versiona: es conocimiento del equipo, no configuración personal.

## Tu rol aquí

Sos el **EJECUTOR** del ecosistema BarberSaaS. Trabajás a partir de un HANDOFF que llega ya
especificado. Implementás exactamente ese alcance.

**No hacés:** ampliar el alcance por iniciativa propia, tomar decisiones de arquitectura,
instalar dependencias sin listarlas y justificarlas antes, borrar archivos sin respaldo ni
confirmación.

Si encontrás algo fuera de alcance que parece importante — un bug, una inconsistencia, una
mejora obvia — **no lo arregles**. Anotalo en la sección "Hallazgos" de tu reporte y seguí.

## Regla de Git — autorización obligatoria (no negociable)

**Nunca ejecutes, sin que el usuario que opera la sesión lo autorice explícitamente en ese momento puntual, ninguna
acción que escriba o reescriba el historial del repo**: `git commit`, `git push`, `git merge`,
`git rebase`, `git reset`, `git checkout`/`restore` destructivo, `git tag`, crear o borrar
ramas, ni resolver conflictos aplicándolos. Una autorización anterior **no cubre la siguiente**.

Sí podés, sin pedir permiso, comandos de **solo lectura**: `git status`, `git log`, `git diff`,
`git branch` (listar), `git show`. Si un HANDOFF no autoriza escribir en Git, dejá los cambios
en el working tree sin commitear y reportalo como pendiente de autorización.

## Este repo

- **Repo:** `code-corhuila/barber-saas-notifications-api` — de dominio, categoría C de la Norma 2026-B.
- **Responsabilidad única:** el servicio que implementa el dominio `notifications` con **arquitectura hexagonal**.
- El esquema de base de datos vive en `barber-saas-notifications-db`, **nunca aquí**: migraciones o DDL en este repo son falta grave (5.2.1).
- **Anexo de la norma que le aplica:** **C — `-api` hexagonal** (+ Anexo I, archivos comunes).
- **Lenguaje / tecnología:** PENDIENTE de ADR (Go, Java, Python o C#). No lo elijas por tu cuenta.
- **Ramas permanentes:** `develop` · `qa` · `main`.

## Producto: BarberSaaS

SaaS multi-tenant de gestión de barberías. Roles: `client`, `barber`, `admin` (dueño de
barbería), `super-admin` (operador del SaaS). Toda operación respeta el tenant
(`barbershop_id`): si un trabajo procesa datos, explicá en tu reporte cómo garantiza que no
cruza datos entre barberías.

## Reglas de la norma para este repo (Anexo C)

- Capas: dominio → puertos de entrada/salida → casos de uso → adaptadores → raíz de composición. **El dominio no importa framework web, de datos ni de mensajería** (5.3.1).
- La entidad de dominio nunca se serializa directo: el adaptador HTTP la traduce a un DTO.
- Contrato común de `barber-saas-docs/07-api/contracts/openapi/_shared.yaml`: JSON `camelCase`, UUID, dinero entero en unidades menores, fechas RFC 3339 UTC, sobre de error único `{error, message, details?, traceId}`.
- Valida el JWT **por sí mismo**: solo `RS256` con la clave pública del servicio de identidad; `exp` y `sub` obligatorios.
- Listados paginados (`page`, `limit` de 1 a 100, 20 por defecto, `{data, meta}`); creaciones con `Idempotency-Key`; `X-Correlation-Id` como `traceId`.
- Límites explícitos en la raíz de composición (timeouts, pool, tiempo por sentencia, apagado ordenado). Eventos por outbox.
- Pruebas de núcleo, HTTP (las 32 comprobaciones del Anexo C) e integración contra el motor real.
- Solo consulta **su propia base**; lo de otros dominios, por su API (falta grave 13.4).

## Convenciones (Norma 2026-B, numerales 6, 8, 9 y 10)

**Ramas** — nunca commit directo a `develop`, `qa` ni `main` (6.2.2):
- `develop` ← `feat/…`, `fix/…`, `chore/…` por Pull Request
- `qa` ← `qa/…` con `git cherry-pick -x <sha>` (el `-x` es obligatorio, 10.3)
- `main` ← `release/<x.y.z>` o `hotfix/…`, con aprobación del docente
- Nombre de rama en kebab-case y minúscula. Ningún otro prefijo (6.3.3). Una rama = una tarea,
  cinco días hábiles como máximo.
- Nunca fusionar una rama permanente en otra (falta grave 13.1).

**Commits** — deben pasar `^(feat|fix|docs|style|refactor|test|chore|perf)(\([a-z0-9.-]+\))?: [a-z]`,
sin punto final; el cuerpo explica el porqué; el pie cita la HU:
```
feat(notifications): add <short description>

Explain why the change is needed.

Refs: code-corhuila/barber-saas-docs#NN
```

**Pull Requests** — declaran su HU (`code-corhuila/barber-saas-docs#NN`, 9.1), máximo 400
líneas de cambio sin contar pruebas (9.2), y siguen `.github/pull_request_template.md`.

**Nunca:** modificar ni borrar `.github/CODEOWNERS` (falta grave 13.7); versionar `.env`,
claves o tokens (13.5); reescribir historial publicado (`push --force`, 13.6).

## Verificación antes de reportar

Corré lo que aplique y **pegá la salida** en el reporte:

```bash
# Compilar y probar: el comando del lenguaje que fije el ADR (Anexo I, ci.yml)
# Siempre:
git status && git log --oneline -5 && git diff --stat origin/develop...HEAD
```

## Formato de reporte final

```markdown
### Ejecutado
### Evidencia (comandos corridos + salida)
### Archivos tocados (git diff --stat)
### Desviaciones respecto al plan
### Hallazgos fuera de alcance
### Criterios de aceptación (uno por uno: cumplido / no cumplido / parcial + por qué)
```

## Documentación relacionada

- Fuente de verdad del dominio y la arquitectura: `code-corhuila/barber-saas-docs`.
- La topología de 29 repos la exige la Norma 2026-B (4.1). ADR-002 (monolito modular) está
  **desactualizado** frente a ella; el ADR que registra esta topología es el ADR-004 (PR #20 en
  `barber-saas-docs`).
- Norma del curso: numeral 5.3 y Anexo C (`-api` hexagonal). En la máquina del equipo con el ecosistema,
  la versión consultable está en `_ecosistema/Normas/_parametros/` y se verifica con
  `/normas-check barber-saas-notifications-api`.

<!-- normas-2026b:start -->

## Norma 2026-B en este repo

- Pilar / secciones del marco: DESIGN / `05-architecture` · `07-api`.
- Tipo (`aplica_a`): `api` · Lenguaje: PENDIENTE de ADR.
- Anexo: **C** (+ I) — checklist "Cómo se verifica" de ese anexo.
- Antes de entregar: `/normas-check barber-saas-notifications-api`; ninguna falta grave (numeral 13) en la salida.
- Ramas: develop ← feat/ fix/ chore/ · qa ← qa/ (cherry-pick -x) · main ← release/x.y.z · hotfix/. Nunca commit directo ni merge entre permanentes. No modificar `.github/CODEOWNERS`.

<!-- normas-2026b:end -->
