# M28 — Kredyt: porządek formularza + edytowalne zakładki (wydanie 0.48.0)

## Context
- Niewydana poprawka `f3ab453` (M27 E2, „ponad plan” w osobnej linii, 390 px) czeka na wydanie → idzie razem z M28.
- Karta kredytu: select „Seria rat w księdze” ustawia się raz, a stale zajmuje miejsce.
- „Stopa oszczędności (% rocznie)” w kalkulatorze jest niezrozumiała: to oprocentowanie konta, z którym
  porównujemy nadpłatę (zysk po Belce); puste = pierwsze konto oszczędnościowe z promocją.
- Użytkownik chce ustawiać kolejność zakładek u góry (Podsumowanie zawsze pierwsze) i móc je ukrywać.

Decyzje (AskUserQuestion): seria → formularz „Zmień” + jedna linia-zachęta, gdy brak serii; stopa → zostaje
z lepszą etykietą i podpisem; zakładki → kolejność + ukrywanie, edytor w menu ⚙ „Więcej”, wspólne dla urządzeń.

Repo: `/config/addons/ha-budget-app` (`main`), kod `budget/app/src/budget/`. Pierwszy krok: ten plan →
`docs/PLAN_M28.md` + wiersz M28 w `docs/ROADMAP.md`.

## E1 — Kredyt: seria w formularzu, opis stopy oszczędności (commit)
- `web/templates/loan.html`:
  - usuń formularz `/loan/{id}/series` z karty; w `loan_form` dodaj `<select name="series_id">`
    (te same opcje: „— bez serii —” + `series`) z podpisem „pozwala wykryć zmianę raty w księdze”.
  - na karcie: gdy `lo.series_id is none` → `<p class="small muted">Powiąż serię rat, żeby panel wykrył zmianę raty. <a … ?edit=id#edit-loan>Zmień</a></p>`;
    linia „Wpisano X na dzień” zostaje (bez zdania o serii).
  - kalkulator: etykieta „Oprocentowanie oszczędności (% rocznie)” + `<p class="small muted">` pod polem:
    „Z tym oprocentowaniem porównujemy nadpłatę (zysk po podatku Belki). Puste = konto „{{account.name}}”
    z promocją.” (bez konta: „Puste = 0%”).
- `web/routes_loan.py`: w `save()` po `loan.save(...)` → `loan.set_series(conn, id, …)` z pola `series_id`
  (łap też `S.SeriesError`); usuń trasę `POST /loan/{id}/series` (osierocona). `loan.set_series` zostaje.
- Testy: web test — zapis formularza z `series_id` ustawia/odpina serię; karta bez serii pokazuje zachętę,
  z serią nie pokazuje selecta.

## E2 — Edytowalne zakładki (commit)
- Uogólnij `home_layout.py`: logika `load/move/toggle/reset` jako klasa `Layout(kv_key, items, pinned=())`;
  `home_layout` = `Layout("home_layout", TILES)` z zachowaniem obecnego API dla `routes_home` (testy
  `test_home_layout.py` przechodzą bez zmian albo z minimalną zmianą wywołań). `pinned` = klucze stałe
  na początku: nie przesuwalne, nie ukrywalne, nic nie wskoczy przed nie.
- `nav_layout` (w tym samym module albo `nav_layout.py`): `TABS` = key → (etykieta, ścieżka, strony „on”)
  dla 9 obecnych zakładek, `home` przypięte. Ukryta zakładka znika z paska (dalej dostępna z URL).
- `web/common.py` `render()`: kontekst `tabs=nav.load(self.conn)` (widoczne); `base.html` renderuje `<nav>`
  pętlą zamiast 9 stałych linków; w „Więcej” nowa pozycja „Zakładki” (`page == 'tabs'`, dodaj do `more_pages`).
- Strona `GET /tabs` + `POST /tabs/move|toggle|reset` (htmx, jak `/layout/*` w `routes_home.py:133-157`);
  szablon: sparametryzuj `_home_layout.html` (`url`, nagłówek, link „Gotowe”) i użyj go w obu miejscach
  zamiast kopii. Wiersz „Podsumowanie” bez przycisków, z dopiskiem „zawsze pierwsza”.
- Testy: kolejność/ukrywanie/reset, pinned nie rusza się i nie ukrywa, nowa zakładka w kodzie wskakuje za
  poprzednika, `base.html` renderuje zapisaną kolejność i pomija ukryte.
- UI przez skill `impeccable` (lekko: istniejący wzorzec), weryfikacja Playwright 390 px i desktop.

## Wydanie 0.48.0 (jedno, na koniec)
- `simplify` → ruff/mypy/pytest → skill `release` (bump `budget/config.yaml`, cache-busting `?v=` jest
  automatyczny przez `version`, published release, aktualizacja add-onu, Playwright na żywo: karta kredytu,
  kalkulator, edytor zakładek, poprawka 390 px z 0.47.1). Bez commitów 02:45–03:15.
- Po wydaniu: wynik w `docs/ROADMAP.md` (M27 „poprawka wydana w 0.48.0”, M28 wydane), notatka pamięci budżetu.

## Ryzyka
- `render()` czyta kv przy każdej stronie — jeden SELECT, pomijalne.
- Usunięcie trasy `/loan/{id}/series`: stare zakładki/linki nie istnieją poza formularzem — bezpieczne.
- Ukrycie wszystkich zakładek poza Podsumowaniem — dozwolone; edytor zawsze w ⚙.

## Weryfikacja
- `BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, ruff, mypy w `budget/app`.
- Lokalny panel na `~/budget_dev/prod/ledger.db` (kopia) + Playwright: screenshot karty kredytu (bez selecta,
  z zachętą/bez), kalkulatora, `/tabs` (przesuń, ukryj, reset), pasek nav po zmianie; konsola bez błędów.
- Po wydaniu: to samo na żywo przez `playwright-ha`, wersja w stopce = 0.48.0.
