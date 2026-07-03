# City Library — Book Rental System (Microservices Edition)

This is a Django project I originally built as a straightforward CRUD app for
tracking library book rentals — one project, one database, three Django apps
living side by side. I later rebuilt it as three independent microservices,
mainly as a way to actually practice the parts of distributed system design
that are easy to read about but only really click once you've built them
yourself: who owns what data, how services find out about each other's
changes without touching each other's databases, what happens when a network
call fails halfway through, and how you keep a user's identity consistent
across services that don't share a login system.

It's a small domain on purpose — book rentals are simple enough that the
architecture is the interesting part, not the business logic.
## What it does

A member can register an account, browse the catalog, borrow a book, return
it, or request a one-time extension if they're running late. Borrowing has a
few rules behind it: 14 days per loan, one 7-day extension, a 5-book limit per
account, and an account gets suspended automatically if a book goes overdue
(suspension lifts once the book is returned or extended). Staff can manage the
catalog and see recent borrowing activity; regular members can only ever see
their own.

## The three services

- **users-service** — accounts. Registration, login, logout, and the profile
  page. This is the only service with an actual password store, and the only
  one that issues identity: on login it signs a JWT and hands it back as an
  httpOnly cookie, which is how the other two services recognize who's making
  a request without ever needing to store a password themselves.
- **books-service** — the catalog and the one true stock count for every
  book. Nothing else is allowed to edit `available_copies` directly.
- **rentals-service** — borrowing, returning, extending, and the suspension
  rule. It doesn't have its own copy of the `Book` or `User` tables, so it
  keeps a small local cache of just the fields it needs (a book's stock count,
  a user's suspension flag) to make borrowing decisions instantly, without
  waiting on a network call for every page load.

## How they actually talk to each other

Two ways, and deliberately not more:

**A shared JWT for identity.** users-service signs it, the other two just
verify the signature — neither of them has a users table to check against
anyway. It travels as a cookie, so the browser experience feels like one
connected app even though it's three separate origins.

**Async messages for anything that changes state.** When books-service's
stock changes, it tells rentals-service so its cache stays current. When
rentals-service decides someone's overdue and needs suspending, it tells
users-service so the profile page reflects it. None of these are calls a
request waits on — they're fire-and-forget, which is what lets rentals-service
answer "does this user have stock left, are they suspended" instantly from
its own local copy instead of phoning two other services on every request.

The one exception is a single one-time sync when rentals-service first starts
up (`manage.py bootstrap_caches`), which does a plain HTTP GET to hydrate its
caches from whatever books and users already exist. Everything after that is
async.

**Borrowing the last copy of a book** is the one place this gets genuinely
distributed, so it's worth explaining properly. rentals-service creates the
loan right away as `pending` and optimistically ticks its own cached stock
count down — that's what makes the UI feel instant. In the background, it
asks books-service to actually claim a copy. books-service is the real source
of truth for stock, so it's the one that makes the final call: if the copy is
still there, it confirms and rentals-service flips the loan to `active`; if
two people went for the last copy at the same instant, one of them gets
rejected and rentals-service quietly undoes its optimistic guess. Every step
of this is also written to tolerate being delivered twice, because real
message queues occasionally do that, and I wanted it to be correct, not just
correct-on-the-happy-path.

## Tech stack

- Python 3, Django, Django REST Framework
- MySQL — one database per service (`users_db`, `books_db`, `rentals_db`)
- Celery for async messaging between services
- PyJWT for the shared authentication token
- python-dotenv for loading configuration and secrets from a gitignored
  `.env` file, so nothing sensitive lives in the committed source
- HTML, CSS and a little JavaScript for the front end (server-rendered
  Django templates, no SPA framework)

## Repo layout

```
library-project/
├── common/                    # small shared library, not a service of its own
│   ├── jwt_auth.py              # sign/verify the shared JWT
│   ├── admin_site.py            # Django admin for services with no local User table
│   ├── dispatch.py               # a thin wrapper around Celery's send_task
│   └── context_processors.py    # makes cross-service URLs available in templates
├── users-service/          # accounts — its own Django project end to end
├── books-service/          # catalog and stock
└── rentals-service/        # borrowing, returning, extending, suspension
```

Each service directory is a complete, independently runnable Django project —
its own `manage.py`, `requirements.txt`, migrations, and test suite. Nothing
in one service imports code from another.

## Configuration and secrets

Nothing in the code carries a real secret — every password, signing key, and
per-service key is read from the environment, and each `settings.py` fails
loudly at startup if one is missing rather than quietly falling back to
something hardcoded. That's on purpose: this repo is meant to be pushed to
GitHub, and a project with a real secret baked into a committed file is worse
than no secret at all.

All three services load their configuration from **one shared `.env` file at
the repo root** (not one per service — `JWT_SECRET` in particular has to be
identical across all three, and a single file is the only way to guarantee
that instead of hoping three copies stay in sync). `.env.example` documents
every variable with either a blank or a non-sensitive placeholder value and
is the only one of the two that's actually committed — `.env` itself is
gitignored.

To set it up:

```
cp .env.example .env
```

Then fill in `.env`: generate the JWT secret and the three per-service
`SECRET_KEY` values with

```
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

(run it once for `JWT_SECRET`, then once each for `USERS_SECRET_KEY`,
`BOOKS_SECRET_KEY`, `RENTALS_SECRET_KEY`), and set `DB_PASSWORD` to whatever
your local MySQL root password actually is.

## Running it locally

Each service needs its own dependencies and its own port. In three separate
terminals, from the repo root:

```
cd users-service    && pip install -r requirements.txt && python manage.py migrate && python manage.py runserver 8001
cd books-service    && pip install -r requirements.txt && python manage.py migrate && python manage.py runserver 8002
cd rentals-service  && pip install -r requirements.txt && python manage.py migrate && python manage.py runserver 8003
```

Each one picks up the shared `.env` automatically (via `python-dotenv`), so
nothing needs to be exported by hand. By default `.env.example` has
`USE_SQLITE=0`, i.e. MySQL — create the three databases once beforehand:

```sql
CREATE DATABASE users_db CHARACTER SET utf8mb4;
CREATE DATABASE books_db CHARACTER SET utf8mb4;
CREATE DATABASE rentals_db CHARACTER SET utf8mb4;
```

(set `USE_SQLITE=1` in `.env` instead if you'd rather skip that and try it
with zero database setup — each service will just use its own local SQLite
file.)

Once books-service and users-service have at least one book and one account
in them, hydrate rentals-service's caches once:

```
cd rentals-service && python manage.py bootstrap_caches
```

Then open **http://localhost:8003/** for the home page, register at
**http://localhost:8001/accounts/register/**, and browse the catalog at
**http://localhost:8002/books/**.

One thing to watch for: always use `localhost`, not `127.0.0.1`, consistently
across all three tabs. Browsers treat those as different hosts for cookie
purposes, so a login from one won't be recognized by the others if you mix
them.

For the async messaging to actually deliver (not just no-op), run a Celery
worker alongside each web process (they all read the same `CELERY_BROKER_URL`
from the shared `.env`, so there's nothing extra to configure):

```
celery -A config worker -Q users_queue    # inside users-service
celery -A config worker -Q books_queue    # inside books-service
celery -A config worker -Q rentals_queue  # inside rentals-service
```

## What's next

This covers the application itself. The parts I'm deliberately leaving for
the deployment side of the project:

- A real message broker (RabbitMQ or Redis) in place of the local
  filesystem-based one I used for development — just a `CELERY_BROKER_URL`
  change, no code changes.
- Docker containers and orchestration for each service, its database, and the
  broker.
- An API gateway or reverse proxy so all three services sit behind one
  address instead of three separate ports.

## Pages and APIs

| Page | Service | URL |
|------|---------|-----|
| Home | rentals | `/` |
| Register / Login / Logout / Profile | users | `/accounts/register/`, `/accounts/login/`, `/accounts/logout/`, `/accounts/profile/` |
| Browse books / Book detail | books | `/books/`, `/books/<id>/` |
| My borrows | rentals | `/my-borrows/` |
| Confirm & borrow | rentals | `/borrow/<book_id>/` (GET to confirm, POST to execute) |
| Return / Extend | rentals | `/return/<record_id>/`, `/extend/<record_id>/` (POST only) |

REST APIs, all JWT-authenticated:

- users-service: `GET /api/users/` (read-only; rentals-service's bootstrap sync uses this)
- books-service: `GET/POST /books/api/`, `/books/api/<id>/` (writes require staff)
- rentals-service: `GET/POST /api/records/`, `/api/records/<id>/`, plus
  `/api/records/<id>/return_book/` and `/api/records/<id>/extend/`

## Business rules

- 14-day loan period, one 7-day extension allowed per loan.
- Maximum 5 books out at once per account.
- An overdue book suspends the account until it's returned or extended.
- A book can't be borrowed twice at once by the same account, and can't be
  borrowed once its stock hits zero.
- Regular members only ever see their own borrowing history — recent
  activity across all members is visible to staff only.
