# Release 0.23.0 : Event History

## Goal

Add a generic, append-only event history system.

The event system must not assume domain-specific content such as experiments, scores, seeds, releases, or simulations.

Each event has:

* a defined event type
* one recorded occurrence
* optional event-specific data

Reading/browsing history is out of scope for v1.

---

# Database Schema

## `event_type`

Defines the meaning of an event.

```sql
CREATE TABLE event_type (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    provider VARCHAR(64) NOT NULL,
    event_id INT UNSIGNED NOT NULL,

    name VARCHAR(64) NOT NULL,
    category VARCHAR(64) NULL,
    title VARCHAR(128) NOT NULL,
    description VARCHAR(512) NULL,

    default_level VARCHAR(16) NOT NULL DEFAULT 'info',
    version SMALLINT UNSIGNED NOT NULL DEFAULT 1,

    UNIQUE KEY uq_event_type (provider, event_id, version),
    UNIQUE KEY uq_event_name (provider, name, version)
);
```

Event definitions are seeded by database migration.

Definitions are immutable once introduced. If the meaning or payload contract changes, create a new version.

Repeatable seeding rules:

* missing definition: insert it
* identical existing definition: succeed as a no-op
* conflicting existing definition: fail clearly
* never update an existing definition in place

The same mechanism must work for both fresh installation and upgrades.

---

## `event_log`

Records individual event occurrences.

```sql
CREATE TABLE event_log (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    occurred_at DATETIME(6) NOT NULL,

    event_type_id BIGINT UNSIGNED NOT NULL,
    level VARCHAR(16) NOT NULL,
    message VARCHAR(1024) NULL,

    FOREIGN KEY (event_type_id)
        REFERENCES event_type(id),

    INDEX idx_event_log_time (occurred_at),
    INDEX idx_event_log_type (event_type_id)
);
```

`occurred_at` is the UTC time at which `EventLog.write()` records the occurrence.

Application code must not update or delete rows from `event_log`.

---

## `event_log_data`

Stores event-specific data.

```sql
CREATE TABLE event_log_data (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    event_log_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(64) NOT NULL,
    value JSON NULL,

    FOREIGN KEY (event_log_id)
        REFERENCES event_log(id)
        ON DELETE RESTRICT,

    UNIQUE KEY uq_event_log_data_name (event_log_id, name),

    INDEX idx_event_log_data_event (event_log_id)
);
```

Application code must not update or delete rows from `event_log_data`.

Payload values must be valid JSON-compatible values:

* string
* finite number
* boolean
* null
* list
* object

Payload keys must:

* be strings
* be non-empty
* be no longer than 64 characters

Nested object keys must also be strings.

Python `None` is stored as JSON `null`, not SQL `NULL`.

Unsupported objects or invalid JSON values raise `TypeError` or `ValueError`.

---

# Module Interface

Create:

```text
fr3d/app/event_log.py
```

```python
class EventLog:
    def __init__(
        self,
        database,
        *,
        provider: str = "fr3d",
        version: int = 1,
    ):
        ...

    def write(
        self,
        event_name: str,
        *,
        message: str | None = None,
        data: dict[str, object] | None = None,
        level: str | None = None,
        session: DbSession | None = None,
    ) -> int:
        """
        Record one event and return event_log.id.
        """
```

Event types are resolved using:

```text
(provider, event_name, version)
```

No automatic "latest version" lookup is allowed.

Unknown event types must fail clearly.

Accepted levels:

```text
debug
info
warning
error
critical
```

If `level` is omitted, use `event_type.default_level`.

`event_name` must be non-empty and fit the schema limit.

`message`, when supplied, must fit the schema limit.

Before performing any database inserts, `write()` must fully validate:

* event name
* level
* message
* payload keys
* payload values
* JSON serialization

No database writes should occur until validation succeeds.

---

# Transaction Behaviour

If `session` is supplied:

* use the caller's existing `DbSession`
* do not commit or roll back the transaction
* the event becomes part of the caller's transaction
* if `write()` raises after database work has begun, the caller must roll back the transaction

Do not introduce savepoint handling in v1.

If `session` is not supplied:

* create a database session
* insert the event and payload rows
* commit them as one transaction
* roll back on failure

`write()` raises on failure.

Duplicate events are allowed in v1.

Do not add:

* deduplication
* retry tracking
* occurrence keys
* idempotency infrastructure

For DB-backed state changes, callers should write the related event using the same `DbSession` when atomic recording is required.

---

# Initial Event Definition

The initial event definition is:

```text
provider:       fr3d
event_id:       3001
name:           seed_generated
category:       configuration
title:          New seed generated
description:    A new seed was generated for the golden configuration.
default_level:  info
version:        1
```

For v1, `seed_generated` is the first production event integrated with the framework.

It must be emitted when Fr3d commits the newly generated seed as the seed to be used for the golden configuration.

It must not be emitted merely because a candidate seed was calculated.

If the seed change is persisted inside a database transaction, the event must be written using the same `DbSession`.

The production emission point is the accounting transaction that establishes the
completed seed-rotation baseline as gold, not candidate calculation or submission.

The `seed_generated` v1 payload requires:

* `seed`: integer, the newly committed golden seed
* `reason`: string, `no_new_high_score` for rotation after stagnant cycles
* `rounds_without_high_score`: integer, the completed stagnant round-robin cycle
  count before rotation (captured before the count is reset)

The production caller owns this payload contract; the generic event framework
validates JSON compatibility without knowing domain-specific fields.

---

# Example Invocation

```python
event_log = EventLog(
    db,
    provider="fr3d",
    version=1,
)

event_log.write(
    "seed_generated",
    message=(
        "Generated new seed for golden config "
        "after 3 rounds with no new high score"
    ),
    data={
        "seed": 1974,
        "reason": "no_new_high_score",
        "rounds_without_high_score": 3,
    },
)
```

---

# Resulting Records

## `event_log`

```text
id             1842
occurred_at    2026-09-10 08:42:13.123456
event_type_id  3
level          info
message        Generated new seed for golden config after 3 rounds with no new high score
```

## `event_log_data`

```text
id    event_log_id    name                         value
9011  1842            seed                         1974
9012  1842            reason                       "no_new_high_score"
9013  1842            rounds_without_high_score    3
```

---

# v1 Scope

Implement:

* schema migration
* repeatable event-type seeding
* `EventLog`
* `EventLog.write()`
* validation before inserts
* transaction support through `DbSession`
* initial `seed_generated` production integration
* tests for:

  * successful lookup
  * unknown event type
  * ambiguous or incorrect provider/version lookup
  * payload serialization
  * invalid payload keys
  * invalid payload values
  * level validation
  * rollback on failure
  * caller-owned transaction failure behavior
  * repeatable identical seeding
  * conflicting event-definition seeding
  * committing a completed seed rotation records its event and required payload
  * calculating or submitting a candidate does not record `seed_generated`
  * transaction failure persists neither the seed change nor its event

Do not add:

* read/browse APIs
* deduplication
* retry infrastructure
* savepoints
* domain-specific columns
* automatic event-version selection
* generalized workflow or tracing features
* automatic migration of existing application logs
* additional event types unless explicitly required by this release

Additional events and richer domain-specific relationships will be added incrementally in later releases.
