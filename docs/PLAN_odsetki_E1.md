# E1 — Odsetki z banku: typ `interest` i kategoria „Odsetki”

Źródło: `docs/ROADMAP_odsetki_oferty_loga.md`. Bank z API (Velobank) księguje odsetki jako dwa wpisy:
„Odsetki - Kapitalizacja odsetek” (+) i „Podatek od odsetek” (−). Dotąd były przelewami i wymagały
ręcznej kategorii. Teraz oba dostają typ `interest` i podkategorię Przychody → Odsetki (netto).

## Wykonawca

**WORKTREE:** podany przez rodzica (`wt new`). Pracuj tylko tam. Skill `addon-conventions`, TDD (test najpierw).

Pliki i zmiany (ścieżki względem `budget/app/`):

1. `src/budget/kinds.py`
   - `Kind.INTEREST = "interest"` (komentarz: kapitalizacja odsetek i podatek od odsetek).
   - Stała `INTEREST_RE = re.compile(r"KAPITALIZACJA ODSETEK|PODATEK OD ODSETEK")` (dopasowanie na `fold(description)`).
   - W `from_api`: zaraz po sprawdzeniu `if card_account: ...` i wyliczeniu `desc`, a PRZED gałęzią `counterparty_account`:
     `if INTEREST_RE.search(desc): return Kind.INTEREST`. Opis ratę kredytu Millennium ma słowo „ODSETKI:” — NIE pasuje do wzorca (wymaga „KAPITALIZACJA ODSETEK”/„PODATEK OD ODSETEK”).
   - W `from_csv`: ten sam test na `desc` przed `_CSV_FALLBACK` (sprawdź, jak funkcja wylicza `desc`, i użyj tej zmiennej).
2. `src/budget/web/common.py` — `KIND_LABELS["interest"] = "odsetki"`.
3. `src/budget/suggest/redact.py` — `KIND_LABELS[Kind.INTEREST.value] = "odsetki"`.
4. `src/budget/storage/migrations/030_interest.sql`
   - `INSERT INTO category (id, parent_id, slug, name, flex_group, sort, ...)` podkategoria: id `103`, parent `1`, slug `odsetki`, nazwa `Odsetki`, `income`, sort `25` — kolumny i ostatnią wartość (`1`) skopiuj z wzorca wierszy 100–102 w `003_categories.sql`; sprawdź, że id 103 jest wolne (`grep -rn "103" storage/migrations`).
   - `UPDATE txn SET kind = 'interest' WHERE kind_source <> 'manual' AND` opis (`UPPER(description)` lub kolumna po `fold`, wzoruj się na tym, jak inne migracje porównują opisy; jeśli brak SQL-owego odpowiednika `fold`, użyj `UPPER(description) LIKE '%KAPITALIZACJA ODSETEK%' OR ... '%PODATEK OD ODSETEK%'`).
   - Dla tych wierszy z `category_source = 'manual'`: `UPDATE txn SET category_id = NULL, category_source = NULL, rule_id = NULL` (silnik przypisze kategorię przy starcie `recategorize`). Tylko wiersze z `kind = 'interest'`.
5. `src/budget/categorize/engine.py`
   - `KIND_DEFAULTS[Kind.INTEREST.value] = "odsetki"`.
   - W `_classify`: wpis typu `interest` ma pierwszeństwo przed gałęziami `t.savings` i `t.transfer` (czyli nie jest traktowany jako przelew na oszczędności ani pozbawiany kategorii). Reguły użytkownika i `manual` nadal wygrywają (kolejność jak dziś: manual → interest → savings → transfer → rule → …). Zrób to minimalnie: dodaj gałąź `elif t.facts.kind == Kind.INTEREST.value and "odsetki" in slugs:` PO `is_manual`, a PRZED `t.savings`; kategoria źródło `"kind"`.
6. Ledger/transfery: sprawdź (`ledger._analyze`, `rebuild_links`), czy wiersz typu `interest` może trafić do `transfer_group` albo `savings_transfer_ids` (kind transfer_*). Jeśli `_analyze` filtruje po `TRANSFER_KINDS`, typ `interest` tam nie wejdzie i nic nie zmieniaj; jeśli filtruje inaczej, dopilnuj, by `interest` był wyłączony. Opisz w raporcie, co sprawdziłeś.

Testy (najpierw czerwone, potem zielone):
- `tests/test_kinds.py`: `from_api("Odsetki - Kapitalizacja odsetek", +, counterparty_account=NRB)` = INTEREST; `"Podatek od odsetek"` ujemne = INTEREST; rata kredytu z tekstem „ODSETKI: 4024.91PLN” NIE jest INTEREST; to samo dla `from_csv`.
- `tests/test_categorize_engine.py`: transakcja `interest` dostaje kategorię `odsetki` ze `source="kind"`, nawet gdy ma `counterparty_account`; transakcja z `category_source='manual'` zostaje przy ręcznej kategorii.
- `tests/test_storage.py` (albo najbliższy test migracji): schemat ≥ 30; baza z wpisem „Kapitalizacja odsetek” (kind `transfer_in`, ręczna kategoria) po migracji ma `kind='interest'` i `category_id IS NULL`.
- Pełny zestaw: `cd budget/app && BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q` + `ruff check .` + `ruff format --check .` + `mypy`.

W worktree `.venv` może nie istnieć: użyj `/config/addons/ha-budget-app/budget/app/.venv/bin/python` z `cd <WORKTREE>/budget/app` (editable install wskazuje na klon — jeśli testy ładują kod z klona zamiast z worktree, ustaw `PYTHONPATH=<WORKTREE>/budget/app/src`).

**DONE:** nowe testy zielone, cały `pytest` zielony, `ruff` i `mypy` bez błędów; `git -C <WORKTREE> status --short` zawiera tylko pliki z listy powyżej (+ testy); raport z wynikami komend i odpowiedzią na pkt 6.

**NIE RÓB:** nie commituj, nie pushuj; nie ruszaj `config.yaml`/wersji, `invest*`, `savings.py`, szablonów HTML poza opisanymi, `docs/`; nie dotykaj `~/budget_dev`; w testach i komentarzach tylko neutralne nazwy (bez prawdziwych danych, bez nazw miejscowości i ulic); nie zmieniaj istniejących testów poza dopisaniem nowych; nie obchodź hooka.

## Rollback
`wt drop` przed landem; po landzie `git revert`. Migracja addytywna (nowa kategoria + przeliczenie typu 2 wierszy); po cofnięciu te wpisy wracają do ręcznej kategoryzacji.

## Weryfikacja na żywo (po wydaniu 0.71.0)
`/transactions?q=odsetk`: oba wpisy z 31.10 w kategorii „Odsetki”, źródło nie „ręczna”; suma kategorii za październik = 120,71 zł.
