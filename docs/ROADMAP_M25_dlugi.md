# Budżet: długi z ryzykiem błędu + M25 „Rok w liczbach” (0.72.0)

## Context
Po 0.71.0 roadmapa budżetu jest pusta. Otwarte zostały dwie rzeczy: pomysł M25 (podsumowanie roku, naturalny termin
koniec 2026) i drobne długi nieblokujące z wydań 0.68.1–0.71.0. User wybrał: zamykamy długi z ryzykiem błędu
(kosmetykę świadomie odpisujemy), potem M25 jako osobny ekran z wyborem roku, wszystkie 4 bloki, powiadomienie 1.01,
zakładka zawsze widoczna, bez źródła dla czatu AI.

Wywiad (2026-11-02):
- **Kto korzysta:** user w panelu (telefon i komputer) i grupa domowników (powiadomienie 1.01).
- **Automatycznie:** ekran liczy się na żądanie z księgi; 1.01 o 7:00 powiadomienie za poprzedni rok; prognoza
  przestaje liczyć podejrzaną nadpłatę karty i pokazuje dzwonek.
- **Za zgodą / ręcznie:** poprawka limitu karty w ustawieniach robi user; nic nie pisze do banku ani do HA poza
  istniejącymi encjami.
- **Sukces:** `/recap?year=2026` pokazuje sumy roku, r/r do tego samego okresu 2025, top zmiany kategorii, sprzedawców
  i rekordy; 2025 bez bloków r/r (brak danych 2024); fałszywa nadpłata nie trafia do prognozy; wydanie 0.72.0 na żywo.

Repo `/config/addons/ha-budget-app` (PUBLIC), gałąź `main`, wersja 0.71.0 → **0.72.0** (jedno wydanie na koniec).
Dane w bazie od 2.01.2025.

## Etapy
Pierwszy krok implementacji: ten plan → `docs/ROADMAP_M25_dlugi.md`, wiersz M25 w `docs/ROADMAP.md` („w realizacji”),
plany etapów `docs/PLAN_M25_E1.md` … `E4.md` z sekcją **Wykonawca** (pliki, zmiana, test, DONE, NIE RÓB).
Każdy etap: TDD, `uv run pytest -q`, ruff, mypy, commit; worker w `wt new` → claimcheck → `verifier`; potem `stage-end`.

### E1: długi z ryzykiem błędu (ryzyko: pieniądze → `sonnet-worker`)
- **Podejrzana nadpłata karty** (`card.py:263` `debt_from`, `forecast.py:211-221`): nadpłata (`limit − ITAV < 0`) większa
  niż suma wpływów na konto karty z ostatnich 35 dni → prognoza bierze 0 i ustawia flagę `suspect_limit`
  (limit, ITAV). Dzwonek (centrum powiadomień M5b): „Sprawdź limit karty: ustawiony X zł, bank pokazuje dostępne Y zł”
  z linkiem do ustawień karty. Testy: realna nadpłata (zwrot) liczona; nadpłata bez wpływów → 0 + flaga + karta dzwonka.
- **Wiek ITAV** (`forecast.py:221`): do `fetched` dochodzi `fetched_at` odczytu ITAV (starszy z dwóch).
- **Test publishera** (`tests/test_ha.py:157`): ujemne `card_debt`/`forecast_card_debt` publikowane jako ujemne.
- **Test `_analyze`** (`ledger.py:737-743`): transakcja `interest` nie trafia do analizy (mutacja warunku → test czerwony).
- **Komentarz** `web/charts.py:26`: usunąć nieistniejący klucz `txn-<id>` (dług „duplikat klucza” = nieaktualny).
- **Odpisane w ROADMAP (nie naprawiamy):** migracja 030 LIKE (już wykonana; klasyfikator `kinds.py:100` używa `fold`),
  reguła usera nie przebija typu `interest` (decyzja E1 odsetek), kolory drill indeksowane, strzałki Unicode, `merchants`/
  `purchases` czytają cały miesiąc, link `q` to wyszukiwanie tekstowe, poz. 2 środek netto vs wycinki dodatnie,
  prognoza liczona przy każdym kliknięciu drill.
- Rollback: `git revert` commita E1.

### E2: silnik `recap.py` (bez UI, `haiku-worker`; REJECT → `sonnet-worker`)
Nowy moduł `budget/app/src/budget/recap.py`, funkcja `build(conn, year, today) -> Recap`, reużywa:
`spending.sums/totals/monthly_totals/_rows/_merchant_group`, `savings.monthly_rates`, `flex.spent_between`, `taxonomy.leaves`.
- Zakres: rok zamknięty = 1.01–31.12; rok bieżący = 1.01–dziś, porównanie z tym samym zakresem rok wcześniej.
  Brak danych za rok porównawczy (pierwszy dzień danych > początek zakresu) → `prev = None`, bloki r/r puste.
- **Wpływy vs wydatki:** sumy wg `spending.totals` (bez oszczędności/wyłączonych), r/r w zł i %, 12 miesięcy
  (`MonthTotals`), średnia stopa oszczędności roku (Σsaved/Σincome z `monthly_rates`), najlepszy/najgorszy miesiąc stopy.
- **Zmiany kategorii r/r:** kategorie główne, top 5 wzrostów i top 5 spadków, próg |Δ| ≥ 200 zł.
- **Sprzedawcy roku:** top 10 wydatków PLN wg `_merchant_group` (suma, liczba transakcji, średnio), części podziału = jedna.
  `spending.merchants` uogólnione: `leaf_id: int | None` (None = wszystkie kategorie wydatków poza oszczędnościami/wyłączonymi).
- **Rekordy:** największy pojedynczy wydatek, najdroższy miesiąc, najdroższy dzień, najdłuższa seria dni bez wydatków
  elastycznych, największy wpływ.
- Testy `tests/test_recap.py` na syntetycznej księdze (rok bieżący/zamknięty, brak roku poprzedniego, podział M29, zwroty).
- Rollback: `git revert` (nowy moduł, bez migracji).

### E3: ekran `/recap?year=` (`impeccable`, robię sam albo `haiku-worker` wg planu)
- `web/routes_recap.py` (router w `web/app.py:114-117`), `templates/recap.html`, zakładka `"recap": Tab("Rok w liczbach",
  "/recap", ...)` w `nav_layout.py:18` (domyślnie widoczna; edytor M28 bez zmian).
- Wybór roku: lata z danymi, domyślnie bieżący (w styczniu — poprzedni); niepoprawny `year` → domyślny.
- Wykres 12 miesięcy wpływy/wydatki z istniejących wykresów słupkowych Podsumowania; zmiany kategorii linkują do
  `/transactions` z zakresem roku; ikony SVG (bez Unicode/emoji).
- Weryfikacja devserve: 390 i 1280 px, `scrollWidth` = szerokość, konsola czysta; testy `tests/test_web_recap.py`.
- Rollback: `git revert` commita E3.

### E4: powiadomienie 1 stycznia (`haiku-worker`)
- `summary.yearly(snap, today) -> Message(YEARLY, "<rok>", "Budżet — rok <rok>", …)`: wpływy, wydatki, stopa oszczędności,
  największa zmiana kategorii, sprzedawca roku, link `/app/<slug>/recap?year=<rok>`.
- `summary.due()` (`:496`): 1.01 i `sent[YEARLY] != poprzedni rok` → dodaj obok miesięcznego; `mark_sent` jak dla MONTHLY.
- Testy: 1.01 wysyła raz, 2.01 nie, brak danych roku → bez wiadomości.
- Rollback: `git revert` commita E4.

### Wydanie 0.72.0 (od razu po E4)
`simplify` → `code-review` + równolegle `silent-failure-hunter`, `pr-test-analyzer`, security `general-purpose`
(`git -C /config/addons/ha-budget-app diff 5d8d592..HEAD`) → CHANGELOG + bump `budget/config.yaml` → skill `release`
(published) → `ha_manage_updates(install, update.<budżet>, backup=true)`.

## Weryfikacja
- Każdy etap: `cd budget/app && uv run pytest -q && uv run ruff check && uv run mypy src`.
- Na żywo po wydaniu: stopka v0.72.0; `/recap?year=2026` i `?year=2025` (Ingress — Playwright dostaje 401, więc
  devserve na kopii `~/budget_dev/prod` + oględziny usera); prognoza bez zmian przy aktualnym limicie
  (`sensor.budget_forecast_card_debt` jak przed wydaniem); log startu bez błędów (`ha_get_logs` add-onu).

## Status
- **E1 ZROBIONE 2026-11-02** (commit f605d81, lokalnie, bez pusha): `card.suspect_limit` (35 dni, wpływy BOOK dodatnie, Decimal),
  `read_balances` zeruje podejrzaną nadpłatę i dolicza `fetched_at` ITAV, karta inbox `card_limit_check`, testy publishera
  (ujemny `card_debt`), `_analyze` pomija `interest`, komentarz `charts.py` bez `txn-<id>`. Weryfikacja: `sonnet-worker`
  w `wt`, claimcheck bez punktów, verifier APPROVE; pytest 1394 ok, ruff i mypy czyste.
- Zmiana poza listą: `test_web_home.py` (kafelek karty: dodany zwrot 150 zł, bo nadpłata bez wpływów daje teraz 0).
- Nieblokujące (verifier): test `fetched_at` nie rozróżnia (latest_balances zwraca jedną `fetched_at` na konto — zapis
  starszego ITAV w praktyce nieosiągalny); asercja `test_analyze_skips_interest` słaba; test publishera regresyjny, nie czerwony.
- **E2 ZROBIONE 2026-11-02** (commit 2e29f7d, lokalnie, bez pusha; plan `docs/PLAN_M25_E2.md`): `recap.py` (`build`, `years`, dataklasy
  Recap/Change/Pick/Streak/Records/PrevPeriod), `spending.merchants(leaf_id=None)` + `Merchant.average`, `tests/test_recap.py` (11) +1 test
  w `test_spending.py`. Weryfikacja: `haiku-worker` w `wt`, testy czerwone przed kodem, claimcheck bez punktów, verifier APPROVE;
  pytest 1405 ok, ruff i mypy czyste.
- Odstępstwa od planu (zaakceptowane): rok zamknięty porównuje z całym poprzednim rokiem (plan gubił 31.12 roku przestępnego);
  `months` przycięte do `end`; `priciest_month` bez bieżącego niepełnego miesiąca; `priciest_day` netto; `savings_rate` n=(today.year-year)*12+today.month.
- Nieblokujące (verifier): 31.12 roku bieżącego → zakres równy zamkniętemu (bez skutku).
- **E3 ZROBIONE 2026-11-02** (commit w historii po e9cc2a1, lokalnie, bez pusha): `web/routes_recap.py` (`/recap?year=`, domyślnie rok
  bieżący, w styczniu poprzedni; niepoprawny rok → domyślny), `templates/recap.html` (sumy z r/r, stopa, wykres 12 mies. przez
  `month_chart` z nowym parametrem `label`, zmiany kategorii z linkami do `/transactions`, sprzedawcy, rekordy), zakładka „Rok w liczbach”
  w `nav_layout.py`, style `.year-nav`, `tests/test_web_recap.py` (9). Weryfikacja: pytest 1414 ok, ruff i mypy czyste; devserve na kopii
  produkcyjnej: 390 i 1280 px bez przepełnienia, konsola czysta (poprawka: lista rekordów w `bar-rows`). Zrobiłem sam (UI, bez workera).
- Odstępstwo: `test_nav_layout` — indeks po dodaniu zakładki (8:11). Brak ikon SVG w ekranie (nie były potrzebne).
- **E4 ZROBIONE 2026-11-02**: `summary.yearly(snap, today) -> Message | None` (wpływy/wydatki, stopa oszczędności, największa zmiana
  r/r, sprzedawca roku; `None` bez danych roku), `Message.path` + `service.send_summary` dokleja ją do `panel_url` (klik → `/recap?year=`),
  `due()` 1.01 po 7:00 dla `sent[YEARLY] != poprzedni rok`. Testy: 5 nowych w `test_summary.py`. pytest 1419 ok, ruff i mypy czyste.
  Zrobiłem sam (4 małe edycje, poniżej progu workera, bez planu wykonawcy).
