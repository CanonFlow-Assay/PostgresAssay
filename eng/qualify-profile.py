"""Qualify the supplemental profile and re-execute its native evidence."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def logged(directory, name, argv, expected=0):
    result = subprocess.run(argv, cwd=directory, text=True, capture_output=True, timeout=120)
    (directory / f"{name}.stdout").write_text(result.stdout)
    (directory / f"{name}.stderr").write_text(result.stderr)
    (directory / f"{name}.command.json").write_text(json.dumps({"argv": argv, "exitCode": result.returncode}) + "\n")
    if result.returncode != expected:
        raise RuntimeError(f"{name} returned {result.returncode}; inspect {directory}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.absolute()
    out.mkdir(parents=True, exist_ok=False)
    config = json.loads((ROOT / "eng/profile-qualification.json").read_text())
    sources = config["files"]
    for path in sources:
        relative = Path(path).name if path.startswith("eng/") else path.removeprefix("examples/")
        (out / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, out / relative)
    profile = config["profile"]
    native = [sys.executable, "native_smoke.py", "--profile", profile, *config["arguments"]]
    logged(out, "collect", [*native, "--output", "snapshot.json"])
    collect_record = json.loads((out / "snapshot.json").read_text())
    if config.get("assertion"):
        check = collect_record["migration"][config["assertion"]]
        if check["successful"] is not False:
            raise RuntimeError("native checksum control missing")
    inputs = [Path(path).name if path.startswith("eng/") else path.removeprefix("examples/") for path in sources]
    policy = {"schemaVersion": 1, "profile": profile, "inputs": inputs,
              "requiredCommands": [[*native, "--check", "snapshot.json"]]}
    (out / "policy.json").write_text(json.dumps(policy, indent=2) + "\n")
    logged(out, "profile-package", [sys.executable, str(ROOT / "eng/package.py")])
    archive = ROOT / "artifacts" / (config["package"] + ".pyz")
    consumer = out / archive.name
    shutil.copyfile(archive, consumer)
    cmd = [sys.executable, consumer.name]
    receipt = json.loads(logged(out, "verify", [
        *cmd, "verify", "snapshot.json", "--policy", "policy.json", "--out", "receipt.json",
    ]))
    if receipt["verdict"] != "Pass" or any(item["outcome"] != "passed" for item in receipt["checks"]):
        raise RuntimeError("required native evidence did not pass the declared profile")
    controls = {}
    for name, expected_rule in config["controls"].items():
        record = json.loads(logged(out, name + "-control", [
            *cmd, "scan", name + ".json", "--policy", "policy.json",
        ], 1))
        if not any(check["ruleId"] == expected_rule and check["outcome"] == "failed" for check in record["checks"]):
            raise RuntimeError("the expected native control finding is absent")
        controls[name] = expected_rule
    print(json.dumps({"profile": profile, "verdict": receipt["verdict"], "verifiedRules": len(receipt["checks"]),
                      "nativeControls": controls, "evidence": str(out)}, indent=2))


if __name__ == "__main__":
    main()
