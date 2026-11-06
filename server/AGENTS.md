# Scoped Rules: `server/` (Central Shared Topic-Tree Service — Java / Spring Boot / Neo4j)

You are working inside `server/`, the centralized multi-user backend service for **EGG**, powering **Pillar 1 (Cognitive Load Management — Intelligent Task Breakdown)**.

## 1. Purpose & Strict Privacy Boundary

- **Shared Topic Graph Only ("The Word Unzipper")**: `server/` decomposes high-level goals into reusable trees of concrete sub-steps (`(:Topic)-[:HAS_SUBTOPIC]->(:Topic)`).
- **Zero Personal Telemetry**: `server/` must **never** receive, process, or store personal user telemetry, keystroke cadence, active windows, or personal task completion states. Those belong strictly inside `local/telemetry/` on the user's device.

## 2. Technology Stack & Semantic Cache Architecture

- **Language & Framework**: Java 27 + Spring Boot 4.1.2 (`Spring Web`, `Spring Data Neo4j`, `Spring AI` / LLM structured output).
- **Database**: **Neo4j 5+** (Graph Database + Built-in Vector Index).
- **Cache-First Semantic Topic Resolution**:
  1. **Vector Similarity Lookup**: When `local/telemetry/` requests a topic breakdown, compute an embedding vector for the query and search Neo4j's vector index (`db.index.vector.queryNodes`) for semantically equivalent existing `:Topic` nodes.
  2. **Semantic Cache Hit**: If a matching `:Topic` node (even if phrased differently) already has a generated subgraph in Neo4j, return the existing subgraph immediately with **0 LLM calls**.
  3. **Cache Miss & Sub-Node Graph Reuse**: If the topic is new, invoke the LLM to decompose the topic into sub-topics. For each generated sub-topic, check Neo4j's vector index before recursing—connecting `[:HAS_SUBTOPIC]` edges to any existing sub-topic subtrees and only invoking the LLM for genuinely missing nodes.

## 3. Hourglass Data Architecture & LCA Crossroads Contracts ("When vs. What")

`server/` follows the exact same **Hourglass + LCA Architecture** as `local/telemetry/`:

- **`common/` ("What do you want?" — LCA Crossroads Contracts)**: Shared Java records/DTOs (`TopicNodeDTO`, `TopicTreeResponse`), configuration properties, and cross-package interfaces (`TopicGraphPort`, `EmbeddingGeneratorPort`, `TopicUnzipperPort`). Zero I/O, zero behavioral imports.
- **`intake/` (External Knowledge & Vector Intake)**:
  - `embedding/`: Generates embedding vectors for incoming topic queries.
  - `unzipper/`: Invokes the LLM ("word unzipper") on semantic cache misses to decompose novel topics into structured sub-steps.
- **`storage/` (The Raw Material Store — Neo4j Graph & Vector Index)**:
  - `graph/`: `:Topic` Neo4j entities, `[:HAS_SUBTOPIC]` relationships, vector similarity queries, and reusable subgraph persistence.
- **`output/` (Value Creation Branches)**:
  - `api/`: REST controllers serving reusable topic trees to clients and exposing Prometheus/Actuator cache-hit metrics.
- **Root Supervisor (`TopicTreeService.java` — "I'll say when")**: Coordinates the cache-first flow: queries `storage/` first, invokes `intake/` (`embedding/` + `unzipper/`) only on cache misses, persists new nodes to `storage/`, and returns the assembled tree to `output/`. Leaf packages (`intake/*`, `storage/*`, `output/*`) must never import each other directly; they only import from themselves or upward from `common/`.

## 4. Verification & Quality Gates (`server/`)

Before marking any task in `server/` complete, run and pass:

1. `./mvnw spotless:check` (or Checkstyle formatting verification)
2. `./mvnw test` (JUnit 5 + Testcontainers Neo4j integration tests)
