## DHIS2 SMS Gateway Makefile
##
## This Makefile provides shortcuts for managing the DHIS2 SMS Gateway Docker services

# Default target
.PHONY: help
help:
	@echo "DHIS2 SMS Gateway Management Commands:"
	@echo "  make build       - Build the SMS gateway container image"
	@echo "  make up          - Start the SMS gateway service"
	@echo "  make down        - Stop the SMS gateway service"
	@echo "  make restart     - Restart the SMS gateway service"
	@echo "  make logs        - View SMS gateway service logs"
	@echo "  make ps          - List running services"
	@echo "  make shell       - Open a shell in the SMS gateway container"
	@echo "  make clean       - Remove containers, volumes, and images"

# Build the container image
.PHONY: build
build:
	docker compose build

# Start the SMS gateway service
.PHONY: up
up:
	docker compose up -d

# Start the SMS gateway service and show logs
.PHONY: up-logs
up-logs:
	docker compose up

# Stop the SMS gateway service
.PHONY: down
down:
	docker compose down

# Restart the SMS gateway service
.PHONY: restart
restart:
	docker compose restart

# View SMS gateway service logs
.PHONY: logs
logs:
	docker compose logs -f

# List running services
.PHONY: ps
ps:
	docker compose ps

# Open a shell in the SMS gateway container
.PHONY: shell
shell:
	docker compose exec dhis2_sms_gateway_receiver sh

# Remove containers, volumes, and images
.PHONY: clean
clean:
	docker compose down -v
	docker compose rm -f
	docker image prune -f --filter "label=com.docker.compose.project=dhis2-metadata-setup"

# Test the SMS receiver by sending a sample SMS
.PHONY: test-sms
test-sms:
	curl -X POST http://localhost:8002/sms/receive \
		-H "Content-Type: application/json" \
		-d '{"originator": "+123456789", "message": "This is a test SMS message"}'
