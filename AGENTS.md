# Repository instructions

Read README.md and CONTRACT.md before changing verifier authority. Keep source evidence inert and preserve four-state verdicts, raw receipts, typed profile predicates, input freshness and bounded command ownership. Use docs/research.md to distinguish primary semantics from community suggestions. Do not promote a contextual recommendation into a blocking rule without explicit scope and qualification.

Run the standard-library unit tests and independent archive checks for engine changes. Use only pinned, disposable native fixtures created by eng/native_smoke.py for engine qualification. Keep the corresponding skill synchronized with the central collection. Existing database/container workloads and host configuration are outside test scope.
