# M8 E1 — „Do wypłaty” na Podsumowaniu (0.25.0)

## Kontekst
Według `docs/ROADMAP.md` po zamkniętym M15 E1–E3 (0.24.3 na produkcji, potwierdzone przez
użytkownika) kolejny jest M8: „czy starczy do wypłaty” (`docs/PLAN_M8.md`, decyzja 17). E1 to
obliczenie i widok, bez encji i bez dzwonka (to E2). Wynik: na Podsumowaniu jest kwota na dzień
wypłaty i najniższy punkt z datą, z jawnym rozbiciem, w tym z odjętym zadłużeniem karty.

Repo: `/config/addons/ha-budget-app`, gałąź `main`. Kod i commity po angielsku, dokumenty po polsku.

## Krok 0 — dokumenty (pierwszy commit, przed kodem)
- `docs/PLAN_M8_E1.md` = ten plan.
- `docs/ROADMAP.md`: w wierszu M15 „E3 … czeka checkpoint” → „0.24.3 (Karta jako główna zakładka),
  ✅ M15 E1–E3 zamknięte przez użytkownika 2026-10-06”. W wierszu M8: „E1 plan (`PLAN_M8_E1.md`)”.
- Commit: `docs(M8 E1): step plan; close M15 E1-E3 in roadmap`.

## Krok 1 — sprawdzenie założenia o saldzie rachunku (tylko odczyt)
Rachunek PLN ma `ITBD` (zaksięgowane) i `ITAV` (dostępne). Porównuję atrybuty `balance_itav` i
`balance_itbd` encji salda rachunku (`ha_get_state`). Jeśli są równe albo różnią się blokadami
autoryzacji, biorę **ITAV**, bo autoryzacje już zmniejszyły wolne środki. Jeśli ITAV zawiera
limit debetu (jest wyraźnie wyższe), biorę **ITBD**. Wynik ogłaszam przed krokiem 2.
Karta: **ITBD** = bieżące zadłużenie, bo ITAV karty jest opóźnione (FINDINGS).

## Krok 2 — moduł `budget/app/src/budget/forecast.py` (nowy, czysta logika + jedno wejście z bazy)
- `@dataclass Forecast`: `account_balance`, `card_debt`, `balance_at` (fetched_at najstarszej z dwóch
  migawek), `free_now`, `series_out` (lista `schedule.Due`), `flex_rest`, `flex_per_day`, `inflows`
  (lista `Due` wpływów przed wypłatą), `payday: date | None`, `payday_series: str | None`,
  `at_payday`, `low: Decimal`, `low_day: date`, `days: list[tuple[date, Decimal]]`, `eur: Decimal | None`,
  `stale: bool`.
- `build(snap, today, now, buffer) -> Forecast | None` (None, gdy brak migawki rachunku PLN):
  1. Salda z ostatniej migawki `balance_snapshot` (wzorzec zapytania jak w `ha_publisher.build_entities`).
  2. Terminy: reużyć `calendar_ics.dues(snap, today, days=62)`, statusy EXPECTED/LATE (spóźnione
     liczone na dziś). Wypłata = najbliższy termin aktywnej serii `direction="in"` o największej oczekiwanej
     kwocie (decyzja użytkownika 2026-10-06, PLAN_M8 pkt 2); spóźniony wpływ jest pomijany.
     Bez serii wpływów → koniec miesiąca. Terminy: bieżący miesiąc z trasy (`mv`), kolejne tylko
     do czasu znalezienia wypłaty.
  3. Flex: `flex.build(snap, month_start(today), today)`. Reszta puli = `max(remaining, 0)` rozłożona
     po równo na dni od jutra do końca miesiąca (dzisiejsze wydatki są już w saldzie). Pula
     przekroczona → tempo `spent / day`. Dni z następnego miesiąca liczone tym samym `per_day`
     (założenie z PLAN_M8).
  4. Pętla dzień po dniu od dziś do dnia wypłaty: saldo −= Flex na dzień, −= serie w ich dniu,
     += wpływy w ich dniu. Dzień wypłaty: przed wpływem wypłaty, bo liczy się dno.
     `low`/`low_day` = minimum.
  5. `stale` = migawka starsza niż doba.
- Bez nowych tabel i migracji.

## Krok 3 — opcja `forecast_buffer`
- `budget/config.yaml`: `options.forecast_buffer: 0`, `schema.forecast_buffer: "int(0,1000000)"`.
- `settings.py`: pole `forecast_buffer: int = 0`.
- `translations/pl.yaml`, `en.yaml`: opis. `DOCS.md`: krótka sekcja „Prognoza do wypłaty”.
- W E1 bufor wpływa tylko na widok: czerwony najniższy punkt i dopisek „poniżej bufora X zł”.

## Krok 4 — widok na Podsumowaniu
- `web/routes_home.py`: dla `f.is_current` → `fc=forecast.build(...)` (try/except jak przy podglądach
  w Status, żeby prognoza nie mogła zablokować strony głównej).
- Nowy szablon `templates/_forecast.html` dołączony w `home.html` pod kartą „Zostało”: rozbicie
  wierszami dokładnie wg PLAN_M8. Wiersz karty widać zawsze, z godziną odczytu. Serie (N) i wpływy
  rozwijane w `<details>`. Do tego linia „najniższy punkt: kwota (data)” i dopisek przy `stale`.
  EUR jako osobna informacja. Cele dotyku ≥ 44 px (reguły M13).
- Wykres: `charts.py` → `forecast_line(days, buffer)` = prosty SVG po stronie serwera, z linią
  zerową i linią bufora, w stylu istniejących `BarChart` (Monarch: monochromat + pomarańczowy akcent).
- `app.css`: style sekcji. Wersja CSS rośnie z wydaniem (`?v=`).

## Krok 5 — testy (pierwszy plan, przed implementacją każdej części, TDD)
- `tests/test_forecast.py`: brak migawki → None; brak serii wpływów → koniec miesiąca; seria wydatku
  przed wypłatą odjęta, po wypłacie nie; spóźniona seria liczona dziś; pula przekroczona → tempo;
  horyzont przez koniec miesiąca; dno w dniu przed wypłatą; zadłużenie karty 0 → wiersz jest;
  stale; bufor.
- `tests/test_web_home.py`: sekcja widoczna w bieżącym miesiącu, brak w minionym, brak przy braku
  migawki; `test_addon_config.py` / `test_settings.py`: nowa opcja.
- Pełny `pytest` + ruff jak w CI.

## Krok 6 — weryfikacja lokalna UI
- Dev panel (`devserve.py` w scratchpadzie, kopia `~/budget_dev/prod/ledger.db` + syntetyczne serie
  przez `detect.run` + `series.set_status`). Playwright: zrzut 390 i 1280 px, konsola bez błędów,
  pomiar celów dotyku.
- Skill `simplify` przed commitem. Hook pre-commit (skan prywatnych nazw) bez obchodzenia.

## Krok 7 — wydanie 0.25.0 (skill `release`)
- Bump `config.yaml`, `__init__.py`, `pyproject.toml`; `CHANGELOG.md`; push; CI zielone; opublikowany
  release `v0.25.0` (nie draft).
- Instalacja: `ha_manage_updates` na `update.budzet_domowy_update` z `backup=true` (timeout klienta jest
  normalny, wersję sprawdzam przez encję update).
- Bez commitów w oknie 02:45–03:15.

## Krok 8 — weryfikacja na produkcji (tylko odczyt)
- playwright-ha → `http://192.168.0.105:8123/app/a9413a25_budget`, Podsumowanie: zrzut + konsola.
- Rachunek ręczny: saldo − karta − serie − reszta Flex + wpływy = „Na dzień wypłaty”, pokazany
  użytkownikowi.
- Czas `/` nadal < 600 ms (pomiar `fetch` z ramki ingress).
- Wynik w `docs/PLAN_M8_E1.md` § Wynik + ROADMAP; potem **checkpoint**, a E2 dopiero po „go”.

## Cofnięcie
- Kod: `git revert` commitów E1 + wydanie 0.25.1. Szybciej: przywrócić backup add-onu sprzed
  aktualizacji (ha_manage_backup restore, robi użytkownik albo ja za zgodą).
- Brak migracji bazy i nowych encji, więc cofnięcie nie zostawia danych.

## Rozstrzygnięte w trakcie
- Saldo rachunku: **ITAV** (na produkcji 9136,98 vs ITBD 9321,00 — różnica to autoryzacje w toku);
  karta: ITBD.
- Wypłata = seria wpływowa o największej kwocie (zob. wyżej). Uwaga na checkpoint: przy dwóch
  pensjach (dwie serie przychodów) horyzont kończy się na późniejszej, a wcześniejsza wchodzi
  do salda jako „Wpływy przed wypłatą”.

## Wynik (2026-10-06)

- **0.25.0 wydane** (release `v0.25.0`, nie draft; CI zielone) i zainstalowane z backupem add-onu;
  `update.budzet_domowy_update` = 0.25.0, znacznik `v0.25.0` w panelu.
- 590 testów (pytest), ruff i mypy czyste. Zmiany ze skilla `simplify`: ponowne użycie `FlexMonth`
  i widoku miesiąca z trasy (bez drugiego `flex.build` i `for_month` na `/`), wspólne
  `ledger.latest_balances`, reguła „poniżej bufora” w `Forecast`.
- Na żywo (390 px, Ingress): sekcja „Do wypłaty”, wiersz zadłużenia karty z godziną odczytu, wykres,
  0 błędów konsoli, 0 elementów < 44 px, brak poziomego przewijania. Rachunek ręczny
  (saldo − karta − serie − reszta Flex + wpływy) zgodny z „Na dzień …” co do grosza.
- Czas `GET /` po rozgrzaniu 445–494 ms (próg < 600 ms); pierwsze żądanie po restarcie ~1,1 s.
- Do oceny na checkpoincie: (1) prognoza rezerwuje całą resztę puli Flex (równo na dni), więc jest
  ostrożna — przy wydawaniu poniżej tempa dno wyjdzie wyżej; (2) wypłata = seria przychodów
  o największej kwocie, mniejsza pensja przed nią wchodzi do salda; (3) zadłużenie karty jest
  odejmowane w całości od razu, także to, co bank pobierze dopiero w terminie spłaty.
