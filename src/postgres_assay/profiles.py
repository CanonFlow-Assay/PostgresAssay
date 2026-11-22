"""Migration profile predicates over actual before/after and Flyway observations."""

import re


def rows(value, key):
    record = value[key]
    if not isinstance(record, dict) or set(record) != {"wallets", "operations", "outbox"}:
        raise ValueError("wallet migration requires three observed record sets")
    for table, data in record.items():
        if not isinstance(data, list) or not data or any(not isinstance(row, dict) for row in data):
            raise ValueError(f"{table}: expected populated deterministic row observations")
        identity = "id" if table == "wallets" else "reference"
        ids = [row.get(identity) for row in data]
        if any(not isinstance(item, str) or not item for item in ids) or ids != sorted(set(ids)):
            raise ValueError(f"{table}: identities must be unique with explicit order")
        fields = {"wallets": ("id", "balance"), "operations": ("reference", "wallet", "amount", "status", "balance"),
                  "outbox": ("reference", "event")}[table]
        money = {"wallets": ("balance",), "operations": ("amount", "balance"), "outbox": ()}[table]
        for row in data:
            if set(row) != set(fields) or any(not isinstance(row[field], str) or not row[field] for field in fields):
                raise ValueError(f"{table}: missing typed row values")
            if any(not re.fullmatch(r"-?[0-9]+\.[0-9]{2}", row[column]) for column in money):
                raise ValueError(f"{table}: missing exact decimal observation")
    return record


def preserved(value):
    return rows(value, "before") == rows(value, "after")


def history(value):
    expected = value["expectedVersions"]
    observed = value["history"]
    if not isinstance(expected, list) or not expected or any(not isinstance(item, str) or not item for item in expected):
        raise ValueError("expected a nonempty migration sequence")
    if not isinstance(observed, list) or not observed:
        raise ValueError("expected observed migration history")
    for row in observed:
        if not isinstance(row, dict) or type(row.get("checksum")) is not int or type(row.get("success")) is not bool:
            raise ValueError("native history requires checksum and success")
    return (len(expected) == len(set(expected)) and [row.get("version") for row in observed] == expected
            and all(row["success"] for row in observed))


def validation(value):
    result = value["flywayValidation"]
    if not isinstance(result, dict) or type(result.get("exitCode")) is not int or type(result.get("successful")) is not bool:
        raise ValueError("actual Flyway validation exit and result required")
    return result == {"exitCode": 0, "successful": True}


def index_evidence(value):
    expected = value["expectedIndex"]
    observed = value["observedIndex"]
    if not isinstance(expected, str) or not expected or (observed is not None and not isinstance(observed, str)):
        raise ValueError("index definition evidence is unavailable")
    return observed == expected


def recovered(value):
    result = value["recovery"]
    if not isinstance(result, dict) or set(result) != {"workerExit", "applyDispatches", "action", "ackBytes"}:
        raise ValueError("missing observed recovery outcome")
    if any(type(result[key]) is not int for key in ("workerExit", "applyDispatches", "ackBytes")):
        raise ValueError("recovery count and exit evidence requires integers")
    return result == {"workerExit": -9, "applyDispatches": 1, "action": "RecoveredFromLedger", "ackBytes": 0}


def checksum_control(value):
    row = value["checksumControl"]
    if not isinstance(row, dict) or type(row.get("exitCode")) is not int or type(row.get("successful")) is not bool:
        raise ValueError("native checksum control result unavailable")
    return row["successful"] is False and row.get("errorCodes") == ["CHECKSUM_MISMATCH"]


CHECKS = {"preserved": preserved, "history": history, "validate": validation,
          "index": index_evidence, "recovered": recovered, "checksum-control": checksum_control}
