# Plan: Local SQLite Auth System

Status: proposed — not started (2026-09-28)

## Requirements (confirmed with user)
- Login ID: **username** (case-insensitive, no email)
- Sign-up: **first user becomes admin**; afterwards only the admin creates users
- Scope: **all API + WebSocket + SSE endpoints** require a session, except `/health` and `/auth/*`
- Session transport: **HttpOnly cookie**, opaque token stored hashed in SQLite
- Password reset via a **recovery code** issued at account creation
- `auth` and `db` code live in **separate packages**

## Design decisions
- **DB layer:** SQLAlchemy 2.0 + Alembic migrations (versioned schema, portable to Postgres later)
- **Hashing:** argon2id via `argon2-cffi`; hash is upgraded automatically on login if parameters change
- **Recovery code:** one code, ~100 bits, formatted `K7Q2-9XMP-4HDA-ZR8N-TW3C`, stored hashed, shown once. Using it rotates it (the reset returns a new code) and revokes every session
- **Admin-created users** get a temporary password with `must_change_password=1`. The forced first change also issues a new recovery code, so only the user knows it
- **Layering:** `auth` imports `db`; `db` never imports `auth`. HTTP routes follow the project convention and live in `api/routers/`

## Folder tree
```
src/leadgen/
├── db/                              # persistence only — no auth logic
│   ├── __init__.py
│   ├── base.py                      # DeclarativeBase, constraint naming convention, TimestampMixin
│   ├── engine.py                    # engine factory + SQLite PRAGMAs (foreign_keys=ON, WAL, busy_timeout)
│   ├── session.py                   # sessionmaker, get_db() FastAPI dependency, unit-of-work helper
│   ├── migrate.py                   # programmatic `alembic upgrade head` (API lifespan + tests)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── auth_session.py
│   │   └── auth_event.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── users.py
│   │   ├── sessions.py
│   │   └── events.py
│   └── migrations/                  # Alembic
│       ├── env.py
│       ├── script.py.mako
│       └── versions/0001_create_auth_tables.py
├── auth/                            # auth domain — no FastAPI routes, no SQL
│   ├── __init__.py
│   ├── __main__.py / cli.py         # python -m leadgen.auth create-admin | reset-password | list-users | disable-user
│   ├── passwords.py                 # argon2 hasher, policy validation, dummy-verify for timing safety
│   ├── recovery.py                  # generate / format / normalize / hash recovery codes
│   ├── tokens.py                    # session token gen (secrets.token_urlsafe(32)) + sha256
│   ├── service.py                   # AuthService: setup, login, logout, change/reset pw, admin user mgmt
│   ├── dependencies.py              # current_user (HTTP + WS), require_admin
│   ├── csrf.py                      # Origin-check middleware for unsafe methods + WS handshake
│   ├── rate_limit.py                # in-memory sliding window per IP and per username
│   ├── schemas.py                   # Pydantic request/response models
│   └── errors.py                    # domain exceptions → mapped to HTTP in the router
└── api/routers/
    ├── auth.py                      # /auth/*
    └── admin.py                     # /admin/users/*
alembic.ini                          # repo root, script_location → src/leadgen/db/migrations
```

## Schema (migration `0001`)

### `users`
| column | type | notes |
|---|---|---|
| id | TEXT PK | UUIDv4, not guessable |
| username | TEXT NOT NULL | shown as typed |
| username_normalized | TEXT NOT NULL UNIQUE | NFKC + casefold; enforces case-insensitive uniqueness |
| password_hash | TEXT NOT NULL | argon2id |
| recovery_code_hash | TEXT NOT NULL | argon2id |
| recovery_code_created_at | DATETIME NOT NULL | |
| role | TEXT NOT NULL DEFAULT 'user' | `CHECK (role IN ('admin','user'))` |
| is_active | BOOLEAN NOT NULL DEFAULT 1 | accounts are disabled, never hard-deleted |
| must_change_password | BOOLEAN NOT NULL DEFAULT 0 | |
| failed_login_attempts | INTEGER NOT NULL DEFAULT 0 | |
| locked_until | DATETIME NULL | lockout |
| last_login_at | DATETIME NULL | |
| password_changed_at | DATETIME NOT NULL | |
| created_by_id | TEXT FK → users.id ON DELETE SET NULL | |
| created_at, updated_at | DATETIME NOT NULL | UTC |

### `auth_sessions`
| column | type | notes |
|---|---|---|
| id | TEXT PK | UUIDv4 |
| user_id | TEXT FK → users.id ON DELETE CASCADE | indexed |
| token_hash | TEXT NOT NULL UNIQUE | sha256 of the cookie token |
| created_at | DATETIME NOT NULL | |
| last_seen_at | DATETIME NOT NULL | used for the idle timeout |
| expires_at | DATETIME NOT NULL | absolute limit |
| revoked_at | DATETIME NULL | |
| revoked_reason | TEXT NULL | `logout`, `password_reset`, `admin`, ... |
| ip_address, user_agent | TEXT NULL | |

Indexes: `(user_id, revoked_at)`, `(expires_at)`.

### `auth_events` (audit log)
| column | type | notes |
|---|---|---|
| id | INTEGER PK AUTOINCREMENT | |
| user_id | TEXT FK → users.id ON DELETE SET NULL | |
| username_attempted | TEXT NULL | for failures on unknown usernames |
| event_type | TEXT NOT NULL | CHECK in: `setup_completed`, `login_success`, `login_failure`, `logout`, `account_locked`, `password_changed`, `password_reset`, `recovery_code_regenerated`, `user_created`, `user_disabled`, `user_enabled` |
| ip_address, user_agent | TEXT NULL | |
| metadata | TEXT NULL | JSON |
| created_at | DATETIME NOT NULL | |

Indexes: `(user_id, created_at)`, `(event_type, created_at)`.

The database file is `var/data/app.db`: gitignored, and already mounted by docker-compose.

## Backend API
| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /auth/setup-status` | public | `{needs_setup}`: true while there are no users |
| `POST /auth/setup` | public, only while 0 users | Creates the admin, returns the recovery code, sets the cookie |
| `POST /auth/login` | public | username + password, sets the cookie |
| `POST /auth/logout` | user | Revokes the current session |
| `GET /auth/me` | user | Current user + `must_change_password` |
| `POST /auth/password/change` | user | Current + new password; revokes other sessions; returns a new recovery code if this was a forced first change |
| `POST /auth/password/reset` | public | username + recovery code + new password → new recovery code; revokes all sessions |
| `POST /auth/recovery-code/regenerate` | user + password confirmation | Returns a new code |
| `GET /admin/users` | admin | List users |
| `POST /admin/users` | admin | Create a user (temporary password) |
| `PATCH /admin/users/{id}` | admin | Enable/disable, change role |
| `POST /admin/users/{id}/revoke-sessions` | admin | Force logout |

### Protecting existing endpoints
- In `app.py`, each existing router is included with `dependencies=[Depends(require_user)]`. The routes themselves don't change, so the paths and response shapes the frontend relies on stay the same.
- `/health` and `/auth/*` stay public.
- WebSockets (`/ws/visualizer`, `/ws/logs`): a separate dependency checks the cookie and Origin during the handshake and closes with code 1008 if either fails.
- SSE (`/shortlister/stream`, `/linkedin/stream`): uses the cookie through `EventSource(url, { withCredentials: true })`.

### Security details
- Every login failure returns the same "Invalid username or password" message. For unknown usernames the server still runs a dummy argon2 check, so response timing doesn't reveal which usernames exist.
- Lockout after 5 failures for 15 minutes, plus per-IP rate limits on login, reset and setup.
- A new session token is issued at every login. Sessions last at most 7 days and time out after 12 hours idle. Only the sha256 of the token is stored.
- Cookie flags: `HttpOnly`, `SameSite=Lax`, `Path=/`. `Secure` is set by `COOKIE_SECURE` (off for local dev, on in production).
- **CORS fix:** the current `allow_origins=["*"]` with `allow_credentials=True` is replaced by `CORS_ALLOWED_ORIGINS` (default `http://localhost:5173`).
- CSRF: an Origin check covers POST/PATCH/DELETE requests and the WebSocket handshake.
- Password policy: 12–128 characters, and it can't equal the username. Usernames: 3–32 characters from `[a-z0-9._-]`.
- Expired sessions are cleaned up at startup and whenever someone logs in.
- The API's startup code runs `alembic upgrade head` automatically (`DB_AUTO_MIGRATE`, default true).

### New settings (`config.py` only, documented in `.env.example`)
`APP_DB_URL`, `DB_AUTO_MIGRATE`, `SESSION_COOKIE_NAME`, `SESSION_TTL_HOURS`, `SESSION_IDLE_MINUTES`, `COOKIE_SECURE`, `CORS_ALLOWED_ORIGINS`, `AUTH_MAX_FAILED_LOGINS`, `AUTH_LOCKOUT_MINUTES`, `PASSWORD_MIN_LENGTH`

### New dependencies
- Python: `sqlalchemy>=2.0`, `alembic>=1.13`, `argon2-cffi>=23.1`
- Frontend: `react-router-dom`

## Frontend
```
frontend/src/
├── lib/http.js                  # apiFetch: credentials:'include', JSON, 401 → redirect to /login
├── auth/
│   ├── AuthContext.jsx          # AuthProvider + useAuth (user, login, logout, refresh)
│   ├── RequireAuth.jsx          # redirects to /setup, /login or /change-password as needed
│   ├── RequireAdmin.jsx
│   └── authApi.js
├── pages/
│   ├── LoginPage.jsx
│   ├── SetupPage.jsx            # first-run admin creation
│   ├── ResetPasswordPage.jsx    # username + recovery code + new password
│   ├── ChangePasswordPage.jsx   # forced first-login change and voluntary change
│   ├── AccountPage.jsx          # change password, regenerate recovery code
│   ├── DashboardPage.jsx        # current App.jsx body, moved with git mv
│   └── admin/UsersPage.jsx
└── components/auth/RecoveryCodeDialog.jsx   # shows the code once: copy, download .txt, "I saved it" checkbox required
```
- `App.jsx` becomes the router.
- The 13 existing `fetch()` calls switch to `apiFetch`.
- `LogStream`'s `EventSource` gets `withCredentials: true`.
- `Header` shows the username, an Account link, an Admin link for admins, and Logout.

## Tests
- `tests/unit/db/`: migrations upgrade and downgrade on a temporary SQLite file; constraints enforced (duplicate username in different case, bad role, FK cascade).
- `tests/unit/auth/`: hashing and rehash, recovery-code normalization, service logic (lockout, rotation, session revocation, setup only once).
- `tests/unit/api/test_auth_routes.py`, `test_admin_routes.py`: cookie flags, 401s, WebSocket rejection, CSRF Origin rejection.
- Existing API tests: `isolated_var` also points the database at the temp directory. A new `authed_client` fixture keeps the existing contract tests passing unchanged. Each protected route gets one new test that expects 401.

## Build order
1. **db/**: models, migration, settings, plus db tests.
2. **auth/**: domain logic and CLI, plus unit tests.
3. **API**: auth and admin routers, guarding the existing routers, CORS/CSRF, startup migration, plus route tests. Full `pytest -q` and `ruff check .` must pass.
4. **Frontend**: router, pages, `apiFetch` migration; `npm run build` and `npm run lint`; manual browser check (setup → recovery code → logout → reset → login → admin creates user → forced change).
5. **Docs**: an ADR in `docs/DECISIONS.md` (auth model, and endpoints now returning 401 as a contract change), `PROJECT_CONTEXT.md`, `README.md`, `.env.example`, `CHANGELOG_WORK.md`.

## Open points
- **Production deployment:** the dev setup (`localhost:5173` → `localhost:8000`) is same-site, so `SameSite=Lax` cookies work. In production, the frontend and API should be served from one origin behind a reverse proxy, with `COOKIE_SECURE=true`. Undecided: add that proxy (for example an nginx service in docker-compose) now, or later.
- **Stale task:** `docs/TASKS.md` still lists "commit the restructure" as active, but the tree is clean at `f4d57d9`. Mark it done when implementation starts.
