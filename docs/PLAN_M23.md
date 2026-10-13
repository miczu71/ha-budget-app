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

## Wynik E0 (2026-10-13, kopia księgi z 2.10, kursy NBP A z api.nbp.pl)
- **API nie zna waluty oryginalnej:** `exchange_rate` = null, `transaction_amount` tylko w PLN. Wszystkie
  78 `orig_amount/orig_currency` w księdze pochodzą ze wzbogacenia z CSV karty (`csv_row`, status
  `enriched`). Bez okresowego importu CSV karty nowe transakcje walutowe nie mają kwoty oryginalnej.
- **Kwota z API ≈ kurs Visy:** mediana +0,33% ponad NBP A (zakres +0,04…+0,47%).
- **CSV pokazuje dodatkowe 2% na 28 z 78 transakcji** (wszystkie we wrześniu, przemieszane z
  transakcjami bez dopłaty z tych samych dni): CSV = kurs Visy + 2,0% ≈ +2,2–2,5% ponad NBP. API tych 2%
  nie pokazuje ani jako osobnej opłaty (karta ma w API 2 opłaty, razem −2,99 zł). Księga trzyma kwotę z
  API, więc **zaniża wydatki kartą o 54,90 zł** na tych 28 pozycjach (reguła L1: CSV tylko wzbogaca).
- **Historia:** karta ma dane dopiero od 2026-06-24. Wiersze CSV rachunku PLN od 2025-01 (karta debetowa)
  nie mają żadnej informacji o walucie, więc spreadu za 2025 nie da się policzyć.
- Wniosek: założenia „pełna historia” i „API wystarczy na bieżąco” nie są prawdziwe → decyzja usera.

## Decyzja po E0 (user, 2026-10-13)
CSV karty importowany raz w miesiącu (po zamknięciu cyklu) jest źródłem waluty oryginalnej i kwoty PLN
transakcji walutowych. E2 zmienione: zamiast backfillu 2025 (niemożliwy) — **kwota PLN z CSV wygrywa**
dla transakcji walutowych (`_enrich`; `ingest_api` nie nadpisuje jej, dopóki wiersz CSV jest powiązany —
`_fx_from_csv`). Ekran pokazuje pokrycie „dane do <ostatni import CSV karty>”. Historia od 06.2026.

## Wynik E2
Na kopii księgi z 2.10 przebudowa (`rebuild_derived`) poprawia 28 transakcji, suma karty −54,90 zł
(zgodnie z E0). Na produkcji poprawka zadziała przy pierwszej synchronizacji po wydaniu. Ograniczenie:
zmiana kwoty kasuje podział M29 transakcji (`_update_changed`), więc podział transakcji walutowej zrobiony
przed importem CSV karty znika przy imporcie — dzieli się ją po imporcie.

## Wynik E3
`hidden_costs.py`: `build(start, end)` (koszt per transakcja ze znakiem — zakupy i zwroty, `missing` bez
kursu), `months`, `csv_until`. Kopia księgi z 2.10 + kursy NBP pobrane na żywo: 78 transakcji walutowych,
0 bez kursu, przewalutowanie 113,55 zł przy wartości 12 291,46 zł wg NBP (średnio 0,9%; wrzesień
106,87 zł — transakcje z 2% prowizją), opłaty 22,79 zł, CSV karty do 2026-09-26. Kontrola ręczna
3 transakcji (kwota × kurs NBP z tabeli z dnia poprzedniego) zgodna co do grosza.

## Wynik E4
Ekran `/costs` (menu ⚙ „Koszty banku”, link w Wydatkach): suma roku, rozbicie (przewalutowanie, % ponad NBP, opłaty,
liczba płatności), miesiące z paskiem (miesiące po ostatnim CSV karty: „bez walut (brak CSV)”), lista płatności
w walutach (koszt, %, kwota · waluta · kurs NBP), lista opłat; nawigacja latami. Źródło czatu `costs` (rok bieżący,
miesiące, „znane do”; bez nazw sprzedawców do LLM). Sprawdzone w Playwright na kopii księgi: 360 i 1280 px, bez
przewijania poziomego, cele dotyku ≥ 44 px, konsola czysta, `/costs` 200 `no-store`.

## Simplify i code-review (przed 0.51.0)
- Simplify: rok czytany raz, miesiące grupowane w Pythonie; `fx.Rates` (jeden odczyt kursów); `money.dec` jako
  filtr; `IS_FX`; `money.CENT/ZERO`. Pominięte: kursy w tle przy imporcie (import rzadki, wynik od razu),
  pamięć nieudanych pobrań (EUR/CZK są w tabeli A).
- Code-review — poprawione: tylko kwoty w PLN (opłaty z rachunku EUR nie mieszają się z zł), `_fx_from_csv`
  zamiast „lepkiego” `orig_currency`, `fx.refresh` nie rzuca przy błędzie bazy, `pct` None przy kwocie
  walutowej 0, komunikat dla walut spoza tabeli A. Świadomie pominięte: `csv_until` dla kilku kart (jest jedna),
  blokowanie odpowiedzi importu przez NBP.
