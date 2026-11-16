"""Offline evidence audit. No database client, SQL execution, or network access."""
from __future__ import annotations
import argparse
import hashlib
import importlib.resources as resources
import json
import os
import re
from decimal import Decimal
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import time

LIMIT = 4 * 1024 * 1024
OUTPUT_LIMIT = 1024 * 1024
TIMEOUT = 30


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def strict_json(data):
    def constant(_):
        raise ValueError("non-finite JSON number")
    return json.loads(data.decode("utf-8", errors="strict"), object_pairs_hook=pairs, parse_constant=constant)


def read_bytes(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError("symlink input is unsupported")
    if not path.is_file():
        raise ValueError("input must be a regular file")
    with path.open("rb") as stream:
        data = stream.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("input exceeds 4 MiB")
    return data


def pointer(value, path):
    for token in path.strip("/").split("/"):
        if not isinstance(value, dict) or token not in value:
            raise ValueError("required field missing")
        value = value[token]
    return value


def scalar(value, rule):
    kind = rule["kind"]
    if kind == "boolean":
        if type(value) is not bool:
            raise ValueError("boolean evidence required")
        return value == rule["expected"]
    if kind == "enum":
        if not isinstance(value, str):
            raise ValueError("string evidence required")
        return value in rule["allowed"]
    if kind == "integer":
        if type(value) is not int:
            raise ValueError("integer evidence required")
        return rule.get("min", 0) <= value <= rule.get("max", 2**63-1)
    if kind == "nonempty":
        if not isinstance(value, str):
            raise ValueError("string evidence required")
        return bool(value.strip())
    if kind == "bytes":
        if not isinstance(value, str) or len(value) > 64:
            raise ValueError("bounded byte-size string required")
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(B|KB|MB|GB|TB|KiB|MiB|GiB|TiB)", value)
        if not match:
            raise ValueError("explicit byte-size unit required")
        powers = {"B":1,"KB":10**3,"MB":10**6,"GB":10**9,"TB":10**12,
                  "KiB":2**10,"MiB":2**20,"GiB":2**30,"TiB":2**40}
        amount = Decimal(match[1]) * powers[match[2]]
        return 0 < amount <= 2**63-1
    raise ValueError("unsupported rule kind")


def evaluate(snapshot, catalogue, profile):
    checks = []
    for rule in catalogue["rules"]:
        if profile not in rule["profiles"]:
            continue
        try:
            value = pointer(snapshot, rule["path"])
            if rule["kind"] == "each":
                if not isinstance(value, list) or not value or len(value) > 10000:
                    raise ValueError("nonempty bounded array required")
                for index, item in enumerate(value):
                    try:
                        passed = scalar(pointer(item, rule["field"]), rule["test"])
                        outcome, detail = ("passed" if passed else "failed"), None
                    except ValueError as error:
                        outcome, detail = "untested", str(error)
                    checks.append({"ruleId": rule["id"], "severity": rule["severity"],
                                   "path": rule["path"] + "/" + str(index) + rule["field"],
                                   "outcome": outcome, "reason": detail})
                continue
            else:
                valid = scalar(value, rule)
            status, reason = ("passed" if valid else "failed"), None
        except ValueError as error:
            status, reason = "untested", str(error)
        checks.append({"ruleId": rule["id"], "severity": rule["severity"],
                       "path": rule["path"], "outcome": status, "reason": reason})
    return checks


def run_command(argv, cwd, timeout=TIMEOUT, output_limit=OUTPUT_LIMIT):
    """POSIX process-group ownership; bounded collection without a shell."""
    if os.name != "posix":
        return {"argv": argv, "status": "Unavailable", "reason": "POSIX runner required"}
    try:
        child = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return {"argv": argv, "status": "Unavailable", "reason": "executable could not start"}
    collected = bytearray()
    reason = None
    deadline = time.monotonic() + timeout
    with selectors.DefaultSelector() as selector:
        selector.register(child.stdout, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                reason = "timeout"
                break
            for key, _ in selector.select(min(remaining, 0.1)):
                chunk = os.read(key.fileobj.fileno(), min(65536, output_limit + 1 - len(collected)))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                collected.extend(chunk)
                if len(collected) > output_limit:
                    reason = "output limit"
                    break
            if reason:
                break
    # Also bound a child that closes output and keeps running. Terminate the
    # owned group after completion so inheriting descendants cannot linger.
    if reason is None:
        try:
            child.wait(timeout=max(0.01, deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            reason = "timeout"
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=2)
    except subprocess.TimeoutExpired:
        reason = "process cleanup unavailable"
    child.stdout.close()
    return {"argv": argv, "status": "Unavailable" if reason else ("Pass" if child.returncode == 0 else "Fail"),
            "exitCode": child.returncode, "outputSha256": digest(bytes(collected)),
            "collectedBytes": len(collected), "reason": reason}


def load_policy(path, catalogue):
    data = read_bytes(path)
    value = strict_json(data)
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "profile", "requiredCommands", "inputs"}:
        raise ValueError("policy requires exactly schemaVersion, profile, requiredCommands, inputs")
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1 or value["profile"] not in catalogue["profiles"]:
        raise ValueError("unsupported policy schema/profile")
    commands = value["requiredCommands"]
    if not isinstance(commands, list) or len(commands) > 32:
        raise ValueError("requiredCommands must be a bounded array")
    for command in commands:
        if not isinstance(command, list) or not 1 <= len(command) <= 128 or any(not isinstance(s, str) or not s or "\x00" in s or len(s) > 4096 for s in command):
            raise ValueError("commands require literal nonempty executable/argument arrays")
    inputs = value["inputs"]
    if not isinstance(inputs, list) or len(inputs) > 128 or len(set(inputs)) != len(inputs):
        raise ValueError("inputs must be a bounded unique array")
    paths = []
    base = Path(path).absolute().parent
    for relative in inputs:
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("policy inputs must be relative files beneath policy root")
        file = base / relative
        if not file.resolve().is_relative_to(base.resolve()):
            raise ValueError("policy input escapes root")
        paths.append(file)
    return value, data, paths


def verdict(checks, missing, commands):
    if any(c["outcome"] == "failed" and c["severity"] == "blocking" for c in checks) or any(c["status"] == "Fail" for c in commands):
        return "Fail"
    return "Inconclusive" if missing else "Pass"


def audit(snapshot_path, policy_path, catalogue, producer, command):
    missing, checks, commands, identities = [], [], [], []
    policy, policy_bytes, declared = load_policy(policy_path, catalogue)
    paths = [Path(snapshot_path).absolute(), Path(policy_path).absolute(), *declared]
    initial = {}
    for n, path in enumerate(paths):
        label = "snapshot" if n == 0 else "policy" if n == 1 else "input:" + policy["inputs"][n-2]
        try:
            data = read_bytes(path)
            initial[path] = digest(data)
            identities.append({"input": label, "sha256": digest(data)})
        except (OSError, ValueError):
            missing.append(label + ": unavailable input")
    try:
        snapshot = strict_json(read_bytes(snapshot_path))
        if not isinstance(snapshot, dict) or type(snapshot.get("schemaVersion")) is not int or snapshot.get("schemaVersion") != 1 or snapshot.get("product") != catalogue["product"]:
            raise ValueError("unsupported snapshot schema/product")
        if snapshot.get("version") != catalogue["engineVersion"]:
            missing.append("engine version differs from qualified baseline " + catalogue["engineVersion"])
        checks = evaluate(snapshot, catalogue, policy["profile"])
    except (OSError, ValueError, RecursionError):
        missing.append("snapshot is unavailable, malformed, or unsupported")
    missing.extend(c["ruleId"] + ": " + c["reason"] for c in checks if c["outcome"] == "untested" and c["severity"] == "blocking")
    if not policy["requiredCommands"]:
        missing.append("required behavior commands not configured")
    if policy["requiredCommands"] and not policy["inputs"]:
        missing.append("required command inputs not declared")
    for argv in policy["requiredCommands"]:
        if command == "scan" or missing:
            commands.append({"argv": argv, "status": "NotRun"})
        else:
            commands.append(run_command(argv, Path(policy_path).absolute().parent))
    if command == "scan":
        missing.append("scan is provisional; required commands not executed")
    if any(c["status"] in ("Unavailable", "NotRun") for c in commands):
        missing.append("required command evidence unavailable")
    for path, before in initial.items():
        try:
            unchanged = digest(read_bytes(path)) == before
        except (OSError, ValueError):
            unchanged = False
        if not unchanged:
            missing.append("input changed or became unavailable after observation")
    result = {"schemaVersion": "data-assay-receipt/1", "producer": producer,
              "product": catalogue["product"], "qualifiedEngineVersion": catalogue["engineVersion"],
              "profile": policy["profile"], "command": command,
              "authority": "supplied-snapshot-and-declared-command-evidence",
              "inputs": identities, "checks": checks, "commands": commands,
              "missingEvidence": sorted(set(missing)), "verdict": verdict(checks, missing, commands)}
    return result, paths


def publish(result, output, inputs):
    output = Path(output).absolute()
    for item in (output, *output.parents):
        if item.is_symlink():
            raise ValueError("redirected output path")
    if output.exists() and (not output.is_file() or output.stat().st_nlink > 1):
        raise ValueError("output must be an unlinked regular target")
    if any(output == p.absolute() or (output.exists() and p.exists() and os.path.samefile(output, p)) for p in inputs):
        raise ValueError("output overlaps observed input")
    # No implicit parent creation: a typo cannot create an unexpected directory tree.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(canonical(result))
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def main(package):
    package_root = resources.files(package)
    catalogue_bytes = package_root.joinpath("catalogue.json").read_bytes()
    catalogue = strict_json(catalogue_bytes)
    def producer_hash():
        return digest(b"".join(package_root.joinpath(name).read_bytes() for name in
                      ("__init__.py", "__main__.py", "engine.py", "catalogue.json")))
    producer = {"name": catalogue["assay"], "version": "0.1.0", "sha256": producer_hash()}
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            self.print_usage(sys.stderr)
            print(canonical({"schemaVersion":"data-assay-receipt/1", "verdict":"ToolFailure", "error":"invalid command line"}), end="")
            raise SystemExit(3)
    parser = Parser(description=catalogue["assay"] + ": bounded offline snapshot audit")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("catalog")
    sub.add_parser("doctor")
    explain = sub.add_parser("explain")
    explain.add_argument("rule")
    for name in ("scan", "verify", "assess"):
        child = sub.add_parser(name)
        child.add_argument("snapshot", type=Path)
        child.add_argument("--policy", type=Path, required=True)
        child.add_argument("--out", type=Path)
    args = parser.parse_args()
    paths = []
    if args.command == "catalog":
        print(canonical(catalogue), end="")
        return 0
    if args.command == "doctor":
        print(canonical({"producer": producer, "python": list(sys.version_info[:3]), "posixCommandRunner": os.name == "posix", "authority": "readiness-only"}), end="")
        return 0
    if args.command == "explain":
        rule = next((r for r in catalogue["rules"] if r["id"] == args.rule), None)
        print(canonical(rule or {"error": "unknown rule"}), end="")
        return 0 if rule else 3
    try:
        result, paths = audit(args.snapshot, args.policy, catalogue, producer, args.command)
        if producer_hash() != producer["sha256"]:
            result["missingEvidence"].append("producer changed during required commands")
            result["verdict"] = verdict(result["checks"], result["missingEvidence"], result["commands"])
        if args.command == "assess":
            result = {"schemaVersion": "data-assay-assessment/1", "verdict": result["verdict"], "receipt": result}
        if args.out:
            publish(result, args.out, paths)
    except (OSError, ValueError, TypeError, RecursionError):
        result = {"schemaVersion": "data-assay-receipt/1", "producer": producer, "verdict": "ToolFailure", "error": "invalid policy or unavailable output; inspect declared paths and contract"}
    print(canonical(result), end="")
    return {"Pass": 0, "Fail": 1, "Inconclusive": 2, "ToolFailure": 3}[result["verdict"]]
