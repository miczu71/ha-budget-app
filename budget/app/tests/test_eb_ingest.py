import json
from pathlib import Path

from budget import eb_ingest
from budget.eb_models import Transaction

FIXTURES = Path(__file__).parent / "fixtures"


def _mock() -> list[Transaction]:
    data = json.loads((FIXTURES / "eb_mock_transactions_main.json").read_text(encoding="utf-8"))
    return [Transaction.from_api(t) for t in data["transactions"]]


def test_convert_mock_dataset() -> None:
    raw = _mock()
    out = eb_ingest.convert(raw, card_account=False)
    assert len(out) == len(raw)
    assert {t.status for t in out} >= {"BOOK", "PDNG"}
    assert all(len(t.fingerprint) == 20 for t in out)
    # Mock gubi część referencji — wtedy tożsamość to odcisk + numer wystąpienia (unikalne)
    assert any(not t.refs and t.status == "BOOK" for t in out)
    booked = [(t.fingerprint, t.occurrence) for t in out if t.status == "BOOK"]
    assert len(booked) == len(set(booked))


def test_fingerprint_ignores_cut_points() -> None:
    from datetime import date
    from decimal import Decimal

    a = eb_ingest.fingerprint(date(2026, 9, 1), Decimal("-1.5"), "SKLEP Przykl adowo")
    b = eb_ingest.fingerprint(date(2026, 9, 1), Decimal("-1.50"), "SKLEP Przyklad owo")
    assert a == b


def test_load_dump_naming(tmp_path: Path) -> None:
    payload = {"date_from": "2026-07-04", "pages": 1, "transactions": []}
    good = tmp_path / "transactions_2_0a1b2c3d_20261002T053210Z.json"
    good.write_text(json.dumps(payload), encoding="utf-8")
    probe = tmp_path / "transactions_0_longest.json"
    probe.write_text(json.dumps(payload), encoding="utf-8")
    dump = eb_ingest.load_dump(good)
    assert dump is not None
    assert (dump.account_index, dump.hash_digest) == (2, "0a1b2c3d")
    assert dump.fetched_at == "2026-10-02T05:32:10+00:00"
    assert eb_ingest.load_dump(probe) is None
    assert len(eb_ingest.hash_digest("x")) == 8
