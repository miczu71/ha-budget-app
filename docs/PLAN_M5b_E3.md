# M5b E3 (0.16.0) — zmiany serii w dzwonku

## Context

Użytkownik zamknął checkpoint E2 (0.15.0, „Ten miesiąc”) 2026-10-05. Następny etap według
`docs/PLAN_M5b.md` to E3. Odpowiada na drugą część pytania B: „co się zmieniło w moich
płatnościach cyklicznych?”. Dziś statusy widać tylko w „Ten miesiąc”. Nic nie trafia do
dzwonka i nie da się zapisać decyzji („to jednorazowo”, „pomiń ten okres”). E3 dodaje
wykrywanie zmian z panelem decyzji, tabelę `series_ack` i karty w dzwonku, a przez dzwonek
także stan `sensor.budget_inbox` w HA. Pula Flex się nie zmienia (to E4).

Stan wyjściowy: kolumna `series.tolerance` jest zapisywana (przez detektor i formularz),
ale dziś nikt jej nie czyta. E3 zaczyna jej używać.

## Reguły (ustalone domyślnie, każdy punkt możesz odrzucić przy akceptacji)

Zmiany są liczone na bieżąco z `schedule` i `assign`, a w bazie zapisuje się tylko decyzja.
Liczą się wyłącznie serie aktywne. Terminy sprzed pierwszej transakcji serii są pomijane, więc
nowa seria ręczna nie dostaje od razu „braków”.

| Zmiana | Kiedy | Akcje |
|---|---|---|
| **Inna kwota** | **ostatni zapłacony** termin serii (bieżący albo poprzedni miesiąc) ma kwotę poza `expected ± tolerance` | „Przyjmij nową” (`expected_amount` := zapłacona kwota, bez wpisu ack) / „Jednorazowo” (ack `amount`/`once`) |
| **Spóźniona** | termin bieżącego albo poprzedniego miesiąca bez płatności po oknie +5 dni (status `late`/`missing`) | „Pomiń ten okres” (ack `late`/`skip`) |
| **Ustała** | 2 ostatnie minione terminy bez płatności (pominięty okres przerywa serię braków); zastępuje kartę „spóźniona” tej serii | „Zakończ” (istniejące `set_status end`) / „Zostaw” (ack `stopped`/`keep` dla ostatniego terminu; następny brak = nowa karta) |

- Tylko ostatni zapłacony termin, a nie każdy w oknie. Inaczej po „przyjmij nową” stara kwota
  z poprzedniego miesiąca od razu dawałaby nową kartę.
- Pominięty okres dostaje w „Ten miesiąc” nowy status **„pominięte”** i **nie liczy się** do
  „jeszcze zejdzie / wpłynie”, a więc ani do encji `fixed_planned`, ani do `income_planned`.
- Wpływy (np. wypłata) podlegają tym samym regułom. Spadek wypłaty po wejściu w II próg da
  kartę „inna kwota” i to jest zamierzone: to realna zmiana do przyjęcia.
- Dzwonek pokazuje jedną kartę na rodzaj zmiany z liczbą serii i linkiem
  `/recurring#changes`. Przyciski akcji są w sekcji „Zmiany” na Cyklicznych, tak jak
  propozycje serii w E1.

## Kroki (po kolei, testy po każdym)

0. **Plan do repo:** `docs/PLAN_M5b_E3.md` (treść tego planu bez kwot usera), wpis w
   `ROADMAP.md` (M5b: „✅ checkpoint E2 zamknięty 2026-10-05; plan E3 zaakceptowany”), commit
   `docs(M5b): checkpoint E2 zamknięty, plan etapu E3`. Najpierw `test -x .git/hooks/pre-commit`.

1. **Migracja `storage/migrations/010_series_ack.sql`:** tabela `series_ack(series_id INTEGER
   NOT NULL REFERENCES series(id), period TEXT NOT NULL /* RRRR-MM terminu */, kind TEXT CHECK
   IN ('amount','late','stopped'), decision TEXT CHECK IN ('once','skip','keep'), decided_at
   TEXT NOT NULL, PRIMARY KEY(series_id, period, kind))`. `db.connect` stosuje ją sam.
   Cofnięcie: tabela jest addytywna, więc starsza wersja add-onu ją po prostu ignoruje.

2. **`recurring/schedule.py`:**
   - `month_view(..., acks)`: termin z ack `late/skip` dostaje status `SKIPPED = "skipped"`
     („pominięte”), który nie wchodzi do `out_planned`/`in_planned`;
   - `for_month` czyta acki (jedno zapytanie);
   - helper `dues_back(s, members, today, n)` — ostatnie `n` minionych terminów (używa
     istniejącego `due_date` i `add_months`, cofa się po miesiącach do 2×kadencji×n).

3. **`recurring/changes.py`** (nowy, czysta logika + cienkie odczyty z bazy):
   `Change(series, kind, period, detail, amount)`, `detect(series, members, acks, today)
   -> list[Change]` według tabeli wyżej; `for_db(conn, today)`; zapis `ack(conn, series_id,
   period, kind, decision)` i `accept_amount(conn, series_id, amount)` (UPDATE
   `expected_amount`). Wejście z `S.all_series(("active",))` i `S.assign(S.candidates(conn))`,
   tak samo jak w `schedule.for_month`.

4. **Dzwonek** (`inbox.py`): dostawca `series_changes`, karty `series_amount` / `series_late`
   / `series_stopped` (severity: inna kwota `info`, spóźniona `warn`, ustała `warn`), dopisany
   do `PROVIDERS`. Encja `sensor.budget_inbox` dostaje je automatycznie przez `Service`.

5. **Panel** (`web/routes_recurring.py`, `recurring.html`): sekcja „Zmiany” (`id="changes"`)
   nad „Ten miesiąc”. Wiersz: nazwa serii (link), rodzaj, szczegół (np. „zapłacono X zamiast
   Y, termin RRRR-MM”) i przyciski. `POST /recurring/{id}/change` (pola `kind`, `period`,
   `action` ∈ accept/once/skip/keep/end) wywołuje `changes.ack` / `accept_amount` /
   `S.set_status(..., "end")` i robi redirect `/recurring#changes`. Middleware `refresh_soon`
   odświeży encje. Plakietka „pominięte” w „Ten miesiąc”.

6. **Testy i pomiar:** `test_recurring_changes.py` (inna kwota: w i poza tolerancją, tylko
   ostatni zapłacony, „jednorazowo” chowa kartę, „przyjmij” zmienia kwotę i chowa kartę;
   spóźniona: bieżący i poprzedni miesiąc, skip chowa kartę i zdejmuje kwotę z „jeszcze
   zejdzie”; ustała: 2 braki, skip przerywa serię braków, keep chowa kartę do następnego braku,
   end; Q z 2 brakami; seria ręczna bez starych braków), `test_inbox.py` (karty),
   `test_web_recurring.py` (POST change, sekcja), migracja w testach db. `pytest` + ruff +
   mypy (`BUDGET_OPTIONS_PATH=/nonexistent`, `budget/app/.venv`). Sonda w scratchpadzie na
   kopii `~/budget_dev/prod/ledger.db` (wykrywanie, potwierdzenie serii na kopii, potem
   `changes.detect`): ile kart wyjdzie i czy „inna kwota” nie jest za głośna dla serii
   o zmiennej kwocie. **Jeśli jest za głośna, zatrzymuję się i pytam przed wydaniem.** Czas
   renderu `/recurring` i `/inbox`, Playwright mobile, 0 błędów konsoli; kopię usuwam.

7. **Wydanie 0.16.0** skillem `release` (bump `config.yaml`, CHANGELOG/README, opublikowany
   release, nie draft). **Update add-onu `a9413a25_budget` przez `ha_manage_app` to akcja
   produkcyjna — tylko po Twoim „go” na wydanie** (przy >300 s sprawdzam `ha_get_app`).
   Weryfikacja: log add-onu, `sensor.budget_inbox` (stan i atrybut `items`), `sw_version`
   0.16.0; panel przez Ingress oglądasz Ty (proxy ha-mcp daje 403). Potem `PLAN_M5b_E3.md`
   § Wynik, `ROADMAP.md`, pamięć `project_budget_app`.

8. **Checkpoint E3:** stop. Przeglądasz karty zmian na żywo. E4 (0.17.0, pula) dopiero po „go”.

## Pliki

`budget/app/src/budget/storage/migrations/010_series_ack.sql` (nowy),
`recurring/changes.py` (nowy), `recurring/schedule.py`, `inbox.py`,
`web/routes_recurring.py`, `web/templates/recurring.html`, testy w `budget/app/tests/`,
`docs/PLAN_M5b_E3.md`, `docs/ROADMAP.md`, `budget/config.yaml`, `CHANGELOG`.
Gałąź: `main` (jak w poprzednich etapach).

## Ryzyka

- Serie o zmiennej kwocie (media, wypłata): możliwa karta co miesiąc. Sonda w kroku 6 to
  zmierzy przed wydaniem.
- Granica miesiąca: płatność 30. na termin 1. Przypisanie do najbliższego terminu jest już
  w `month_view`, więc testy muszą pokryć „inną kwotę” i „spóźnioną” na granicy.
- Repo publiczne: testy tylko na syntetycznych nazwach, hook pre-commit.

## Cofnięcie

Przed update: poprzedni release v0.15.0 (reinstalacja wersji przez Supervisor). Tabela
`series_ack` jest addytywna, więc 0.15.0 działa na bazie po migracji 010. Commity kodu są
osobne i dają się odwrócić przez `git revert`.
