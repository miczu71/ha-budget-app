# PLAN M25 E2: silnik `recap.py` (bez UI, bez wydania)

Źródło: `docs/ROADMAP_M25_dlugi.md` § E2. Wykonawca: `haiku-worker` w `wt new` (REJECT → `sonnet-worker`), potem
claimcheck → `verifier` → `wt land`.

## Decyzje projektowe (odchylenia od ROADMAP)
- „Najdłuższa seria dni bez wydatków elastycznych” liczona z jednego przebiegu `spending._rows(..., details=True)`,
  nie przez `flex.spent_between` (365 zapytań, wymaga `Snapshot`). Wydatek elastyczny = kwota < 0, PLN, podkategoria
  `flex_group == "flexible"` albo brak kategorii (jak `flex._spent`). Pula serii (`pool_series.skip`) nie jest wyłączana.
- Stopa oszczędności z `savings.monthly_rates(conn, today, n)` (`n` = liczba miesięcy od stycznia roku do bieżącego
  miesiąca włącznie), potem filtr `month.year == year`. Średnia roku = Σsaved / Σincome tych miesięcy (income z
  `MonthRate`, nie z `spending.totals`: `monthly_rates` pomija przelewy z kont oszczędnościowych).
- Zakres roku: zamknięty = [1.01, 1.01 następnego); bieżący = [1.01, dziś+1). Porównanie: ten sam zakres dni rok
  wcześniej (`prev_start = start.replace(year-1)`, `prev_end = prev_start + (end - start)`). `prev` = `None`, gdy
  `flex.first_day(conn)` jest `None` albo `> prev_start`.

## Wykonawca
Repo `/home/claude/ha-config/addons/ha-budget-app`, kod `budget/app/src/budget`, testy `budget/app/tests`.
**Najpierw test czerwony** (uruchom, zobacz porażkę), dopiero potem kod. Przy edycji kodu add-onu: skill `addon-conventions`.

1. `spending.py`: `merchants(conn, leaf_id: int | None, start, end)`. Dla `leaf_id=None` bierze wszystkie transakcje
   PLN z `amount < 0`, których sekcja (`section(leaf, amount)`, `leaf = taxonomy.leaves(conn).get(category_id)`) to
   `"expenses"` (czyli bez oszczędności/wyłączonych/przychodów; brak kategorii liczy się). Dla `int` zachowanie bez
   zmian. Do `Merchant` dodaj `@property average -> Decimal` (`amount / count`, kwantyzacja `Decimal("0.01")`).
   Istniejące wywołanie `routes_home.py:245` bez zmian.
2. Nowy `recap.py` (docstring po polsku, wzorzec `spending.py`), dataklasy `frozen=True`:
   - `Change(category: Category, amount: Decimal, prev: Decimal)` + `delta`.
   - `Pick(day: date, label: str, amount: Decimal)` (pojedyncza transakcja: suma części podziału, etykieta z
     `spending._merchant_group`).
   - `Streak(start: date, end: date, days: int)` (końce włącznie).
   - `Records(biggest_expense: Pick | None, priciest_month: tuple[date, Decimal] | None,
     priciest_day: tuple[date, Decimal] | None, flex_free: Streak | None, biggest_income: Pick | None)`.
   - `Recap(year, start, end, partial, income, expenses, prev: PrevPeriod | None, months: list[MonthTotals],
     savings_rate: Decimal | None, best_month: MonthRate | None, worst_month: MonthRate | None, rises: list[Change],
     falls: list[Change], merchants: list[Merchant], records: Records)`, `PrevPeriod(start, end, income, expenses)`.
   - `years(conn, today) -> list[int]`: lata od roku `flex.first_day` do roku `today` malejąco; pusta księga → `[]`.
   - `build(conn, year, today) -> Recap` wg „Decyzji projektowych” i ROADMAP § E2: sumy przez `spending.sums/totals`;
     12 `MonthTotals` (`partial` tylko dla bieżącego miesiąca; miesiące po `today` mają zera); `rises`/`falls` =
     kategorie główne z `taxonomy.tree` (tylko `flex_group` spoza income/savings/excluded; kwota = suma
     `by_leaf` jej podkategorii, wydatek dodatni), top 5 z `delta >= 200` / `delta <= -200`, puste gdy `prev is None`;
     `merchants` = `spending.merchants(conn, None, start, end)[:10]`; best/worst miesiąc stopy z miesięcy
     o `rate is not None`, bez bieżącego niepełnego miesiąca; rekordy z jednego przebiegu `_rows(details=True)`.
3. `tests/test_recap.py` (importy jak `tests/test_spending.py`: `from .test_categorize_engine import add, conn, sid`).
   Syntetyczna księga, przypadki: rok zamknięty (sumy, 12 miesięcy, r/r); rok bieżący (zakres do dziś, porównanie tego
   samego zakresu dni); brak roku poprzedniego → `prev is None`, `rises == falls == []`; podział M29 (transakcja
   z podziałem = jedna w sprzedawcach i rekordach); zwrot zmniejsza kategorię; próg 200 zł (199,99 nie wchodzi);
   top 5 (6 kategorii → 5); rekordy (największy wydatek, najdroższy dzień, seria dni bez elastycznych — z lukami
   i z wydatkiem nieskategoryzowanym przerywającym serię); `years` (pusta księga, dwa lata); stopa oszczędności
   (przelew na konto oszczędnościowe — wzór w `tests/test_savings.py`).
4. `tests/test_spending.py`: `merchants(conn, None, ...)` — wszystkie wydatki, bez oszczędności/wyłączonych
   i przychodów; podział nadal liczony raz.

- Test: `cd /home/claude/ha-config/addons/ha-budget-app/budget/app && uv run --extra dev pytest -q && uv run --extra dev ruff check . && uv run --extra dev mypy src`
- DONE: pytest, ruff, mypy zielone; `tests/test_recap.py` pokrywa każdy przypadek z pkt 3; `git diff --stat` ma tylko:
  `spending.py`, `recap.py`, `tests/test_recap.py`, `tests/test_spending.py`.
- NIE RÓB: zmian UI/routes/szablonów/`nav_layout.py`, `summary.py`, migracji, wersji, CHANGELOG, formatowania
  sąsiedniego kodu, zmian sygnatur innych funkcji `spending`, commitów.
- Rollback: `wt drop` przed landem; po landzie `git revert` commita E2 (nowy moduł, bez migracji).
