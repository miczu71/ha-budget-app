# Kredyt: kalibracja harmonogramu z bankiem (M9, poprawka po checkpoincie 0.43.0)

## Context
Checkpoint M9 („user wpisuje kredyt, porównujemy z bankiem ±1 zł”) wykazał rozbieżności. Harmonogram banku
(rata 4 787,42, saldo przed ratą 14-10-2026 766 030,34, 5,90%, ostatnia rata 29-12-2052 4 947,37):
- **Odsetki:** bank = saldo × stopa / 12 za każdy pełny miesiąc (30/360; ostatni okres 45 dni → 36,22 =
  45/360). Add-on liczy dni/365 → odsetki skaczą ±60 zł/mies., suma do końca 743 308 vs bank 742 167 (+1 140 zł).
- **Ostatnia rata:** add-on stawia ją w dniu raty (14-12-2052, 6 025 zł), bank w dniu końca kredytu (29-12-2052).
- **Rata:** wzór daje 4 787,62, bank 4 787,42 (bank przelicza ratę przy resecie WIBOR po swojemu) →
  user wybrał opcjonalne pole „rata wg banku”.
Symulacja 30/360 + rata banku + ostatni dzień = data końca: suma odsetek różni się od banku o 0,22 zł,
saldo przed ostatnią ratą o 0,22 zł.

## Zmiany (repo `/config/addons/ha-budget-app`, gałąź `main`)
1. `budget/app/src/budget/loan.py`
   - `_days360(a, b)` (30E/360: dzień 31 → 30) i odsetki `(waga + saldo × dni360) × stopa / 100 / 360`
     w `run()` (także pierwszy okres dzielony nadpłatą dziś). Docstring modułu: 30/360 zamiast act/365.
   - `payment_dates`: w miesiącu `last` dzień raty = `last` (nie dzień raty przycięty).
   - `Loan.installment: Decimal | None`; w `run()` przy racie równej i braku `seed`: `level = lo.installment`
     (przeliczenie `reprice` nadal przy zmianie stopy / nadpłacie „niższa rata”). `save()` przyjmuje
     `installment` (puste = None, > 0), `_row` czyta kolumnę.
2. `storage/migrations/016_loan_installment.sql`: `ALTER TABLE loan ADD COLUMN installment TEXT` (addytywna).
3. `web/routes_loan.py` + `templates/loan.html`: pole „Rata wg banku (opcjonalnie)” w formularzu, tylko
   dla rat równych (placeholder „z harmonogramu banku”).
4. Testy `tests/test_loan.py`: odsetki = saldo × r/12 w pełnym miesiącu (neutralne liczby, np. 100 000 zł,
   6%, 500,00), ostatnia rata w dniu `last_payment_date` z odsetkami za 45 dni/360, rata ręczna używana jako
   poziom i domyka saldo ostatnią ratą; aktualizacja istniejących testów, które zakładały /365.
   `test_loan_sim.py`/`test_web_loan.py` — poprawić oczekiwane kwoty, jeśli zależą od konwencji.
5. `docs/PLAN_M9.md` § Wynik: kalibracja (30/360, data końca, rata wg banku); CHANGELOG.

## Wydanie
`simplify` → skill `release` (0.44.1 albo 0.45.0 wg CHANGELOG; migracja 016 sprawdzona na kopii księgi
`~/budget_dev/prod/ledger.db`). Bez pushy 02:45–03:15. User po instalacji wpisuje w kredycie „ratę wg banku”
4 787,42 (i ew. kapitał na dzień ostatniej raty).

## Ryzyka
- Kwoty bankowe co do grosza: bank zaokrągla odsetki czasem w dół (3 766,31 vs 3 766,32) — tolerancja ±1 grosz/ratę.
- Rata wg banku nieaktualna po zmianie WIBOR → dzwonek `loan_rate` (już jest) pokaże różnicę z księgą.
- Cofnięcie: kolumna zostaje (addytywna), revert commitu.

## Weryfikacja
- `BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, ruff, mypy.
- Skrypt porównawczy (scratchpad, dane tylko lokalnie): kredyt 766 030,34 na 2026-09-14, 3,8 + 2,1,
  rata 4 787,42, koniec 2052-12-29, dzień 14 → 315 rat; 1. rata odsetki 3 766,31±0,01, kapitał 1 021,11±0,01;
  saldo po 12 ratach ≈ 753 440,25; ostatnia rata 29-12-2052 ≈ 4 947,37; suma odsetek ≈ 742 166,91 (±1 zł).
- Devserve + Playwright: ekran `/loan` z nowym polem (360/1280 px, konsola), po wydaniu na żywo przez Ingress.
