# Plan M2 — Rdzeń danych: jedna księga bez duplikatów

Zakres i kryteria akceptacji: [`ROADMAP.md`](ROADMAP.md#m2--rdzeń-danych-jedna-księga-bez-duplikatów).
Plan zaakceptowany 2026-10-01; start najwcześniej 2026-10-02 (drugi zrzut API).

## Pliki (`budget/app/src/budget/`)

| Plik | Odpowiedzialność |
|---|---|
| `kinds.py` | Taksonomia typów: 26 wartości „Rodzaj transakcji” z CSV → supertypy (karta, zwrot, BLIK zakup/P2P, przelew, zlecenie, gotówka, kredyt, spłata karty, opłata); heurystyka typu z pól API |
| `normalize.py` | `fold()` (wielkie litery, bez diakrytyków/NBSP), opis do odcisku, klucz sprzedawcy (pierwsze znaczące tokeny) |
| `money.py` | Parsowanie/formatowanie `Decimal`, kwota ze znakiem |
| `csv_import.py` | Parser Millenetu: BOM, CRLF, QUOTE_ALL, odwijanie opisów (segment 44 = zjedzona spacja, 45 = nic), pola karty o stałej szerokości, waluta oryginalna, data transakcji z opisu |
| `eb_ingest.py` | `Transaction` z API → wspólny model + typ heurystyczny |
| `ledger.py` | Proces wczytywania: konta/aliasy, L0–L4, uzgadnianie salda, raport |
| `storage/db.py`, `storage/migrations/001_core.sql` | SQLite, migracje, `PRAGMA user_version` |
| `cli.py` | `ingest-csv FILE`, `ingest-eb [--dumps DIR \| --live --days N]`, `report` (same liczby) |

## Schemat (`001_core.sql`)

- `account(id, kind[current|card|fx|savings|other], iban UNIQUE, currency, product, display_name, include_in_budget, created_at)`
- `account_alias(source[eb_hash|eb_uid|csv_number], value, account_id)` — PK (source, value)
- `txn(id, account_id, status, booking_date, value_date, tx_date, amount TEXT, currency, orig_amount, orig_currency, description, counterparty_name, counterparty_account, kind, kind_source, balance_after, fingerprint, transfer_group, refund_of, budget_flag, source, raw_json, first_seen_at, updated_at)`; indeksy (account_id, booking_date), (account_id, fingerprint)
- `txn_ref(account_id, source, ref, txn_id, batch_id)` — PK (account_id, source, ref)
- `import_batch`, `unmatched_csv`, `balance_snapshot`, `eb_session`, `sync_log`
- Kwoty wyłącznie jako tekst; sumy w Pythonie (`Decimal`), nigdy `SUM()` w SQL.

## Algorytm

1. **API:** dopasowanie po `entry_reference` (i `transaction_id`, jeśli jest) → inaczej odcisk
   (konto, data, kwota, opis znormalizowany) + numer wystąpienia w obrębie dnia → inaczej nowa
   transakcja. Przenumerowany `entry_reference` dopisywany jako alias.
2. **CSV:**
   - L0: wiersze karty pod różnymi numerami kart liczone jako max(liczności), nie suma.
   - Numer karty → konto karty automatycznie (≥ 3 zgodne transakcje z API), inaczej flaga CLI.
   - L1: wiersze sprzed najstarszej transakcji API konta → wstawiane; nowsze tylko wzbogacają
     (typ, konto kontrahenta, waluta oryginalna): rachunek dokładnie (data, kwota), karta
     dokładnie lub rozmyto tylko przy walucie obcej (sprzedawca, ±5 dni, kwota ±5%).
     Bez pary → `unmatched_csv` + raport.
   - Kolejność importów obojętna: API po CSV scala się z wierszami CSV (kwota i daty z API).
3. **L2 przelewy:** DBIT konto A ↔ CRDT konto B (podlinkowane), ta sama kwota, ≤ 3 dni; sygnały:
   pusty opis, typ spłaty karty, „WCZESN.SPL”, własny IBAN. Strona bez pary z silnym sygnałem
   też oznaczana jako przelew.
4. **L3 zwroty:** zwrot → zakup u tego samego sprzedawcy ≤ 90 dni, kwota ≤ zakupu.
5. **L4 PDNG→BOOK** jak w SPEC.
6. **Uzgodnienie salda:** ciągłość `balance_after` z CSV; saldo z API (ITBD) cofnięte o transakcje
   późniejsze vs `balance_after` z CSV → rozbieżność = brak/duplikat → raport.

## Testy

Dane syntetyczne, `tests/fixtures/millenet_sample.csv`, fixture'y Mock ASPSP (obie strony
przelewów własnych). Przypadki: odwijanie opisów, pola karty, L0 duplikaty karty, bliźniaki,
idempotencja ponownego importu, symulacja przenumerowania `entry_reference`, L1 dokładne
i rozmyte, kolejność CSV→API i API→CSV, L2 pary i strona bez pary, L3, uzgodnienie salda,
migracje.

## Weryfikacja na prawdziwych danych (lokalnie, raport = liczby)

Drugi zrzut API (stabilność `entry_reference`); import CSV + zrzutów: zdublowany blok karty
usunięty, 370/370 w oknie wspólnym, 7/7 spłat sparowanych, 0 przerw salda, ponowny import = 0 zmian.

## Kolejność kroków

1. `kinds`, `normalize`, `money` + testy → 2. parser CSV → 3. schemat i migracje →
4. ingest API → 5. ingest CSV (L0, L1) → 6. L2, L3 → 7. uzgodnienie, raport, CLI →
8. przebieg na prawdziwych danych → checkpoint.

## Ryzyka

- Rozmyte dopasowanie karty → fałszywa para: tylko waluta obca + zgodny sprzedawca.
- Limit PSD2 (4 zapytania/konto/dobę): praca głównie na zapisanych zrzutach.
