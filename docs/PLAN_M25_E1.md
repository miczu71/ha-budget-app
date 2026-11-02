# PLAN M25 E1: długi z ryzykiem błędu (0.72.0, bez wydania po etapie)

Źródło: `docs/ROADMAP_M25_dlugi.md` § E1. Ryzyko (pieniądze) → `sonnet-worker` w `wt new`, potem `verifier`.

## Wykonawca
Repo `/home/claude/ha-config/addons/ha-budget-app`, kod w `budget/app/src/budget`, testy w `budget/app/tests`.

1. `card.py`: nowa funkcja `suspect_limit(conn, today, itav, limit) -> SuspectLimit | None` oraz
   `@dataclass(frozen=True) class SuspectLimit: limit: Decimal; available: Decimal; overpaid: Decimal`.
   Reguła: `overpaid = itav - limit`; jeśli `limit` i `itav` są znane, `overpaid > 0` i `overpaid` jest większa niż suma
   dodatnich zaksięgowanych (`status = 'BOOK'`, `amount` dodatnie) transakcji konta karty (`card_account(conn)`) z ostatnich
   35 dni (`booking_date >= today − 35 dni`) → zwróć `SuspectLimit`, inaczej `None`. Stała `SUSPECT_DAYS = 35`.
   Sumuj przez `money.total` (jak w `due_status`), nie `float`.
2. `forecast.py` `read_balances` (l. ~211–221): gdy `card.debt_from(...)` da wartość ujemną (nadpłata), a
   `card.suspect_limit(conn, date.today(), itav, limit)` zwraca wynik → `card_debt = ZERO`. Do `fetched` dochodzi też
   `available["fetched_at"]` (ITAV), gdy `available` istnieje (`min(fetched)` bierze starszy odczyt).
3. `inbox.py`: nowa karta `card_limit_check(conn, ctx, memo) -> list[Item]` (wzór: `card_due`, l. 244) dodana do listy
   generatorów obok `card_due` (l. ~613). Gdy `card.suspect_limit(...)` na ostatnich migawkach karty zwraca wynik:
   `Item("card_limit_check", "Sprawdź limit karty", 1, "/card", "warn", f"Ustawiony limit {zl(limit)}, bank pokazuje dostępne {zl(available)} — nadpłata {zl(overpaid)} bez wpływów na kartę. Prognoza jej nie liczy.")`
   (użyj `money.pl(x, "PLN")` jak w `card_due`). Brak karty/limitu/ITAV → pusta lista.
4. Testy (najpierw czerwone, TDD):
   - `tests/test_forecast.py`: (a) nadpłata z wpływem na kartę ≥ nadpłaty → `card_debt` ujemny jak dziś
     (istniejący `test_read_balances_card_overpayment_is_negative_debt` dopasuj: dodaj wpływ zwrotu, jeśli trzeba);
     (b) nadpłata bez wpływów (limit zaniżony) → `card_debt == 0`; (c) `fetched_at` = starszy z ITBD/ITAV.
   - `tests/test_inbox*.py` (znajdź plik z testami `card_due`): karta `card_limit_check` jest przy (b), nie ma jej przy (a)
     i bez limitu.
   - `tests/test_ha.py` (l. ~157 `_entities`): publisher przy `Balances.card_debt` ujemnym publikuje ujemne
     `card_debt` i `forecast_card_debt` (asercja na stanie encji).
   - `tests/test_ledger*.py` (znajdź test `_analyze`): transakcja z `kind = interest` nie trafia do wyniku `_analyze`;
     sprawdź, że test jest czerwony po usunięciu warunku w `ledger.py:737-743` (mutacja ręczna, potem przywróć).
5. `web/charts.py:26`: w komentarzu usuń `` `txn-<id>` (drill-down),`` (klucz nie istnieje; zostają `cat-<id>`, `shop-<n>`).
- Test: `cd /home/claude/ha-config/addons/ha-budget-app/budget/app && uv run pytest -q && uv run ruff check . && uv run mypy src`
- DONE: pytest, ruff i mypy zielone; nowe testy (b), karta inbox, publisher ujemny, `_analyze` interest istnieją i bez
  poprawki (b) są czerwone; `git diff --stat` obejmuje tylko pliki z listy niżej.
- NIE RÓB: zmian w `ledger.py:963` (uzgodnienie salda karty zostaje bez filtra podejrzanego limitu), migracji, wersji,
  CHANGELOG, formatowania sąsiedniego kodu, kolorów/strzałek drill, `merchants`/`purchases`, commitów.
- Pliki: `card.py`, `forecast.py`, `inbox.py`, `web/charts.py`, testy jak wyżej.
- Rollback: `wt drop` przed landem; po landzie `git revert` commita E1.

## Odpisane długi (bez kodu, do ROADMAP przy zamknięciu)
Migracja 030 LIKE (wykonana, klasyfikator używa `fold`), reguła usera nie przebija `interest` (decyzja odsetek E1), kolory
drill indeksowane, strzałki Unicode, `merchants`/`purchases` czytają cały miesiąc, link `q` to wyszukiwanie tekstowe,
poz. 2 środek netto vs wycinki dodatnie, prognoza liczona przy każdym kliknięciu drill.
