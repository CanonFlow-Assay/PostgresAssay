# Initial local qualification

Reviewed on 2026-11-16. This is a bounded initial implementation, not a mature production certification programme.

- Unit suite: 42 passed, 0 inapplicable cases skipped, no failures.
- Every applicable catalogue rule has a negative-value fixture; incomplete fields/types and array scope are tested separately.
- Independent archive: built deterministically and executed from a fresh directory without the source checkout on PYTHONPATH.
- Native engine: 8 real behavior cases passed on the exact pinned version/artifact.
- Native snapshot assessment: expected Fail for the deliberately insecure disposable fixture, retaining raw findings and missing evidence.

The [machine-readable record](qualification.json) binds implementation/test/qualification source files and command-log digests. Raw local receipts, logs and snapshots remain under ignored artifacts/. The record is a local integrity record, not a signature. GitHub CI has its own actual run result and is not implied by this local record.

See [native qualification](native.md), [best practices](best-practices.md) and [contract](../CONTRACT.md). Missing production PKI, authorization, HA/recovery, performance and other scopes are retained in the native result limits.
