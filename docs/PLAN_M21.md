# M21 — Okres wypłaty jako główna oś Podsumowania

## Context
Na Podsumowaniu są dziś dwie karty o różnych horyzontach: hero „Zostało na elastyczne” (miesiąc
kalendarzowy, `_flex_hero.html`) i kafelek „Do wypłaty” (prognoza M8, `_forecast.html`). Planujesz
jednak od głównej wypłaty do następnej, więc hero ma mówić o okresie wypłaty, a miesiąc ma być
dodatkiem. Druga sprawa: termin wypłaty bierze się z dnia serii (`anchor_day`, dziś 24.10), a
faktyczną datę (np. 23.10) poznajesz ok. 10. dnia miesiąca. Ma się dać ją wpisać ręcznie, a add-on
ma przeliczyć prognozę.

Decyzje z wywiadu (2026-10-09):
- hero = „limit do wypłaty” zbudowany na istniejącej prognozie M8, a nie osobny budżet okresowy;
  karta miesięczna zostaje jako zwykły kafelek;
- datę wypłaty ustawiasz tylko w panelu, bez przypomnienia w dzwonku i bez encji w HA.

Ograniczenia:
- korzystasz ty (panel, telefon); encje HA zmieniają się same, bo czytają tę samą prognozę;
- automatycznie: przeliczenie po wpisaniu daty; ręcznie: tylko wpisanie daty;
- sukces: po wpisaniu 23.10 hero, lista „Co jeszcze zejdzie”, encja `budget_forecast_at_payday`
  (`payday`) i ICS pokazują 23.10; hero odpowiada na pytanie „ile dziennie do wypłaty”.

Gałąź `main`. Każdy etap kończy się wydaniem przez skill `release`.

## Etapy

### E0 — dokumenty
`docs/ROADMAP.md` (wiersz M21) i `docs/PLAN_M21.md` (ten plan) w repo, przed kodem.

### E1 — ręczna data wypłaty
- `forecast.py`: klucz kv `PAYDAY_DATES_KEY = "payday_dates"` → `{"2026-10": "2026-10-23"}` (jeden wpis
  na miesiąc, więc stare daty nie przechodzą na kolejne okresy); `payday_dates(conn)` i `set_payday_date`.
- `recurring/schedule.py`: `month_view(..., due_overrides=None)` z mapą `{(series_id, "YYYY-MM"): date}`
  (wzór jak `acks`); w miejscu `dues = {m: due_date(...)}` nadpisanie terminu. `for_month` czyta
  nadpisanie tylko dla serii wypłaty (`forecast.payday_series_id`), żeby forecast, „Co jeszcze zejdzie”,
  kalendarz ICS i dopasowanie wpływu (MATCH_DAYS wokół nowej daty) były spójne w jednym miejscu.
  Uwaga na cykl importów forecast ↔ schedule: klucz i odczyt kv trzymać w `schedule` (albo w małym
  module), a `forecast` tylko z niego korzysta.
- Panel: w nagłówku karty „Do wypłaty — 24.10” link/pole `<input type="date">` „Zmień datę”
  (min = jutro, w miesiącu terminu), POST `/forecast/payday-date` w `routes_home.py` (wzór:
  `/forecast/card-debt`, htmx `#fc`), plus „przywróć dzień z serii”. Dopisek „data ustawiona ręcznie”.
  Walidacja: data > dziś, najwyżej 2 miesiące naprzód; bez serii wypłaty pole jest ukryte.
- Testy: `month_view` z nadpisaniem (termin, status, dopasowanie wpływu ±MATCH_DAYS), `project` kończy
  horyzont na nadpisanej dacie, route (zła data → komunikat błędu).

### E2 — hero = okres wypłaty, miesiąc jako kafelek
- `home.html`: na górze, dla bieżącego miesiąca i gdy jest `fc`, nowy partial `_payday_hero.html`:
  „Do wypłaty — 23.10 · za 14 dni”, główna liczba = `fc.safe_per_day` („możesz wydawać X zł/dzień”),
  pod nią werdykt (zapas/zabraknie na dzień wypłaty) z `_forecast.html`. Szczegóły (pasek równania,
  wykres, oś zdarzeń) zostają w kafelku „forecast” (nazwa w `home_layout.TILES` → „Prognoza do wypłaty”).
- `home_layout.TILES`: nowy klucz `"month": "Zostało na elastyczne (miesiąc)"` renderujący obecny
  `_flex_hero.html`; `load()` dokłada nowe kafelki na koniec, więc trzeba go wstawić za „forecast”
  (jednorazowo w `load`, gdy `month` nie ma w zapisanym `order`).
- Bez `fc` (brak sald) albo dla minionych miesięcy hero zostaje jak dziś (`_flex_hero.html`), bez zmian.
- Weryfikacja UI: Playwright (screenshot telefon/desktop + konsola), cache-busting statyk.

### E3 — „wydane od wypłaty” i pasek okresu
- Początek okresu = data ostatniej zapłaconej wypłaty z serii (ostatnia transakcja członka serii
  wypłaty, `S.assign`), a bez niej 1. dzień miesiąca.
- Wydane = ta sama definicja co `flex._spent` (elastyczne + bez kategorii, bez transakcji serii z puli),
  `spending.sums(conn, period_start, tomorrow, pool.skip)`, bo `sums` przyjmuje dowolne daty.
- W hero: „od 25.09 wydane 2 900 zł” + pasek „minęło X% okresu”, styl `.flex-bar`.
- Ewentualnie atrybut `period_start`/`spent_since_payday` w encji `budget_forecast_at_payday`.

## Pliki
`budget/app/src/budget/{forecast.py,recurring/schedule.py,home_layout.py,web/routes_home.py}`,
`web/templates/{home.html,_forecast.html,_payday_hero.html (nowy)}`, `static/app.css`, testy w
`budget/app/tests/`, `docs/ROADMAP.md`, `docs/PLAN_M21.md`, `budget/config.yaml` (wersja).

## Ryzyka
- Nadpisanie terminu w `schedule` dotyka statusów (PAID/LATE) serii wypłaty: test dopasowania.
- Encja i dzwonek liczą prognozę przez `ForecastMemo` (sygnatura bazy): zapis kv musi zmieniać
  `snap.signature()`; sprawdzić, czy `kv_set` ją zmienia, a jeśli nie, dołożyć do klucza memo.
- Zmiana kolejności kafelków u ciebie: migracja w `load` tylko dodaje „month”, niczego nie ukrywa.

## Weryfikacja
- `BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, ruff, mypy (w `budget/app`).
- Lokalny panel na kopii bazy deweloperskiej + Playwright: wpisanie 23.10 → nagłówek, oś zdarzeń, lista
  „Co jeszcze zejdzie” i `/calendar.ics` pokazują 23.10; reset przywraca 24.10.
- Po wydaniu: `ha_get_state(sensor.budget_forecast_at_payday)` → `payday: 2026-10-23`; screenshot panelu
  w HA (playwright-ha).
