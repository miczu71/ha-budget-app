# Budżet: poprawki kalkulatora kredytu i tygodni prognozy

## Context
Trzy uwagi użytkownika do panelu 0.46.0 (`/config/addons/ha-budget-app`, gałąź `main`):
1. **Kredyt.** Tabela „Zmiana WIBOR przy tej nadpłacie” powtarza to, co suwak pokazuje na żywo. Decyzja: zwinąć ją w `<details>`, mieć 5 wierszy (−2, −1, 0, +1, +2 kroki) i wybór kroku 1 / 0,5 / 0,25 p.p.
2. **Paski tygodni** w „Prognoza do wypłaty”. Logika już przelicza bieżący i kolejne tygodnie z dzisiejszego limitu dziennego (`forecast.weeks`), więc przekroczenie obniża następne tygodnie po równo na dzień. Minione tygodnie mierzy plan z dnia wypłaty. Na ekranie brak wyjaśnienia, a przyszłe tygodnie nie mają paska. Decyzja: podpis + pusty pasek planu + „+X zł ponad plan” przy minionym przekroczeniu.
3. **Ostatni tydzień** (na żywo „19.10–22.10 · plan 722,68 zł”, wypłata pt 23.10) jest przycięty i nie wiadomo dlaczego. Decyzja: zostaje przycięty, z etykietą liczby dni („4 dni do wypłaty”). Pierwszy przycięty tydzień okresu dostaje symetrycznie „4 dni od wypłaty”.

Sukces: kalkulator kredytu jest krótszy (tabela zwinięta, liczona dopiero po rozwinięciu), a tygodnie da się zrozumieć bez pytania. Jedno wydanie na koniec (0.47.0).

## Etapy (commity; jedno wydanie na końcu)
Pierwszy krok implementacji: skopiować ten plan do `docs/PLAN_M9_M21_poprawki.md` i dopisać wiersz w `docs/ROADMAP.md`.

### E1: tabela WIBOR zwinięta, 5 wierszy, wybór kroku
- `budget/app/src/budget/loan_sim.py`: `DELTAS` → `variants(lo, scen, today, step=Decimal(1))` liczy delty `step × k` dla k ∈ −2…2 (dziś 4 wiersze −1…+2).
- `web/routes_loan.py` (calc, ~l. 114): parsuje `wibor_step` ∈ {1, 0.5, 0.25} (inaczej 1) i `table == "1"`. Tabelę liczy **tylko przy rozwiniętej sekcji**: dziś to 12 symulacji przy każdym ruchu suwaka, a CPU hosta jest wolny. Do partiala przekazuje `step`, `table_open`, `loan_id`.
- `web/templates/loan.html`: formularz dostaje `id="calc-form-{{ lo.id }}"` i dwa ukryte pola, `table` i `wibor_step`.
- `web/templates/_loan_calc.html`: `<details{{ ' open' if table_open }}>` z `<summary>`„Porównaj warianty przy innym WIBOR”. `ontoggle` ustawia ukryte `table` i przy otwarciu woła `htmx.trigger(form,'change')`. Wewnątrz `<select>` kroku (1 / 0,5 / 0,25 p.p.), którego `onchange` ustawia ukryte `wibor_step` i wyzwala formularz. Etykieta wiersza w formacie suwaka („+0,25 p.p.”, „0 p.p.”). Stan otwarcia przeżywa przeładowanie partiala, bo jedzie w formularzu.
- Testy: `tests/test_loan_sim.py::test_variants_table_rows_and_ordering` dla kroku 1 i 0,25 (5 wierszy, monotoniczne odsetki). Test trasy: bez `table=1` brak tabeli, z `table=1&wibor_step=0.5` wiersze ±1. Jeśli istnieją testy trasy calc, rozszerzyć je.

### E2: tygodnie: podpis, pasek planu, przekroczenie, liczba dni
- `forecast.py`: `Week.days` (property, `(end-start).days+1`). `Forecast.plan_per_day` = `plan_day` z `period_plan` (już liczone w `build`, tylko przekazać).
- `web/templates/_forecast.html` (sekcja „Tygodnie okresu”):
  - podpis pod `h3`: „Minione tygodnie liczę planem z dnia wypłaty ({{ plan_per_day }}/dz.), bieżący i kolejne dzisiejszym limitem ({{ safe_per_day }}/dz.). Wydasz więcej, kolejne tygodnie zmaleją po równo na każdy dzień.”
  - `week-next`: kwota „plan X” + `bar(0, "plan …")` (pusty pasek, ta sama wysokość wiersza).
  - `week-past` z `w.over`: dopisek `+{{ (w.spent - w.limit) | money }} ponad plan`.
  - tydzień z `w.days < 7`: ostatni → „· N dni do wypłaty”, pierwszy → „· N dni od wypłaty” (odmiana „1 dzień”).
- CSS (`static/app.css`) tylko gdy pusty pasek albo dopisek łamie wiersz przy 360 px.
- Testy: `Week.days`, render `_forecast.html` z tygodniem przyciętym, przekroczonym i next (istniejące testy home/forecast jako wzór).

### Wydanie (po E2)
`simplify` → testy (`BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, ruff, mypy) → skill `release` (0.47.0, published, cache-busting, znacznik wersji) → poza oknem 02:45–03:15.

## Ryzyka
- Inline JS w `ontoggle`/`onchange` musi trafić w formularz z poprawnym id. Sprawdzić przy dwóch kredytach na stronie.
- Zmiana sygnatury `variants` ma tylko jednego wołającego (`routes_loan.py:114`) i jeden test.
- WebView Companion: obsługuje to skill release (wersjonowane statyki + `X-Panel-Version`).

## Weryfikacja
1. Testy, ruff i mypy na zielono.
2. Lokalny devserve na kopii `~/budget_dev`, Playwright 390 px: kredyt (tabela zwinięta, rozwinięcie liczy, zmiana kroku 0,25 daje wiersze −0,5…+0,5, wpisanie nadpłaty nie zwija sekcji), Podsumowanie (podpis, pusty pasek planu, „N dni do wypłaty”), konsola bez błędów. Zrzuty do scratchpada, potem skasować (finanse).
3. Po wydaniu: na żywo `/app/a9413a25_budget`, stopka v0.47.0, ten sam przegląd obu ekranów.
