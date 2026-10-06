# M16 — Układ ekranu głównego: kolejność i ukrywanie kafelków (ha-budget-app)

## Kontekst
Ekran „Podsumowanie” (`web/templates/home.html`, v0.27.0) ma stałą kolejność 8 kafelków w `.home-grid`.
Cel (wywiad 2026-10-06): móc **przestawiać i ukrywać** kafelki. Decyzje:
- interakcja: **tryb edycji ze strzałkami ↑/↓ + oko (ukryj/pokaż)**, bez biblioteki drag&drop;
- zakres: **tylko 8 kafelków siatki**; nawigacja miesiąca, linia „Dane z…” i hero Flex zostają na sztywno;
- układ **wspólny** (jedna baza SQLite add-onu → ten sam układ na OP12 i Pixelu; tego nie pytałem wprost — do odrzucenia).

Ograniczenia: zmiana działa natychmiast po kliknięciu (htmx), nic automatycznie poza zapisem układu; sukces =
na telefonie w Companion ustawiam kolejność/ukrycie i po odświeżeniu/innym urządzeniu jest tak samo; kafelki
warunkowe (Do wypłaty, Karta, Co jeszcze zejdzie — tylko bieżący miesiąc) dalej pojawiają się tylko, gdy mają dane.

## Repo / gałąź
`/config/addons/ha-budget-app` (`gh` push), gałąź `main` (jak dotąd). Wersja 0.27.0 → **0.28.0** przez skill `release`.

## Kroki (jeden etap, E1)
0. **Docs przed kodem:** wiersz M16 w `docs/ROADMAP.md` + `docs/PLAN_M16.md` (kopia tego planu).
1. **`src/budget/home_layout.py`** (~35 linii), stan w istniejącej tabeli `kv` (`db.kv_get/kv_set`, `storage/db.py:106`) — bez migracji:
   - `TILES` = domyślna kolejność kluczy: `forecast, spending, inbox, balance, card, upcoming, recent, months` + polskie nazwy.
   - `KEY = "home_layout"`, wartość `{"order": [...], "hidden": [...]}`.
   - `load(conn) -> list[Tile(key, name, hidden)]` — normalizacja: nieznane klucze odrzucone, nowe kafelki z przyszłych wersji dopisane na końcu jako widoczne.
   - `move(conn, key, delta)` (±1, na brzegach no-op), `toggle(conn, key)`, `reset(conn)` (`kv_set(..., None)`).
2. **`home.html`:** sekcje siatki bez zmian treści, owinięte w pętlę
   `{% for t in layout if not t.hidden %}{% if t.key == "forecast" %}…{% elif … %}{% endfor %}` (jeden plik, bez nowych partiali).
   `_forecast.html` zostaje includem. Reguła CSS „ostatni nieparzysty kafelek na całą szerokość” działa dalej.
3. **Tryb edycji:** `GET /?edit=1` — zamiast siatki renderuje się zwarta lista `_home_layout.html` (nazwa kafelka +
   przyciski ↑, ↓, oko/przekreślone oko; ukryte wyszarzone), na dole „Przywróć domyślny” i „Gotowe” (link do `/`).
   Link „Edytuj układ” na dole ekranu głównego. Ikony inline SVG w stylu Lucide (jak `_bell.html`, ISC), bez emoji/Unicode.
   Lista zamiast pełnych kafelków, żeby przestawianie na telefonie nie wymagało przewijania długich kart.
4. **Trasy w `routes_home.py`:** `POST /layout/move` (key, delta), `POST /layout/toggle` (key), `POST /layout/reset`;
   htmx `hx-post` + `hx-target="#layout" hx-swap="outerHTML"` zwraca partial listy; bez JS — zwykły form + redirect
   do `/?edit=1` (wzór: `card_debt`, `routes_home.py:104`). Nieznany klucz → 400.
5. **CSS** w `static/app.css`: kilka reguł dla `.layout-list` (wiersz, przyciski 44px — dotyk). Cache-busting już jest (`?v={{ version }}` w `base.html`).
6. **Testy** (`tests/test_home_layout.py` + rozszerzenie `tests/test_web_home.py`): normalizacja/move/toggle/reset;
   ukryty kafelek nie renderuje się; kolejność w HTML zgodna z zapisaną; `?edit=1` pokazuje listę; POST-y działają przez htmx i bez.
   `uv run pytest`, `ruff`, `mypy` — jak w CI.
7. `simplify` → commit → skill `release` (0.28.0, published release) → aktualizacja add-onu w HA (Supervisor).

## Weryfikacja
- Lokalnie: pełny pytest zielony.
- Na żywo (Playwright `playwright-ha`, viewport telefonu 412px i desktop): przestaw 2 kafelki, ukryj 1, odśwież,
  screenshot + `browser_console_messages` bez błędów; „Przywróć domyślny” wraca do obecnego układu. Zrzuty do `/config/playwright/`.
- Potwierdzenie na telefonie przez Ciebie (Companion WebView).

## Ryzyka / cofnięcie
- Ryzyko niskie: tylko odczyt/zapis jednego klucza `kv`; brak migracji schematu. Cofnięcie: „Przywróć domyślny” albo
  powrót do 0.27.0 (klucz `home_layout` zostaje w `kv` niegroźnie ignorowany).
- Bez commitów 02:45–03:15.
