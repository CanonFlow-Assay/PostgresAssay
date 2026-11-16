# Research and admission decisions

Reviewed 2026-11-16 for postgresql 18.7. Community articles identify hypotheses, incidents and test cases. Exact product semantics come from primary documentation and executed native fixtures. No article, popularity score or benchmark ratio automatically admits a blocking rule.

| Source | Kind | Decision |
|---|---|---|
| [PG-WAL](https://www.postgresql.org/docs/18/runtime-config-wal.html) | primary | Durability settings and explicit disposable-data exceptions. |
| [PG-AUTH](https://www.postgresql.org/docs/18/auth-pg-hba-conf.html) | primary | Authentication rules are ordered; HBA snapshots do not prove TLS identity or actual matching. |
| [PG-ROLES](https://www.postgresql.org/docs/18/role-attributes.html) | primary | Application role privilege boundaries. |
| [PG-TIMEOUT](https://www.postgresql.org/docs/18/runtime-config-client.html) | primary | Timeouts are workload/session scoped, not arbitrary global constants. |
| [PG-VACUUM](https://www.postgresql.org/docs/18/routine-vacuuming.html) | primary | Autovacuum and maintenance require workload evidence. |
| [PG-DUMP](https://www.postgresql.org/docs/18/app-pgdump.html) | primary | Logical dumps are a supported backup mechanism; recovery objectives determine adequacy. |
| [PG-REDDIT](https://www.reddit.com/r/PostgreSQL/comments/1h0zt4u/postgresql_best_practices_guidelines/) | community | Backup/restore and maintenance concerns accepted; blanket claims that pg_dump is not a backup and VACUUM FULL is never valid rejected. |
| [PG-MEDIUM](https://medium.com/towards-data-engineering/postgresql-in-production-scaling-high-availability-and-lessons-from-real-failures-4c307d0afeea) | community | Pooling, replication lag and failover inspire contextual tests; no fixed pool size or universal partitioning rule. |
| [PG-MIGRATION](https://medium.com/engineering-playbook/our-database-migration-took-200ms-in-staging-production-went-down-for-47-minutes-e000ad7cf414) | community | Lock timing and overlapping application versions motivate migration/recovery tests; anecdote is not an admitted rule. |
| [PG-SUBSTACK-MIGRATION](https://segfaultpw.substack.com/p/devops-from-zero-to-hero-database-migrations) | community | Expand/contract and representative migration testing accepted as contextual workflows. Claims that additive DDL is always safe or concurrent indexes take no locks are rejected. |
| [PG-SUBSTACK-POOL](https://engrlog.substack.com/p/what-happens-when-thousands-of-users) | community | Pool saturation/connection ownership inspires load cases. Fixed pool ratios and blanket prepared-statement incompatibility are not admitted. |
| [PG-POOLER](https://www.pgbouncer.org/config.html) | primary | Check pooler/protocol version, pooling mode, reset semantics and max_prepared_statements rather than universally disabling prepared statements. |
| [PG-LOCK-BLOG](https://www.crunchydata.com/blog/one-pid-to-lock-them-all-finding-the-source-of-the-lock-in-postgres) | specialist | Lock-chain diagnosis informs operator workflow. Example timeout values are not imported as universal global settings. |
| [PG-INDEX](https://www.postgresql.org/docs/18/sql-createindex.html) | primary | Concurrent index construction still has waits/constraints and cannot run inside a transaction block. |

The complete conceptual checklist is in [best practices](best-practices.md). Only the finite catalogue is implemented as executable profile checks. Missing inputs remain untested; contextual recovery, performance, migrations and security behavior require declared external tests. These sources are linked and synthesized in original wording rather than copied in full.
