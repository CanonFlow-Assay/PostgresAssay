# Wallet migration profile

The wallet-migration profile checks PostgreSQL 18.7 and Flyway 13.12.1
observations for a two-version Wallet upgrade. Use the pinned images in
eng/migration_native.py and run on a local Linux Docker daemon.

~~~sh
python3 eng/qualify-profile.py --out artifacts/wallet-qualified
~~~

The fixture initializes V1 and seeds a decimal balance, debit and
outbox row. It starts one V2 application, observes the committed schema
history, then kills the owned worker before it returns the migration
response. Recovery inspects the ledger and validates its checksum.
The before and after rows, expected index, one apply dispatch, and
absence of a worker acknowledgement are required evidence.

The checksum control changes the V2 index expression in a disposable copy.
Flyway returns a structured CHECKSUM_MISMATCH. Its JSON reports rejection
even when the process exit is zero. The profile checks the result and
the positive validation independently.

The zipapp verifies six rules and invokes the same native fixture again
against the bound migration files. Each run uses an owned PostgreSQL
namespace without a published host port. This is a small V1 to V2
qualification for the stated recovery boundary.

- [Flyway validation](https://documentation.red-gate.com/flyway/reference/commands/validate)
- [Flyway schema history](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/flyway-schema-history-table)
