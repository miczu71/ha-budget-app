"""Anonimizacja eksportu „Historia transakcji” z Millenetu do fixture'a testowego.

Zachowuje to, co ważne dla parsera: kodowanie (UTF-8 z BOM), CRLF, cytowanie wszystkich pól,
nagłówek, formaty dat i kwot, układ kolumn, puste pola, typy transakcji („Rodzaj transakcji”),
zawijanie opisów twardą spacją co 45 znaków, stałe szerokości pól opisu karty kredytowej.

Zamienia:
- numery rachunków/kart — spójnie (ten sam numer → ten sam fałszywy, przelewy własne się parują),
- strony i tytuły przelewów — pseudonimy („OSOBA TESTOWA nnn”, „FIRMA TESTOWA nnn SP. Z O.O.”),
- **lokalizacje**: ulice, kody pocztowe, miasta (opisy płatności kartą, odbiorcy BLIK/bankomaty,
  pole miasta karty kredytowej) → fikcyjne, spójnie,
- sprzedawców spoza listy sieci (lokalne punkty zdradzają okolicę) → pseudonim z zachowanym słowem
  rodzajowym („PIEKARNIA TESTOWA 007”); **nazwy sieci zostają** (testy reguł kategoryzacji),
- ciągi ≥ 4 cyfr; kwoty dostają jitter (znak zachowany), saldo przeliczane spójnie, daty (także
  data w opisie płatności kartą) przesunięte o stały offset.

Próbka: wszystkie typy transakcji, puste kwoty, a dla kart także zduplikowane bloki (eksport karty
kredytowej z kartą dodatkową zawiera te same transakcje pod dwoma numerami kart).

Użycie:
    python tools/anonymize_millenet.py WEJŚCIE.csv WYJŚCIE.csv [--per-type 6] [--seed 7]
    python tools/anonymize_millenet.py WEJŚCIE.csv WYJŚCIE.csv --check   # raport wycieków
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import random
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

ACCOUNT = "Numer rachunku/karty"
TX_DATE = "Data transakcji"
SETTLE_DATE = "Data rozliczenia"
KIND = "Rodzaj transakcji"
OTHER_ACC = "Na konto/Z konta"
PARTY = "Odbiorca/Zleceniodawca"
DESC = "Opis"
DEBIT = "Obciążenia"
CREDIT = "Uznania"
BALANCE = "Saldo"

NBSP = "\xa0"
WRAP = 45  # Millenet zawija opisy twardą spacją co 45 znaków
DATE_SHIFT = timedelta(days=-14)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
POSTCODE_RE = re.compile(r"\b\d{2}-\d{3}\b")
EMAIL_RE = re.compile(r"[\w.%+-]+@[\w.-]+\.\w+")
EMAIL_PLACEHOLDER = "osoba@example.com"  # domena zarezerwowana (RFC 2606)
STREET_RE = re.compile(r"^(UL|AL|OS|PL|ULICA|ALEJA|RONDO)\b\.?", re.IGNORECASE)

COMPANY_MARKERS = re.compile(
    r"\b(SP\.? ?Z ?O\.? ?O|S\.? ?A\.?$|S\.A\.|SPÓŁKA|SPOLKA|SP\. ?J|SP\. ?K|BANK|"
    r"URZĄD|URZAD|ZUS|GMINA|FUNDACJA|STOWARZYSZENIE|SKLEP|ALLEGRO|TAURON|PGE|ORANGE|"
    r"PLAY|PLUS|T-MOBILE|NETFLIX|SPOTIFY|GOOGLE|APPLE|PAYU|PRZELEWY24|TPAY)\b",
    re.IGNORECASE,
)
# Typy, w których „Opis” to tytuł przelewu wpisany przez człowieka (może zawierać dane osobowe)
FREE_TEXT_KINDS = re.compile(r"PRZELEW|ZLECENIE|POLECENIE|^$")

# Sieci i marki ogólnopolskie/międzynarodowe — nazwy zostają (nie wskazują miejsca)
CHAINS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pattern), name)
    for pattern, name in (
        (r"BIEDRONKA", "BIEDRONKA"),
        (r"\bLIDL\b", "LIDL"),
        (r"\bZABKA\b", "ZABKA"),
        (r"KAUFLAND", "KAUFLAND"),
        (r"AUCHAN", "AUCHAN"),
        (r"CARREFOUR", "CARREFOUR"),
        (r"\bDINO\b", "DINO"),
        (r"\bNETTO\b", "NETTO"),
        (r"STOKROTKA", "STOKROTKA"),
        (r"\bALDI\b", "ALDI"),
        (r"ROSSMANN", "ROSSMANN"),
        (r"\bHEBE\b", "HEBE"),
        (r"SUPER-?PHARM", "SUPER-PHARM"),
        (r"\bDOZ\b", "DOZ"),
        (r"\bZIKO\b", "ZIKO"),
        (r"ORLEN", "ORLEN"),
        (r"\bBP\b", "BP"),
        (r"\bSHELL\b", "SHELL"),
        (r"CIRCLE ?K", "CIRCLE K"),
        (r"\bMOYA\b", "MOYA"),
        (r"\bAMIC\b", "AMIC"),
        (r"\bENI\b", "ENI"),
        (r"\bESSO\b", "ESSO"),
        (r"\bIKEA\b", "IKEA"),
        (r"CASTORAMA", "CASTORAMA"),
        (r"LEROY", "LEROY MERLIN"),
        (r"\bOBI\b", "OBI"),
        (r"PEPCO", "PEPCO"),
        (r"\bACTION\b", "ACTION"),
        (r"\bJYSK\b", "JYSK"),
        (r"MEDIA ?EXPERT", "MEDIA EXPERT"),
        (r"RTV ?EURO", "RTV EURO AGD"),
        (r"MEDIA ?MARKT", "MEDIA MARKT"),
        (r"X-?KOM", "X-KOM"),
        (r"ZALANDO", "ZALANDO"),
        (r"ALLEGRO", "ALLEGRO"),
        (r"AMZN|AMAZON", "AMAZON"),
        (r"ALIEXPRESS", "ALIEXPRESS"),
        (r"\bTEMU\b", "TEMU"),
        (r"\bSHEIN\b", "SHEIN"),
        (r"\bEMPIK\b", "EMPIK"),
        (r"DECATHLON", "DECATHLON"),
        (r"\bH ?& ?M\b", "H&M"),
        (r"RESERVED", "RESERVED"),
        (r"SINSAY", "SINSAY"),
        (r"\bCCC\b", "CCC"),
        (r"NETFLIX", "NETFLIX"),
        (r"SPOTIFY", "SPOTIFY"),
        (r"GOOGLE", "GOOGLE"),
        (r"\bAPPLE\b", "APPLE"),
        (r"MICROSOFT", "MICROSOFT"),
        (r"NABU CASA", "NABU CASA"),
        (r"SKYSHOWTIME", "SKYSHOWTIME"),
        (r"DISNEY", "DISNEY"),
        (r"\bHBO\b", "HBO"),
        (r"YOUTUBE", "YOUTUBE"),
        (r"MCDONALD", "MCDONALDS"),
        (r"\bKFC\b", "KFC"),
        (r"STARBUCKS", "STARBUCKS"),
        (r"\bUBER\b", "UBER"),
        (r"\bBOLT\b", "BOLT"),
        (r"\bGLOVO\b", "GLOVO"),
        (r"\bWOLT\b", "WOLT"),
        (r"PYSZNE", "PYSZNE.PL"),
        (r"INPOST", "INPOST"),
        (r"TAURON", "TAURON"),
        (r"\bPGE\b", "PGE"),
        (r"\bORANGE\b", "ORANGE"),
        (r"T-?MOBILE", "T-MOBILE"),
        (r"\bPZU\b", "PZU"),
        (r"UNIQA", "UNIQA"),
        (r"ALLIANZ", "ALLIANZ"),
        (r"INTERRISK", "INTERRISK"),
        (r"BOOKING", "BOOKING.COM"),
        (r"AIRBNB", "AIRBNB"),
        (r"RYANAIR", "RYANAIR"),
        (r"\bWIZZ", "WIZZ AIR"),
        (r"MIGROS", "MIGROS"),
        (r"\bREWE\b", "REWE"),
        (r"\bSPAR\b", "SPAR"),
        (r"\bCOOP\b", "COOP"),
        (r"EURONET", "EURONET"),
        (r"\bMPK\b", "MPK"),
        (r"JAKDOJADE", "JAKDOJADE"),
        (r"INTERCITY|\bPKP\b", "PKP INTERCITY"),
        (r"GEMINI", "GEMINI"),
        (r"MEDICOVER", "MEDICOVER"),
        (r"LUX ?MED", "LUX MED"),
        (r"BOOKSY", "BOOKSY"),
        (r"FITSSEY", "FITSSEY"),
        (r"PAYPAL", "PAYPAL"),
        (r"\bSUMUP\b", "SUMUP"),
        (r"BONPRIX", "BONPRIX"),
        (r"OPENAI|CHATGPT", "OPENAI"),
        (r"ANTHROPIC|CLAUDE\.AI", "ANTHROPIC"),
        (r"\bADOBE\b", "ADOBE"),
        (r"DROPBOX", "DROPBOX"),
        (r"\bCANVA\b", "CANVA"),
        (r"GITHUB", "GITHUB"),
        (r"PATREON", "PATREON"),
        (r"\bSTEAM", "STEAM"),
        (r"PLAYSTATION|\bSONY\b", "PLAYSTATION"),
        (r"NINTENDO", "NINTENDO"),
        (r"\bXBOX\b", "XBOX"),
        (r"AUDIBLE", "AUDIBLE"),
        (r"STORYTEL", "STORYTEL"),
        (r"LEGIMI", "LEGIMI"),
        (r"\bTIDAL\b", "TIDAL"),
        (r"DUOLINGO", "DUOLINGO"),
        (r"\bZOOM\b", "ZOOM"),
        (r"NORDVPN|EXPRESSVPN|PROTON", "VPN"),
        (r"HETZNER", "HETZNER"),
        (r"CLOUDFLARE", "CLOUDFLARE"),
        (r"\bPADDLE\b", "PADDLE"),
        (r"\bMETA\b|FACEBK|FACEBOOK", "META"),
    )
]
# Pośrednicy płatności w polu odbiorcy BLIK — zostają
PROCESSORS = re.compile(
    r"^(PAYU( S\.?A\.?)?|PAYPRO S\.?A\.?|AUTOPAY S\.?A\.?|PAYNOW|PRZELEWY24|TPAY|BLIK|STRIPE|"
    r"ADYEN|DOTPAY|IMOJE|ESPAGO|PAYPAL)$"
)
# Słowa rodzajowe — zostają w pseudonimie lokalnego punktu (przydatne do testów reguł)
GENERIC = (
    "RESTAURACJA",
    "RISTORANTE",
    "TRATTORIA",
    "OSTERIA",
    "PIZZERIA",
    "PIEKARNIA",
    "CUKIERNIA",
    "DELIKATESY",
    "APTEKA",
    "KAWIARNIA",
    "CAFE",
    "BAR",
    "BISTRO",
    "HOTEL",
    "SKLEP",
    "MARKET",
    "KWIACIARNIA",
    "LODY",
    "PARKING",
    "KINO",
    "MUZEUM",
    "BASEN",
    "FRYZJER",
    "SALON",
    "KEBAB",
    "SUSHI",
    "DROGERIA",
    "OPTYK",
    "WETERYNARZ",
    "GABINET",
    "PRZYCHODNIA",
    "STACJA",
    "MYJNIA",
    "BANKOMAT",
)
FAKE_CITIES = ("TESTOWO", "PRZYKLADOWO", "FIKCYJNE", "WYMYSLONE", "ZMYSLONE")


def fold(text: str) -> str:
    """Wielkie litery bez polskich znaków i twardych spacji — do porównań."""
    text = text.replace("ł", "l").replace("Ł", "L").replace(NBSP, " ")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text.upper()).strip()


def mask_emails(text: str) -> str:
    """Adresy e-mail → placeholder; zawijanie (twarde spacje) nie ukrywa adresu przed wykryciem."""
    flat = text.replace(NBSP, "")
    return wrap(EMAIL_RE.sub(EMAIL_PLACEHOLDER, flat)) if EMAIL_RE.search(flat) else text


def unwrap(parts: list[str]) -> str:
    """Odwraca zawijanie Millenetu: segment 44-znakowy zjadł spację, 45-znakowy — nic."""
    out = ""
    for part in parts[:-1]:
        out += part + (" " if len(part) == WRAP - 1 else "")
    return out + parts[-1]


def wrap(text: str) -> str:
    segments = []
    while len(text) > WRAP:
        if text[WRAP - 1] == " ":
            segments.append(text[: WRAP - 1])
        else:
            segments.append(text[:WRAP])
        text = text[WRAP:]
    segments.append(text)
    return NBSP.join(segments)


class Anonymizer:
    def __init__(self, seed: int) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.numbers: dict[str, str] = {}
        self.people: dict[str, str] = {}
        self.merchants: dict[str, str] = {}
        self.cities: dict[str, str] = {}

    def number(self, value: str) -> str:
        """Fałszywy numer o tym samym kształcie (spacje, litery, gwiazdki zostają)."""
        if not value.strip():
            return value
        key = re.sub(r"\D", "", value)
        if key not in self.numbers:
            self.numbers[key] = "".join(str(self.rng.randint(0, 9)) for _ in key)
        digits = iter(self.numbers[key])
        return re.sub(r"\d", lambda _: next(digits), value)

    def person_or_company(self, value: str) -> str:
        """Strona przelewu (osoba albo firma, np. pracodawca z adresem) → zawsze pseudonim."""
        if not value.strip():
            return value
        key = value.strip().upper()
        if key not in self.people:
            n = len(self.people) + 1
            company = COMPANY_MARKERS.search(value)
            self.people[key] = (
                f"FIRMA TESTOWA {n:03d} SP. Z O.O." if company else (f"OSOBA TESTOWA {n:03d}")
            )
        return self.people[key]

    def city(self, value: str) -> str:
        key = fold(value)
        if not key:
            return FAKE_CITIES[0]
        if key not in self.cities:
            i = len(self.cities)
            suffix = f" {i // len(FAKE_CITIES) + 1}" if i >= len(FAKE_CITIES) else ""
            self.cities[key] = FAKE_CITIES[i % len(FAKE_CITIES)] + suffix
        return self.cities[key]

    def merchant(self, text: str) -> str:
        """Sieć → jej nazwa; lokalny punkt → pseudonim ze słowem rodzajowym (spójnie)."""
        folded = fold(text)
        for pattern, name in CHAINS:
            if pattern.search(folded):
                return f"BANKOMAT {name}" if "BANKOMAT" in folded and name != "BANKOMAT" else name
        tokens = re.findall(r"[A-Z]+", folded)
        key = " ".join(tokens[:2]) or folded
        if key not in self.merchants:
            n = len(self.merchants) + 1
            generic = next((t for t in tokens[:3] if t in GENERIC), None)
            self.merchants[key] = (
                f"{generic} TESTOWA {n:03d}" if generic else (f"SKLEP TESTOWY {n:03d}")
            )
        return self.merchants[key]

    def street(self, key: str) -> str:
        """Fikcyjna ulica, deterministyczna dla tego samego oryginału (bliźniacze transakcje
        zostają identyczne)."""
        digest = hashlib.sha256(f"{self.seed}|{fold(key)}".encode()).digest()
        return f"UL. TESTOWA {digest[0] % 99 + 1}"

    def digits(self, value: str) -> str:
        """Ciągi ≥ 4 cyfr (numery kart, telefonów, faktur, referencji) → losowe cyfry."""
        return re.sub(
            r"\d{4,}", lambda m: "".join(str(self.rng.randint(0, 9)) for _ in m.group()), value
        )

    def scrub(self, value: str) -> str:
        return POSTCODE_RE.sub("00-000", self.digits(value))

    def amount(self, value: str, salt: str) -> str:
        """Jitter ±30% deterministyczny względem oryginalnego wiersza (`salt`) — identyczne
        wiersze (duplikaty karty dodatkowej) pozostają identyczne, więc fixture testuje dedup."""
        if not value:
            return value
        digest = hashlib.sha256(f"{self.seed}|{salt}|{value}".encode()).digest()
        factor = Decimal(str(round(0.7 + 0.6 * int.from_bytes(digest[:4]) / 2**32, 3)))
        out = (Decimal(value) * factor).quantize(Decimal("0.01"))
        if out == 0:
            out = Decimal("0.01").copy_sign(Decimal(value))
        return str(out)

    # --- pola z lokalizacją ---------------------------------------------------------------

    def card_purchase_desc(self, value: str) -> str:
        """Opis płatności kartą na rachunku: „SPRZEDAWCA ULICA MIASTO KRAJ⍽RRRR-MM-DD”,
        zawinięty co 45 znaków — sprzedawca/ulica/miasto → fikcyjne, kraj zostaje, data
        przesunięta."""
        parts = value.split(NBSP)
        tx_date = _shift(parts.pop()) if len(parts) > 1 and DATE_RE.fullmatch(parts[-1]) else None
        body = unwrap(parts)
        m = re.search(r"\s([A-Z]{3})$", body)
        country = m.group(1) if m else None
        core = body[: m.start()] if m else body
        words = core.split()
        city = self.city(words[-1] if len(words) > 1 else "")
        new = f"{self.merchant(core)} {self.street(core)} {city}" + (
            f" {country}" if country else ""
        )
        return wrap(new) + (NBSP + tx_date if tx_date else "")

    def merchant_party(self, value: str) -> str:
        """Odbiorca przy BLIK/bankomacie: „nazwa⍽pośrednik⍽ulica⍽kod miasto”."""
        out = []
        for segment in value.split(NBSP):
            text = segment.strip()
            if not text:
                out.append(segment)
            elif POSTCODE_RE.search(text):
                out.append(f"00-000 {self.city(POSTCODE_RE.split(text)[-1]).title()}")
            elif STREET_RE.match(text) or re.search(r"\d", text):
                out.append(self.street(text).title())
            elif PROCESSORS.match(fold(text)):
                out.append(segment)
            elif "." in text and " " not in text and any(p.search(fold(text)) for p, _ in CHAINS):
                out.append(segment)  # domena sieci (np. zalando.pl) zostaje
            else:
                out.append(self.merchant(text))
        return NBSP.join(out)

    def credit_card_desc(self, value: str) -> str:
        """Opis z eksportu karty kredytowej: pola o stałej szerokości „SPRZEDAWCA(25),
        MIASTO(14), kod kraju [kwota waluta]”."""
        fields = value.split(",")
        if len(fields) < 3:
            return self.scrub(value)
        merchant_w, city_w = len(fields[0]), len(fields[1])
        merchant = self.merchant(fields[0]).ljust(merchant_w)[:merchant_w]
        city = (" " + self.city(fields[1])).ljust(city_w)[:city_w]
        return ",".join([merchant, city, *fields[2:]])


def _shift(value: str) -> str:
    return (date.fromisoformat(value) + DATE_SHIFT).isoformat() if value else value


def _is_card_account(row: dict[str, str]) -> bool:
    return len(re.sub(r"\D", "", row[ACCOUNT])) != 26


def _sample(rows: list[dict[str, str]], per_type: int, rng: random.Random) -> list[dict[str, str]]:
    """Po `per_type` wierszy każdego (konto-typ, Rodzaj transakcji) + przypadki brzegowe."""
    groups: dict[tuple[bool, str], list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        groups[(_is_card_account(r), r[KIND])].append(i)
    chosen: set[int] = set()
    for idx in groups.values():
        chosen.update(rng.sample(idx, min(per_type, len(idx))))
    chosen.update(i for i, r in enumerate(rows) if not r[DEBIT] and not r[CREDIT])
    # Duplikaty kart: dla wybranych wierszy kart dobierz identyczne wiersze spod drugiego numeru
    sig = lambda r: (r[TX_DATE], r[SETTLE_DATE], r[DEBIT], r[CREDIT], r[DESC])  # noqa: E731
    wanted = {sig(rows[i]) for i in chosen if _is_card_account(rows[i])}
    chosen.update(i for i, r in enumerate(rows) if _is_card_account(r) and sig(r) in wanted)
    return [rows[i] for i in sorted(chosen)]


def _recompute_balances(rows: list[dict[str, str]], rng: random.Random) -> None:
    """Saldo spójne z (zanonimizowanymi) kwotami; wiersze są od najnowszych, per rachunek."""
    by_account: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_account[r[ACCOUNT]].append(r)
    for acc_rows in by_account.values():
        if not any(r[BALANCE] for r in acc_rows):
            continue  # karty nie mają salda w eksporcie
        balance = Decimal(rng.randint(3000, 15000)).quantize(Decimal("0.01"))
        for r in acc_rows:  # od najnowszego: saldo po transakcji, potem cofamy
            r[BALANCE] = str(balance)
            balance -= Decimal(r[CREDIT] or r[DEBIT] or "0")


def _read(src: bytes) -> tuple[bool, str, list[str], list[dict[str, str]]]:
    bom = src.startswith(b"\xef\xbb\xbf")
    text = src.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text[:2000] else "\n"
    reader = csv.DictReader(io.StringIO(text, newline=""))
    return bom, newline, list(reader.fieldnames or []), list(reader)


def anonymize(src: bytes, per_type: int, seed: int) -> bytes:
    bom, newline, fields, rows = _read(src)
    anon = Anonymizer(seed)
    out_rows = []
    for r in _sample(rows, per_type, anon.rng):
        salt = "|".join((r[TX_DATE], r[SETTLE_DATE], r[DESC], r[PARTY]))
        r = dict(r)
        r[ACCOUNT] = anon.number(r[ACCOUNT])
        r[OTHER_ACC] = anon.number(r[OTHER_ACC])
        r[TX_DATE] = _shift(r[TX_DATE])
        r[SETTLE_DATE] = _shift(r[SETTLE_DATE])
        if _is_card_account(r):
            r[DESC] = anon.credit_card_desc(r[DESC])
            r[PARTY] = anon.merchant_party(r[PARTY]) if r[PARTY] else r[PARTY]
        elif FREE_TEXT_KINDS.search(r[KIND]):
            r[PARTY] = anon.person_or_company(r[PARTY])
            r[DESC] = f"TYTUŁ PRZELEWU {anon.rng.randint(100, 999)}" if r[DESC].strip() else ""
        else:
            r[PARTY] = anon.merchant_party(r[PARTY]) if r[PARTY] else r[PARTY]
            if re.search(NBSP + r"\d{4}-\d{2}-\d{2}$", r[DESC]):
                r[DESC] = anon.card_purchase_desc(r[DESC])
            else:
                r[DESC] = anon.scrub(r[DESC])
        r[DEBIT] = anon.amount(r[DEBIT], salt)
        r[CREDIT] = anon.amount(r[CREDIT], salt)
        r[DESC], r[PARTY] = mask_emails(r[DESC]), mask_emails(r[PARTY])
        out_rows.append(r)
    _recompute_balances(out_rows, anon.rng)

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields, quoting=csv.QUOTE_ALL, lineterminator=newline)
    writer.writeheader()
    writer.writerows(out_rows)
    return (b"\xef\xbb\xbf" if bom else b"") + buf.getvalue().encode("utf-8")


# --- kontrola wycieków -----------------------------------------------------------------------


def _location_tokens(rows: Iterable[dict[str, str]]) -> dict[str, set[str]]:
    """Wrażliwe fragmenty oryginału pogrupowane w kategorie (do sprawdzenia w wyniku)."""
    found: dict[str, set[str]] = defaultdict(set)
    chains = [p for p, _ in CHAINS]
    for r in rows:
        for number in (r[ACCOUNT], r[OTHER_ACC]):
            if len(re.sub(r"\D", "", number)) >= 8:
                found["numer"].add(re.sub(r"\D", "", number))
        if FREE_TEXT_KINDS.search(r[KIND]) and not _is_card_account(r) and r[PARTY].strip():
            found["strona przelewu"].add(fold(r[PARTY].split(NBSP)[0]))
        for text in (r[DESC], r[PARTY]):
            folded = fold(text)
            found["e-mail"].update(fold(m) for m in EMAIL_RE.findall(text.replace(NBSP, "")))
            found["kod pocztowy"].update(POSTCODE_RE.findall(text))
            # bez „PL” — myli się z domenami .pl (np. „…PL PAYPRO”)
            for street in re.findall(r"\b(?:UL|AL|OS)\b\.? ?([A-Z]{4,})", folded):
                found["ulica"].add(street)
        if _is_card_account(r) and r[DESC].count(",") >= 2:
            found["miasto"].add(fold(r[DESC].split(",")[1]))
            merchant = fold(r[DESC].split(",")[0])
            if not any(p.search(merchant) for p in chains):
                found["lokalny sprzedawca"].add(" ".join(merchant.split()[:2]))
        m = re.search(NBSP + r"\d{4}-\d{2}-\d{2}$", r[DESC])
        if m and not FREE_TEXT_KINDS.search(r[KIND]):
            body = fold(unwrap(r[DESC][: m.start()].split(NBSP)))
            words = re.sub(r"\s[A-Z]{3}$", "", body).split()
            if len(words) > 1:
                found["miasto"].add(words[-1])
            if not any(p.search(body) for p in chains):
                found["lokalny sprzedawca"].add(" ".join(words[:2]))
    ignore = set(GENERIC) | {name for _, name in CHAINS} | set(FAKE_CITIES)
    return {
        k: {v for v in vs if len(v) >= 4 and v not in ignore and not v.startswith("TESTOW")}
        for k, vs in found.items()
    }


def leak_report(original: bytes, anonymized: bytes) -> Counter[str]:
    """Ile wrażliwych fragmentów oryginału (z całego pliku) występuje w wyniku — wg kategorii."""
    _, _, _, rows = _read(original)
    out = fold(anonymized.decode("utf-8-sig"))
    out_flat = fold(anonymized.decode("utf-8-sig").replace(NBSP, ""))  # adres przecięty zawijaniem
    out_digits = re.sub(r"\D", "", out)
    leaks: Counter[str] = Counter()
    for category, values in _location_tokens(rows).items():
        for value in values:
            if category == "numer":
                hit = value in out_digits
            else:  # całe słowa — „MIASTO” w „NATYCHMIASTOWY” to nie wyciek
                text = out_flat if category == "e-mail" else out
                hit = (
                    re.search(rf"(?<![A-Z0-9]){re.escape(fold(value))}(?![A-Z0-9])", text)
                    is not None
                )
            leaks[category] += hit
    return +leaks  # tylko kategorie z wyciekiem


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("src", type=Path)
    p.add_argument("dst", type=Path)
    p.add_argument("--per-type", type=int, default=6)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--check", action="store_true", help="raport wycieków (same liczby)")
    args = p.parse_args()
    src = args.src.read_bytes()
    out = anonymize(src, args.per_type, args.seed)
    args.dst.write_bytes(out)
    if args.check:
        report = leak_report(src, out)
        print("wycieki:", dict(report) if report else "brak")


if __name__ == "__main__":
    main()
