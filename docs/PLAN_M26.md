# M26 Majątek netto — plan (ha-budget-app)

## Kontekst
Następny otwarty kamień roadmapy Budżetu po zamknięciu M22 (0.59.0, M17 scalone jako E5). M26 wydzielono
z M9 (decyzja 28). Cel z wywiadu 2026-10-20: **trend** („czy jest lepiej niż rok temu”), **bilans na dziś**
i **wejście dla decyzji** (agent M22, kalkulator nadpłaty M9, czat).

### Podsumowanie wywiadu
1. **Kto korzysta:** domownicy w panelu (nowa zakładka „Majątek” + kafel na Podsumowaniu), agent M22 i czat
   (nowe źródło), HA (sensor).
2. **Automatycznie:** codzienna migawka, jednorazowe odtworzenie końców miesięcy wstecz, linijka w miesięcznym
   podsumowaniu M6 (majątek + zmiana m/m + „zaktualizuj wartość Y” dla aktywów starszych niż 90 dni).
3. **Za zgodą/ręcznie:** wartości aktywów M22, powiązanie „to samo co oszczędność X”. Bez osobnych alertów.
4. **Sukces:** liczba na ekranie zgadza się z ręczną sumą składników co do 1 zł; wykres pokazuje ≥12 miesięcy
   od pierwszego dnia; zmiana r/r widoczna od razu (punkty odtworzone oznaczone „przybliżone”).

### Decyzje (→ decyzja 31 w ROADMAP)
- **Tylko majątek finansowy**: bez nieruchomości i aut; wynik może być ujemny przez hipotekę.
- **Aktywa:** konta bankowe (bieżące PLN, EUR po kursie średnim NBP z tabeli A), oszczędności M10
  (`savings.overview().total`), skarbonki (`piggy.statuses`), aktywa M22 (`invest_asset`) **z pominięciem
  powiązanych z oszczędnością M10** (nowa kolumna `savings_id`).
- **Pasywa:** kredyt(y) M9 (`loan.summary(...).principal`), zadłużenie karty (ITBD z `card.due_status`).
- **Wskaźniki:** płynność = (konta + oszczędności + skarbonki) / mediana miesięcznych wydatków (w miesiącach);
  LTV = kredyt / aktywa finansowe.
- **Aktywa M22:** kolumna `valued_at` („wartość z dnia X”), przypomnienie po 90 dniach tylko w podsumowaniu.
- **Parking oszczędności (dopisane 2026-10-20):** środki wyprowadzone z Profit (przez bieżące Millennium) do
  innego banku na przerwę między edycjami promocji nadal są oszczędnościami. Konto docelowe = drugie konto M10
  z flagą `parking_for` (id konta Profit). Wypłata z Profit + wpłata na parking w ciągu 7 dni, kwota ±1 zł =
  „przeniesienie” (bez wpływu na stopę oszczędności M10 E4). Przy nowej edycji promocji (`promo_watch`)
  dzwonek „przenieś X zł z parkingu do Profit”.
- **Poza zakresem:** M11 (tracker akcji), auto-odsetki obligacji, alerty spadku/kamieni milowych.

## Repo i pliki
`/config/addons/ha-budget-app`, gałąź `main`; kod w `budget/app/src/budget/` (dalej `B/`).
- Nowe: `B/networth.py`, `B/storage/migrations/027_networth.sql`, `B/web/routes_networth.py` + szablon,
  `B/fx.py` (kurs NBP — odzyskany z `82ce0ff^`, tabela `fx_rate` z migracji 020 już istnieje, nieużywana).
- Zmieniane: `B/service.py` (`daily_tick` → migawka), `B/summary.py` (`monthly`), `B/ha_publisher.py`
  (`build_entities`), `B/ask/sources.py` (źródło „majatek”), `B/invest.py` / `invest_why.py` (wskaźniki
  do agenta), `B/nav_layout.py` (zakładka), formularz aktywa M22 (powiązanie + data wartości).
- Do ponownego użycia: `ledger.latest_balances`, `forecast.read_balances` (EUR, card_debt), `savings.estimate`,
  `piggy.statuses`, `invest.assets_total`, `loan.schedule/summary`, mediana wydatków z M18 (`forecast`/`flex`).

## Etapy (każdy = commit, TDD; wydanie jedno na końcu: **0.60.0**)
- **E0 Dokumenty:** `docs/PLAN_M26.md` (ten plan + sekcje Wykonawca), wiersz M26 i decyzja 31 w ROADMAP.
- **E0b Parking M10 ✅ 2026-10-20:** migracja 026 `savings_account.parking_for`; w formularzu konta oszczędnościowego
  „parking dla …”; parowanie przeniesień w `savings.movements`/`monthly_rates` (ruchy pokazane jako
  „przeniesienie”, nie wypłata/wpłata); dzwonek w `promo_watch` przy nowej edycji, gdy parking ma saldo > 0.
  Po wdrożeniu user dodaje konto docelowe z saldem 0 na dzień przed przelewem. Rollback: revert, kolumna
  addytywna.
- **E1 Model ✅ 2026-10-20:** `fx.py` (NBP z odzyskanego kodu M23, cache w `fx_rate`, fallback na ostatni znany kurs),
  `networth.compute(conn, day) -> NetWorth` (składniki, sumy, płynność, LTV, flaga approx); migracja 027:
  `invest_asset.savings_id`, `invest_asset.valued_at`, tabela `networth_snapshot(day PK, total, assets,
  liabilities, components_json, approx)` (migracja 027). Testy jednostkowe na fixturach (w tym dubel M10↔M22, EUR, 2 kredyty).
  Rollback: revert; migracja addytywna (starsza wersja ignoruje).
- **E2 Historia ✅ 2026-10-20:** migawka w `daily_tick`; jednorazowe odtworzenie końców miesięcy od najstarszej transakcji
  (saldo = dzisiejsze − transakcje po dacie; M10/skarbonki z przelewów; kredyt z harmonogramu; M22 = dzisiejsza
  wartość od `start_date`, karta przed pierwszą transakcją = 0; wszystko `approx=1`). Idempotentne.
  Rollback: revert + `DELETE FROM networth_snapshot`.
- **E3 Ekran:** zakładka „Majątek” (bilans aktywa/pasywa, wykres miesięczny z oznaczeniem przybliżeń, m/m, r/r,
  płynność, LTV, „wartość z dnia X”), kafel na Podsumowaniu, w formularzu aktywa M22 pole „to samo co
  oszczędność” + data wartości. Projekt skillem `impeccable` (system Monarch), weryfikacja Playwright 360/1280 px.
- **E4 Integracje:** `sensor.budget_net_worth` (atrybuty: assets, liabilities, liquidity_months, ltv, change_mom,
  change_yoy), linijka w podsumowaniu miesięcznym + przypomnienie o starych wartościach, źródło czatu „majatek”,
  płynność i LTV w uzasadnieniu agenta M22.
- **Koniec:** `simplify` → `code-review` → `release` 0.60.0 (backup add-onu przez `ha_manage_updates`).

## Weryfikacja
- `uv run pytest` w repo add-onu (wszystkie testy zielone, nowe testy `test_networth*.py`).
- Po wydaniu: stopka v0.60.0, `/networth` 200, suma składników na ekranie = suma z `networth_snapshot`,
  `sensor.budget_net_worth` w HA (`ha_get_state`), czat: „ile wynosi mój majątek netto?” zgodne z ekranem,
  konsola przeglądarki bez błędów.
- Parking: po dodaniu konta docelowego suma oszczędności M10 = stan sprzed wyprowadzenia (± odsetki), ruchy
  widoczne jako „przeniesienie”, stopa oszczędności za ten miesiąc bez spadku.
- Checkpoint usera: porównanie salda kont/oszczędności z bankiem na dziś.

## Wynik E0b (2026-10-20)
`savings_account.parking_for` (026), parowanie przeniesień w `savings._paired` (≤7 dni, ±1 zł, każdy ruch w jednej parze;
oznaczone ruchy nie liczą się do `MonthRate.saved`), pole „Parking dla” w formularzu konta, etykieta „przeniesienie”
w rozwiniętym miesiącu, dopisek o zaparkowanych środkach w pushu `promo_confirm` (`savings.parked`). 1087 testów,
ruff i mypy czyste. Podgląd w przeglądarce dopiero przy E3/wydaniu (zmiana formularza jest mała, pokryta testem renderu).

## Wynik E1 (2026-10-20)
`fx.py` (odzyskane z `82ce0ff^`, bez części kartowej: `Rates.at`, `refresh(conn, day, get, since)` — jeszcze niepodpięte,
wywoła je `daily_tick` w E2), `networth.py` (`compute(conn, day, spend)` → `NetWorth`: składniki per grupa, aktywa/pasywa/total,
płynność, LTV, `stale`, `missing_fx`), migracja 027 (`invest_asset.savings_id`/`valued_at`, `networth_snapshot`),
`invest.link_savings` (formularz powiązania dopiero w E3), `valued_at` ustawiane przy zmianie kwoty. 1099 testów, ruff i mypy czyste.
Uwaga dla E2: `compute` bierze salda z OSTATNICH migawek, więc przeszłe dni trzeba liczyć osobną ścieżką odtwarzania, nie `compute`.

## Wynik E2 (2026-10-20)
`networth.compute(..., past=True)` / `reconstruct(conn, day)` (salda kont cofnięte o późniejsze transakcje BOOK, karta = dług − wydatki po dniu,
0 przed pierwszą transakcją; skarbonki z przelewów do dnia; oszczędności/kredyty/aktywa dopiero od daty otwarcia/startu), `save` (dokładna migawka
zastępuje, przybliżona nigdy nie nadpisuje), `first_day`, `has_history`, `backfill` (końce miesięcy od najstarszej transakcji, tylko gdy tabela pusta).
`Service.record_networth` (kursy NBP → backfill z `fx.refresh(since=pierwszy dzień)` → migawka na dziś ze `spend` z `invest_advice`) wołane
na starcie `daily_tick` i po każdej północy; błąd nie zatrzymuje pętli. 1104 testów, ruff i mypy czyste. Plan E2 wykonany bez workera
(ok. 5 edycji w 3 plikach, robione bezpośrednio).
