"""Replay the Wallet upgrade in an owned PostgreSQL namespace."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

from native_common import call, container, ready

POSTGRES = "postgres:18.7@sha256:2ea8630df176ad090ec92136dee850397c5af8781e4bcf2e4162593691c61bbc"
FLYWAY = "flyway/flyway:13.12.1@sha256:3b4fae57858ee25735230e42f426fd200144fedbe692ea7789aa3e50a7c11657"
EXPECTED_INDEX = "CREATE INDEX operations_wallet_idx ON public.operations USING btree (wallet)"
FILES = ("V1__wallet.sql", "V2__index_wallet_operations.sql")
WORKER = """
import subprocess
import sys

result = subprocess.run(sys.argv[1:], capture_output=True)
if result.returncode:
    sys.exit(result.returncode)
# The response remains inside this process until the recipient acknowledges.
sys.stdin.buffer.read(1)
sys.stdout.buffer.write(result.stdout)
"""


def snapshot_rows(sql):
    return json.loads(sql("""
SELECT json_build_object(
  'wallets', (SELECT json_agg(v ORDER BY id) FROM (SELECT id,balance::text AS balance FROM wallets) v),
  'operations', (SELECT json_agg(v ORDER BY reference) FROM
    (SELECT reference,wallet,amount::text AS amount,status,balance::text AS balance FROM operations) v),
  'outbox', (SELECT json_agg(v ORDER BY reference) FROM outbox v));
"""))


def migration_history(sql):
    return json.loads(sql("""
SELECT COALESCE(json_agg(json_build_object(
    'version',version,'checksum',checksum,'success',success) ORDER BY installed_rank)
    FILTER (WHERE version IS NOT NULL), '[]')
FROM public.flyway_schema_history;
"""))


def flyway_args(container_name, directory, *args):
    return [
        "docker", "run", "--rm", "--pull=never", "--network", f"container:{container_name}",
        "--memory", "768m", "--cpus", "2",
        "--mount", f"type=bind,source={directory},target=/flyway/sql,readonly",
        "-e", "FLYWAY_URL=jdbc:postgresql://127.0.0.1:5432/postgres",
        "-e", "FLYWAY_USER=postgres", FLYWAY, "-outputType=json", *args,
    ]


def interrupt_after_commit(name, argv, sql):
    worker_container = name + "-flyway"
    argv[2:2] = ["--name", worker_container]
    child = subprocess.Popen(
        [sys.executable, "-c", WORKER, *argv], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, start_new_session=True,
    )
    try:
        def committed():
            history = migration_history(sql)
            if [row["version"] for row in history if row["success"]] != ["1", "2"]:
                raise ValueError("V2 has not committed")
            return history

        committed_history = ready(committed, seconds=20)
        if child.poll() is not None:
            raise RuntimeError("worker returned before the acknowledgement boundary")
        os.killpg(child.pid, signal.SIGKILL)
        stdout, _ = child.communicate(timeout=5)
        return committed_history, child.returncode, len(stdout)
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
        child.communicate(timeout=5)
        # This randomly named container can only belong to this fixture.
        subprocess.run(["docker", "rm", "-f", "-v", worker_container], capture_output=True, timeout=10)


def run(source_directory):
    with tempfile.TemporaryDirectory(prefix="postgres-assay-wallet-") as temp:
        directory = Path(temp)
        for filename in FILES:
            shutil.copyfile(source_directory / filename, directory / filename)
        inputs = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in FILES}
        with container(POSTGRES, ["--env", "POSTGRES_HOST_AUTH_METHOD=trust"]) as (name, image):
            def sql(text):
                return call(["docker", "exec", "-i", name, "psql", "-X", "-h", "127.0.0.1", "-U", "postgres",
                             "-v", "ON_ERROR_STOP=1", "-tA"], text, timeout=10).strip()

            ready(lambda: sql("SELECT 1;"), seconds=15)
            version = sql("SELECT current_setting('server_version');").split()[0]
            if version != "18.7":
                raise RuntimeError("unexpected PostgreSQL version")
            invocations = []

            def flyway(*args):
                invocations.append(list(args))
                return flyway_args(name, directory, *args)

            call(flyway("-target=1", "migrate"), timeout=15)
            sql("""
UPDATE wallets SET balance=75.25 WHERE id='a';
INSERT INTO operations VALUES('op-1','a',24.75,'accepted',75.25);
INSERT INTO outbox VALUES('op-1','debited');
""")
            before = snapshot_rows(sql)
            committed_history, worker_exit, ack_bytes = interrupt_after_commit(name, flyway("-target=2", "migrate"), sql)
            validation = subprocess.run(
                flyway("validate"), capture_output=True, text=True, timeout=12,
            )
            validation_payload = json.loads(validation.stdout)
            history = migration_history(sql)
            valid = validation.returncode == 0 and validation_payload["validationSuccessful"]
            action = "RecoveredFromLedger" if valid and history == committed_history else "ReviewRequired"
            after = snapshot_rows(sql)
            index = json.loads(sql("SELECT to_json(pg_get_indexdef(to_regclass('public.operations_wallet_idx')));") or "null")

            # A changed staged migration is rejected by the native checksum validator.
            v2 = directory / FILES[1]
            original = v2.read_text()
            changed = original.replace("operations(wallet)", "operations(reference)")
            if changed == original:
                raise RuntimeError("checksum control could not alter the indexed field")
            v2.write_text(changed)
            mismatched = subprocess.run(
                flyway("validate"), capture_output=True, text=True, timeout=12,
            )
            mismatch_payload = json.loads(mismatched.stdout)
            codes = [item["errorDetails"]["errorCode"] for item in mismatch_payload["invalidMigrations"]]
            if mismatch_payload.get("validationSuccessful") is not False or codes != ["CHECKSUM_MISMATCH"]:
                raise RuntimeError("Flyway did not return the native checksum mismatch result")
        return {
            "schemaVersion": 1, "product": "postgresql", "version": version,
            "migration": {
                "expectedVersions": ["1", "2"], "before": before, "after": after, "history": history,
                "flywayValidation": {"exitCode": validation.returncode,
                                     "successful": validation_payload["validationSuccessful"]},
                "expectedIndex": EXPECTED_INDEX, "observedIndex": index,
                "recovery": {"workerExit": worker_exit,
                             "applyDispatches": invocations.count(["-target=2", "migrate"]),
                             "action": action, "ackBytes": ack_bytes},
                "inputs": inputs, "postgresImage": image, "flywayImage": FLYWAY, "flywayInvocations": invocations,
                "checksumControl": {"exitCode": mismatched.returncode,
                                    "successful": mismatch_payload["validationSuccessful"],
                                    "errorCodes": codes},
            },
        }


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", required=True, type=Path)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--output", type=Path)
    target.add_argument("--check", type=Path)
    options = parser.parse_args(argv)
    result = run(options.sources.absolute())
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if options.output:
        options.output.write_text(encoded)
    elif result != json.loads(options.check.read_text()):
        raise RuntimeError("re-executed Wallet observations differ from the declared snapshot")
    print(encoded, end="")
