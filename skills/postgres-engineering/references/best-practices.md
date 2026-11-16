# PostgreSQL engineering decisions

Baseline reviewed on 2026-11-16: PostgreSQL 18.7 is the latest stable release; PostgreSQL 19 RC2 is a preview lane. Recheck official releases before a later upgrade. The Assay qualifies the recorded snapshot shape/version, not all historical or future engines.

## Model and query boundaries

Use primary/unique keys for actual identity, foreign keys for required relationships and CHECK/NOT NULL constraints for row invariants. Choose numeric/decimal and explicit currency/rounding rules for money; choose timestamp/time-zone semantics from the business event. Do not turn a style preference into a mandatory SERIAL-to-identity migration.

Use bind parameters for data and a supported identifier-composition API or allowlist for identifiers. A placeholder cannot stand for a table name. Validate dynamic sort/filter choices. Avoid granting schema creation, elevated search_path entries or superuser privileges to the application merely to simplify deployment. The role checks here cover three explicit flags, not all privileges reachable through memberships, ownership, SECURITY DEFINER functions or grants.

PostgreSQL does not automatically create every useful referencing-side foreign-key index. Inspect DELETE/UPDATE/join paths and measured plans; an index on every column is equally unjustified. Prefer EXPLAIN for initial plan inspection. EXPLAIN ANALYZE executes the query and needs the same authorization and side-effect review as that query.

## Transactions and concurrency

Keep transactions short and avoid holding a connection/transaction across unrelated HTTP work. Model a conditional update, row lock or optimistic version check for a shared-state transition. Retry the whole appropriate transaction for serialization/deadlock failures, with bounded attempts and idempotency for external side effects. A lost COMMIT response is ambiguous; blind retries can duplicate a business action.

Choose isolation from the invariant. A statement timeout, lock timeout, idle-in-transaction timeout and application deadline have different scopes. The strict Assay profile requires explicit positive application/session values; it does not prescribe a global timeout for batch maintenance. Keep lock timeout below the effective statement deadline where the former should act first.

## Migrations

Test old/new application compatibility and expand/backfill/contract separately where a rolling rollout needs it. Fast metadata-only DDL can still request locks and wait behind a long transaction. Concurrent index creation is not lock-free, cannot run inside an ordinary transaction block and can leave an invalid index after failure. Check catalogue state and recovery before retrying. Use bounded backfill batches, monitor WAL/lag/locks, and test with representative data and concurrent sessions.

## Pooling and resource budgets

Choose pool size from total clients/workers and measured database capacity; reserve operational headroom. Session pooling and transaction pooling expose different guarantees for session state, temporary objects, advisory locks and prepared statements. Check the pinned driver and PgBouncer protocol/configuration, including prepared-statement support, rather than disabling prepared statements universally. A pool is not automatically required for every tiny application, and increasing max_connections is not a substitute for admission control.

## Maintenance, durability and recovery

Keep fsync/full_page_writes for the durable production profile. PostgreSQL documents legitimate disposable-data exceptions; use a separately reviewed scope rather than hiding a strict-profile finding. Synchronous-commit settings require an explicit loss/latency decision and are not blanket failures here.

Monitor vacuum progress, oldest transaction, transaction-ID age, dead tuples, replication slots/WAL retention, disk and lag. Tune autovacuum by table/workload. VACUUM FULL can be legitimate during planned maintenance; it is not an everyday replacement for autovacuum. Normal vacuum and filesystem space reclamation have different goals.

Choose logical dumps, physical backups and WAL/PITR from recovery point/time requirements. Include roles/global objects and extension/config dependencies where the chosen backup method needs them. Encrypt/control access to backups and execute restores. Replicas and VM snapshots do not alone establish recoverability. The native fixture restores a tiny logical dump; it does not qualify PITR, failover or production recovery time.

## Operational evidence

Collect effective settings from the relevant server/session and declare the scoped application roles. Retain collection time/context separately from a deterministic verifier receipt. Test TLS identity, least privilege through actual grants, backup recovery and migrations with their own commands. Query/parameter logs can expose private data; collect only what the investigation needs.

The Assay checks 12 explicit values/collections in a strict SCRAM/network/durable/application-timeout profile. It does not parse SQL, prove query performance, infer RLS coverage or connect to a production server. See sources.json for official, Reddit, Medium, Substack and specialist references and their admission decisions.
