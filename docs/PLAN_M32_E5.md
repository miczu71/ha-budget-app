# M32 E5 — Prognoza do wypłaty bez Flexu (przed wydaniem M32)

## Kontekst
Prośba usera z 2026-10-26, przed wydaniem końcowym M32 (E1–E4 i simplify są już na `main`, `237eff8`). Prognoza
„Do wypłaty” w Podsumowaniu odejmuje dziś co dzień `flex_per_day`: resztę puli Flex rozłożoną na dni albo, gdy puli
nie ma lub się skończyła, dotychczasowe tempo wydatków (`forecast.flex_per_day`, `forecast.py:199`). User uważa to
za oderwane od rzeczywistości. Prognoza ma liczyć **tylko znane i zaplanowane** pozycje: saldo, serie cykliczne
(wydatki i wpływy), przelewy do skarbonek, blokady `held`. Flexu nie szacujemy w żaden sposób.
„Bezpieczny limit dzienny” (`safe_per_day`) zostaje i liczy się wtedy wprost jako `(saldo − bufor) / dni` w
najostrzejszym dniu, czyli „ile możesz dziennie wydać na niezaplanowane”. Hero, tygodnie i plan okresu działają
na nim bez zmian.

Blokady przy przydzielaniu kategorii (pytanie 2): **osobny M33 po wydaniu** (decyzja usera). Fakty: Millennium
przez EB zwraca tylko `BOOK` (FINDINGS_millennium.md:21, zrzuty prod 0 PDNG/~950). Velobank jest nieznany do czasu
połączenia. `ledger.ingest_api` kasuje i wstawia PDNG przy każdym syncu, więc kategoria nadana blokadzie by
przepadła. Do ROADMAP trafia tylko wpis M33 (wywiad później), bez kodu.

Repo `miczu71/ha-budget-app` (`/config/addons/ha-budget-app`), gałąź `main`. Zmiana idzie do wydania końcowego M32.

## Zmiana (budget/app/src/budget)
1. `forecast.py`
   - `project()`: usunąć parametr `per_day` i odejmowanie Flexu w pętli dni; usunąć pole `Projection.flex_total`.
   - `safe_per_day(days, today, buffer)`: bez `per_day`, czyli `min((saldo − bufor) / dni do d)`.
   - `build()`: bez parametru `f` (`flex.FlexMonth`) i bez `flex_per_day`; usunąć pole `Forecast.flex_per_day`
     i funkcję `flex_per_day` (osierocone). `for_today` przestaje liczyć `flex.build`. `flex.spent_between`
     i `flex.pool_series` (wydane od wypłaty, tygodnie) zostają, bo to fakty z księgi, nie prognoza.
   - Docstring modułu: „reszta puli Flex po równo na dni” → prognoza tylko z pozycji znanych i zaplanowanych.
2. `web/routes_home.py:132`: wywołanie `forecast.build` bez `f`.
3. `web/templates/_forecast.html:14`: usunąć kolumnę „Flex” z paska równania.
   `_payday_hero.html:10`: „przy obecnym tempie (X dziennie)” → np. „licząc tylko płatności cykliczne i skarbonki”.
   `safe_per_day` w hero zostaje jako główna kwota „dziennie”.
4. `ha_publisher.py:355`: usunąć atrybut `flex_rest` encji `forecast_at_payday`. Przed tym sprawdzić `ha_search`
   (dashboardy, automatyzacje), że nikt go nie czyta. Jeśli ktoś czyta, zostawić `flex_rest=0` i zgłosić.
5. Testy: `tests/test_forecast.py` (wywołania `project(... per_day=...)`, asercje `flex_total`/`flex_per_day`,
   nowy test: pula Flex ustawiona → prognoza i `at_payday` się nie zmieniają), `tests/test_ha.py` (atrybut
   `flex_rest`, jeśli jest asertowany), `tests/test_web_home.py` (tekst hero, brak „Flex” w pasku).
   Encje `flex_*` z `ha_publisher` (ekran Budżet/Flex) zostają bez zmian, bo to nie prognoza.
6. Docs: `docs/PLAN_M32.md`, czyli sekcja E5 (ten plan, wynik), wiersz w tabeli wyników; `docs/ROADMAP.md`, czyli
   wpis M33 „Kategoria na etapie blokady” (fakty wyżej, opcje: zapowiedź w panelu z dopasowaniem do księgowania /
   przeniesienie kategorii PDNG→BOOK dla Velobanku / powiadomienia Companion; najpierw sprawdzić PDNG Velobanku
   po połączeniu).

Poza zakresem: Prognoza Rok (`year.py`) i ekran Flex (pula, „na dzień do końca miesiąca”) bez zmian.

## Wykonawca (haiku-worker, worktree z `wt new`)
- Pliki: `budget/app/src/budget/forecast.py`, `web/routes_home.py`, `web/templates/_forecast.html`,
  `web/templates/_payday_hero.html`, `ha_publisher.py`, `tests/test_forecast.py`, `tests/test_ha.py`,
  `tests/test_web_home.py`.
- Zmiana: punkty 1–5 wyżej (TDD: najpierw test „pula Flex nie zmienia prognozy”, czerwony; potem kod).
- Test: `cd budget/app && BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q && .venv/bin/ruff check . && .venv/bin/mypy src`
- DONE: w `src` brak `flex_per_day` w forecast/szablonach prognozy i brak `flex_total`; `project`/`safe_per_day`
  bez `per_day`; nowy test zielony; pytest bez nowych faili; ruff czysty; mypy bez nowych błędów.
- NIE RÓB: zmian w `flex.py`, `year.py`, `summary.py`, encjach `flex_*`, `forecast.held`/skarbonkach; bumpu
  wersji; commitu.
- Potem `verifier` (z BASELINE `git status --short`) i commit `feat(M32 E5): prognoza do wypłaty bez Flexu …`.

## Weryfikacja
- pytest/ruff/mypy jak wyżej. Lokalnie `budget/app` na kopii `~/budget_dev`: strona główna, hero bez „przy
  obecnym tempie”, pasek bez „Flex”, `safe_per_day` ≥ dotychczasowej wartości.
- Po wydaniu (w łańcuchu M32: `simplify` → `code-review` + `silent-failure-hunter` + security + druga opinia →
  `release`): Podsumowanie w HA (Playwright), encja `sensor.*forecast_at_payday` bez `flex_rest`,
  `binary_sensor.*forecast_shortfall` zgodny z nową prognozą.

## Rollback
`git revert` commitu E5 (bez migracji i kluczy kv).
