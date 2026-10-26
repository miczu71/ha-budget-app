# Budżet: poprawki M32 (synchronizacja per bank) + M14 E2c (`/status`) → wydanie 0.66.0

Repo: `/config/addons/ha-budget-app` (`main`, czysty), kod `budget/app/src/budget`, testy `budget/app/tests`.
Plan kopiuję do `docs/PLAN_M32_M14_E2c.md` jako pierwszy krok.

## Context
Po 0.65.0 zostały uwagi z review M32: alerty o zgodzie i nieudanych synchronizacjach widzą tylko jeden bank
(`sessions.current()` = „najpilniejsza” sesja, jeden licznik `consecutive_failures` dla całego przebiegu),
a komunikaty nie mówią, którego banku dotyczą. Druga sprawa: `/status` 584 ms przy progu 400 ms, z czego
~367 ms to dwa podglądy `summary.build` (`routes_status.py:89`). Test kredytu cloud na claude.ai/code — anulowany.

## Co sprawdziłem i nie wymaga kodu (do raportu, weryfikacja na żywo)
- **Odrzucanie powiadomienia o nowej edycji Velo** — zrobione w 0.65.0 (E14): „Widziałem” (`promo_watch_velo.ack`,
  `POST /promo/velo/ack`), karta dzwonka znika, push z deduplikacją `mark_sent`; karty da się też ukryć ogólnym
  „ukryj” dzwonka (`inbox.dismiss`). Sprawdzę na żywo.
- **Cel rekomendacji = konto Velo** — naprawione w E6: `rotation.velo_balance` bierze konta powiązane, nie `kind='savings'`.
- **`END_PAST_DAYS`** — edycja zakończona ≤30 dni temu przechodzi walidację, ale dzwonek (`ctx.today > o.ends_by()`)
  i rotacja (`0 <= ends-today`) ją pomijają. Bez zmian.
- **id `promo_cashless`** — klucz karty to `kind|title`, tytuł zawiera bank, więc karty różnych banków się nie mieszają. Bez zmian.

## Etap A — synchronizacja i alerty per bank (kod, sonnet-worker w worktree `wt new`)
Decyzja (domyślna, do potwierdzenia w ExitPlan): nieaktywna zgoda **nie** jest „nieudaną synchronizacją” —
ma własny alert per bank; licznik porażek liczy błąd/limit/wygasłą sesję **osobno dla każdego banku**.

### Wykonawca (kontrakt dla `sonnet-worker`, potem `verifier`)
Pliki i zmiany:
1. `sync_service.py` — w `sync()` po każdym banku aktualizacja kv `sync_bank_failures` (`{aspsp: n}`):
   status `ok` → 0, `error`/`rate_limited`/`expired` → n+1, bank nieaktywny → bez zmiany; banki spoza `records`
   usuwane. Nowa funkcja `bank_failures(conn) -> dict[str, int]`. `consecutive_failures()` bez zmian (Status, historia).
2. `notifications.py` — `evaluate(records: list[SessionRecord], *, bank_failures: dict[str,int], ...)`:
   dla każdego banku osobno `session_inactive`, `consent_expiring`, `sync_failures` z kluczem `"<rodzaj>:<aspsp>"`
   i nazwą banku w treści („Zgoda Velobank wygasa za 5 dni…”, „Velobank: 3 nieudane synchronizacje z rzędu…”).
   `manual_sync` bez zmian (globalny). Notifier bez zmian (id `budget_<klucz>`; stare klucze zamknie sam).
3. `service.py:471` — przekazuje `sessions.current_all(conn)` i `sync_service.bank_failures(conn)`.
4. `inbox.py::operational` — to samo; tytuł/link/severity po prefiksie klucza (przed `:`), tytuł z nazwą banku,
   `count` = porażki tego banku.
5. `ha_publisher.py:144–186` — `consent_days_left` zostaje (najpilniejsza), dochodzi atrybut
   `banks: {aspsp: {days_left, status, valid_until}}`; `sync_problem` ON, gdy któryś bank nieaktywny albo ma porażki,
   atrybut `bank_failures`.
6. `web/routes_accounts.py:31–38` — jeden `UPDATE` (display_name, include_in_budget, kind) zamiast dwóch (atomowość `kind`).
7. Testy: `test_sync_service.py` (licznik per bank: błąd jednego, reset po ok, nieaktywny nie liczy),
   `test_*notif*`/`test_ha.py` (dwa banki → dwa osobne alerty z nazwą banku), `test_web.py` lub odpowiedni dla dzwonka.
Komenda testu: `cd budget/app && uv run pytest -q && uv run ruff check . && uv run mypy src`
DONE: dwa banki z różnymi problemami dają osobne alerty i karty dzwonka z nazwą banku; wszystkie testy zielone.
NIE RÓB: migracji bazy, zmian `consecutive_failures`, `Notifier.process`, szablonów HTML poza koniecznym; commitów.

Rollback: `git revert` commita etapu (dane tylko w kv `sync_bank_failures`, ignorowane przez starą wersję).

## Etap B — M14 E2c `/status` (sam, TDD)
1. Pomiar lokalnie na danych `~/budget_dev`: cProfile `summary.weekly` i `summary.monthly` — który krok zjada
   ~367 ms (`flex.build`, `top_categories`, `upcoming`, `review.pending_count`, `networth`).
2. Poprawka wg wyniku; domyślnie memo podglądów po `(snap.signature(), today)` wzorem `invest.AdviceMemo`
   (podgląd nie zmienia się między odświeżeniami Status), plus kroki `s_weekly`/`s_monthly` w `Server-Timing`.
   Jeśli winny jest wspólny krok (np. `flex.build`) — memo tam, z korzyścią także dla `/`.
3. Test: drugie wywołanie przy tej samej sygnaturze nie liczy ponownie; zmiana bazy unieważnia.
DONE: `s_summaries` < 50 ms przy ciepłym memo, pierwsze wejście bez regresji.

## Dokumenty
- `docs/PLAN_M32.md` § Następne kroki: pkt 1 „test kredytu cloud — anulowany przez usera 2026-10-26”, pkt 2 → wynik etapu A.
- `docs/ROADMAP.md` wiersz M14 (E2c) i M32; notatka pamięci `reference_remote_isolation_runs_locally.md` + linia w MEMORY.md (test anulowany).

## Wydanie 0.66.0 (po A i B, bez pytania)
`simplify` → `code-review` (+ `silent-failure-hunter`, `pr-test-analyzer`, security review, second-opinion — pomiar 5/10)
→ skill `release` (bump `config.yaml` + `pyproject.toml`, CHANGELOG, published) → aktualizacja przez
`ha_manage_updates` z backupem add-onu.

## Weryfikacja na żywo
- `/status` Server-Timing: mediana z 5 < 400 ms, `s_summaries` znikome.
- Dzwonek i persistent notifications: brak duplikatów, nazwy banków w treści; `binary_sensor.budget_sync_problem`
  z atrybutem `bank_failures`, `sensor.budget_consent_days_left` z `banks` (Millennium + Velobank).
- Velo: „Widziałem” ukrywa kartę nowej edycji (jeśli jest), konsola czysta, 390 px bez przepełnienia.
- Log add-onu po synchronizacji bez błędów.
