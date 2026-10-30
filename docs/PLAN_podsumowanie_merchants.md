# Budżet — poziom 3 donuta wg sprzedawców (0.70.0)

## Context
Wykres „Gdzie poszły pieniądze” (0.69.0, E4 `docs/ROADMAP_podsumowanie.md`) na poziomie 3 (podkategoria) pokazuje
pojedyncze transakcje (top 6 + „Pozostałe”). Przy częstych zakupach (np. 9× Lidl w „Spożywcze”) wycinki to
powtórzenia tego samego sklepu, a sklepy z wieloma drobnymi zakupami giną w „Pozostałe”. User wraca do odrzuconej
wcześniej propozycji: poziom 3 = **sprzedawcy** (suma i liczba transakcji na sklep).

## Zachowanie
- Poziom 3 (`cat=&sub=`): wycinek = sprzedawca, kwota = suma zakupów w okresie, legenda „N transakcji” (już liczy `count`).
  Top 6 + „Pozostałe” bez zmian (`charts.drill_slices`).
- Klucz grupy: `fold(t.merchant)` (pole `merchant` jest już znormalizowane przez `categorize/merchants.base_merchant`
  + słownik/reguły — „Lidl” to jedna nazwa). Bez `merchant`: `merchant_ident(counterparty_name or description)`,
  pusty → „—”. Etykieta = najczęstsza oryginalna nazwa w grupie (przycięta jak dziś, `PURCHASE_LABEL`).
- Klik wycinka/legendy sprzedawcy → `/transactions?category=<leaf>&q=<etykieta>&<okres>` (Szukaj po `fold`
  obejmuje `t.merchant`); „Pozostałe” i „Zobacz transakcje »” jak dziś. Bez poziomu 4.
- Środek donuta bez zmian (suma zakupów, „w podkategorii”).

## Zmiany (`/config/addons/ha-budget-app/budget/app/`)
1. `src/budget/spending.py`: `Purchase` → `Merchant(label, amount, count)` i `purchases()` → `merchants()`
   grupujące jak wyżej (malejąco po kwocie). Reużyć `normalize.fold`, `normalize.merchant_ident`.
2. `src/budget/web/routes_home.py` (poz. 3, ~l. 244–263): `Item(key=f"shop-{n}", label, amount, count, href=…&q=<urlencode label>)`;
   `drill_total` = suma `amount`.
3. Testy (najpierw czerwone): `tests/test_spending.py` (dwa zakupy „Sklep X” → jedna pozycja z sumą i count=2;
   fallback na kontrahenta; zwroty pominięte; część podziału M29 liczy się do sprzedawcy), `tests/test_web_home.py`
   (poz. 3 pokazuje sprzedawcę raz, link z `q=`). Zastąpione testy `purchases` — przerobić na `merchants`.
4. `CHANGELOG`, bump 0.70.0 (skill `release`), wpis „Wynik” w `docs/ROADMAP_podsumowanie.md` (dług „klucz `txn-<id>`
   przy częściach podziału” znika).

Robię sam (≤ 5 edycji, bez workera), TDD + `addon-conventions`. Potem `simplify` → `code-review` (+ silent-failure-hunter,
pr-test-analyzer, security general-purpose na `<v0.69.0>..HEAD`) → `release` → weryfikacja na żywo.

## Weryfikacja
- `cd budget/app && BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests && .venv/bin/mypy src`
- Na żywo (playwright-ha, Ingress): Podsumowanie → Spożywcze → podkategoria: Lidl jeden wycinek z „N transakcji”,
  klik → lista transakcji z filtrem Lidl i okresem; konsola bez błędów; 390 px bez przewijania poziomego.

## Rollback
`git revert` commitu albo instalacja 0.69.0 (UI bez migracji).
