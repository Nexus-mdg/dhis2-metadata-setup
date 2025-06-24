## DHIS2 SMS Gateway Makefile
##
## This Makefile provides shortcuts for managing the DHIS2 SMS Gateway Docker services

# Default target
.PHONY: help
help:
	@echo "DHIS2 SMS Gateway Management Commands:"
	@echo "  make build       - Build the SMS gateway container image"
	@echo "  make up          - Start the SMS gateway service and Redis"
	@echo "  make down        - Stop the SMS gateway service and Redis"
	@echo "  make restart     - Restart the SMS gateway service and Redis"
	@echo "  make logs        - View SMS gateway service logs"
	@echo "  make logs-redis  - View Redis logs"
	@echo "  make ps          - List running services"
	@echo "  make shell       - Open a shell in the SMS gateway container"
	@echo "  make redis-cli   - Open Redis CLI"
	@echo "  make clean       - Remove containers, volumes, and images"
	@echo "  make test-sms    - Send a test SMS to the receiver"
	@echo "  make sms-stats   - Get SMS statistics from Redis"

# Build the container image
.PHONY: build
build:
	docker compose build

# Start the SMS gateway service and Redis
.PHONY: up
up:
	docker compose up -d

# Start the SMS gateway service and show logs
.PHONY: up-logs
up-logs:
	docker compose up

# Stop the SMS gateway service and Redis
.PHONY: down
down:
	docker compose down

# Restart the SMS gateway service and Redis
.PHONY: restart
restart:
	docker compose restart

# View SMS gateway service logs
.PHONY: logs
logs:
	docker compose logs -f dhis2-sms-gateway.receiver

# View Redis logs
.PHONY: logs-redis
logs-redis:
	docker compose logs -f redis

# List running services
.PHONY: ps
ps:
	docker compose ps

# Open a shell in the SMS gateway container
.PHONY: shell
shell:
	docker compose exec dhis2_sms_gateway_receiver sh

# Open Redis CLI
.PHONY: redis-cli
redis-cli:
	docker compose exec redis redis-cli

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

# Get SMS statistics from Redis
.PHONY: sms-stats
sms-stats:
	curl -X GET http://localhost:8002/sms/stats

# List recent SMS messages
.PHONY: sms-list
sms-list:
	curl -X GET http://localhost:8002/sms/list?limit=10