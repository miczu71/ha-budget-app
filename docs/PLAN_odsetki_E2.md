# E2 — zwięzły wiersz oferty

Zakres wg `ROADMAP_odsetki_oferty_loga.md` (E2). Małe (3 edycje, bez migracji), więc bez workera.

## Kroki
1. `web/templates/invest.html`, makro `offer_row`: widoczne są nagłówek (rodzaj · bank), linia „stawka · marża · okres · limit”, warunki w jednej linii z `ellipsis`, linia źródła (plakietka „tylko dla nowych”, źródło, „opis oferty”). Pełne warunki, formularz „Potwierdź”, „Skorzystaj”, „Odrzuć/Usuń” i notka „pominięta” trafiają do `<details class="offer-more">`.
2. `web/static/app.css`: klasy `offer-item`, `offer-head`, `offer-line`, `offer-cond`, `offer-more` (unikalne nazwy).
3. `tests/test_web_invest.py`: oferta `review` renderuje `<details class="offer-more">` z formularzem „Potwierdź”.

## Weryfikacja
pytest + ruff + mypy; devserve + Playwright 390 px: brak przepełnienia poziomego, wiersz ≤ ~120 px.

## Rollback
`git revert` commitu etapu.
