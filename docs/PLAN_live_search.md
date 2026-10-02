# Budżet Domowy 0.6.1 — wyszukiwanie na żywo w całym panelu

## Context

Reguł jest już kilkadziesiąt, a zakładka „Reguły” nie ma wyszukiwania. User chce nowoczesnego
wyszukiwania (lista zawęża się na żywo w trakcie pisania) i to samo zachowanie we **wszystkich**
polach wyszukiwania add-onu. Inwentarz (grep po szablonach): są dziś dwa pola — **Słownik**
(`/dictionary?q=`, przycisk „Szukaj”) i **Transakcje** (`/transactions?q=` w formularzu filtrów,
przycisk „Filtruj”); trzecie, **Reguły**, dochodzi w tym etapie. Kolejka, Wydatki, Kategorie nie
mają wyszukiwania. Etap poza roadmapą (jak 0.6.0).

## Jedno zachowanie wszędzie

- **htmx, filtrowanie po stronie serwera** — panel jest na htmx (`hx-boost` na `<body>`,
  `input changed delay:…` w `rule_form.html`), bez własnego JS. Pole szukania:
  `hx-get` na tę samą stronę, `hx-trigger="input changed delay:200ms, search"`,
  `hx-select`/`hx-target` = blok wyników strony, `hx-swap="outerHTML"`, `hx-replace-url="true"`
  (filtr w adresie → odświeżenie i powrót z edycji go zachowują). Bez JS formularz GET działa
  jak dziś (Enter).
- **Dopasowanie jak w silniku reguł:** `fold` z `budget/normalize.py` (wielkie litery, bez
  ogonków, ł→L) po obu stronach; **wszystkie słowa zapytania muszą wystąpić, w dowolnej
  kolejności** („czyn mies” → „Czynsz za miesiąc”). Dziś Słownik używa `merchants.words`,
  a Transakcje SQL `LIKE` (w SQLite bez ogonków-niewrażliwości: „żółw” ≠ „ŻÓŁW”) — po zmianie
  wszystkie trzy zachowują się identycznie.
- Licznik wyników („12 z 48”) i pusty stan „Nic nie pasuje do „…”” + „wyczyść”, spójne w
  trzech miejscach.

## Per ekran

**Reguły** (`routes_rules.py`, `rules.html`)
- Pole nad tabelą; przeszukiwany tekst: opis warunków z `describe()`, podkategoria + kategoria
  główna (`taxonomy`), `rename`, „wyłączona”.
- Przy aktywnym filtrze **ukryte „wyżej/niżej”** (sąsiad w liście przefiltrowanej ≠ sąsiad w
  kolejności) + notka „Kolejność zmieniasz bez filtra”. Wyłącz/Usuń zostają i wracają na
  `/rules?q=…` (ukryte `q` w formularzach, `panel.redirect` z zapytaniem).

**Słownik** (`dictionary.html`, route w `routes_rules.py`)
- Pole dostaje atrybuty htmx; przycisk „Szukaj” zostaje tylko jako fallback (ukryty, gdy htmx
  działa — CSS). Dopasowanie przez wspólną funkcję zamiast `merchants.words`.

**Transakcje** (`routes_transactions.py`, `transactions.html`)
- Na żywo cały formularz filtrów: tekst z opóźnieniem 200 ms, listy/daty od razu (`change`).
  Każda zmiana wraca na stronę 1. „Filtruj” zostaje jako fallback.
- SQL: rejestracja funkcji `fold` na połączeniu w `storage/db.py::connect`
  (`conn.create_function("fold", 1, fold, deterministic=True)`), warunek per słowo:
  `fold(t.description || ' ' || coalesce(t.counterparty_name,'') || ' ' || coalesce(t.merchant,'')) LIKE ?`
  z wartością `%SŁOWO%` (po `fold`, z escapowaniem `%`/`_` jak dziś). ~3 tys. wierszy → pełny
  skan w milisekundach.
- Wyniki + licznik (`total` w nagłówku) + stronicowanie w jednym bloku `#tx-results`, żeby
  podmiana objęła wszystko.

## Wspólny kod (bez duplikacji)

- `budget/normalize.py`: `search_words(q) -> list[str]` (fold + split) i
  `matches_all(haystack_folded, words) -> bool` — używane przez Reguły i Słownik; Transakcje
  używają `search_words` do budowy warunków SQL.
- Makro `search_field(...)` w `templates/_macros.html` (label, input, atrybuty htmx, fallback
  button) — jedno źródło wyglądu i zachowania.
- CSS w `static/app.css`: pole pełnej szerokości na telefonie, licznik; tylko znaki Latin-1/CSS
  (czcionka Chromium w kontenerze nie ma części symboli).

## Pliki (repo `miczu71/ha-budget-app`, klon `/config/addons/ha-budget-app`, gałąź `main`)

`budget/app/src/budget/{normalize.py, storage/db.py, web/routes_rules.py,
web/routes_transactions.py, web/templates/{_macros,rules,dictionary,transactions}.html,
web/static/app.css}`; testy `tests/test_normalize.py`, `tests/test_web_categorize.py`,
`tests/test_web.py`; wersja 0.6.1 w `budget/config.yaml`, `budget/app/pyproject.toml`,
`budget/app/src/budget/__init__.py` (`?v=` CSS idzie za wersją → bez problemu z cache WebView);
`CHANGELOG.md`, `docs/ROADMAP.md` (sekcja „poza planem”), `docs/PLAN_live_search.md`.

## Kroki

1. Skopiować plan do `docs/PLAN_live_search.md` + wpis w ROADMAP.
2. Testy najpierw: `search_words`/`matches_all` (ogonki, ł, wielkość liter, wiele słów);
   Reguły (wartość warunku, kategoria główna, pusty wynik, brak „wyżej/niżej” przy `q`, toggle
   wraca na `?q=`); Słownik (bez ogonków); Transakcje („zolw” znajduje „ŻÓŁW”, dwa słowa AND,
   `%`/`_` dosłownie, fold w SQL); odpowiedzi htmx zawierają bloki wyników.
3. Implementacja → `pytest` całości + ruff/mypy jak w repo.
4. Panel dev na kopii księgi (`create_app(dev=True)`, bez harmonogramu) + Playwright na trzech
   ekranach, szerokość 390 px i desktop; zrzuty + konsola.
5. Commit (hook pre-commit skanuje dane prywatne — w testach tylko syntetyczne nazwy) → push →
   wydanie 0.6.1 wg skill `release` (opublikowane, nie draft) → aktualizacja przez Supervisor.
6. Na żywo przez Ingress: v0.6.1 w nagłówku; Reguły — fragment wartości warunku → jedna reguła; Słownik „zabka”;
   Transakcje — dwa słowa w odwrotnej kolejności + zmiana kategorii z listy; wyłącz/włącz reguły z filtrem zachowuje
   `?q=`; 0 błędów konsoli.
7. Checkpoint z userem.

## Ryzyka

- Każde naciśnięcie = żądanie przez Ingress; `delay:200ms` + `changed` tnie zbędne. Przy tej
  skali (≈50 reguł, ≈3 tys. transakcji) odpowiedź to milisekundy.
- `hx-boost` + `hx-replace-url`: sprawdzić „wstecz” w przeglądarce i że kategoria zmieniana
  w wierszu Transakcji (htmx w `_txn_category.html`) działa po podmianie listy.
- Zero zmian w schemacie bazy, silniku reguł i synchronizacji z bankiem (funkcja `fold`
  rejestrowana w połączeniu, nie zapisywana w bazie).
