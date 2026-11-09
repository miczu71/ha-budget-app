# Budżet 0.74.0: A) „do spłaty 20.11” bez listopadowych autoryzacji, B) przełącznik karty na Podsumowaniu

## Context
Ekran Karta (0.73.2, na żywo 09.11 ~14:20): do spłaty do 20.11 = **81,29 zł**.
Rachunek: zadłużenie z banku 2 800,37 − zakupy zaksięgowane od 3.11 (203,50 + 336,09 + 181,29 + 536,65 + 1 349,00 + 84,00 = 2 690,53)
− „nieksięgowane” 28,55 = 81,29. Cykl październikowy był rozliczony (sensor 0,00 do 4.11, saldo −1,67).
Całe 109,84 zł różnicy to więc listopadowe autoryzacje, których bank jeszcze nie zaksięgował. Należą do wyciągu z terminem 20.12.

Przyczyna: `ledger.card_unbooked` (`budget/app/src/budget/ledger.py:1017`, commit 8520ac2) odejmuje tylko
przyrost różnicy z ostatnich `IN_TRANSIT_DAYS` = 3 dni. Autoryzacja, która czeka dłużej niż 3 dni (Zalando, sklepy online, weekend),
uznawana jest za „ustabilizowaną” i wraca do „do spłaty”. Stąd skoki 84 → 103,50 → 0 → 29,89 → 81,29 przy kolejnych synchronizacjach.

Podstawa: Regulamin kart kredytowych Bank Millennium (umowy od 20.10.2021, akt. 1.04.2025; wersja dla umów do 19.10.2021 ma te same zapisy):
- def. 6: Cykl rozliczeniowy to „miesięczny okres, po którym Bank rozlicza zadłużenie”,
- def. 68: Wyciąg zawiera „wszystkie kwoty zaksięgowane na Rachunku Karty w danym Cyklu rozliczeniowym”,
- § 13: autoryzacja „blokuje dostępny Limit Karty do czasu rozliczenia” (maks. 30 dni), a rozliczenie następuje najpóźniej następnego dnia roboczego po otrzymaniu zlecenia,
- § 20: brak odsetek, gdy saldo zostanie spłacone w całości przed Terminem spłaty z Wyciągu,
- Cennik: termin spłaty wynosi 20 dni od zamknięcia cyklu. Termin 20.11 oznacza zamknięcie cyklu 31.10.
Wniosek: transakcja zaksięgowana w listopadzie, a tym bardziej sama autoryzacja, nie trafia na wyciąg płatny 20.11.

## Zmiana (repo `/config/addons/ha-budget-app`, gałąź `main`)
Kryterium „za stara różnica” zamieniam na kryterium „różnica sprzed zamknięcia cyklu”:
- `ledger.card_unbooked(conn, account_id, cycle_start: datetime)`: `settled` = różnica (bank − księga od bazy)
  z **ostatniej migawki okna sprzed `cycle_start`** (zamiast migawki starszej o `IN_TRANSIT_DAYS` od ostatniej).
  Nie ma takiej migawki (baza po starcie cyklu) → `settled = 0`.
  Wynik: `max(drift_now − settled, 0)`. Reszta funkcji bez zmian (maks. 3 migawki, `_snapshot_sums`, `_since_base`).
  - Różnica powstała w bieżącym cyklu (autoryzacja, także po 3+ dniach) → odjęta, czyli nie jest do spłaty.
  - Różnica istniejąca już przed 1. dniem miesiąca (brakująca opłata, odsetki, zakup z 31.10 w drodze) → zostaje w „do spłaty”.
    Zabezpieczenie z 8520ac2 zostaje dla poprzedniego cyklu.
- `card.due_status` (`card.py:344`): przekazuje `cycle_start` = północ 1. dnia miesiąca w strefie Europe/Warsaw
  (`fetched_at` jest w ISO z offsetem, porównanie przez `datetime.fromisoformat`).
- `IN_TRANSIT_DAYS` zostaje bez zmian w `check_balances` (kontrola salda). Zmieniają się docstringi `card_unbooked` i komentarz w `card.py:14`.
- Tekst `card.html:33` bez zmian merytorycznych („zakupów, których bank jeszcze nie zaksięgował (wejdą na następny wyciąg)” pozostaje prawdziwe).

## Zmiana B: przełącznik „Odejmij zadłużenie karty” na Podsumowaniu (prośba usera 09.11)
- Przełącznik przenoszę z kafelka Prognoza (`_forecast.html:48–52`, stopka `fc-foot`) do hero „Do wypłaty”
  (`_payday_hero.html:7`). Nagłówek staje się wierszem flex: po lewej `<h2>` „Do wypłaty — 25.11 (data ręczna) · za 16 dni”,
  w prawym górnym rogu przełącznik. Na wąskim ekranie (390 px) przełącznik może zejść pod tytuł, ale bez poziomego przewijania.
  CSS w arkuszu add-onu (np. `.hero-head { display:flex; justify-content:space-between; gap; flex-wrap:wrap }`).
- Domyślnie odznaczony: `forecast.include_card_debt` (`forecast.py:188`) zwraca `kv_get(...) is True` (zamiast `is not False`).
  Zapamiętywanie zostaje bez zmian: `POST /forecast/card-debt` zapisuje kv `forecast_card_debt` (`routes_home.py:426`).
  Uwaga: jeśli na produkcji kv jest już zapisane jako True (wcześniej przełączane), przełącznik zostanie zaznaczony, bo to zapamiętany wybór.
- htmx: formularz w hero wysyła `hx-post` z `hx-trigger="change"`. Podmienia hero (`id="payday-hero"`, `hx-select`, `outerHTML`),
  a `#fc-body` i `#fc-sum` odświeżają się przez `hx-select-oob`, bo zmieniają się kwoty w obu miejscach. Bez JS działa przycisk w `<noscript>` i 303.
- W stopce Prognozy zostaje tekst „karta X zł (nie odjęta)”.
- Skutek uboczny: przy domyślnym „nie odejmuj” encje `sensor.budget_forecast_*` i dzwonek `forecast_low` liczą bez karty
  (atrybut `card_debt_included` = false). To zamierzone i trafi do CHANGELOG.
- Testy: `test_web_home.py:277` (formularz jest w hero, cele htmx), `:484` (domyślnie niezaznaczony; po `include=1` zaznaczony po przeładowaniu),
  `test_forecast.py:372` i inne zakładające domyślne odejmowanie: dopasować do nowego domyślnego.
- Weryfikacja UI: Playwright przez Ingress przy 390 i 1280 px (zrzut, `scrollWidth` ≤ `innerWidth`, konsola), przełączenie i przeładowanie strony.

## Testy zmiany A (`tdd`, `tests/test_ledger.py`)
- NOWY (czerwony przed poprawką): cykl poprzedni rozliczony; autoryzacja 100 zł widoczna w ITBD od 4.11,
  ostatnia migawka 9.11 (> 3 dni) → `card_unbooked == 100`, `due_status.left == 0`.
- `test_card_unbooked_ignores_stuck_difference`: różnica 40 z 25.10 nadal zostaje (`0`), przyrost 100 z 4.11 → `100`; ma przejść bez zmian.
- Pozostałe testy `card_unbooked`/`due_status` przechodzą; dopisać argument `cycle_start` w wywołaniach.
- `pytest`, `ruff`, `mypy` w `budget/app`.

## Wydanie
`simplify` → `code-review` + w równoległych subagentach `silent-failure-hunter`, `pr-test-analyzer` i security `general-purpose` (repo + `b387ff5..HEAD`)
→ skill `release` **0.74.0** (A + B razem; B to nowa funkcja UI) (backup add-onu przez `ha_manage_updates`, CHANGELOG po polsku, release opublikowany).

## Weryfikacja na żywo
- Po instalacji i synchronizacji (albo od razu, bo liczone przy renderze): `sensor.budget_card_due` = 0,00, `/card` przez Ingress pokazuje „Spłacone” albo 0 zł,
  wiersz „nieksięgowane” ≈ 109,84 zł; konsola bez błędów.
- 20.11: porównanie z kwotą do spłaty w aplikacji banku (wg księgi −1,67, czyli 0).

## Poza zakresem (decyzja usera 09.11)
Okno `BOOKING_LAG` (zakupy zaksięgowane 1.–2. dnia liczone do poprzedniego wyciągu) zostaje bez zmian. Według def. 68 regulaminu
może być błędne. User rozstrzygnie to 20.11, porównując z wyciągiem w aplikacji banku.

## Rollback
Revert commitu (A i B to osobne commity) + 0.74.1 albo przywrócenie backupu add-onu 0.73.2.
