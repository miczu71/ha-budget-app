# M5b E2 (0.15.0) — „Ten miesiąc”: co zejdzie / co wpłynie

## Context

M5b E1 (0.14.0: dzwonek, detektor, zakładka „Cykliczne”, potwierdzanie serii) zamknięty
przez usera 2026-10-05. Następny etap wg `docs/PLAN_M5b.md`: E2 odpowiada na pytanie A —
„co jeszcze zejdzie (i wpłynie) w tym miesiącu?”. Teraz serie są tylko listą; E2 daje im
termin i status w miesiącu, sumy, serię ręczną z transakcji i 3 encje MQTT. Pula Flex bez
zmian (E4), zmiany serii w dzwonku — E3.

Decyzje z wywiadu (2026-10-05):
- Widok: sekcja „Ten miesiąc” na górze zakładki Cykliczne **+ jedna linia na ekranie Budżet**
  („cykliczne: zapłacone X · jeszcze zejdzie Y · jeszcze wpłynie Z” → link do Cykliczne).
- Seria ręczna: „to się powtarza” na Transakcjach otwiera **formularz serii wypełniony
  z transakcji** (nazwa, `merchant equals` + kierunek, kwota, dzień, kadencja M), podgląd
  objętych transakcji, zapis = seria od razu aktywna.

Domyślne reguły (bez pytania, do korekty przy akceptacji):
- Liczą się tylko serie `active` (decyzja 1); zakończone/propozycje — nie.
- Termin: M = `anchor_day` w danym miesiącu (obcięty do ostatniego dnia); Q/Y = ostatnie
  wystąpienie przed miesiącem + k×kadencja (miesiące kalendarzowe) — seria bez wystąpień Q/Y
  nie ma terminu. Okno ±5 dni.
- Transakcja serii przypisana do **najbliższego terminu** (płatność 30. na termin 1. liczy się
  raz, do miesiąca terminu). Wystąpienie poza każdym oknem w miesiącu = „dodatkowe”, wlicza
  się do „zapłacone”.
- Status: **zapłacone** / **oczekiwane** (dziś ≤ termin+5) / **spóźnione** (dziś > termin+5,
  bez transakcji). Spóźnione nadal liczą się do „jeszcze zejdzie/wpłynie” (do „pomiń ten
  okres” w E3). Miesiące przeszłe (`?month=`): zamiast „spóźnione” — „brak płatności”.
- Kwota „zapłacone” = rzeczywista suma transakcji; „jeszcze” = `expected_amount`.

## Kroki (każdy krok po kolei, testy po każdym)

0. **Plan do repo:** `docs/PLAN_M5b_E2.md` (treść tego planu, bez kwot usera), wpis w
   `ROADMAP.md` (M5b: „plan E2 zaakceptowany”), commit `docs(M5b): plan etapu E2`.
   Sprawdzić hook: `test -x /config/addons/ha-budget-app/.git/hooks/pre-commit`.

1. **`recurring/schedule.py`** (nowy, czysta logika):
   `due_dates(s, members, month)`, `month_view(series, members, month, today) -> MonthView`
   z wierszami `Due(series, due, status, paid_amount, txns)` + sumy `out_paid`,
   `out_planned`, `in_received`, `in_planned`. Wejście = `S.all_series` + `S.assign(...)`
   z `recurring/series.py` (bez nowych zapytań).
   Pamięć wyniku `assign` po sygnaturze bazy — wzorzec `inbox.BalanceMemo` — tylko jeśli
   pomiar w kroku 6 pokaże render Transakcji/Budżetu > ~50 ms.

2. **Cykliczne „Ten miesiąc”** (`web/routes_recurring.py`, `recurring.html`): sekcja nad
   propozycjami — 4 sumy, lista po terminie ze statusem (plakietki), `?month=RRRR-MM`
   ze strzałkami jak „Wydatki” (`spending.add_months/month_label`).

3. **Seria ręczna:** wydzielić formularz z `series.html` do `_series_form.html`
   (warunki przez `_rule_conditions.html` + `web/rule_form.py`);
   `GET /recurring/new?txn=ID` (formularz z podpowiedziami), `POST /recurring/new/preview`
   (htmx: ile i które transakcje obejmie — `S.assign` z tymczasową serią),
   `POST /recurring/new` → `S.insert(status="active", origin="manual",
   key=S.group_key(...))` (detektor nie zaproponuje tej grupy ponownie).
   `anchor_day` = dzień transakcji.

4. **Transakcje** (`routes_transactions.py`, `transactions.html`): w „Szczegółach”
   plakietka serii (link `/recurring/{id}`) dla transakcji należących do serii, a dla
   kandydatów bez serii link „to się powtarza” → `/recurring/new?txn=ID`.

5. **Budżet + encje:** linia na `budget.html` (`routes_budget.py` podaje `MonthView`);
   `ha_publisher.recurring_entities(conn, today)` obok `flex_entities` (z tym samym
   `try/except`): `sensor.budget_fixed_paid`, `sensor.budget_fixed_planned`,
   `sensor.budget_income_planned` (stan = kwota, atrybuty: `month`, liczby
   zapłaconych/oczekiwanych/spóźnionych, `items` [nazwa, termin, kwota, status]);
   odświeżanie istniejącym `refresh`/`refresh_soon`/`daily_tick`.

6. **Testy i pomiar:** `test_recurring_schedule.py` (M/Q/Y, anchor 31 w lutym, płatność
   przed/po granicy miesiąca, dodatkowe wystąpienie, spóźnione vs brak płatności, seria Q/Y
   bez historii), `test_web_recurring.py` (new/preview/new POST, `?month=`), plakietka
   na Transakcjach, encje w `test_ha.py`. `pytest` + ruff + mypy
   (`BUDGET_OPTIONS_PATH=/nonexistent`, venv `budget/app/.venv`). Panel dev w scratchpadzie
   na kopii `~/budget_dev/prod/ledger.db` (+ `engine.recategorize`, serie wstawione testowo):
   czasy renderu Transakcji/Budżetu/Cykliczne, Playwright mobile, 0 błędów konsoli; kopię
   usunąć.

7. **Wydanie 0.15.0** skillem `release` (bump, README: encje + ekrany, release notes), update
   add-onu `a9413a25_budget` przez `ha_manage_app` (>300 s → sprawdzać `ha_get_app`),
   weryfikacja przez Ingress: `/recurring`, `/budget`, `/transactions`; encje przez
   `ha_get_device`. `PLAN_M5b_E2.md` § Wynik, `ROADMAP.md`, memory.
   **Update add-onu = akcja produkcyjna — tylko po Twoim „go” na wydanie.**

8. **Checkpoint E2:** stop; przeglądasz „Ten miesiąc” na żywo. E3 dopiero po „go”.

## Ryzyka

- `S.assign` na wszystkich kandydatach przy każdym renderze Transakcji/Budżetu (wolny CPU
  GX-415GA) — zmierzyć w kroku 6, ewentualnie memo (krok 1).
- Seria M z `anchor_day` blisko granicy miesiąca (np. 1.) — reguła „najbliższy termin” musi
  być pokryta testami, inaczej podwójne/brakujące zapłacone.
- Repo publiczne: testy na syntetycznych nazwach, hook pre-commit.

## Weryfikacja

- `pytest` zielony, ruff, mypy.
- Panel dev + Playwright mobile: Cykliczne „Ten miesiąc”, poprzedni miesiąc, „to się
  powtarza” → formularz → podgląd → zapis → seria aktywna z transakcjami, plakietka na
  Transakcjach, linia na Budżecie.
- Na żywo przez Ingress + 3 nowe encje w `ha_get_device`.

## Wynik

2026-10-05: 0.15.0 wydane i zainstalowane (462 testów, release v0.15.0). Panel dev na kopii
księgi (19 serii potwierdzonych na potrzeby pomiaru): `/budget` ~60 ms, `/recurring` ~45 ms,
`/transactions` ~30 ms, encje ~15 ms — pamięć podręczna `assign` niepotrzebna. Plakietkę serii
na Transakcjach liczy się tylko dla transakcji bieżącej strony (`S.candidates(conn, ids)`).
Playwright mobile: 0 błędów konsoli, podgląd serii ręcznej działa. Decyzje wykonawcze:
promień 15 dni do najbliższego terminu; seria Q/Y przesuwa harmonogram wystąpieniem w innym
miesiącu; brak płatności w minionym miesiącu nie liczy się do „jeszcze zejdzie”. Na żywo:
update add-onu OK, log bez błędów, urządzenie MQTT `sw_version` 0.15.0, 3 nowe encje
zarejestrowane; panel przez Ingress niesprawdzony przez Claude (proxy ha-mcp 403, brak LLAT) —
do obejrzenia przez użytkownika na checkpoincie. Checkpoint E2 czeka; E3 (0.16.0) po „go”.
