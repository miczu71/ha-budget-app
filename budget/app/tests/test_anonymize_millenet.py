"""Regresja prywatności anonimizatora CSV Millenetu — na danych syntetycznych (CI).

Narzędzie produkuje fixture do publicznego repo, więc test pilnuje, że lokalizacje, osoby,
lokalni sprzedawcy i numery nie przechodzą, a format (BOM, CRLF, zawijanie, szerokości pól,
duplikaty karty dodatkowej, ciągłość salda) zostaje zachowany.
"""

import csv
import importlib.util
import io
import re
import sys
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from types import ModuleType

import pytest

TOOL = Path(__file__).parents[1] / "tools" / "anonymize_millenet.py"
HEADER = [
    "Numer rachunku/karty",
    "Data transakcji",
    "Data rozliczenia",
    "Rodzaj transakcji",
    "Na konto/Z konta",
    "Odbiorca/Zleceniodawca",
    "Opis",
    "Obciążenia",
    "Uznania",
    "Saldo",
    "Waluta",
]
ACC = "PL61 1090 1014 0000 0712 1981 2874"
OTHER = "27 1140 2004 0000 3002 0135 5387"
CARD_MAIN, CARD_EXTRA = "4255****1111", "4255****2222"
NBSP = "\xa0"


@pytest.fixture(scope="module")
def tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("anonymize_millenet", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["anonymize_millenet"] = module
    spec.loader.exec_module(module)
    return module


def _source(tool: ModuleType) -> bytes:
    wrap = tool.wrap
    card_desc = wrap("DELIKATESY POD LIPAMI UL. KWIATOWA 7 WIOSKOWO POL") + NBSP + "2026-09-01"
    rows = [
        # rachunek (od najnowszych), saldo ciągłe
        [
            ACC,
            "2026-09-03",
            "2026-09-03",
            "PRZELEW PRZYCHODZĄCY",
            OTHER,
            f"PRACODAWCA SPÓŁKA Z O.O.{NBSP}UL. FABRYCZNA 1{NBSP}00-001 MIASTECZKO",
            "Wynagrodzenie 09/2026",
            "",
            "8000.00",
            "9850.00",
            "PLN",
        ],
        [
            ACC,
            "2026-09-02",
            "2026-09-02",
            "PRZELEW NA TELEFON",
            "",
            "JAN KOWALSKI",
            "obiad u Kowalskich",
            "-50.00",
            "",
            "1850.00",
            "PLN",
        ],
        [
            ACC,
            "2026-09-02",
            "2026-09-02",
            "ZAKUP - FIZ. UŻYCIE KARTY",
            "",
            "",
            card_desc,
            "-4.50",
            "",
            "1900.00",
            "PLN",
        ],
        [
            ACC,
            "2026-09-02",
            "2026-09-02",
            "ZAKUP - FIZ. UŻYCIE KARTY",
            "",
            "",
            card_desc,
            "-4.50",
            "",
            "1904.50",
            "PLN",
        ],
        [
            ACC,
            "2026-09-01",
            "2026-09-01",
            "PŁATNOŚĆ BLIK W INTERNECIE",
            "",
            f"sklep-lokalny.pl{NBSP}PayU{NBSP}ul. Kwiatowa 5{NBSP}12-345 Wioskowo",
            f"/OPT/X///// BPID:AB12CD34{NBSP}Zamówienie 123456{NBSP}PayU S.A.",
            "-95.50",
            "",
            "1909.00",
            "PLN",
        ],
        [
            ACC,
            "2026-09-01",
            "2026-09-01",
            "ZAKUP - FIZ. UŻYCIE KARTY",
            "",
            "",
            "LIDL UL. KWIATOWA 9 WIOSKOWO POL" + NBSP + "2026-08-31",
            "-120.00",
            "",
            "2004.50",
            "PLN",
        ],
        [ACC, "2026-08-31", "2026-08-31", "PROWIZJA", "", "", "", "", "", "2124.50", "PLN"],
        # karta kredytowa: ten sam zakup pod kartą główną i dodatkową + zakup walutowy
        [
            CARD_MAIN,
            "2026-08-20",
            "2026-08-22",
            "",
            "",
            "",
            "LOKALNA KAWIARNIA        ,  WIOSKOWO    , 616",
            "-18.00",
            "",
            "",
            "PLN",
        ],
        [
            CARD_EXTRA,
            "2026-08-20",
            "2026-08-22",
            "",
            "",
            "",
            "LOKALNA KAWIARNIA        ,  WIOSKOWO    , 616",
            "-18.00",
            "",
            "",
            "PLN",
        ],
        [
            CARD_MAIN,
            "2026-08-18",
            "2026-08-21",
            "",
            "",
            "",
            "LIDL ITALIA              ,  MILANO      , 380 -12.3 EUR",
            "-54.10",
            "",
            "",
            "PLN",
        ],
    ]
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(HEADER)
    writer.writerows(rows)
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def _rows(data: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline="")))


def test_no_personal_or_location_data(tool: ModuleType) -> None:
    src = _source(tool)
    out = tool.anonymize(src, per_type=50, seed=7)
    text = tool.fold(out.decode("utf-8-sig"))
    for secret in (
        "KOWALSK",
        "PRACODAWCA",
        "FABRYCZNA",
        "MIASTECZKO",
        "KWIATOWA",
        "WIOSKOWO",
        "LIPAMI",
        "LOKALNA",
        "MILANO",
        "SKLEP-LOKALNY",
        "12-345",
        "00-001",
        "123456",
        "1981",
        "OBIAD",
        "WYNAGRODZENIE",
    ):
        assert secret not in text, secret
    assert not tool.leak_report(src, out)
    for kept in ("LIDL", "PAYU", "EUR", "616", "380", "DELIKATESY", "PROWIZJA"):
        assert kept in text, kept


def test_format_preserved(tool: ModuleType) -> None:
    src = _source(tool)
    out = tool.anonymize(src, per_type=50, seed=7)
    assert out.startswith(b"\xef\xbb\xbf")
    assert out.split(b"\r\n")[0] == src.split(b"\r\n")[0]
    rows = _rows(out)
    assert len(rows) == len(_rows(src))
    for r in rows:
        if re.search(NBSP + r"\d{4}-\d{2}-\d{2}$", r["Opis"]):
            segments = r["Opis"].split(NBSP)[:-1]
            assert all(len(s) in (44, 45) for s in segments[:-1])
            assert len(segments[-1]) <= 45
    card = [r for r in rows if "*" in r["Numer rachunku/karty"]]
    for r in card:
        fields = r["Opis"].split(",")
        assert (len(fields[0]), len(fields[1])) == (25, 14)
    assert any(r["Opis"].endswith("-12.3 EUR") for r in card)


def test_duplicates_twins_and_balances_survive(tool: ModuleType) -> None:
    rows = _rows(tool.anonymize(_source(tool), per_type=50, seed=7))
    card = [r for r in rows if "*" in r["Numer rachunku/karty"]]
    dup = [r for r in card if "KAWIARNIA" in r["Opis"]]
    assert len(dup) == 2 and dup[0]["Numer rachunku/karty"] != dup[1]["Numer rachunku/karty"]
    assert {k: v for k, v in dup[0].items() if k != "Numer rachunku/karty"} == {
        k: v for k, v in dup[1].items() if k != "Numer rachunku/karty"
    }
    account = [r for r in rows if "*" not in r["Numer rachunku/karty"]]
    twins = [r for r in account if "DELIKATESY" in r["Opis"]]
    assert len(twins) == 2 and twins[0]["Opis"] == twins[1]["Opis"]
    assert twins[0]["Obciążenia"] == twins[1]["Obciążenia"]
    for newer, older in pairwise(account):
        amount = Decimal(newer["Uznania"] or newer["Obciążenia"] or "0")
        assert Decimal(newer["Saldo"]) - amount == Decimal(older["Saldo"])


def test_numbers_consistent_and_dates_shifted(tool: ModuleType) -> None:
    rows = _rows(tool.anonymize(_source(tool), per_type=50, seed=7))
    accounts = {r["Numer rachunku/karty"] for r in rows}
    assert ACC not in accounts and CARD_MAIN not in accounts
    assert len(accounts) == 3  # rachunek + 2 karty, spójnie
    assert all(r["Data transakcji"] <= "2026-08-20" for r in rows)  # −14 dni
    assert any(r["Opis"].endswith(NBSP + "2026-08-17") for r in rows)  # data w opisie też


def test_committed_fixture_is_anonymized() -> None:
    """Siatka bezpieczeństwa na sam plik w repo (wygenerowany z prawdziwego eksportu)."""
    data = (Path(__file__).parent / "fixtures" / "millenet_sample.csv").read_bytes()
    assert data.startswith(b"\xef\xbb\xbf") and b"\r\n" in data
    rows = _rows(data)
    assert list(rows[0]) == HEADER
    assert len(rows) >= 100 and len({r["Rodzaj transakcji"] for r in rows}) >= 20
    text = data.decode("utf-8-sig")
    assert set(re.findall(r"\b\d{2}-\d{3}\b", text)) <= {"00-000"}
    assert not re.search(r"\bUL\. (?!TESTOWA)", text, re.IGNORECASE)
    free_text = re.compile(r"PRZELEW|ZLECENIE|POLECENIE")
    for r in rows:
        party = r["Odbiorca/Zleceniodawca"]
        if free_text.search(r["Rodzaj transakcji"]) and party:
            assert re.fullmatch(r"(OSOBA|FIRMA) TESTOWA \d{3}( SP\. Z O\.O\.)?", party), party
            assert re.fullmatch(r"(TYTUŁ PRZELEWU \d{3})?", r["Opis"]), r["Opis"]
