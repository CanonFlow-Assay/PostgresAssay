# PostgresAssay playground

The wrapper evaluates a checked-in PostgreSQL 18.7 settings snapshot. The unit suite also exercises the separate Wallet Migration profile.

Run the source commands from the repository root with Python 3.
[Native fixture setup](../docs/native.md)

```sh
python3 playground/run.py
```

The v2 receipt preserves command arguments, exits, and raw logs for
readiness, catalogue explanations, source tests, the showcase verification,
and the provisional scan control. The scan control expects
`Inconclusive` with exit `2`. The wrapper propagates a failed or
incomplete showcase and refuses a contradictory receipt and process exit.

For the native receipt alone, run each command independently.

```sh
PYTHONPATH=src python3 -m postgres_assay scan examples/snapshot.json --policy examples/policy.json
PYTHONPATH=src python3 -m postgres_assay verify examples/snapshot.json --policy examples/policy.json
```

The example policy has an empty `requiredCommands` list. Both commands report `Inconclusive` with exit `2` for this fixture. Wallet Migration and the native database fixture each use their own evidence.

Qualify the pinned native wallet profile in a fresh directory and pass its
policy and snapshot to the wrapper.

```sh
python3 eng/qualify-profile.py --out artifacts/wallet-qualification
python3 playground/run.py --policy artifacts/wallet-qualification/policy.json \
  --snapshot artifacts/wallet-qualification/snapshot.json
```
