# M14 E4 — memo `savings_transfer_ids` na `Snapshot`

Cel: dzwonek (`inbox`) nie liczy `ledger._analyze` przy każdym renderowaniu. Pomiar na produkcji 0.72.1
(2026-11-04, mediana z 5): `p_rotation_card` ~510 ms i `p_promo_track_due` ~510 ms (każde woła
`ledger.savings_transfer_ids` → `_analyze`), dzwonek ~1170 ms; na `/inbox` dzwonek liczy się dwa razy (~1000 ms).
Lokalnie na kopii z 02.10 (2939 BOOK) `savings_transfer_ids` = 25 ms, więc pełne potwierdzenie dopiero pomiarem po wydaniu.

## Wykonawca

Wzorzec: `Snapshot.piggy_ids` (`budget/app/src/budget/snapshot.py`) — pamięć po `signature()`, bez zapisu cache
przy `conn.in_transaction`.

1. `budget/app/src/budget/snapshot.py`: pola `_savings_key: tuple[int, int] | None = None` i
   `_savings_ids: frozenset[int] = frozenset()`; metoda `savings_ids(self) -> frozenset[int]` =
   `frozenset(ledger.savings_transfer_ids(self.conn))` (import `from budget import ledger` w ciele, jak `piggy_ids`,
   jeśli grozi cykl importów), zapis do cache tylko gdy `not self.conn.in_transaction`.
2. `budget/app/src/budget/promo_track.py`: `tracks(conn, *, status=None, today=None, savings: AbstractSet[int] | None = None)`
   i `active_for_bank(conn, bank_like, today, savings: AbstractSet[int] | None = None)`; gdy `savings is None` →
   `ledger.savings_transfer_ids(conn)` jak dziś. `_track` i `_progress` przyjmują `AbstractSet[int]` (`collections.abc.Set`)
   zamiast `set[int]`, tylko adnotacje.
3. `budget/app/src/budget/rotation.py`: `recommend(conn, today, savings: AbstractSet[int] | None = None)` przekazuje `savings`
   do `promo_track.active_for_bank`.
4. `budget/app/src/budget/inbox.py`: `rotation_card` woła `rotation.recommend(conn, ctx.today, ctx.snap.savings_ids())`,
   `promo_track_due` woła `promo_track.tracks(conn, status="active", today=ctx.today, savings=ctx.snap.savings_ids())`.
5. Testy (TDD, najpierw czerwone):
   - `tests/test_snapshot.py`: (a) dwa wywołania `savings_ids()` przy tej samej sygnaturze → `ledger._analyze`
     wywołane 1× (monkeypatch licznika na `budget.ledger._analyze`); (b) zapis do `txn` unieważnia (po `add(...)` liczy ponownie);
     (c) wywołanie wewnątrz otwartej transakcji nie zapisuje cache (po `conn.execute("BEGIN")`/`INSERT` dwa wywołania = 2×);
     (d) wynik równy `ledger.savings_transfer_ids(conn)`.
   - `tests/test_promo_track.py`: `tracks(..., savings=ids)` zwraca te same liczniki co `tracks(...)` bez `savings`
     (użyć istniejącego seedu testu licznika bezgotówkowego); `savings=set()` pomija wywołanie `ledger.savings_transfer_ids`
     (monkeypatch, który rzuca wyjątek).
   - `tests/test_rotation.py`: `recommend(..., savings=ids)` = `recommend(...)` na istniejącym seedzie.
6. Komenda testu (z `budget/app`): `BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`,
   potem `.venv/bin/ruff check .` i `.venv/bin/mypy`. Przed edycją `addon-conventions`.

DONE: pytest/ruff/mypy zielone bez nowych ostrzeżeń; 3 nowe grupy testów z p. 5 przechodzą, a bez zmian w
kodzie (1–4) są czerwone; `rotation_card` + `promo_track_due` w jednym renderowaniu dzwonka wołają `_analyze` ≤ 1×
(test w `test_snapshot.py` albo `test_inbox*.py` z licznikiem), a w drugim renderowaniu bez zapisu 0×.

NIE RÓB: zmian w `ledger.py` (`_analyze`, `rebuild_links`), `categorize/engine.py`, kolejności `inbox.ITEMS`,
treści kart dzwonka, `summary.py`, `web/*`, migracjach, CHANGELOG ani numerze wersji; commitów; innych refaktorów.
Wywołania `rotation.recommend`/`promo_track.*` poza `inbox.py` zostają bez `savings` (zachowanie jak dziś).

Rollback: `git revert` (parametry opcjonalne, brak migracji).

## Uwaga
Pierwsze renderowanie po każdym zapisie nadal liczy `_analyze` raz (~500 ms na produkcji), kolejne z pamięci.
Jeśli po wydaniu zimny koszt nie mieści się w progach, E5a = przyspieszenie samego `_analyze` (np. `fold` bez
powtórnego liczenia dla tego samego opisu) z testem równości wyniku.
