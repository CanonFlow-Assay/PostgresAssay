# Audit and evidence contract

This initial implementation audits a supplied, normalized JSON snapshot under a named project-owned profile. A Pass means only the finite profile checks and configured required commands passed over the bound input bytes. Snapshot contents are reported evidence: the tool does not establish who collected them, that they describe a live deployment, or that every declaration is true. Hashes provide local integrity identities, not signatures.

## Commands and verdicts

`doctor` reports local readiness with no compliance authority. `catalog` lists every implemented rule and its primary-source ID. `explain <rule>` returns the rule's exact predicate/profile/source. `scan` retains observations and marks required commands NotRun. `verify` executes configured command argument arrays without a shell. `assess` wraps the complete verification receipt in an additive envelope.

Verdicts and process exits are Pass=0, Fail=1, Inconclusive=2, ToolFailure=3. Invalid command syntax/policy and output failures are ToolFailure. A known blocking failure or failed required command remains Fail alongside missing evidence. Missing/malformed snapshot evidence, unsupported versions, empty required arrays, unexecuted/unavailable commands or changed inputs remain visible. A clean scan is provisional and cannot Pass.

The baseline version is pinned in `toolchain.json` and the rule catalogue. A different version is incomplete evidence even if known predicates can still run. This prevents a future/older engine from silently inheriting qualification. External latest-version discovery never occurs during an audit.

## Input format and scope

Snapshot requires integer `schemaVersion: 1`, exact `product` and version strings, plus the fields consumed by the selected profile. `examples/snapshot.json` defines the normalized shape; native smoke scripts demonstrate actual collection for a bounded local fixture. Unknown fields/settings are outside the finite catalogue, not additional passing checks. Values not supplied are not inferred from product defaults. Values can be normalized from native string settings, but that transformation needs its own tested collection contract.

Each array-valued check observes every supplied item. An empty array is untested, not vacuous success. A failing item and an unavailable item are retained separately. This does not prove an operator supplied every role/index/authentication rule. Application-role membership, inherited privileges, effective HBA ordering, certificate validity and workload behavior require additional evidence.

Policy requires exactly `schemaVersion`, `profile`, `requiredCommands`, `inputs`. Commands are literal nonempty executable/argument arrays. `inputs` names the command evidence/code files to bind, relative to and beneath the policy directory. Snapshot and policy bytes are always bound automatically. Configure at least one meaningful behavior command and declare its inputs to obtain Pass. The bundled example deliberately has no behavior commands and remains incomplete.

The policy is trusted execution configuration. A command can read additional files, call services or mutate external state. Input hashing is not whole-process dependency tracking, and literal argument arrays are not a sandbox. Review command policy within the actual task authorization. Keep credentials out of policy arguments and receipts.

## Bounds and resource ownership

Python 3.12 is the development/CI lane; the offline runtime uses only the standard library. POSIX is required for executed command evidence. Each file is limited to 4 MiB, with at most 128 additional declared inputs and 32 commands of at most 128 arguments. Duplicate JSON keys, malformed UTF-8 and non-finite JSON numbers are rejected. Deep/malformed input is incomplete or invalid rather than repaired into a passing document. Symbolic-link paths and non-regular files are unsupported.

Each command has a 30-second deadline and at most 1 MiB plus one detection byte of collected combined output. Timeout/output-limit/start/cleanup gaps are Unavailable. The owned POSIX process group is terminated after collection. These limits control this local runner; they do not isolate hostile commands or undo committed external effects.

Re-observe snapshot, policy, declared input and producer identities after commands. Changed/unavailable bytes invalidate freshness. Canonical JSON excludes clocks, random IDs and log contents; execution results can still vary with the actual commands. Raw output is represented by digest/count/status rather than copied into the receipt.

## Output and packaging

`--out` writes canonical JSON through a same-directory staged file and atomic replacement, with fsync of that file. Parents must already exist. Symlink paths, hard-linked output targets and overlap with observed inputs are refused. This assumes a trusted local filesystem without concurrent path substitution; no hostile-filesystem or crash-durable-directory guarantee is made. Publication failure returns ToolFailure and does not grant Pass.

The deterministic zipapp contains the engine and catalogue and runs from an independent directory without importing the producer checkout. Source/policy/receipt identities and packaged-consumer tests are evidence for that archive; there is no registry upload, live database change or deployment action in the CLI.

## Qualification limits

The catalogue admits finite configuration predicates, not universal best practices. Broader tuning, SQL correctness, migrations, resource isolation, authorization, backup/PITR, failover, query relevance and production performance remain contextual guidance or external tests. No CIS certification, security certification or guarantee of business correctness is implied.

Native fixtures operate only on temporary databases/containers created by their scripts. PostgreSQL/OpenSearch intentionally use private test-only insecure configurations and retain expected production-profile failures. Their successful semantic tests must not be relabelled as a compliant production deployment.
