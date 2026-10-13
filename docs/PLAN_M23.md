# M23 — Koszty ukryte (ha-budget-app)

## Context
Wywiad 2026-10-13 (grill-me). Cel: **tylko wiedza** — ile kosztuje bank poza ceną zakupów; bez
rekomendacji kart, bez alertów. Wynik zasila też czat (decyzja 24) i przyszłe M25 „Rok w liczbach”.

Decyzje z wywiadu:
1. Zakres = **spread walutowy** przy płatnościach kartą + **opłaty/prowizje** (`Kind.FEE`, `kinds.py`).
   Podwójne obciążenia → backlog. Wymiana PLN↔EUR między własnymi rachunkami — poza zakresem.
2. Kurs odniesienia = **NBP średni, tabela A** (api.nbp.pl), z dnia transakcji albo ostatni wcześniejszy
   dzień roboczy. Koszt = kwota PLN − kwota walutowa × kurs NBP (marża Visy + prowizja banku razem).
3. Historia **pełna** (CSV od 2025-01 + API od 2026-07).
4. Forma: **ekran „Koszty banku”** (suma rok / 12 mies., podział spread/opłaty, średni % spreadu,
   lista transakcji walutowych z kosztem) + **źródło czatu**. Bez encji i powiadomień.

Fakty z danych (kopia księgi z 2.10, tylko liczby): API ma `orig_amount/orig_currency` dla 78 płatności
(77 EUR, 1 CZK); wiersze CSV mają je puste, a opis jest już oczyszczony z sufiksu `[kwota WAL]` — źródłem
do uzupełnienia jest tabela `csv_row` (surowy plik ma ~142 linie walutowe). ROADMAP: kwota PLN zakupów
walutowych w CSV ≠ API (mediana ~2%) — nie wiadomo, która jest faktycznym obciążeniem.

## Repo / gałąź
`/config/addons/ha-budget-app` (`miczu71/ha-budget-app`), `main`. Pierwszy krok: wiersz M23 w
`docs/ROADMAP.md` + `docs/PLAN_M23.md` (ten plan), podwójne obciążenia dopisane do Backlogu.

## Etapy (commity; jedno wydanie 0.51.0 na koniec)
- **E0 — weryfikacja danych (bez kodu produkcyjnego):** na kopii księgi: (a) która kwota PLN (API czy CSV)
  składa się z saldem karty (`balance_after`/`balance_snapshot`) — to nią liczymy spread; jeśli API to
  kwota przed prowizją, spread z API byłby zaniżony → STOP i pytanie; (b) ile wierszy `csv_row` karty ma
  sufiks walutowy i czy mapują się 1:1 na `txn`. Wynik w `PLAN_M23.md` § E0.
- **E1 — kursy NBP:** migracja `fx_rate(currency, date, mid)`, moduł `fx.py`: pobranie zakresu
  (`/api/exchangerates/rates/A/{cur}/{start}/{end}/`, ≤ 93 dni na zapytanie), cache w bazie, fallback na
  ostatni dzień roboczy; dociąganie przy synchronizacji. TDD z nagranymi odpowiedziami NBP.
- **E2 — uzupełnienie CSV:** jednorazowa migracja/backfill `orig_amount/orig_currency` dla wierszy karty
  z CSV na podstawie `csv_row` (reużyć `_ORIG_RE`/`_card_description` z `csv_import.py`). Testy.
- **E3 — silnik `hidden_costs.py`:** koszt per transakcja walutowa (z uwzględnieniem podziału M29 i
  zwrotów `refund_of`), suma opłat `Kind.FEE`, agregaty rok/12 mies.; snapshot jak w M14. Testy.
- **E4 — ekran + czat:** `/costs` (link z Wydatków i z menu ⚙), styl Monarch wg `DESIGN.md` (skill
  `impeccable`), cache-busting `?v=`; rejestracja źródła w rejestrze czatu (M12 E3b). Weryfikacja
  Playwright 360/1280 px na kopii księgi.
- **Wydanie 0.51.0:** `simplify` → `code-review` → skill `release`; weryfikacja na żywo przez Ingress.

## Ryzyka
- Kwota API sprzed prowizji (E0) — zmienia metodę; staję i pytam.
- NBP: brak tabeli w święta → fallback; limit 93 dni → dzielenie zakresów.
- Dane prywatne: fixtures tylko z neutralnymi nazwami (hook pre-commit).
- Kopia `~/budget_dev/prod/ledger.db` prywatna — skasować po testach (zapis w pamięci).

## Weryfikacja (sukces)
- 3 losowe transakcje walutowe: koszt z ekranu = ręcznie (kwota × kurs NBP z api.nbp.pl) co do grosza.
- Suma opłat = suma `Kind.FEE` z filtra w Transakcjach za ten sam okres.
- Pokrycie: liczba transakcji walutowych w 2025 > 0 (backfill zadziałał), zgodna z E0.
- Czat: „ile zapłaciłem bankowi za przewalutowanie w tym roku?” = liczba z ekranu.
- Pełny zestaw testów zielony; na żywo stopka v0.51.0, `/costs` 200 `no-store`.
