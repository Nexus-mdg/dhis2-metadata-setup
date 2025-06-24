# DHIS2 SMS Gateway

> **Disclaimer:** This codebase is mostly AI-generated and is intended for testing and demonstration purposes only. It is not designed or reviewed for production use. Use at your own risk.

A lightweight SMS gateway service for DHIS2 that handles both incoming and outgoing SMS messages using Docker containers.

## Features

- Receives SMS messages from external providers
- Stores messages in Redis for persistence
- Provides simple REST API endpoints
- Connects to external DHIS2 network
- Includes comprehensive testing tools

## Getting Started

### Prerequisites

- Docker and Docker Compose
- DHIS2 instance available on the same Docker network

### Installation

1. Clone this repository
2. Run the SMS gateway service:

   ```bash
   make up
   ```

## Usage

The SMS gateway provides several endpoints:

- `/sms/receive` - Receives SMS messages (POST)
- `/sms/send` - Sends outbound SMS messages (POST)
- `/health` - Check service health (GET)
- `/sms/stats` - Get SMS statistics (GET)
- `/sms/list` - List received messages (GET)

## Testing

Run the test suite to verify functionality:

```bash
make test-suite
```

Or send a test SMS with:

```bash
make test-sms
```

## Management Commands

Use the included Makefile for easy management:

```bash
make help        # Show available commands
make up          # Start services
make down        # Stop services
make rebuild     # Rebuild and restart services
make logs        # View logs
```

## Integration

This SMS gateway connects to the DHIS2 instance via the external `dhis2-external-net` Docker network, allowing seamless integration with the DHIS2 stack.

## License

See the [LICENSE](LICENSE) file for details.
