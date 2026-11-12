# `server` — Standalone Shared Topic-Tree Service ("The Word Unzipper")

Centralized multi-user backend service (**Java 27 + Spring Boot 4.1.2 + Neo4j 5+**) powering **Pillar 1 (Cognitive Load Management — Intelligent Task Breakdown)**.

---

## 1. Purpose & Privacy Boundary

- **Shared Topic Graph Only**: Decomposes high-level goals into reusable trees of concrete sub-steps (`(:Topic)-[:HAS_SUBTOPIC]->(:Topic)`).
- **Zero Personal Telemetry**: Never receives, processes, or stores personal user telemetry, keystrokes, active windows, or personal task completion states (which remain 100% inside `local/`).

---

## 2. Internal Feature Packages

`server/` combines 3 internal feature packages coordinated by `TopicTreeService`:

1. **`graph_cache/`**: Neo4j `:Topic` graph entities, `[:HAS_SUBTOPIC]` relationships, and vector similarity index lookups (`db.index.vector.queryNodes`) returning existing subtrees with `0` LLM calls on a semantic hit.
2. **`unzipper/`**: Embedding generation and structured LLM decomposition invoked only on cache misses, reusing existing Neo4j sub-nodes whenever a generated step already exists.
3. **`api/`**: Spring Web REST controllers, DTOs, and Actuator/Prometheus cache-hit metrics.

---

## 3. Standalone Verification

```bash
./mvnw spotless:check
./mvnw test
```
