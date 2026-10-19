# M18 — Prognoza roczna i scenariusze (Budżet Domowy)

## Kontekst

M8 prognozuje saldo tylko do najbliższej wypłaty. Prognoza roczna ma odpowiadać na trzy pytania
na jednym ekranie: ile odłożę do końca roku, czy któryś miesiąc wyjdzie na minus i ile mogę
miesięcznie wydawać na wydatki elastyczne (Flex), żeby dojść do celu. Wywiad: 2026-10-14
(decyzja 29). Repo `/config/addons/ha-budget-app` (`main`), produkcja 0.52.3.

**Podsumowanie wywiadu**
- **Kto korzysta:** użytkownik w zakładce „Rok” i kafelku na Podsumowaniu, czat (źródło `year`),
  encja `sensor.budget_year_end`.
- **Automatycznie:** przeliczanie po każdej synchronizacji/zapisie oraz propozycje zdarzeń
  z historii (próg PIT, premia). Propozycje są tylko propozycjami.
- **Za zgodą użytkownika:** zatwierdzenie i edycja zdarzeń, przełączanie plan/scenariusz, cel
  roczny, ręczny Flex. Bez powiadomień i dzwonka.
- **Sukces:** backtest „z 1.01.2026” na kopii księgi daje sumę nadwyżki I–IX w ±10% faktu i nie
  gubi żadnego miesiąca z deficytem. Potem użytkownik ocenia ekran na żywo.

## Model (decyzje wywiadu)

- **Horyzont:** od dziś do 31.12. Od 1.11 doklejamy cały następny rok (do 31.12 następnego roku).
  Saldo startowe = `free_now` z M8 (`forecast.read_balances`: rachunek PLN − zadłużenie karty,
  wg `include_card_debt`).
- **Miesiąc:** wpływy z serii `in` + wydatki z serii `out` (terminy z `schedule.for_month(snap, m,
  today)`, M/Q/Y). Do tego Flex = mediana elastycznych z 12 pełnych miesięcy (te same zasady co
  `flex._history`/`_spent`, okno 12 zamiast `HISTORY_MONTHS`=6, bez transakcji serii) oraz wiersz
  „nieregularne” = (suma 12 mies. − 12 × mediana) / 12. Wydatki spoza serii i spoza Flex (grupy
  `non_monthly` i `fixed` bez aktywnej serii, np. roczne OC, ubezpieczenia) wchodzą jako wiersz
  „roczne bez serii”: kwota z TEGO SAMEGO miesiąca rok wcześniej (sezonowość), a nie rozłożona po
  równo. Zdarzenia „plan” w bazie. Wynik miesiąca:
  nadwyżka i saldo narastająco. Bieżący miesiąc liczony od dziś: zostałe terminy (EXPECTED/LATE)
  + Flex proporcjonalnie do pozostałych dni.
- **Ręczny Flex:** pole na ekranie (kv `year_flex`) zastępuje medianę. „Wróć do automatycznej”.
- **„Ile mogę wydać”:** cel na koniec horyzontu (kv `year_target`, domyślnie 0). Szukamy
  maksymalnego Flex/mies., przy którym saldo żadnego miesiąca nie spada poniżej bufora M8
  (`forecast_buffer`), a koniec horyzontu ≥ cel. Liczone analitycznie, jak `forecast.safe_per_day`,
  tyle że na miesiącach.
- **Zdarzenia** (tabela `year_event`, migracja 021): `kind` ∈ {`series_amount` (seria S od M =
  kwota K), `new_series` (nazwa, kierunek, kwota, od M, opcjonalnie do M), `one_off` (nazwa,
  kwota ±, miesiąc M)}, `mode` ∈ {`plan`, `scenario`}, `source` ∈ {`manual`, `proposed`},
  `status` ∈ {`proposed`, `active`, `dismissed`}. Zdarzenia „scenariusz” rysują drugą linię
  i różnicę na końcu roku.
- **Propozycje z historii:**
  - *Próg PIT:* dla serii wypłaty (`payday_series_id`) znajdź w zeszłym roku miesiąc spadku
    > `DROP_RATIO` względem stycznia (logika jak `flex._drop`). Proponuj `series_amount` od 01
    następnego roku = kwota sprzed spadku i od miesiąca spadku = kwota bieżąca serii. Tryb `plan`,
    status `proposed`.
  - *Premia:* nadwyżka ponad `_bonus_limit` (flex) w zeszłym roku → `one_off` w tym samym
    miesiącu, tryb `scenario`, status `proposed`.
  - Propozycja odrzucona (`dismissed`) nie wraca dla tego samego (seria, rok).
- **M9/M10 luźno:** rata to zwykła seria. Nadpłata i wpłata na oszczędności to `one_off`. Bez
  przeliczania rat i odsetek. Link „sprawdź w kalkulatorze kredytu” (`/loan`) z kwotą nadwyżki.
- Imiona, kwoty i numery tylko w bazie. W repo i testach nazwy neutralne („Seria A”, „Źródło 1”).

## Etapy (jedno wydanie 0.53.0 na końcu)

Krok 0 (przed E1): skopiować ten plan do `docs/PLAN_M18.md`, dopisać w `docs/ROADMAP.md` wiersz
M18 (wywiad, etapy) i decyzję 29, commit `docs(m18): plan i decyzja 29`.

### E1 — silnik + backtest + ekran „Rok” (tylko odczyt, bez zdarzeń)
1. `budget/year.py` (czysta logika + `build(snap, today, now)`): `YearMonth` (wpływy, serie_out,
   flex, nieregularne, zdarzenia, nadwyżka, narastająco, below_buffer), `YearForecast` (miesiące,
   koniec, pierwszy deficyt, max_flex, cel). Reużyć: `schedule.for_month`, `forecast.read_balances`,
   `forecast.include_card_debt`, `flex._flexible/_spent`, `money.CENT`, `add_months`/`month_start`.
2. Memo jak `forecast.ForecastMemo` (po sygnaturze `Snapshot`).
3. Testy TDD `tests/test_year.py`: horyzont (X vs XI → +rok), bieżący miesiąc częściowy, serie
   Q/Y w dobrym miesiącu, mediana + nieregularne sumują się do 12 mies., max_flex z buforem
   i celem, brak salda → None.
4. Lista „Płatności roczne bez serii do potwierdzenia” na `/year` (E1): transakcje z ostatnich 13
   mies. w `non_monthly`/`fixed` poza seriami, pogrupowane po sprzedawcy, z miesiącem i kwotą.
   Użytkownik zamienia je w serię (link do Cyklicznych) albo odrzuca. Źródło: odpowiedź na uwagę,
   że detektor rzadko łapie serie roczne (historia ~21 mies.). Do czasu potwierdzenia pokrywa je
   wiersz „roczne bez serii”.
4b. Backtest: skrypt w scratchpadzie na kopii `~/budget_dev/prod/ledger.db` (świeża kopia
   wymaga zgody, bo dane prywatne zostają lokalnie). `year.project(...)` z `today=2026-01-01`
   na historii do 31.12.2025 kontra faktyczne I–IX. Raport (tylko metryki, bez kwot w repo)
   w `PLAN_M18.md` § Wynik E1. **Wynik poza ±10% albo zgubiony deficyt = stop i pytanie**
   (podważa założenie metody).
5. Ekran `/year` (`web/routes_year.py`, `templates/year.html`). Na górze: „na koniec roku” +
   „ile mogę wydać / mies.”. Pod tym wykres salda narastająco (SVG jak w `web/charts.py`; strefa
   < bufor) i tabela miesięcy rozwijana do serii. Pola: cel, ręczny Flex. Zakładka w
   `nav_layout` (domyślnie po „Kredyt”). Komponenty wg `DESIGN.md`, skill `impeccable`,
   weryfikacja Playwright 390 px (`scrollWidth` ≤ `innerWidth`) i desktop.
6. `simplify`, commit.
Rollback: revert commitów E1 (bez migracji).

### E2 — zdarzenia: plan/scenariusz + propozycje
1. Migracja `021_year_event.sql` (addytywna, tylko nowa tabela; cofnięcie = DROP TABLE,
   schemat 21). Moduł `year_events.py`: CRUD, walidacja, `proposals(snap, today)`.
2. `year.build` stosuje zdarzenia `plan` do bazy, a `scenario` do drugiej projekcji.
   `YearForecast.scenario` + różnica.
3. UI na `/year`: lista zdarzeń (dodaj/edytuj/usuń, przełącznik plan/scenariusz), sekcja
   „Propozycje” (zatwierdź / popraw / odrzuć), druga linia na wykresie i kolumna różnicy.
4. Testy: każdy `kind`, zakres od–do, propozycja progu z syntetycznego spadku, premia jako
   scenariusz, `dismissed` nie wraca.
5. `simplify`, commit.
Rollback: revert + migracja 021 zostaje pusta (jak 020 po M23) albo DROP przy cofnięciu przed
wydaniem.

### E3 — kafelek, encja, źródło czatu
1. Kafelek „Rok” w `home_layout.TILES` (koniec roku, pierwszy deficyt) z linkiem do `/year`.
2. `ha_publisher.year_entities` → `sensor.budget_year_end` (PLN, atrybuty `horizon_end`,
   `first_deficit`, `max_flex`, `scenario_end`), wpięte w `build_entities`.
3. Źródło czatu `year` w `ask/sources.py` (rejestr, `prompt_lines`): miesiące, koniec,
   deficyt, max Flex; etykiety zdarzeń anonimizowane jak `[Seria N]`.
4. Testy + `simplify`, commit.
Rollback: revert.

### Wydanie 0.53.0
`code-review` → skill `release` (bump `config.yaml`, CHANGELOG, opublikowany release, store
reload, instalacja z backupem). Na żywo: `/year`, kafelek, encja w HA, jedno pytanie do czatu
zgodne z ekranem. Potem ROADMAP § Wynik i checkpoint użytkownika.

## Weryfikacja
- `uv run pytest` (obecnie ~884 testy, wszystkie zielone + nowe).
- Backtest E1 (±10%, deficyty).
- Playwright przez `playwright-ha` → `/app/a9413a25_budget`: 390 px bez poziomego przewijania,
  konsola bez błędów, wartości „koniec roku” = kafelek = encja = odpowiedź czatu.

## Ryzyka
- Mediana 12 mies. obejmuje miesiące sprzed progu PIT i premie. Premia poza Flex (to wpływ),
  ale sezonowość wydatków jest spłaszczona. Akceptowane, korekta „nieregularne” trzyma sumę.
- Seria wypłaty bez historii zeszłego roku → brak propozycji progu (tylko ręcznie).
- Przy niepełnym bieżącym miesiącu nieskategoryzowane transakcje zaniżają Flex historyczny
  (jak w M5a). Backtest to pokaże.

## Wynik E1 (2026-10-14, commit 418015e, niewydane)

- `year.py` (rdzeń `project` + `history`/`build`/`backtest`/`evaluate`/`unseried`), ekran `/year`
  (podsumowanie, wykres przez `forecast_line`, miesiące, ustawienia Flex i cel, płatności roczne bez
  serii), zakładka „Rok” po „Kredyt”, `Service.year_memo`, `flex.group_spent` (dawne `_group`).
- 901 testów zielone, mypy czysty; ruff: jedyna uwaga `tests/test_web.py:98` jest sprzed M18.
- Ekran na danych syntetycznych: 390 px bez przewijania poziomego, 0 elementów < 44 px, 1280 px OK.
- **Zmiana względem planu (decyzja usera 2026-10-14):** backtest na kopii księgi z 2.10 odpadł (kopia
  bez kategorii i serii — „nieregularne” wyszło 8,5 tys. zł/mies. przez duże nieskategoryzowane
  przelewy), więc pomiar jest w add-onie (Status → „Prognoza roczna — pomiar”). Mierzy wyłącznie
  wydatki spoza serii (Flex + korekta + sezonowość) z 31.12 wobec faktu; serie, wpływy i deficyty
  zostają niesprawdzone (obecne kwoty serii znają próg PIT). Dlatego checkpoint = pomiar ±10%
  **oraz** ocena tabeli miesięcy na żywo (porównanie z nadchodzącymi opłatami i wypłatą).
- Ryzyko do zbadania na żywo: „nieregularne” = średnia − mediana może być duże, gdy rzadkie duże
  przelewy są nieskategoryzowane (wchodzą do Flex). Jeśli pomiar to pokaże, rozważyć obcięcie
  miesięcy powyżej progu (jak `flex._bonus_limit`).
- Odroczone z `simplify` (nie zmieniają zachowania): zapytania `sums` per miesiąc (≈45 przy
  pomiarze) — mierzyć czas na żywo, w razie potrzeby jedno `_rows` kubełkowane po miesiącach;
  `for_month` ×14 wczytuje serie/acks za każdym razem; wspólny generyczny `Memo` (3 klasy:
  `BalanceMemo`, `ForecastMemo`, `year.Memo`); `Balances.free()` zamiast powtórzonej formuły z
  `forecast.build`; publiczne `spending.rows` (dziś `_rows` używa też `ask/query.py`).

## Wynik E2 (2026-10-14, niewydane)

- Migracja `021_year_event.sql` (tabela `year_event`), `year_events.py` (CRUD, `apply`, `proposals`,
  `save_form`), `year.build` stosuje zdarzenia `plan` do bazy, a wszystkie aktywne do drugiej projekcji
  (`Projection.scenario`, `scenario_delta`); druga linia wykresu (`forecast_line(second=...)`), sekcja
  „Zdarzenia” i „Propozycje z historii” na `/year`. 923 testy, mypy czysty, `simplify` zastosowany.
- **Odchylenia od planu:** propozycje liczone na żywo i niezapisywane — wiersz powstaje po zatwierdzeniu
  albo odrzuceniu (`proposal_key` UNIQUE), więc status `proposed` nie istnieje (tylko `active`/`dismissed`).
  „Popraw” = zatwierdź, potem edytuj zdarzenie. Kwota po progu PIT pochodzi z mediany zeszłorocznych
  wypłat po spadku (nie z bieżącej kwoty serii); propozycję pomija się, gdy równa się kwocie serii albo
  jej zakres jest już w przeszłości. Od 1.11 propozycje obejmują też styczeń następnego roku.
  Rok docelowy N bierze historię N−1.
- Odroczone z `simplify` (bez zmiany zachowania): jedna lista `ChartLine` zamiast `points2/end2_*`;
  wspólna funkcja „limit + typowa mediana” dla `flex.auto_budget`/`_drop` i `year_events`;
  memoizacja `proposals()` (dziś liczone przy każdym GET `/year`); wspólny `_write` dla `add`/`update`.

## Checkpoint (2026-10-19, 0.56.0 na żywo)
- Pomiar (Status → „Prognoza roczna — pomiar”): **odchylenie −24,5% (poza ±10%)**; prognoza 57 857,01 zł vs fakt
  76 676,79 zł za I–IX, każdy miesiąc zaniżony (−18…−36%). Wg tego planu: stop i decyzja usera.
- Pytanie do czatu o rok: −1 744,20 zł = `sensor.budget_year_end`, pierwszy deficyt 2026-12.
- Do oceny przez usera: tabela miesięcy na `/year` wobec nadchodzących opłat i wypłaty.
