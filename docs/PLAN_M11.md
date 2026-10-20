# M11 — Akcje Nokia (Nokia Tracker) w majątku netto Budżetu

## Context
Roadmapa Budżetu (`/config/addons/ha-budget-app/docs/ROADMAP.md`) ma otwarte M11, M19, M24 i M25; user wybrał M11.
M26 (0.60.1) liczy majątek netto bez akcji. Akcje Nokia to dziś największe aktywo (~139 tys. zł), więc majątek netto
i LTV (dziś 141684%) są bez nich bezużyteczne. Add-on `nokia_tracker` wystawia wszystko przez MQTT jako encje HA.

## Decyzje z wywiadu (2026-10-20)
1. Wartość = **brutto + niezawiązane**: `market_value_pln` (2750 akcji, ~95,8 tys.) + `unvested_qty` × `price_pln`
   (1266 akcji, ~44 tys.). Suma ≈ `sensor.nokia_portfolio_pln` (139 402 zł, ta sama formuła). Niezawiązane są osobnym wierszem
   z datą i liczbą akcji najbliższego vestingu (`next_vest_date` 2027-07-05, atrybut `next_vest_qty` 633). Akcje nie wchodzą do płynności
   (`networth.LIQUID_GROUPS` już je pomija).
2. Źródło = **encje HA** przez `ha_client` (Supervisor `/core/api/states/<id>`), prefiks w opcjach, domyślnie `sensor.nokia_tracker_`.
3. Historia = **odtworzenie ze statystyk długoterminowych HA** (sensory mają `state_class`), wartości na koniec miesiąca dopisane do migawek
   jako przybliżone (`approx=1`), bez fałszywego skoku m/m.
4. Przepływy: dywidendy (DRIP) i środki zostają u brokera, więc **wiązanie z księgą odpada** (w księdze 0 wpływów Computershare/EquatePlus).
5. Dodatkowo tylko **dzwonek vestingu** w panelu (bez push, bo push wysyła już tracker o 06:30). Bez nowego źródła czatu i bez zmian w agencie M22.
6. Integracja **szyta pod Nokia Tracker**, a nie ogólne „aktywo z encji”.

Podsumowanie: z wyniku korzysta user (zakładka Majątek, kafel, `sensor.budget_net_worth`, podsumowanie M6). Odczyt encji przy każdym
`compute`, migawka dzienna i jednorazowe odtworzenie historii dzieją się automatycznie. Kroków za zgodą nie ma (wydanie zgodnie z regułą „bez pytania”).
Kryteria sukcesu: akcje na żywo w ±1% od `nokia_portfolio_pln`, wykres bez skoku w dniu wdrożenia, dzwonek działa na teście z przesuniętą datą.

## Etapy (repo `/config/addons/ha-budget-app`, gałąź `main`)
Pierwszy krok implementacji: skopiować ten plan do `docs/PLAN_M11.md`, a w ROADMAP wpisać wiersz M11 ze statusem.

- **E0 Pomiar (tylko odczyt):** przez ha-mcp sprawdzić zasięg statystyk (`market_value_pln`, `price_pln`, `unvested_qty`) i to, czy
  Nokia nie jest już wpisana ręcznie jako aktywo M22 (`invest_asset`), bo wtedy byłaby liczona podwójnie. Sprawdzić też, czy Supervisor
  przepuszcza WebSocket `/core/websocket` (`recorder/statistics_during_period`). Jeśli statystyki są krótsze niż księga, przed pierwszym
  punktem przyjmujemy brak akcji i oznaczamy to na wykresie.
- **E1 Odczyt i składnik majątku:** `ha_client.get_state`; nowy moduł `stocks.py` (odczyt 4 encji → 2 komponenty grupy
  `INVESTMENTS`: „Akcje Nokia”, „Akcje Nokia — niezawiązane”); gdy encja jest `unavailable`, używamy ostatniej znanej wartości z `kv` z datą
  (`stale`, jak w M26). Wpięcie w `networth.compute` (migawka dzienna dostaje to za darmo); opcja `stocks_entity_prefix` w `config.yaml`
  + `settings.py`. Testy jednostkowe z atrapą klienta HA. Rollback: revert commitu (bez migracji).
- **E2 Historia:** klient WS statystyk (miesięczne, `mean`/`state` na koniec miesiąca); jednorazowe, idempotentne (flaga w `kv`)
  dopisanie składnika akcji do istniejących przybliżonych migawek. Dokładne migawki zostają nietknięte. Rollback: revert, migawki
  przeliczy `backfill` po wyczyszczeniu flagi i wierszy `approx=1`.
- **E3 Ekran i dzwonek:** w Majątku wiersz niezawiązanych z podpisem „vesting DD.MM.RRRR: N akcji”; `inbox.vest_soon` (wzór
  `inbox.invest_maturity`) 14 dni przed `next_vest_date`: „przejdzie N akcji ≈ Y zł”. Playwright 360/1280 px, konsola czysta.
- **Wydanie 0.61.0** po E3: `simplify` → `code-review` → `release`; weryfikacja na żywo.

Każdy etap kodu ma w `docs/PLAN_M11.md` sekcję **Wykonawca** (pliki, zmiana, `uv run pytest`) dla `sonnet-worker` w `wt new`.

## Ryzyka
- `sensor.budget_net_worth` i LTV skoczą o ~139 tys. zł. To zamierzone, ale kontekst agenta M22 (który bierze majątek z M26) też to zobaczy.
- Nazwa i treść nie mogą zawierać danych prywatnych w fixtures/docs (hook pre-commit): w testach neutralne kwoty.

## Weryfikacja
`uv run pytest` (pełny zestaw zielony, ruff/mypy czyste); na żywo po wydaniu: Majątek pokazuje oba wiersze, suma w ±1% od
`sensor.nokia_portfolio_pln`, `sensor.budget_net_worth` zawiera akcje, wykres miesięczny bez skoku, test dzwonka z wymuszoną datą.

## Wynik E0 (2026-10-20)
- Statystyki długoterminowe HA trzech sensorów obejmują **tylko 07–10.2026** (4 miesiące), księga zaczyna się 01.2025. Odtworzenie
  historii (E2) pokryje więc tylko końce 07, 08, 09 i bieżący miesiąc; wcześniejsze migawki zostają bez akcji i **wykres oznacza to jako
  „brak danych o akcjach”** (nie odtwarzamy z cen i liczby akcji z innych źródeł — poza zakresem).
- `market_value_pln` ma `state_class: total` → w statystykach tylko `sum`/`state`, bez `mean`. W E2 wartość akcji na koniec miesiąca =
  `state` tego sensora; niezawiązane = `unvested_qty` (`mean`/`state`) × `price_pln` (`state`) z tego samego końca miesiąca.
- Poprawka do E1: formuła niezawiązanych to `unvested_qty × price_pln` (nie osobny sensor wartości).
- Podwójne liczenie z M22: `sensor.budget_net_worth` ma aktywa 67 670 zł przy akcjach ~139 tys. zł → Nokia nie jest wpisana ręcznie
  jako `invest_asset`. Do potwierdzenia w E1 przez ekran „Inwestycje” (zero ręcznych aktywów o nazwie z „Nokia”).
- Nie sprawdzone (wymaga uruchomienia w add-onie): przepuszczalność WebSocket `/core/websocket` przez Supervisor. Sonda jest pierwszym
  krokiem E2; fallback = `POST /core/api/…` nie ma endpointu statystyk, więc wtedy historia odpada, a wykres zaczyna się od dnia wydania.

## Wykonawca E1 (prompt dla `sonnet-worker`; repo `/config/addons/ha-budget-app`, kod w `budget/app/src/budget/`)
Cel: akcje Nokia jako dwa składniki grupy `networth.INVESTMENTS`, odczyt z encji HA, bez migracji.
Projekt: `networth.compute` jest synchroniczne i wołane z wielu miejsc (web, summary, czat), więc odczyt HTTP robi osobna
funkcja async, a wynik leży w `kv`; `compute` czyta tylko `kv`. `stocks.py` NIE importuje `networth` (cykl) — zwraca `Holding`,
komponenty buduje `networth._investments`.

1. `ha_client.py`: `async def get_state(self, entity_id) -> dict | None` — `GET /core/api/states/<id>`; 404 → `None`, inne błędy `HAError`.
2. NOWY `stocks.py`: `@dataclass Holding(market_value, unvested_qty, price, next_vest, next_vest_qty, fetched_at)` (Decimal/date);
   `KEY = "stocks_nokia"`; `async refresh(conn, ha, prefix, now)` — czyta `{prefix}market_value_pln`, `{prefix}price_pln`,
   `{prefix}unvested_qty`, `{prefix}next_vest_date` (+ atrybut `next_vest_qty`); `unavailable`/`unknown`/brak encji ⇒ nie nadpisuje
   poprzedniego wpisu; pusty prefiks ⇒ nic nie robi; `load(conn) -> Holding | None` (przez `db.kv_get`/`kv_set` z `budget.storage.db`).
3. `networth.py::_investments`: gdy `not past`, dołóż z `stocks.load(conn)`: „Akcje Nokia” = `market_value`, „Akcje Nokia — niezawiązane” =
   `unvested_qty × price` (note: `vesting DD.MM.RRRR: N akcji`, jeśli `next_vest`), `stale` gdy `fetched_at` starsze niż `STALE_DAYS`.
   Dla `past=True` nic (historia = E2). Grupa INVESTMENTS zostaje poza `LIQUID_GROUPS`.
4. `settings.py` + `config.yaml` (options `stocks_entity_prefix: "sensor.nokia_tracker_"`, schema
   `"match(^(sensor\\.[a-z0-9_]+_)?$)?"`) + `translations/pl.yaml` i `en.yaml` (nazwa + opis) — wzór: `calendar_entity`. Walidator jak przy `calendar_entity`.
5. `service.py`: `await stocks.refresh(self.conn, self.ha, self.settings.stocks_entity_prefix, self.now())` na początku `record_networth`
   (w istniejącym `try`) oraz na początku `refresh()` (osobny `try/except Exception: log.exception`, nie zatrzymuje encji).
6. Testy `tests/test_stocks.py` (httpx MockTransport/atrapa `HAClient`): odczyt i zapis do `kv`; `unavailable` zachowuje stary wpis;
   komponenty mają sumę `market_value + unvested×price` (neutralne kwoty, np. 100 akcji po 10,00 zł); `past=True` bez akcji;
   stale po 2×`STALE_DAYS`; pusty prefiks. Dołóż przypadek do `tests/test_networth*.py`, jeśli istnieje.
Komenda: `cd budget/app && uv run pytest -q && uv run ruff check . && uv run mypy src`. Nie commituj, nie wydawaj.
Zakres poza planem: żadnych zmian w UI (E3), historii (E2), innych modułach.

## Wynik E1 (2026-10-20)
`ca9b823` na `main` (lokalnie, bez pusha): `stocks.py`, `ha_client.get_state`, składniki „Akcje Nokia” i „Akcje Nokia — niezawiązane” w `networth._investments`,
opcja `stocks_entity_prefix` (domyślnie `sensor.nokia_tracker_` w `config.yaml`, `""` w `settings.py`), 8 testów; 1126 testów, ruff i mypy czyste.
Verifier: REJECT z jednym trafnym zarzutem (`stocks.refresh` w jednym `try` z migawką) — naprawione osobnym `try/except` w `record_networth`.
Do sprawdzenia na żywo po wydaniu: brak ręcznego aktywa „Nokia” w Inwestycjach (podwójne liczenie).
