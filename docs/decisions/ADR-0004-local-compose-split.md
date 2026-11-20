# ADR-0004: Platform Compose is separate from Dify and Sim

## Status

Accepted

## Context

Official Dify Compose starts ~15 containers (min 4 GiB, realistically more). Sim evaluation sizing is ~12 GiB RAM with an 8 GiB app limit. This workstation has 32 GiB. Windows Docker + both engines + Ollama + our stack will thrash.

Ports: Sim claims **3000** and **3002**. Dify nginx claims **80**. Our web therefore uses **3100**, API **8080**, Postgres **5433**.

## Decision

Root `docker-compose.yml` runs only Postgres, API, and web. Dify and Sim are installed with **their** official procedures in directories ignored by git (`infrastructure/providers/`). A reduced profile is “platform only”; add one engine at a time.

## Consequences

Live provider tests are optional and env-gated. Adapter unit tests mock HTTP.
