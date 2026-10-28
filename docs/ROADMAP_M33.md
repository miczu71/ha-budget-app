# M33 Budżet: dzień wypłaty w nowym okresie + nieregularne zmniejszają pulę (0.67.0)

## Context
Na żywo 28.10 hero „Od wypłaty 23.10 wydane 410,90 zł” to tylko flex od 24.10. `forecast.weeks()`
(`budget/app/src/budget/forecast.py:485`) liczy okres (start, payday], więc 929,93 zł flex z dnia wypłaty
wypada. Rok temu (`flex.spent_year_ago`, `flex.py:446`) liczy się od dnia wypłaty włącznie, dlatego −79% r/r
jest zawyżone. Druga sprawa: pula miesiąca = wpływy − stałe, a nieregularne (Prezenty, Ogród, Rozliczenia,
Auto: serwis, Ubezpieczenia…) są „tylko informacyjnie” (decyzja 13, `flex.py:8`). Pieniądze na nie znikają
więc z modelu i „Zostało” jest zawyżone.

Wywiad (2026-10-28):
- **Kto korzysta:** Ty w panelu (hero „Do wypłaty”, ekran Budżet, Podsumowanie), sensory `budget_flex_*` (bez automatyzacji w HA) i podsumowania tygodnia/miesiąca.
- **Automatycznie:** okres od wypłaty liczy się od dnia wypłaty włącznie do dnia przed następną; nieregularne wydane w miesiącu odejmują się od „Zostało” (opcja 2: faktyczne, bez rezerwy).
- **Za zgodą / ręcznie:** brak w puli uzupełniasz sam z oszczędności; przelew z oszczędności dalej jest wewnętrzny i nie zmienia puli. Panel pokazuje „do uzupełnienia z oszczędności: X zł”.
- **Sukces:** hero ≈ 1 340,83 zł od 23.10 z r/r liczonym na obu stronach od dnia wypłaty; „Zostało” w październiku mniejsze o nieregularne z października, a prezent „Sklep X” 300 zł widać w rozbiciu.

Repo `/config/addons/ha-budget-app`, gałąź `main`, wersja 0.66.0 → 0.67.0 (zmiana zachowania, jedno wydanie na końcu).
Pierwszy krok: ten plan → `docs/ROADMAP_M33.md` (+ `docs/PLAN_M33_E1.md`, `docs/PLAN_M33_E2.md`), wiersz M33 i decyzje 32–33 w `docs/ROADMAP.md`.

## E1: dzień wypłaty otwiera nowy okres (robię sam, < 5 edycji, TDD)
- `forecast.py` `weeks()`: `ws = start`, `while ws < payday`, `we = min(niedziela, payday − 1 dzień)`; docstring [start, payday).
  `spent_since` (suma tygodni) liczy się wtedy od `start`, tak jak gałąź bez wypłaty (`:442`) i r/r. `year_ago_days`, `period_elapsed`, `period_plan` bez zmian.
- `tests/test_forecast.py`: najpierw czerwone, potem poprawka. Przeliczyć `test_weeks_split_period_monday_to_sunday` (30.09–04.10, 05–11.10, 12–14.10),
  `test_payday_itself_belongs_to_the_old_period` → `..._opens_the_new_period` (dziś = start → tydzień NOW),
  `test_past_weeks_use_plan...`, `test_build_has_weeks...` (7.09–6.10, limit 7.09–13.09 × 1 zł = 7);
  nowy test: wydatek w dniu wypłaty wchodzi do `spent_since`.
- Świadomy skutek: `safe_per_day` liczy horyzont do dnia wypłaty włącznie, a tygodnie kończą się dzień wcześniej, więc limity tygodni są ostrożniejsze o 1 dzień.
- Rollback: `git revert` commita E1.

## E2: nieregularne zmniejszają „Zostało” (ryzyko: pieniądze → `sonnet-worker` w `wt new`, potem `verifier`)
**Wykonawca W1**
- Pliki: `budget/app/src/budget/flex.py`, `summary.py`, `ha_publisher.py`, `web/templates/_flex_hero.html`, `web/templates/budget.html`, `tests/test_flex.py`, `tests/test_web_budget.py`, testy summary/publisher, jeśli asercje się zmieniają.
- Zmiana:
  - `FlexMonth`: nowa właściwość `charged = spent + max(non_monthly, 0)`.
  - `remaining = budget − charged`.
  - `used`, `over_pace` i różnica tempa (`summary._pool_lines`, `monthly`, hero „Tempo”) liczą z `charged`.
  - `spent`, `history`, `suggested` i `lines` zostają tylko flex.
  - Docstring modułu: nieregularne zmniejszają pulę faktycznym wydatkiem w miesiącu; decyzja 33.
- Hero: „wydane {spent} elastyczne + {non_monthly} nieregularne z {budget}”, gdy `non_monthly > 0`; przy `remaining < 0` w bieżącym miesiącu dopisek
  „Do uzupełnienia z oszczędności: |remaining|”. Notka o „bez kategorii”: po skategoryzowaniu jako stałe wrócą do puli (już nie „albo nieregularne”).
- `budget.html`: karta „Poza pulą” bez wiersza Nieregularne (przenieść do hero) + poprawiony opis; tekst na l.18 („nieregularne … nie zmniejszają”) zgodny z nową regułą.
- `ha_publisher`: `flex_remaining` dostaje atrybut `non_monthly`; `flex_spent` bez zmian.
- Test: `cd budget/app && uv run pytest -q`.
- DONE: wszystkie testy zielone. Nowe testy obejmują: `remaining` = budżet − flex − nieregularne, zwrot w nieregularnych nie powiększa puli (clamp 0), dopisek „do uzupełnienia” w HTML przy ujemnym `remaining`, atrybut `non_monthly` sensora.
- NIE RÓB: `forecast.py` i logiki salda/prognozy, `auto_budget`/rezerwy, przelewów z oszczędności, migracji bazy, wersji i CHANGELOG, commitów.
- Rollback: `git revert` commita E2.

## E3: kafelek „Akcje” tylko z zawiązanymi (robię sam, 3 edycje)
- `web/templates/_balance_tiles.html:15`: usunąć „+ {stocks_unvested} niezawiązane”. Zostaje wartość zawiązanych
  (`market_value`), znacznik „nieaktualne” i „zawiązanie {data}” (kiedy dojdą nowe; bez kwoty niezawiązanych).
- `web/routes_home.py`: usunąć osierocone pole `stocks_unvested` z `BalanceTiles` (`:81`, `:118`). `Holding.unvested_value`
  zostaje, bo używa go Majątek.
- `tests/test_web_home.py::test_stocks_tile_shows_value_unvested_and_vest` → `..._shows_vested_value_and_vest`:
  `"niezawiązane" not in` w sekcji kafelków (sprawdzić, czy ekran Majątek na tej stronie nie ma tego słowa), `"zawiązanie" in`.
- Rollback: `git revert` commita E3.

## Wydanie (od razu po E3, wg CLAUDE.md)
`simplify` → `code-review` + równolegle `silent-failure-hunter`, `pr-test-analyzer`, security general-purpose, `second-opinion` (jeśli repo PUBLIC; wynik do pomiaru) →
CHANGELOG + bump 0.67.0 → skill `release` (published) → `ha_manage_updates` z `backup=true`.

## Weryfikacja na żywo (playwright-ha, `/a9413a25_budget`)
- Hero „Do wypłaty”: „Od wypłaty 23.10 wydane ≈ 1 340,83 zł” (+ transakcje po 28.10); tydzień 23–25.10 = 1 029,92 zł.
- Ekran Budżet (październik): „Zostało” = poprzednie 1 377,23 − nieregularne października; prezent „Sklep X” 300 zł widoczne w rozbiciu.
- Podsumowanie: kafelek „Akcje” bez „niezawiązane”.
- `sensor.budget_flex_remaining` zgodny z panelem i ma atrybut `non_monthly`. Konsola bez błędów, 390 px bez przepełnienia.
