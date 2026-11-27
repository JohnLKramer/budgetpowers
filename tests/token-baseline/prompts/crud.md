/budgetpowers:brainstorming

Build a Spring Boot 3 (Kotlin, Gradle) CRUD REST app for one entity `item` stored in Postgres: columns id (PK), quantity (integer, must be >= 0), code (string, alphanumeric only, required). Endpoints: create, get by id, list, update, delete. Return 400 on validation failure, 404 on missing id. Provide the PG schema as a Flyway migration and a docker-compose.yml running Postgres. Tests with JUnit 5 (Testcontainers or the compose DB).
