# OpenRelik worker for THOR Lite

This worker uses [THOR Lite](https://www.nextron-systems.com/thor-lite/) from [Nextron Systems](https://nextron-systems.com/) to scan files and directories for malicious content.

## Prerequisites

You need a valid THOR Lite license to use this worker. You can get a free license for non-commercial use from the [Nextron Systems website](https://www.nextron-systems.com/thor-lite/#get-thor).

## Installation Instructions

> **Warning:** OpenRelik is a fresh project and things are changing rapidly. Thus this worker is considered _experimental_. Use with care!

> Note: Last tested with OpenRelik 2024.09.23 . Use `2024.09.23` as the version in your `config.env` file (OpenRelik core system and worker versions).

Add this to your `docker-compose.yml` file:
```yaml
  openrelik-worker-thor-lite:
    container_name: openrelik-worker-thor-lite
    image: ghcr.io/nextronsystems/openrelik-worker-thor-lite:latest
    restart: always
    environment:
      - REDIS_URL=redis://openrelik-redis:6379
      - OPENRELIK_PYDEBUG=0
      - OPENRELIK_PYDEBUG_PORT=5678
      - THOR_LICENSE=<your license key, base64 encoded>
    volumes:
      - ./data:/usr/share/openrelik/data
    command: "celery --app=src.app worker --task-events --concurrency=2 --loglevel=INFO -Q openrelik-worker-thor-lite"
```

> Note: Currently (as of 2024-10-07), you need to add `openrelik:worker:thor-lite:html_report` to `[ui] allowed_data_types_preview` in your `settings.toml` to get embedded previews of the HTML reports that the worker generates.
