.PHONY: help up down logs ps build clean prune requirements

# Default target
help:
	@echo "Available commands:"
	@echo "  make up             - Start all services in detached mode"
	@echo "  make down           - Stop and remove all services"
	@echo "  make logs           - View logs from all services"
	@echo "  make logs service=<service_name> - View logs from a specific service (e.g., make logs service=kafka)"
	@echo "  make ps             - List running services"
	@echo "  make build          - Build or rebuild services"
	@echo "  make clean          - Remove stopped containers and dangling images/volumes"
	@echo "  make prune          - Remove all unused Docker objects (containers, networks, volumes, images)"
	@echo "  make requirements   - Install/update python requirements from requirements.txt into a venv"

# Docker Compose commands
up:
	docker-compose up -d

down:
	docker-compose down --remove-orphans

logs:
	@if [ -z "$(service)" ]; then \
		docker-compose logs -f; \
	else \
		docker-compose logs -f $(service); \
	fi

ps:
	docker-compose ps

build:
	docker-compose build

# Docker system commands
clean: down
	docker-compose down -v --remove-orphans # Stop containers, remove volumes
	docker system prune -af --volumes # Remove unused data

prune: clean # A more aggressive clean
	docker system prune --all --force --volumes

# Python environment
VENV_DIR := .venv
ACTIVATE := $(VENV_DIR)/bin/activate

$(VENV_DIR):
	python3 -m venv $(VENV_DIR)

requirements: $(VENV_DIR)
	@echo "Activating venv and installing/updating requirements..."
	@. $(ACTIVATE); \
	pip install --upgrade pip; \
	pip install -r requirements.txt; \
	echo "To activate the venv, run: source $(ACTIVATE)"