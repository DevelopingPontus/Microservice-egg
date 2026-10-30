# Scoped Rules: `server/` (Central Shared Topic-Tree Service — Java / Spring Boot / Neo4j)

You are working inside `server/`, the centralized multi-user backend service for **EGG**, powering **Pillar 1 (Cognitive Load Management — Intelligent Task Breakdown)**.

## 1. Purpose & Strict Privacy Boundary

- **Shared Topic Graph Only ("The Word Unzipper")**: `server/` decomposes high-level goals into reusable trees of concrete sub-steps (`(:Topic)-[:HAS_SUBTOPIC]->(:Topic)`).
- **Zero Personal Telemetry**: `server/` must **never** receive, process, or store personal user telemetry, keystroke cadence, active windows, or personal task completion states. Those belong strictly inside `local/agent/` on the user's device.

## 2. Technology Stack & Semantic Cache Architecture

- **Language & Framework**: Java 27 + Spring Boot 4.1.2 (`Spring Web`, `Spring Data Neo4j`, `Spring AI` / LLM structured output).
- **Database**: **Neo4j 5+** (Graph Database + Built-in Vector Index).
- **Cache-First Semantic Topic Resolution**:
  1. **Vector Similarity Lookup**: When `local/agent/` requests a topic breakdown, compute an embedding vector for the query and search Neo4j's vector index (`db.index.vector.queryNodes`) for semantically equivalent existing `:Topic` nodes.
  2. **Semantic Cache Hit**: If a matching `:Topic` node (even if phrased differently) already has a generated subgraph in Neo4j, return the existing subgraph immediately with **0 LLM calls**.
  3. **Cache Miss & Sub-Node Graph Reuse**: If the topic is new, invoke the LLM to decompose the topic into sub-topics. For each generated sub-topic, check Neo4j's vector index before recursing—connecting `[:HAS_SUBTOPIC]` edges to any existing sub-topic subtrees and only invoking the LLM for genuinely missing nodes.

## 3. Verification & Quality Gates (`server/`)

Before marking any task in `server/` complete, run and pass:
1. `./mvnw spotless:check` (or Checkstyle formatting verification)
2. `./mvnw test` (JUnit 5 + Testcontainers Neo4j integration tests)
