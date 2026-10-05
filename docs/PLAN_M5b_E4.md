# M5b E4 (0.17.0) — pula Flex ze stałymi z serii

## Context

Checkpoint E3 (0.16.0, zmiany serii) zamknięty przez użytkownika 2026-10-05. Ostatni etap M5b
(`docs/PLAN_M5b.md`, decyzja 4) to E4: pula liczy stałe z potwierdzonych serii zamiast samych
median podkategorii, a transakcje serii wypadają z „wydane” elastycznych. Dziś seria w
podkategorii elastycznej (np. subskrypcja w „Rozrywce”) zjada pulę dwa razy: raz w „wydane”,
drugi raz nie ma jej w stałych. Z kolei mediana podkategorii „stałe” myli się przy płatnościach
kwartalnych i rocznych. Po E4 pula = wpływy − (serie w przeliczeniu na miesiąc + mediany
stałych spoza serii).

## Reguły

1. **Seria liczy się do puli**, gdy jest aktywna, wydatkowa i jej ostatnia transakcja **nie** ma
   kategorii z grupy `savings` / `income` / `excluded` (decyzja z wywiadu 2026-10-05: oszczędności
   nie zmniejszają puli, zgodnie z decyzją 14). Seria bez transakcji też się liczy. Pozostałe serie
   nadal są widoczne w Cyklicznych i w encjach `fixed_*`, a ich transakcje liczą się jak dotąd.
2. **Stałe w puli** = Σ `Series.monthly` serii liczonych + Σ median podkategorii `fixed`
   policzonych **bez transakcji tych serii** (bez podwójnego liczenia).
3. **„Wydane” elastycznych** (bieżący miesiąc, historia i podpowiedź kwoty, linie kategorii, bez
   kategorii) liczone bez transakcji serii liczonych. Przynależność do serii liczona od zera,
   więc obowiązuje też wstecz.
4. „Poza pulą” (informacyjnie): „Stałe” i „Nieregularne” bez transakcji serii + nowy wiersz
   „Cykliczne” (zapłacone w miesiącu z serii liczonych). Suma grup dalej równa się wydatkom.
5. Kwota ręczna się nie zmienia, zmienia się tylko „wydane”. Serie wpływów nie wpływają na pulę.

## Kroki (po kolei, testy po każdym)

0. **Plan do repo:** `docs/PLAN_M5b_E4.md` (ten plan bez kwot użytkownika), w `PLAN_M5b.md`
   decyzja 4 dostaje dopisek o seriach oszczędnościowych, `ROADMAP.md` M5b dostaje „✅ checkpoint
   E3 zamknięty 2026-10-05; plan E4 zaakceptowany”. Commit `docs(M5b): checkpoint E3 zamknięty,
   plan etapu E4`. Najpierw `test -x .git/hooks/pre-commit`.

1. **`spending.py`:** `sums(..., skip: Collection[int] = ())` i `_rows` z `t.id`. Transakcje
   z `skip` są pomijane. Ekran Wydatki się nie zmienia (domyślnie pusty `skip`).

2. **`flex.py`:**
   - `SeriesLine(series, monthly)`; `_pool_series(conn) -> (lines, skip_ids, paid_by_month)`:
     `S.all_series(conn, ("active",))` + `S.assign(..., S.candidates(conn))`, filtr z reguły 1
     (grupa z `taxonomy.leaves` po `category_id` ostatniej transakcji; potrzebny jest
     `category_id` w `Candidate`, więc dodaję go w `series.candidates`, bez osobnego zapytania).
   - `_history`, `build` i `auto_budget` używają `sums(..., skip=skip_ids)`.
   - `AutoBudget.series_lines`; `fixed = Σ median + Σ monthly`; `FlexMonth.recurring`
     (zapłacone w miesiącu z serii liczonych).
   - Docstring modułu: punkt o E4.

3. **`budget.html`:** w rozwinięciu „Koszty stałe” najpierw sekcja „Płatności cykliczne” (nazwa
   z linkiem do serii, kadencja, kwota na miesiąc), potem dotychczasowe podkategorie
   („mediany spoza serii”) i nowy opis sumy. W „Poza pulą” wiersz „Cykliczne”.
   `routes_budget.py` bez zmian logiki (komunikat po „Przenieś” liczy `auto_budget` jak dotąd).

4. **`ha_publisher.py`:** `flex_budget` dostaje nowy atrybut `fixed_series` (suma serii);
   `fixed_median` zostaje pod tą samą nazwą (= całe stałe), żeby nie psuć odwołań.

5. **Testy i pomiar:** `test_flex.py` (seria w podkategorii elastycznej: nie ma jej w
   „wydane”, jest w stałych; seria w podkategorii `fixed`: mediana bez niej, brak podwójnego
   liczenia; Q i Y w przeliczeniu ⅓ i 1/12; seria oszczędnościowa pominięta; seria zakończona
   i propozycja nie wpływają; suma grup = wydatki), `test_web_budget.py` (render sekcji serii,
   wiersz „Cykliczne”), `test_ha_publisher` (atrybut). `pytest` + ruff + mypy
   (`BUDGET_OPTIONS_PATH=/nonexistent`, `budget/app/.venv`). Sonda w scratchpadzie na świeżej
   kopii `~/budget_dev/prod/ledger.db` (migracje, wykrywanie, potwierdzenie propozycji): pula
   przed i po, liczba serii pominiętych regułą 1, czas `flex.build`. Panel dev + Playwright
   mobile, 0 błędów konsoli; kopię usuwam.

6. **Wydanie 0.17.0** skillem `release` (bump `budget/config.yaml`, CHANGELOG, opublikowany
   release). **Update add-onu `a9413a25_budget` przez `ha_manage_app` robię dopiero po Twoim
   „go” na wydanie.** Weryfikacja: log add-onu, `sw_version` 0.17.0, `sensor.budget_flex_budget`
   (nowe `auto_amount`, `fixed_median`, `fixed_series`) w porównaniu ze stanem sprzed wydania (odczyt encji przed update). Potem
   § Wynik w `PLAN_M5b_E4.md`, `ROADMAP.md` i pamięć `project_budget_app`.

7. **Checkpoint E4 = zamknięcie M5b:** zatrzymuję się. Na checkpoincie porównujesz pulę przed
   i po w panelu (rozwinięcie „Koszty stałe”). Bez commitów w oknie 02:45–03:15.

## Pliki

`budget/app/src/budget/spending.py`, `flex.py`, `recurring/series.py` (`Candidate.category_id`),
`ha_publisher.py`, `web/templates/budget.html`, testy w `budget/app/tests/`,
`docs/PLAN_M5b_E4.md`, `docs/PLAN_M5b.md`, `docs/ROADMAP.md`, `budget/config.yaml`, `CHANGELOG`.
Gałąź: `main`. Bez migracji bazy.

## Ryzyka

- Seria o zmiennej kwocie (np. media) wchodzi do puli oczekiwaną kwotą, a nie medianą. To
  zamierzone (decyzja 4), a rozjazd pokazują karty „inna kwota” z E3.
- Seria, która złapie za dużo (szerokie warunki), zabierze transakcje z „wydane”. Sonda porówna
  „wydane” przed i po per miesiąc. Jeśli spadek wyjdzie wyraźnie większy niż suma serii,
  zatrzymuję się przed wydaniem.
- Wydajność: `assign` po wszystkich kandydatach przy każdym `build`. Mierzę w sondzie.
  E3 mierzył ~18 ms.
- Repo publiczne: testy tylko na syntetycznych nazwach, hook pre-commit.

## Cofnięcie

Bez migracji: reinstalacja v0.16.0 przez Supervisor przywraca stare liczenie. Commity są
osobne i dają się odwrócić przez `git revert`.

## Wynik

2026-10-05: 0.17.0 wydane i zainstalowane (479 testów, CI zielone, release v0.17.0, bez migracji).
Sonda na kopii księgi: 19 propozycji → 14 aktywnych serii wydatkowych, żadna pominięta regułą
oszczędności; `flex.build` ~20 ms; spadek „wydane” mniejszy niż suma serii. Panel dev: Playwright
mobile, 0 błędów konsoli. Na żywo: log add-onu bez błędów, MQTT połączone, `sensor.budget_flex_budget`
po odświeżeniu = 6 103,98 zł (przed: 6 230,76 zł), stałe 8 424,88 zł (z tego serie 8 358,48 zł,
atrybut `fixed_series`), `sensor.budget_inbox` = 0. Panel przez Ingress niesprawdzony przez Claude
(proxy ha-mcp 403) — do obejrzenia przez użytkownika na checkpoincie. Checkpoint E4 = zamknięcie M5b.

Poprawka 0.17.1 (2026-10-05, wywiad po E4): oczekiwana kwota serii wpływowej to mediana 6 wpływów,
więc po spadku wypłaty (II próg) była zawyżona, a tolerancja z rozrzutu chowała zmianę przed kartą
„inna kwota”. Od 0.17.1 nowa propozycja serii wpływowej = ostatni wpływ niebędący premią
(> 1,5 × mediany ogona pomijany), tolerancja 10%; wydatki bez zmian. Istniejące serie nie są
przeliczane — kwotę i tolerancję poprawia użytkownik w Cykliczne → Edytuj. Zainstalowane
2026-10-05 13:15 (481 testów, log bez błędów).
