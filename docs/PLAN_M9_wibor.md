# Kredyt: śledzenie WIBOR 3M i informacja o nowej racie (M9 E4)

## Context
Kredyt ma zmienne oprocentowanie (WIBOR 3M + marża). Bank zmienia stopę co 3 miesiące, **9. dnia**
(9.03/9.06/9.09/9.12), a zmiana pojawia się w banku przed północą tego dnia. User chce wiedzieć z góry,
jaka będzie rata, a dzień po zmianie (10.) dostać powiadomienie z nową stopą i ratą.

Ograniczenia z wywiadu:
- Korzysta: user (ekran Kredyt, dzwonek, telefon) i HA (atrybuty encji `sensor.budget_loan_principal`).
- Automatycznie: codzienny odczyt WIBOR 3M, prognoza raty od najbliższej zmiany, powiadomienie 10. dnia
  miesiąca zmiany.
- Tylko za zgodą usera: zmiana stopy w kredycie. Add-on niczego w kredycie nie nadpisuje, karta w dzwonku
  linkuje do formularza.
- Sukces: 10.12.2026 przychodzi powiadomienie „WIBOR 3M X% → stopa Y%, rata ≈ Z zł”, a rata różni się
  od nowej raty banku o ≤ 1 zł (do skalibrowania: bank może brać fixing z innego dnia niż 9.).

Źródło danych: `https://www.bankier.pl/mieszkaniowe/stopy-procentowe/wibor?rateDate=YYYY-MM-DD`. Strona
zwraca 200 bez JS i zawiera „Data|2026-10-09|…|WIBOR 3M|3,88%”. Stooq odrzucone (wyzwanie JS),
money.pl zwraca 404.

## Etapy (commity; jedno wydanie na koniec)
Pierwszy krok: ten plan → `docs/PLAN_M9_wibor.md`, wiersz E4 w `docs/ROADMAP.md`.

**E4a — odczyt WIBOR** (`budget/app/src/budget/wibor.py`, wzorzec `promo_watch.py`):
- `fetch(client, day)` → `(data_notowania, wartość)`, parser regexem; `refresh(conn, now)` raz dziennie
  zapisuje do `kv` (`db.kv_*` jak w promo_watch, klucz `wibor`) ostatnie notowanie i licznik błędów.
- Wywołanie w `service.summaries()` obok `watch_promo()`, tylko gdy jest kredyt (`loan.all_loans`).
- Karta w dzwonku po `ERROR_ALERT_DAYS` nieudanych dniach (jak promo_watch).
- Testy: parser na zapisanym fragmencie HTML (neutralny fixture), refresh z mockiem httpx.

**E4b — data zmian i prognoza:**
- Migracja `017_loan_reset.sql`: `ALTER TABLE loan ADD COLUMN rate_reset_date TEXT` (ostatnia znana
  zmiana oprocentowania; kolejne co `RESET_MONTHS = 3`). Pole w formularzu „Ostatnia zmiana oprocentowania”.
- `loan.next_reset(lo, today)` i `loan.forecast(lo, wibor, today)` → rata od najbliższej zmiany:
  `run()` z `Scenario(wibor_delta=wibor − lo.reference_rate, wibor_from=next_reset)` (silnik już
  obsługuje zmianę stopy od daty i liczy ratę na nowo, `loan_sim._start` daje kapitał/ziarno).
- Ekran `/loan` (kafel kredytu): „WIBOR 3M 3,88% (9.10) → od 9.12 rata ≈ X zł (+Y)”. Atrybuty encji:
  `wibor`, `wibor_date`, `next_reset`, `forecast_installment` (`ha_publisher`).

**E4c — powiadomienie 10. dnia i dzwonek:**
- `summary.due`: w dniu `next_reset + 1` (o `SEND_AT`, przez `summary_notify_service` jak inne
  powiadomienia add-onu) wiadomość „Kredyt: od 9.12 WIBOR 3M A% (notowanie z DD.MM) → stopa B%, rata ≈ X zł
  (było Y)”. Notowanie pobierane z `rateDate` = dzień zmiany (ostatnie notowanie ≤ tego dnia). Raz na zmianę
  (`mark_sent`).
- `inbox`: karta „Nowy WIBOR od 9.12 — zaktualizuj kredyt” od dnia zmiany, dopóki `reference_rate` w kredycie
  ≠ notowaniu z dnia zmiany; link `/loan?edit=…`. Istniejąca karta `loan_rate` zostaje.

## Wydanie
`simplify` → skill `release` (0.45.0, CHANGELOG, migracja 017 na kopii księgi), weryfikacja na żywo
(playwright-ha: kafel WIBOR, pole daty), bez pushy 02:45–03:15. Po instalacji user wpisuje „Ostatnia zmiana
oprocentowania” 09.09.2026.

## Ryzyka
- Scraping bankier.pl może się zepsuć przy zmianie strony → licznik błędów i karta w dzwonku. Nie blokuje
  reszty add-onu, bo `refresh` nigdy nie rzuca.
- Bank może liczyć WIBOR z innego dnia (np. 2 dni robocze przed 9.) → pierwsza zmiana 9.12 to kalibracja:
  porównać z ratą banku, ewentualnie stała `FIXING_LAG_DAYS`.
- Cofnięcie: migracja addytywna, revert commitów.

## Weryfikacja
- pytest + ruff + mypy po każdym etapie.
- Ręcznie: `wibor.fetch` na żywo dla dzisiaj i `rateDate=2026-09-09` (scratchpad); prognoza dla danych
  kredytu przy WIBOR 3,88% policzona niezależnym skryptem annuitetowym (30/360) zgodna co do grosza.
- `summary.due` z podstawioną datą 2026-12-10 zwraca wiadomość, 2026-12-11 już nie (po `mark_sent`).
- UI: devserve + Playwright 390 i 1280 px, konsola bez błędów; na żywo po wydaniu.
