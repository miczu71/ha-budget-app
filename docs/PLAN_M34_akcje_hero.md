# Budżet: kafelek Akcje tylko z kwotą + „ponad zaplanowane” w hero Do wypłaty

## Context
Prośba usera (2026-10-28) dotyczy strony głównej Budżetu (`ha-budget-app`, 0.67.0):
1. **Akcje.** Kafelek nad hero ma pokazywać tylko kwotę wolnych akcji. Kwota to już `holding.market_value`, czyli same zawiązane akcje (niezawiązane są osobną pozycją w majątku). Znikają dopiski „zawiązanie DD.MM” i „nieaktualne” (user wybrał „Tylko kwota”).
2. **Hero „Do wypłaty”.** Ma pokazywać, ile zostanie ponad stałe i zaplanowane pozycje. Definicja usera: aktualny stan konta + kolejne wpływy do wypłaty − wszystkie zaplanowane cykliczne − skarbonki. To dokładnie `fc.at_payday`, wynik paska równania w kafelku prognozy (`_forecast.html`, `fc-result`). Liczy się w nim:
   - wolne dziś (konto, a przy włączonej opcji `forecast_card_debt` także minus dług karty);
   - minus serie;
   - plus mniejsze wpływy;
   - minus skarbonki.

   To saldo na dzień wypłaty, przed wpłynięciem wypłaty. Bufora nie odejmujemy. Nowych obliczeń nie ma.

Repo: `/config/addons/ha-budget-app` (PUBLIC), gałąź `main`, kod `budget/app/src/budget/`.

## Zmiany
1. `web/templates/_balance_tiles.html`: usunąć cały blok `{% if tiles.stocks_stale or tiles.stocks_vest %}…{% endif %}` (linie 15–17). Kafelek = etykieta + kwota.
2. `web/routes_home.py`: pola `stocks_vest` i `stocks_stale` w `BalanceTiles` oraz ich wyliczenie w `balance_tiles()` osierocą się, więc je usuwam. Import `timedelta`/`date` zostaje, jeśli nadal jest używany (sprawdzić ruffem).
3. `web/templates/_payday_hero.html`: pod kwotą dzienną (`hero-amount`) dodać linię:
   `<p class="hero-left"><span class="muted">Ponad zaplanowane do {{ payday|horizon }}</span> <strong class="{{ 'neg' if fc.at_payday < 0 else 'pos' }}">{{ fc.at_payday | money("PLN") }}</strong></p>`.
   Napis daty: „do wypłaty” albo „do końca miesiąca” bez wypłaty. Linia jest zawsze widoczna, a ujemna kwota jest czerwona. Ewentualnie mały styl w `app.css`, wzorowany na istniejących klasach hero (`impeccable` tylko do szybkiej oceny, bez przebudowy).
4. Testy `tests/test_web_home.py` (TDD, najpierw czerwone):
   - `test_stocks_tile_shows_vested_value_and_next_vest_only` zmienia się w „tylko kwota”: brak „zawiązanie” i „nieaktualne”;
   - `test_stocks_tile_marks_stale_value` zmienia się w „stare dane nadal bez dopisku” (albo usunięcie testu);
   - nowy test: hero zawiera „Ponad zaplanowane” i kwotę `fmt_money(fc.at_payday)`, wyliczoną z tej samej prognozy (`service.forecast()`).
5. `docs/ROADMAP.md`: krótki wpis (M34 albo poprawka), CHANGELOG, bump do **0.68.0**.

## Weryfikacja
- `cd budget/app && BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, ruff, mypy.
- Łańcuch wydania wg CLAUDE.md:
  - `simplify`;
  - `code-review`, równolegle `silent-failure-hunter`, security review (`general-purpose`) i `second-opinion` (pomiar 5/10);
  - skill `release` (0.68.0, opublikowany);
  - aktualizacja przez `ha_manage_updates`.
- Na żywo (`playwright-ha`): screenshot strony głównej. Kafelek Akcje ma tylko kwotę, hero ma linię „Ponad zaplanowane”, a jej kwota = „=” w kafelku prognozy. Plus `browser_console_messages`.

## Rollback
`git revert` commitu i wydanie 0.68.1. Dane i migracje nie są ruszane.
