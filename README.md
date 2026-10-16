# CAD-IT Data Engineer Assessment

Movie data modeling, a PostgreSQL database, a Python ETL pipeline, and five analytical SQL views.

## Requirements

- Python 3.10+ with an activated virtual or Conda environment.
- Docker with Docker Compose, Make, and OpenSSL 3.x.
- Local port `5432` available.

## Setup and run

Run from the repository root:

```bash
python -m pip install -r requirements.txt
make setup

# Only needed if this image is not already available locally:
docker pull postgres:15-alpine

docker compose up -d --wait
python -m main
```

`make setup` creates `.env`, a random password in `secrets/postgres_password.txt`,
and local CA/server certificates in `certs/`. Existing complete files are preserved.
Use `.env.example` as the configuration reference; passwords and private keys are excluded from Git.

PostgreSQL is exposed at `127.0.0.1:5432`. The ETL connects using TLS with certificate verification.
Compose uses `pull_policy: never`, so the image must be available before startup.

## Models and database

- [Conceptual model](diagram/conseptual.png)
- [Logical model](diagram/logical.png)
- [Physical model](diagram/physical.png)
- [Table definitions](initdb/01-schema.sql)
- [Analytical views](initdb/02-views.sql)

The model contains `titles`, `genres`, `persons`, `title_genres`, and `credits`.
PostgreSQL generates primary keys; the loader maps temporary references to the returned IDs.
Database initialization scripts run automatically only when the data volume is first created.

## ETL behavior and assumptions

`main.py` extracts `material/movies.csv`, transforms it with pandas, validates basic values,
and loads all five tables using SQLAlchemy.

- Each run replaces all five tables using `TRUNCATE ... RESTART IDENTITY` and inserts in one transaction. A failed load rolls back the replacement. Repeated loads do not accumulate duplicates; IDs are not guaranteed to remain stable across changed datasets.
- Exact source duplicates are removed. Titles with identical stored attributes are merged, preserving their genres and credits; duplicate relationships are removed.
- Titles with the same name but different attributes remain separate. The source provides no stable title ID or reliable film/episode distinction.
- People are merged by exact trimmed name, which may conflate different people with the same name. `Director(s)` becomes `director`; `Star(s)` becomes `actor`.
- A single year sets both release years; an open range leaves the end year empty. Text without a four-digit year produces empty release years.
- Blank cleaned values become SQL `NULL`. Gross values such as `$75.47M` become `75470000.0`; missing gross remains unknown.
- Validation checks required columns, numeric conversion, rating range, nonnegative votes/gross, positive runtime, and release-year order. PostgreSQL enforces detailed schema constraints. Progress and errors are logged to the console.

Expected output for the supplied CSV:

| Table | Rows |
|---|---:|
| titles | 9,359 |
| genres | 27 |
| persons | 21,106 |
| title_genres | 20,742 |
| credits | 40,122 |

## Assessment queries

[scripts/query.sql](scripts/query.sql) queries five views for unique title names,
Lena Headey's films, director gross totals, the top five comedy films by known gross,
and films directed by Martin Scorsese starring Robert De Niro.
The unique-title query counts distinct names (6,423 for the supplied data), not database IDs.

```bash
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < scripts/query.sql
```

For an existing database created before views were added, install them once:

```bash
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < initdb/02-views.sql
```

## Tests and local commands

```bash
python -m unittest discover -s tests -v
make db-shell       # Interactive psql over TLS
make docker-down    # Stop services; retain database data
```