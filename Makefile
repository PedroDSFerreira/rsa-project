COMPOSE = docker compose -f docker-compose.dev.yml

.PHONY: prepare-env up upd down restart build logs clean

## Copy .env-sample to .env (first-time setup)
prepare-env:
	@if [ -f .env ]; then \
		echo ".env already exists — skipping (delete it first to reset)"; \
	else \
		cp .env-sample .env; \
		echo ".env created from .env-sample"; \
	fi

## Build all service images
build:
	$(COMPOSE) build

## Start all containers (foreground, stream logs)
up:
	$(COMPOSE) up

## Start all containers in detached mode
upd:
	$(COMPOSE) up -d

## Stop and remove containers
down:
	$(COMPOSE) down

## Restart all containers
restart:
	$(COMPOSE) restart

## Tail logs for all services
logs:
	$(COMPOSE) logs -f

## Remove stopped containers, dangling images and unused volumes
clean:
	$(COMPOSE) down -v --remove-orphans
	docker image prune -f
