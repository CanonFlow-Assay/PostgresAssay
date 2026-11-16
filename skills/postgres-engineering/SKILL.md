---
name: postgres-engineering
description: "Design, implement or review PostgreSQL schemas, transactions, migrations, access controls and recovery using the project version and explicit operational evidence."
---

# PostgreSQL engineering

Read the project's actual PostgreSQL version, deployment model, schema/migration conventions, client and pooler before selecting features. The researched latest-stable baseline is 18.7 as of 2026-11-16; 19 RC2 is a preview. Recheck primary release information when a later task needs the latest version. Preserve an existing supported project version unless the change requires an upgrade.

Model identity, relationships, amounts and time explicitly. Use constraints for real invariants, bind data values, compose identifiers safely and scope application privileges. Inspect query plans and workload before adding indexes or tuning memory. EXPLAIN ANALYZE executes the query.

Keep transactions and connection ownership bounded. Choose atomic updates/locking/isolation from the business invariant, handle serialization/deadlock retries deliberately and preserve idempotency across external effects. Pooling mode and prepared-statement behavior depend on the pinned client/pooler; avoid blanket compatibility claims.

Plan migrations around lock acquisition and overlapping application versions. Additive DDL can still wait for locks; concurrent index creation has its own transaction/failure constraints. Test representative data, backfills, cancellation, invalid-index recovery and rollback before claiming low disruption.

Choose logical/physical backups and WAL/PITR from recovery objectives and exercise restoration. Monitor vacuum, old transactions, slots/WAL, lag, disk and workload. Do not replace these decisions with fixed pool sizes, vacuum settings or a rule that logical dumps are never backups.

Read [engineering decisions](references/best-practices.md) for implementation details and [source decisions](references/sources.json) when a recommendation needs justification. Use PostgresAssay when a bounded snapshot/configuration assessment is requested or useful; inspect its current contract before running configured commands. Its strict profile checks declarations and executed required evidence, not all SQL, grants, TLS handshakes, failover or live production health.
