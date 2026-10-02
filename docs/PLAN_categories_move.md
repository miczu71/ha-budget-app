# Budżet Domowy 0.6.0 — nowe kategorie główne i przenoszenie podkategorii

## Context
User chce przegrupować istniejące podkategorie pod nowe kategorie główne, żeby ekran „Wydatki”
lepiej pokazywał, gdzie idą pieniądze. Dziś zakładka Kategorie umie tylko dodać podkategorię
i zmienić nazwę. Przenoszenie odłożono na M5 (docstring `taxonomy.py`). Transakcje, reguły,
słownik i podpowiedzi AI wskazują na **podkategorię** (id/slug), a kategoria główna tylko grupuje.
Przeniesienie to więc `UPDATE category SET parent_id`: historia, reguły i ręczne przypisania idą
za podkategorią bez przeliczania księgi, a „Wydatki” od razu pokazują nowy podział, także wstecz.

Jeden etap (mała, samodzielna wartość) → jeden checkpoint. Repo: `/config/addons/ha-budget-app`
(`miczu71/ha-budget-app`), branch `main`.

## Zmiany

**`budget/app/src/budget/categorize/taxonomy.py`** (reuse `_clean_name`, `_slug`, `all_categories`, `fold`)
- `add_main(conn, name) -> int`: `parent_id NULL`, `flex_group NULL` (wymaga tego CHECK z
  `003_categories.sql`), `sort = max(sort mains) + 10` (na końcu), nazwa unikalna wśród głównych.
- `move(conn, category_id, new_parent_id)`: tylko podkategoria → istniejąca główna, inna niż
  obecna; `_check_unique` w grupie docelowej (kolizja nazw = `TaxonomyError`); `sort` na koniec
  grupy docelowej; `flex_group` bez zmian.
- `delete_main(conn, category_id)`: tylko pusta kategoria główna (bez podkategorii). Zostaje
  po przeniesieniach i da się nią posprzątać. Podkategorii nie usuwamy (to dalej M5).
- `rename` dla głównej: dodać sprawdzenie unikalności wśród głównych (dziś go brak).
- Docstring modułu: zaktualizować zakres („przenoszenie podkategorii — 0.6.0; usuwanie
  podkategorii, grupy Flex — M5”).

**`budget/app/src/budget/web/routes_rules.py`** (wzorzec jak `add_category`/`rename_category`:
`try` → `panel.redirect(..., str(exc), "error")`)
- `POST /categories/add-main` (name), `POST /categories/{id}/move` (parent_id),
  `POST /categories/{id}/delete` (tylko pusta główna).

**`budget/app/src/budget/web/templates/categories.html`**
- Przy każdej podkategorii: `<select name="parent_id">` z pozostałymi głównymi + „Przenieś”.
- Na końcu siatki: karta „Nowa kategoria główna” (input + „Dodaj”).
- Główna bez podkategorii: przycisk „Usuń” (inne go nie mają).
- Opis na górze: dopisać, że przeniesienie zabiera historię i reguły.

**Testy** `budget/app/tests/test_taxonomy.py` + `test_web_categorize.py` (lub tam, gdzie testy
tras kategorii): add_main (pozycja, unikalność), move (parent zmieniony, transakcja dalej
z tą samą podkategorią, `spending` liczy ją pod nową główną, kolizja nazwy, przeniesienie
głównej odrzucone), delete_main (pusta OK, niepusta odrzucona), trasy (redirect + komunikat).

**Wydanie:** `budget/config.yaml` 0.5.0 → 0.6.0, `budget/CHANGELOG.md`, DOCS/README (sekcja
Kategorie), wiersz w `docs/ROADMAP.md` (poza planem, przed M5) i ten plan jako
`docs/PLAN_categories_move.md` (pierwszy krok wykonania). Release skillem `release`:
opublikowany GH release, update add-onu `a9413a25_budget` przez Supervisor.

## Ryzyka
- Hook pre-commit skanuje dane prywatne: w testach tylko syntetyczne nazwy kategorii.
- Usunięcie głównej z seeda: dozwolone tylko pustej, nie wpływa na migracje (seed tylko INSERT).
- Pomiar trafności AI dla kategorii głównej porówna z nowym rodzicem, więc wynik „główna”
  może się przesunąć. Spodziewane, bez zmian w kodzie.

## Weryfikacja
1. `pytest` (cały zestaw) + `ruff`/`mypy` jak w repo.
2. Panel dev na kopii księgi (`create_app(dev=True)`, bez harmonogramu): Playwright —
   dodaj główną, przenieś 2 podkategorie, sprawdź „Wydatki” (kwoty pod nową główną, także
   poprzedni miesiąc), usuń pustą główną; screenshot + konsola bez błędów.
3. Po wydaniu: Ingress na żywo — wersja 0.6.0 w badge, zakładka Kategorie działa
   (bez zmian w danych usera; przegrupowanie robi user sam).
4. Checkpoint: wynik do przeglądu, user przegrupowuje swoje kategorie.

## Wynik (2026-10-02)
- 355 testów, ruff, mypy OK. Panel dev na kopii księgi (390 px): nowa główna na końcu, dwie
  podkategorie przeniesione z transakcjami, „Wydatki” za poprzedni miesiąc liczą je pod nową
  główną (kwota i zmiana m/m), pusta główna usunięta; brak poziomego przewijania i błędów konsoli.
- Zmiana w trakcie: lista „przenieś do…” zaczyna od pustej, wymaganej pozycji — wcześniej
  domyślnie wskazywała pierwszą kategorię i przypadkowe „Przenieś” przenosiło podkategorię.
- Uwaga dla testów curl: formularz bez `--data-urlencode` daje mojibake w nazwie (przeglądarka
  koduje poprawnie).
