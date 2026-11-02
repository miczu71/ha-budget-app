# E1b — Ręczne dopisywanie odsetek na koncie bez API (Millennium Profit)

Źródło: `docs/ROADMAP_odsetki_oferty_loga.md`. Millennium nie udostępnia konta oszczędnościowego przez
Enable Banking, więc saldo konta to wpisane saldo + przelewy po numerze + **szacunek** odsetek
(`savings.estimate`, kapitalizacja na koniec miesiąca). Użytkownik po każdej miesięcznej kapitalizacji
wpisuje kwotę netto, którą bank faktycznie dopisał; szacunek tego miesiąca jest wtedy zastąpiony faktem.

Uproszczenie względem ROADMAP: bez „różnicy względem szacunku” i podpowiedzi kwoty w formularzu
(wystarczy lista wpisów); można dodać później.

## Wykonawca

**WORKTREE:** podany przez rodzica (`wt new`). Pracuj tylko tam. Skill `addon-conventions`, TDD.

Pliki i zmiany (ścieżki względem `budget/app/`):

1. `src/budget/storage/migrations/031_savings_interest.sql` (numer 031 zakłada, że 030 z E1 istnieje na
   `main`; jeśli w worktree go nie ma, mimo to użyj 031 — kolejność rozstrzygnie rebase przy `wt land`):
   ```sql
   -- E1b: odsetki dopisane przez bank na koncie oszczędnościowym bez API (wpis ręczny, netto po Belce).
   CREATE TABLE savings_interest (
       id INTEGER PRIMARY KEY,
       account_id INTEGER NOT NULL REFERENCES savings_account (id),
       month TEXT NOT NULL,            -- 'YYYY-MM' miesiąca kapitalizacji
       amount TEXT NOT NULL,           -- Decimal jako tekst, netto
       created_at TEXT NOT NULL,
       UNIQUE (account_id, month)
   );
   ```
   Komentarz w stylu innych migracji (addytywna).
2. `src/budget/savings.py`
   - `@dataclass(frozen=True) class InterestEntry: id: int; account_id: int; month: str; amount: Decimal`.
   - `interest_entries(conn, account_id) -> list[InterestEntry]` (malejąco po `month`).
   - `record_interest(conn, account_id, month, amount, today, now) -> None`: waliduje `month` (`YYYY-MM`,
     musi być **wcześniejszy niż miesiąc `today`** — kapitalizacja musi już nastąpić, błąd
     `SavingsError("Kapitalizacja za ten miesiąc jeszcze nie nastąpiła.")`), `amount` jako `Decimal`
     ≥ 0 (użyj istniejącego parsera kwot z modułu, jeśli jest — `money.parse` albo `_rate`/`piggy` helper;
     przecinek dziesiętny dozwolony), konto istnieje i **nie jest powiązane z księgą**
     (`linked_ledger_id(conn, acc) is None`, inaczej `SavingsError("Konto jest połączone z bankiem — odsetki
     przychodzą z synchronizacji.")`). Upsert po `(account_id, month)` (`INSERT ... ON CONFLICT DO UPDATE`).
   - `delete_interest(conn, account_id, entry_id)`.
   - W `estimate()` (gałąź ręczna, pętla dzienna): wczytaj wpisy raz przed pętlą
     (`{month: amount}`); przy kapitalizacji na koniec miesiąca (`(day + 1 dzień).month != day.month`)
     użyj `capital = entries.get(f"{day:%Y-%m}")` jeśli jest, w przeciwnym razie `net(gross)`. Reszta bez zmian
     (`bal`, `earned` rosną o `capital`, `gross = 0`). Gałąź `_from_bank` NIE zmienia się.
3. `src/budget/web/routes_piggy.py`: trasy `POST /savings/{account_id}/interest` (pola formularza
   `month`, `amount`) i `POST /savings/{account_id}/interest/{entry_id}/delete`; wzór: `promo_savings`
   (try/except `piggy.PiggyError` → `panel.redirect(request, f"/piggy#savings-{account_id}", str(exc), "error")`,
   sukces: komunikat „Dopisano odsetki.” / „Usunięto wpis.”). W widoku `/piggy` przekaż do szablonu
   `interest_entries = {a.id: savings.interest_entries(conn, a.id) for a in accts}` oraz domyślny miesiąc
   formularza (`prev_month` = poprzedni miesiąc `today` w formacie `YYYY-MM`).
4. `src/budget/web/templates/piggy.html`: w karcie konta (`<section ... id="savings-{{ a.id }}">`), tylko
   gdy `not est.as_of` (konto bez migawki z banku), przed formularzem archiwizacji:
   `<details class="piggy-new">` z `<summary>Odsetki dopisane przez bank</summary>`, lista ostatnich
   wpisów (`miesiąc` jako `MM.RRRR`, kwota `| money("PLN")`, przycisk „Usuń” = POST na trasę delete,
   `class="link"`) albo „Brak wpisów — szacunek.”, oraz formularz: `<input type="month" name="month"
   value="{{ prev_month }}" max="{{ prev_month }}" required>`, `<input name="amount" inputmode="decimal"
   size="10" required placeholder="netto, po podatku">`, przycisk „Dopisz odsetki”, notka `small muted`:
   „Wpisz kwotę, którą bank dopisał po kapitalizacji (netto, po podatku). Zastępuje szacunek za ten miesiąc.”
   Klasy istniejące (`rule-form piggy-form`, `inline`, `actions-row`); `hx-boost="false"` jak w sąsiednich
   formularzach. Jeśli `details` ma być otwarte po zapisie: nie (komunikat flash wystarczy).
5. `src/budget/inbox.py`: provider `savings_interest_due(conn, ctx, memo)`: dla `savings.all_accounts`
   z `ctx.today.day <= 7`, bez powiązania z księgą (`savings.linked_ledger_id is None`), z ustawioną stopą
   (`base_rate` lub `promo_rate`), z `opening_date` przed 1. dniem bieżącego miesiąca, z saldem
   `savings.estimate(conn, acc, ctx.today).total > 0` i bez wpisu za poprzedni miesiąc → `Item(
   "savings_interest", f"Dopisz odsetki za {nazwa miesiąca} na koncie „{acc.name}”", 1,
   f"/piggy#savings-{acc.id}", "info", "Wpisz kwotę z aplikacji banku — zastąpi szacunek.")`.
   Nazwę miesiąca weź z istniejącego helpera w `summary.py` (poszukaj funkcji z nazwami miesięcy; jeśli
   brak, użyj `f"{prev:%m.%Y}"`). Dopisz provider do listy `PROVIDERS` (obok `savings_promo`). Bez push.

Testy (najpierw czerwone):
- `tests/test_savings.py` (lub istniejący plik testów oszczędności; sprawdź `ls tests | grep -i sav`):
  szacunek z wpisem za zamknięty miesiąc = saldo uwzględnia **wpisaną** kwotę zamiast `net(gross)`;
  bez wpisu wynik jak dotąd (test regresji); upsert tego samego miesiąca nadpisuje; odrzucenie miesiąca
  bieżącego/przyszłego; odrzucenie ujemnej kwoty; odrzucenie wpisu dla konta powiązanego z księgą;
  `delete_interest` przywraca szacunek.
- `tests/test_inbox*.py`: karta pojawia się 3. dnia miesiąca przy saldzie > 0 bez wpisu; brak karty
  przy wpisie za poprzedni miesiąc, przy saldzie 0, 10. dnia miesiąca i dla konta powiązanego z księgą.
- Test web (`tests/test_web_*piggy*` jeśli istnieje, inaczej najbliższy): POST na trasę zapisuje wpis,
  strona `/piggy` pokazuje go i formularz; konto z migawką z banku formularza nie ma.
- Pełny zestaw: `BUDGET_OPTIONS_PATH=/nonexistent <python> -m pytest -q`, `ruff check .`,
  `ruff format --check .`, `mypy` (z `budget/app`; `PYTHONPATH=<WORKTREE>/budget/app/src` jeśli trzeba).

**DONE:** nowe testy zielone, pełny `pytest` zielony, `ruff` i `mypy` bez błędów; `git status --short` w
worktree tylko pliki z listy (+ testy); raport z wynikami komend.

**NIE RÓB:** nie commituj, nie pushuj; nie ruszaj `kinds.py`, `categorize/`, `invest*`, `config.yaml`
(wersja), `docs/`; nie zmieniaj gałęzi `_from_bank`; nie wpisuj żadnych prawdziwych kwot ani nazw
(testy: „Konto A”, kwoty wymyślone); nie dotykaj `~/budget_dev`; nie obchodź hooka; nie zmieniaj
istniejących testów poza dopisaniem nowych.

## Rollback
`wt drop` przed landem; po landzie `git revert`. Tabela addytywna; bez wpisów wynik identyczny jak dotąd.

## Weryfikacja na żywo (po wydaniu 0.71.0)
`/piggy`: przy koncie Profit jest „Odsetki dopisane przez bank” z formularzem; po wpisie użytkownika
saldo rośnie o wpisaną kwotę. Wpisów nie robię sam (to dane finansowe użytkownika).
