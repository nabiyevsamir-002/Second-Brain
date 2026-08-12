.PHONY: help up down logs build restart db-only ps

help:
	@echo "Second Brain — komandalar:"
	@echo "  make up        - bütün servisləri qaldır (db + bot), arxa planda"
	@echo "  make down      - servisləri dayandır"
	@echo "  make logs      - bot loglarını izlə"
	@echo "  make build     - image-i yenidən build et"
	@echo "  make restart   - botu yenidən başlat"
	@echo "  make db-only   - yalnız Postgres qaldır"
	@echo "  make ps        - servislərin vəziyyəti"

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f bot

build:
	docker compose build

restart:
	docker compose restart bot

db-only:
	docker compose up -d db

ps:
	docker compose ps
