# M30 — Prognoza roczna bez wydatków jednorazowych

## Kontekst
Ekran „Rok” (M18, 0.53.0) pokazuje −23 229 zł na 31.12.2026. Przyczyna: prognoza kopiuje 1:1
wydatki sprzed roku z grup stałe/nieregularne („roczne bez serii” — remont 11–12.2025, ~12 tys.),
a mediana Flex i korekta „nieregularne” zawierają jednorazowe duże wydatki (15 tys. wypłat gotówki
w 11.2025, podróże). Cel ustalony w wywiadzie: **„typowy rok + plan”** — prognoza z typowych
wydatków; jednorazowe duże wydatki planuje się zdarzeniem.

Decyzje z wywiadu:
- Rozpoznanie **po kategoriach**: nowa **osobna flaga kategorii** „pomiń w prognozie rocznej”
  (kategoria zostaje w swojej grupie; Budżet/Wydatki bez zmian — zmienia się tylko „Rok”).
- „Roczne bez serii” zostaje, ale bez flagowanych kategorii.
- Korekta „nieregularne” zostaje, liczona z historii bez flagowanych kategorii.
- Przelewy z oszczędności — poza zakresem (osobny temat).
- Ekran „Rok” pokazuje jedną linijkę: pominięte kategorie + średnio X zł/mies. (12 mies.) + link.
- Flagi na start (na żywo, po wydaniu, za zgodą): Wyposażenie i remont, Wypłaty gotówki,
  Noclegi, Bilety i transport, Inne w podróży, Elektronika.

Repo: `/config/addons/ha-budget-app` (gałąź `main`, wersja 0.53.0), kod `budget/app/src/budget/`.

## Etapy

### E1 — flaga kategorii i obliczenia (fundament + wartość)
1. Migracja `storage/migrations/022_year_skip.sql`: `ALTER TABLE category ADD COLUMN year_skip
   INTEGER NOT NULL DEFAULT 0` (addytywna).
2. `categorize/taxonomy.py`: pole `year_skip: bool` w `Category` i `_row`; funkcja
   `set_year_skip(conn, category_id, on)` (tylko podkategoria, wzór `set_flex_group`).
3. `flex.py`: `spent_between(..., leaves=None)` — opcjonalna lista elastycznych podkategorii
   (domyślnie `_flexible(conn)`), przekazana do `_spent`. Uwaga: `_spent` = `unc_out − net(flexible)`,
   więc pominięcie liścia z listy wyjmuje go z wydatków Flex; Budżet woła bez parametru → bez zmian.
4. `year.py`:
   - `history()`: `flexible` = elastyczne bez `year_skip`; `leaves` do `_seasonal_spent` bez
     `year_skip`; nowe pole `History.skipped: Decimal` (średnia mies. wydatków flagowanych kategorii
     z tych samych 12 mies.) i `skipped_names`.
   - `Projection` dostaje `skipped`, `skipped_names` (ustawiane w `build`).
   - `backtest()` używa tych samych list (spójny pomiar na Statusie).
5. Testy TDD w `tests/test_year.py` (+ `test_taxonomy`/`test_flex` jeśli tam są odpowiedniki):
   flagowana kategoria elastyczna nie wpływa na medianę i korektę; flagowana nieregularna nie wchodzi
   do „roczne bez serii”; `spent_between` bez `leaves` daje wynik jak dotąd; migracja ustawia 0.
6. Pełne `pytest`, `ruff`, `mypy`. Commit.
Rollback: `git revert`; kolumna z DEFAULT 0 jest nieszkodliwa dla starszego kodu.

### E2 — UI: przełącznik w Kategoriach i linijka na „Rok”
1. `web/templates/categories.html`: w `<details class="leaf">` formularz z checkboxem
   „Pomiń w prognozie rocznej (wydatki jednorazowe)”; znacznik „poza prognozą” w `summary`.
2. `web/routes_rules.py`: `POST /categories/{id}/year-skip` → `taxonomy.set_year_skip`, flash.
3. `web/templates/year.html`: pod listą miesięcy `p.small.muted`: „Pominięte w prognozie:
   {nazwy} — średnio {skipped} zł/mies. w ostatnich 12 mies. Duży planowany wydatek dodaj jako
   zdarzenie. [Zmień w Kategoriach]”; widoczne tylko gdy są flagi.
4. Testy tras (wzór istniejących testów `/categories/{id}/group` i `/year`). Weryfikacja dev
   (devserve z kopią księgi, Playwright: zrzut + konsola). Skill `impeccable` dla drobnego UI.
5. Commit.
Rollback: `git revert`.

### Wydanie (po E2, bez pytania)
`simplify` → `code-review` → skill `release` 0.54.0 (CHANGELOG po polsku, neutralne nazwy),
update add-onu przez ha-mcp, weryfikacja na żywo przez Ingress.

### Krok na żywo (za zgodą — zmiana danych produkcyjnych)
Ustawić flagę w Kategoriach dla 6 podkategorii z listy; odczytać „Rok”: koniec, Flex, roczne bez
serii, linijka pominiętych. Rollback: odznaczyć flagi.

## Dokumentacja
`docs/ROADMAP.md` — wiersz M30; `docs/PLAN_M30.md` — ten plan (pierwszy krok implementacji).
Handoff po E1 wg protokołu auto-handoff.

## Weryfikacja końcowa
- Testy/ruff/mypy zielone.
- Na żywo: Budżet i Wydatki — te same liczby co przed wydaniem (porównanie stat dla 09.2026
  i bieżącego miesiąca); „Rok” — koniec wyraźnie wyżej niż −23 229 zł (oczekiwanie ~−5…−10 tys.),
  „roczne bez serii” 11/12.2026 bez remontu, linijka pominiętych widoczna, brak błędów konsoli.
