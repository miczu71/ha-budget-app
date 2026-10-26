# M32 cd. — VeloBank w Budżecie: licznik, oszczędności z banku, hero r/r, kafelek Akcje

## Context
VeloBank jest połączony (2026-10-26, ponowna zgoda po podlinkowaniu kont w EB). W księdze są #4 „Konto
oszczędnościowe” (…0001, 67 130 zł) i #5 ROR (…0002, przemianowany przez usera; 5× BLIK w październiku). Wnioski
z odczytu na żywo i kodu:
- **Licznik 5 transakcji nie zadziała**: `kinds.from_api` (`budget/kinds.py`) rozpoznaje BLIK Millennium po opisie
  `/OPT/…`, a Velo ma `BLIK: /OPT/…` + numer kontrahenta → `transfer_out` („przelew wych.”). Licznik `cashless`
  (`promo_track.py:148`) liczy tylko `card`/`blik` → 0/5. Do tego „Promocje w toku: nic nie śledzisz” — brak edycji Velo.
- **Podwójne liczenie w Majątku**: `networth._accounts` bierze wszystkie konta z księgi (Velo #4 = 67 130) i osobno
  `_savings` (ręczne konto „VeloBank …0001” = 67 170). To samo konto, ten sam numer.
- `card.count_purchases` (warunek karty Millennium, M22 E5) liczy zakupy kartą ze **wszystkich** banków — karta Velo
  zawyżyłaby warunek Millennium.
- `rotation.py:55` szuka konta Velo `kind='savings'`, a #4 ma rodzaj „rachunek” → rekomendacja E4 nie widzi Velo.
- Odpowiedź na pytanie usera: **tak**, odznaczenie „w budżecie” (`account.include_in_budget`) wyłącza konto z wydatków,
  Flex, hero, prognozy wydatków, roku, przeglądu kategorii i serii. Salda (Majątek, encje HA) zostają. Kafelek „Konto”
  i saldo prognozy biorą pierwszy rachunek PLN po id → nadal Millennium #1.
- Decyzje usera: blokady (PDNG) olewamy — tylko API/BOOK, **M33 do zamknięcia jako odrzucone**; saldo oszczędności
  Velo z banku, odsetki osobno (nie doliczane); hero: „Starczy · zapas” → porównanie wydatków elastycznych od wypłaty
  z tym samym dniem okresu rok temu; 4. kafelek „Akcje” = wolne akcje pracownicze (dane już są: `stocks.py`, M11).

## Etapy (repo `/config/addons/ha-budget-app`, gałąź `main`, worktree `wt new`, jedno wydanie na końcu)
Najpierw: ten plan → `docs/PLAN_M32_E6.md`, wpis w `docs/ROADMAP.md` (M32 cd., M33 odrzucone). Test każdego etapu:
`cd budget/app && BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q && .venv/bin/ruff check . && .venv/bin/mypy .`
(2 znane faile `test_web_recurring` na `main` — bez nowych). Skille: `tdd`, `addon-conventions`. Po każdym `verifier`.

### E6 — BLIK/karta Velo + liczniki per bank (haiku-worker; ryzyko niskie)
- `kinds.from_api`: zdjąć prefiks `BLIK:` z opisu przed dotychczasowymi regułami (`/OPT/` → BLIK, `/OPF/` → zwrot).
- Przeliczenie `kind` istniejących transakcji API kont spoza Millennium: sprawdzić, czy sync nadpisuje `kind` przy
  ponownym pobraniu; jeśli nie — migracja danych przeliczająca `kind` tylko dla transakcji z opisem `BLIK:`.
- `card.count_purchases`: tylko konta banku, do którego należy karta (Millennium) — warunek M22 bez transakcji Velo.
- DONE: fixture (neutralne nazwy) z opisem `BLIK: /OPT/…` → `blik`; licznik `cashless` dla banku Velo = 5 przy 5 BLIK;
  zakup kartą na koncie innego banku nie zmienia `count_purchases`. Rollback: `git revert` (migracja danych odwracalna
  kolejnym syncem/przeliczeniem).

### E7 — Oszczędności z banku (sonnet-worker; „ryzyko”: pieniądze)
- `savings.py`: konto oszczędności powiązane z kontem w księdze **po numerze** (NRB `account_number` = IBAN konta bez
  `PL`), bez migracji. Dla powiązanego: saldo = ostatnie saldo z API (`ledger.latest_balances`, ITAV/ITBD jak
  `forecast.read_balances`), bez `opening_balance`/przelewów; szacowane odsetki od ostatniej kapitalizacji (1. dzień
  miesiąca) jako osobne pole „do dopisania ok. X zł”, **nie** w `total`. Niepowiązane — bez zmian.
- `piggy.html`: dla powiązanego „Saldo z banku, stan z dd.mm” zamiast ręcznego „od dd.mm”; formularz salda ukryty.
- `networth._accounts`: pomija konto z księgi powiązane z kontem oszczędności (liczone raz, jako oszczędność).
- `rotation.py`: saldo Velo z powiązanego konta oszczędności (zamiast `kind='savings'`) — wtedy nie trzeba zmieniać
  rodzaju #4.
- DONE: powiązane konto → `total` = saldo API, odsetki osobno; Majątek bez dubla; kafelek Oszczędności = saldo API +
  skarbonki + Oszczędności Wspólne; niepowiązane i testy Profit bez zmian. Rollback: `git revert`.

#### E7 — Wykonawca (sonnet-worker, jedna paczka)
Repo/worktree: `wt new /config/addons/ha-budget-app m32-e7`. Katalog testów: `budget/app`. Skille: `tdd`, `addon-conventions`.
- `src/budget/savings.py`: `linked_ledger_id(conn, acc) -> int | None` (konto z tabeli `account`, którego `iban` bez
  prefiksu `PL` == `acc.account_number`; `iban` może być z `PL` lub bez, porównuj po `removeprefix("PL")`).
  `Interest` dostaje pola `pending: Decimal = ZERO` (odsetki „do dopisania”, NIE w `total`) i `as_of: date | None = None`
  (data salda z banku; None = saldo ręczne). `estimate()`: gdy powiązane konto ma migawkę (ITAV, potem ITBD — jak
  `forecast.read_balances`, przez `ledger.latest_balances`) → `Interest(balance=saldo API, earned=ZERO, accrued=ZERO,
  pending=net(suma daily od 1. dnia bieżącego miesiąca do today po saldzie API), as_of=data fetched_at)`; brak migawki
  → dotychczasowa ścieżka ręczna (bez zmian). Pozostałe wywołania `estimate` (invest, ask/sources, routes_piggy,
  networth) dostają to za darmo — nie zmieniaj ich.
- `src/budget/networth.py::_accounts`: pomiń konto z księgi, jeśli jakieś niearchiwalne
  `savings.all_accounts` jest do niego powiązane (`linked_ledger_id`), ale TYLKO gdy powiązanie ma migawkę salda
  (inaczej konto nie byłoby liczone wcale). Dla `past=True` (wykres historii) nie zmieniaj zachowania poza tym pominięciem.
- `src/budget/rotation.py::velo_balance`: zamiast `kind='savings'` sumuj saldo kont księgi powiązanych z kontami
  oszczędności (`savings.all_accounts` → `linked_ledger_id`), z bankiem `LIKE VELO_BANK` i migawką ≤ `STALE_DAYS`.
  Konto Velo bez powiązania — nie liczy się.
- `src/budget/web/templates/piggy.html` (blok konta ok. l.101 i formularz l.75–76): dla `est.as_of` ustawionego:
  „Saldo z banku, stan z dd.mm” (filtr `pldate`) zamiast „od … : opening_balance”, wiersz „Odsetki do dopisania ok. X zł”
  z `est.pending` (gdy > 0); pola `opening_balance`/`opening_date` w formularzu edycji ukryte (zostaw ich wartości w
  ukrytych inputach, żeby `save()` działało).
- Testy (neutralne nazwy; wzór: `tests/test_savings.py`, `test_networth.py`, `test_rotation.py`): powiązane konto →
  `total` = saldo API, `pending` > 0 i poza `total`; Majątek liczy Velo raz; `velo_balance` z powiązanego; niepowiązane i
  powiązane bez migawki = dotychczasowe wyniki; trasa `/piggy` renderuje „Saldo z banku”.
- Test: `cd budget/app && BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy .`
- DONE: jak w E7 wyżej + pytest zielony (bez nowych failów ponad 2 znane), ruff, mypy czyste.
- NIE RÓB: migracji SQL, zmian `invest.py`/`ask/sources.py`/`routes_piggy.py`, wersji/CHANGELOG, commitów, zmian innych etapów (E8/E9), odświeżania dokumentacji.

### E8 — Hero r/r (haiku-worker)
- `_payday_hero.html`: przy stanie OK zamiast „Starczy · zapas…” linia: „Od wypłaty dd.mm wydane X zł — o Y zł (Z%)
  mniej/więcej niż rok temu po N dniach okresu”. „Poniżej bufora”/„Zabraknie” zostają bez zmian. Linia „Najniżej dd.mm”
  zostaje.
- Logika (nowa funkcja w `flex.py` obok `spent_between`): okres rok temu = okres wypłaty zawierający `today − 1 rok`
  (`flex.first_day`), wydatki elastyczne od jego startu przez N dni (N = dni od bieżącej wypłaty). Brak danych rok temu
  → linia bez porównania. `Decimal`, procent zaokrąglony do całości.
- DONE: testy z zamrożoną datą: mniej / więcej / brak historii. Rollback: `git revert`.

#### E8 — Wykonawca (haiku-worker, jedna paczka)
Repo/worktree: `wt new /config/addons/ha-budget-app m32-e8`. Katalog testów: `budget/app` (w worktree brak .venv:
`PYTHONPATH=<wt>/budget/app/src` + `.venv` z `/config/addons/ha-budget-app/budget/app`). Skille: `tdd`, `addon-conventions`.
- `src/budget/flex.py` (po `spent_between`): `spent_year_ago(snap, payday_then: date | None, days: int, skip=None) -> Decimal | None`
  — `None`, gdy `payday_then` jest `None` albo wcześniejszy niż `first_day(snap.conn)`; inaczej
  `spent_between(snap, payday_then, payday_then + timedelta(days=days), skip)`.
- `src/budget/forecast.py::Forecast`: pola `spent_year_ago: Decimal | None = None`, `year_ago_days: int = 0` oraz własności
  `yoy_delta -> Decimal | None` (`spent_since - spent_year_ago`) i `yoy_pct -> int | None` (`round(delta / spent_year_ago * 100)`,
  `None` gdy `spent_year_ago` brak albo 0). W `build()`, gdy `start is not None`: `payday_then = last_payday(snap, p.payday_series_id,
  add_months(start, -12))`, `days = (today - start).days + 1`, `spent_year_ago = flex.spent_between…` przez `flex.spent_year_ago`
  (ten sam `skip`). Reszta `build()` bez zmian.
- `src/budget/web/templates/_payday_hero.html`: w stanie OK (`not fc.below_buffer`) zamiast „Starczy · zapas X” akapit: „Od wypłaty
  dd.mm wydane X zł — o Y zł (Z%) mniej/więcej niż rok temu po N dniach okresu” (X = `fc.spent_since`; mniej gdy delta < 0,
  Y = `|delta|`); gdy `yoy_delta is none` — „Od wypłaty dd.mm wydane X zł.” bez porównania. „Poniżej bufora”/„Zabraknie” oraz linię
  „Najniżej dd.mm” zostaw. Gdy `fc.period_start` brak — zostaw dotychczasowy tekst „Starczy · zapas”.
- Testy (neutralne dane; wzór: `tests/test_forecast.py`, `tests/test_flex.py`, zamrożona data): mniej / więcej / brak historii /
  zero rok temu (bez procentu); trasa `/` renderuje nową linię.
- Test: `cd budget/app && BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q && .venv/bin/ruff check . && .venv/bin/ruff format --check .`
- DONE: jak w E8 wyżej + pytest bez nowych failów, ruff czysty (mypy: 73 błędy bazowe, bez nowych).
- NIE RÓB: zmian `routes_home.py`/kafelków (E9), migracji, wersji/CHANGELOG, commitów, dokumentacji, zmian logiki `safe_per_day`/projekcji.

#### E9 — Wykonawca (haiku-worker, jedna paczka; po zlandowaniu E8)
Repo/worktree: `wt new /config/addons/ha-budget-app m32-e9`. Skille: `tdd`, `addon-conventions`.
- `src/budget/web/routes_home.py::BalanceTiles`: pola `stocks_value: Decimal | None`, `stocks_unvested: Decimal | None`,
  `stocks_vest: date | None`, `stocks_stale: bool`; `balance_tiles(...)` dostaje `holding: stocks.Holding | None`
  (wywołanie w `home()`: `stocks.load(conn)`) — `stocks_value = holding.market_value` (None bez danych), `stocks_unvested =
  holding.unvested_value`, `stocks_vest = holding.next_vest`, `stocks_stale = now − holding.fetched_at > timedelta(days=stocks.STALE_DAYS)`.
- `src/budget/web/templates/_balance_tiles.html`: 4. kafelek (link `{{ base }}/networth`) „Akcje” = `money(whole=True)`, podpis
  `small` „+ X zł niezawiązane · zawiązanie dd.mm” (część po „·” tylko z `stocks_vest`), znacznik nieaktualności jak w Majątku
  (sprawdź `networth.html` — ta sama klasa/tekst); bez `stocks_value` kafelek ukryty.
- `src/budget/web/static/app.css` (l.~1036): `.bal-tiles` 4 w rzędzie na desktopie; ≤600 px siatka 2×2 (`grid-auto-flow: row`,
  `grid-template-columns: repeat(2, minmax(0, 1fr))`); bez przepełnienia poziomego.
- Testy: trasa `/` z danymi akcji (kafelek + podpis) i bez (brak kafelka); nieaktualne → znacznik.
- Test jak w E8. DONE: jak w E9 wyżej (zrzuty Playwright robię sam po zlandowaniu).
- NIE RÓB: zmian `stocks.py`, Majątku, hero (E8), migracji, wersji/CHANGELOG, commitów.

### E9 — Kafelek „Akcje” (haiku-worker)
- `routes_home.balance_tiles` + `_balance_tiles.html`: 4. kafelek „Akcje” = `stocks.load(conn).market_value` (wolne);
  podpis „+ X zł niezawiązane · zawiązanie dd.mm” gdy są dane; oznaczenie nieaktualnych jak w Majątku
  (`stocks.STALE_DAYS`); bez danych kafelek ukryty. Układ: 4 w rzędzie na desktopie, 2×2 na telefonie (`impeccable`,
  sprawdzić przepełnienie `scrollWidth` vs `innerWidth`).
- DONE: test trasy `/` z danymi i bez; zrzut Playwright desktop + 390 px.

## Wydanie i kroki na żywo
1. `simplify` → `code-review` + `silent-failure-hunter` + `pr-test-analyzer` + security (general-purpose) + druga opinia
   (pomiar 5/10) → `release` (0.64.0, `ha_manage_updates` z backupem add-onu) → weryfikacja.
2. Dane na żywo przez UI Budżetu (Playwright, w ramach tego planu): odznaczyć „w budżecie” dla #4 i #5; utworzyć
   edycję promocji Velo (bank VeloBank, warunek 5 transakcji bezgotówkowych w miesiącu, parametry z karty Oszczędności:
   4,5% do 22.01.2027) — jeśli formularz wymaga danych, których nie ma w karcie, pytam.
3. Weryfikacja: `/invest` licznik Velo **5/5** za październik; `/piggy` VeloBank = saldo z banku + „odsetki do dopisania”;
   `/networth` bez dubla (Velo raz); `/` hero z porównaniem r/r i 4 kafelki (desktop + 390 px, konsola bez błędów);
   wydatki października bez darowizn 5× 1 zł z Velo.
4. Docs: `PLAN_M32.md` § Wyniki, `ROADMAP.md`, pamięć `project_budget_app.md`; follow-upy: `/status` pokazuje zgody
   wszystkich banków; zgoda z 0 kont → ostrzeżenie zamiast cichego `ok`; pułapka „najpierw link kont w Control Panelu
   EB, potem zgoda”.

## Stan wykonania
- **E6 zrobione 2026-10-26** (`7f7e440`, lokalnie — push na `origin/main` zablokowany przez klasyfikator uprawnień, czeka
  na decyzję usera): `kinds.from_api` zdejmuje prefiks `BLIK:`; `card.count_purchases(bank=…)` + `promo_track._ledger_bank`.
  Migracja danych niepotrzebna — `ledger.ingest_api` przelicza `kind` (`kind_source='heuristic'`) przy każdym syncu.
  Weryfikacja: pytest 1253 ok, ruff, ruff format, mypy czyste (+3 testy, fixture `test_promo_track` z bankiem EB).
- **E7 zrobione 2026-10-26** (`b41a2a4`, lokalnie): `savings.linked_ledger_id`/`bank_snapshot`, `Interest.pending`/`as_of`;
  `estimate` powiązanego konta = saldo API (odsetki „do dopisania” poza `total`); Majątek pomija duplikat z księgi
  (tylko gdy jest migawka); `rotation.velo_balance` z powiązanych; `piggy.html` „Saldo z banku”. sonnet-worker + verifier
  APPROVE; pytest 1260 ok, ruff ok, mypy 73 błędy = stan `main` (sprawdzone). Nieblokujące: pending zaniża przy migawce
  z poprzedniego miesiąca; brak limitu wieku migawki w `estimate`/Majątku (jest w `velo_balance`).
- **E8 zrobione 2026-10-26** (`3720b23`): `flex.spent_year_ago`, `Forecast.spent_year_ago/yoy_delta/yoy_pct`, linia r/r w hero
  (stan OK); okres rok temu = `last_payday` dla tego samego dnia rok wcześniej (`add_months` dawał 1. dzień miesiąca). haiku-worker +
  verifier APPROVE; pytest 1265 ok. Nieblokujące: delta 0 → „o 0,00 zł więcej”.
- **E9 zrobione 2026-10-26** (`596fc0d`): kafelek „Akcje” (wolne akcje, podpis niezawiązane · zawiązanie, nieaktualność po dacie jak w Majątku
  + prefiks „nieaktualne”), 2×2 ≤600 px. verifier APPROVE; pytest 1268 ok; Playwright 1280/390 px: 4 w rzędzie / 2×2, bez przepełnienia, konsola czysta.
- Dalej: simplify → code-review (+ recenzenci) → release 0.64.0. Commit planu: `72ece2a`.
