.PHONY: setup docker-build docker-up docker-down docker-down-v db-shell

setup:
	sh scripts/setup.sh

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-down-v:
	docker compose down -v

db-shell:
	docker compose exec postgres sh -ec 'export PGPASSWORD="$$(cat "$$POSTGRES_PASSWORD_FILE")"; exec psql "host=localhost port=5432 dbname=$$POSTGRES_DB user=$$POSTGRES_USER sslmode=verify-full sslrootcert=/certs/ca.crt"'
