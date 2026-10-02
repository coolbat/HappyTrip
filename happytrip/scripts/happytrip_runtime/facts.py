"""Fact provenance stays explicit; guesses never become printable facts."""
from copy import deepcopy
from .types import HappyTripError

TRUSTED_SOURCES = {"user", "user_confirmed_metadata", "verified_reference"}


def normalize_facts(request):
    facts = request.get("facts", [])
    hypotheses = request.get("hypotheses", [])
    if not isinstance(facts, list) or not isinstance(hypotheses, list):
        raise HappyTripError("FACT_INVALID", "facts and hypotheses must be arrays")
    ledger = {"confirmed": [], "hypotheses": [], "warnings": []}
    for original in facts:
        if not isinstance(original, dict) or "value" not in original:
            raise HappyTripError("FACT_INVALID", "Each fact requires a value and provenance")
        item = deepcopy(original)
        source = item.get("source")
        confirmation = item.get("confirmed", source == "user")
        if item["value"] is None or item["value"] == "":
            continue
        if isinstance(source, str) and source in TRUSTED_SOURCES and confirmation is True:
            item["confirmed"] = True
            ledger["confirmed"].append(item)
        else:
            item["confirmed"] = False
            ledger["hypotheses"].append(item)
            ledger["warnings"].append("Unconfirmed or untrusted fact excluded from printable facts")
    for original in hypotheses:
        item = deepcopy(original) if isinstance(original, dict) else {"value": deepcopy(original)}
        item["confirmed"] = False
        ledger["hypotheses"].append(item)
    return ledger
