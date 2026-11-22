from copy import deepcopy
import unittest

from test_engine import CAT, engine

PROFILE = "wallet-migration"
STATE = {
    "wallets": [{"id": "a", "balance": "9.75"}],
    "operations": [{"reference": "r", "wallet": "a", "status": "accepted", "amount": "0.25", "balance": "9.75"}],
    "outbox": [{"reference": "r", "event": "debited"}],
}
GOOD = {
    "before": STATE, "after": deepcopy(STATE), "expectedVersions": ["1", "2"],
    "history": [{"version": "1", "checksum": 4, "success": True}, {"version": "2", "checksum": 9, "success": True}],
    "flywayValidation": {"exitCode": 0, "successful": True}, "expectedIndex": "native index",
    "observedIndex": "native index",
    "recovery": {"workerExit": -9, "applyDispatches": 1, "action": "RecoveredFromLedger", "ackBytes": 0},
    "checksumControl": {"exitCode": 0, "successful": False, "errorCodes": ["CHECKSUM_MISMATCH"]},
}


def outcomes(value):
    return {item["ruleId"]: item["outcome"] for item in engine.evaluate({"migration": value}, CAT, PROFILE)}


class WalletMigrationProfile(unittest.TestCase):
    def test_no_unchecked_rules_in_the_profile(self):
        actual = outcomes(deepcopy(GOOD))
        selected = {rule["id"] for rule in CAT["rules"] if PROFILE in rule["profiles"]}
        self.assertEqual(actual, {rule_id: "passed" for rule_id in selected})

    def test_each_rule_has_a_conclusive_negative_control(self):
        for rule, field, value in (
            ("PGM001", "after", {**STATE, "outbox": [{"reference": "r", "event": "lost"}]}),
            ("PGM002", "history", GOOD["history"] + [GOOD["history"][1]]),
            ("PGM003", "flywayValidation", {"exitCode": 0, "successful": False}),
            ("PGM004", "observedIndex", None),
            ("PGM005", "recovery", {**GOOD["recovery"], "applyDispatches": 2}),
            ("PGM006", "checksumControl", {"exitCode": 0, "successful": True, "errorCodes": []}),
        ):
            with self.subTest(rule=rule):
                sample = deepcopy(GOOD)
                sample[field] = value
                self.assertEqual(outcomes(sample)[rule], "failed")

    def test_empty_or_typed_incomplete_evidence_remains_untested(self):
        sample = deepcopy(GOOD)
        sample["before"]["wallets"] = []
        sample["flywayValidation"]["exitCode"] = False
        del sample["recovery"]["ackBytes"]
        actual = outcomes(sample)
        for missing in ("PGM001", "PGM003", "PGM005"):
            self.assertEqual(actual[missing], "untested")
