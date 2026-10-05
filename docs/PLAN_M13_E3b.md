# M13 E3b — cele dotyku na Podsumowaniu (0.20.1)

Do akceptacji. Bez kodu przed „go”. Drobny etap po E3 (`PLAN_M13_E3.md`): ten sam cel (≥ 44 px) dla ekranu Podsumowanie (`/`)
i wspólnej karty Zostało (`_flex_hero.html`, używanej też na Budżecie). Bez nowych funkcji, bez zmian logiki, encji i schematu.

## Ograniczenia
1. Korzysta jedna osoba, głównie telefon w HA Companion; czasem desktop.
2. Automatycznie dzieje się tylko render istniejących danych; wydanie dopiero po „go”.
3. Wygląd = Monarch (`DESIGN.md`); statyki `?v=` rosną z wersją.
4. **Sukces:** na `/` przy 360 i 1280 px zero linków/przycisków < 44 px wysokości, słupki wykresu ≥ 24 px szerokości
   (44 px się nie zmieści: 12 słupków w karcie), bez przepełnienia poziomego, konsola czysta, testy zielone.

## Stan wyjściowy (pomiar 2026-10-05, 360 px, kopia księgi)
`month-link` 90×23, link „Status” 38×16, `a.button` „Ustaw budżet” 39 px, `card-link` (3 szt.) 16 px, pozycje „Do decyzji”
(`.inbox-item a`) 23 px, 12 słupków wykresu 22×160 px (przy 1280: 31 px). `_flex_hero.html`: linki „W tym N wydatków bez kategorii” i
„Szczegóły budżetu” (nie zmierzone, bo kopia nie ma ustawionej puli).

## Decyzja usera (2026-10-05)
Słupki: **etykiety osi Y wewnątrz wykresu**. Powód: samo zmniejszenie odstępów nie wystarcza — w `web/charts.py` `LEFT = 30` z 320
jednostek zajmuje kolumna etykiet; przy skali ~0,92 na 360 px słupek ma 22 px. Przesunięcie etykiet nad linie siatki
(po lewej, w obszarze wykresu) pozwala zejść z `LEFT` do ~4 i dać słupkowi ~26 jednostek, czyli ≈ 24 px.

## Kroki (jedno wydanie 0.20.1, checkpoint po pomiarze)

**Krok 1 — CSS i szablony** (`static/app.css`, `home.html`, `_flex_hero.html`):
- blok „M13 E3b”: `.month-link`, `.fresh a`, `.card-link a`, `.inbox-item a`, `.flex-hero a`, `.warn-note a`, `a.button` w karcie Zostało
  → `min-height: var(--tap)`, `inline-flex`, wyśrodkowanie; `.inbox-item a` jako wiersz 44 px;
- klasy w szablonach tylko tam, gdzie selektor nie wystarczy (np. `tx-link` na linku „Status”, „Szczegóły budżetu”).

**Krok 2 — wykres** (`web/charts.py`, `_charts.html`, `.bars .axis`): `LEFT` 30 → ~4; etykiety osi Y jako `text-anchor: start`
nad linią siatki (y − 3), tło/`paint-order` obrysem w kolorze karty dla czytelności nad słupkami; `hit` rect ≥ 24 px po skali;
aktualizacja testów geometrii (`tests/test_charts*`), pomiar szerokości `a.col` przy 360 px.

**Krok 3 — weryfikacja i wydanie** (po „go”): kopia księgi + `devserve.py` (scratchpad), pomiar 360/390/1280 na `/` (bieżący i
miniony miesiąc, z pulą i bez), zrzuty przed/po, regresja `/budget` (wspólna karta), `pytest`, `ruff`, `mypy`, `simplify`; bump
0.20.0 → 0.20.1 (`config.yaml`, `pyproject.toml`, `__init__.py`), CHANGELOG, push, CI, `gh release create v0.20.1` (nie draft),
backup add-onu, update w HA (limit czasu klienta MCP → polling), weryfikacja encji `update.*`.

## Weryfikacja
`BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, `ruff check`, `ruff format --check`, `mypy`; pomiar Playwright jak w E3
(wysokość < 44 px = 0, szerokość słupków ≥ 24 px, brak przepełnienia, konsola); cache: `fetch(app.css, {cache: "reload"})`.

## Ryzyka
- Etykiety osi Y nad słupkami mogą nachodzić na słupki w pierwszych miesiącach → obrys w kolorze karty, ocena na zrzutach.
- Karta Zostało jest wspólna z Budżetem: zmiana wysokości linków dotknie obu ekranów (sprawdzam oba).
- Przy 1280 słupek ma 31 px (bez zmian w zasadzie), więc zysk jest tylko na telefonie.
- **Cofnięcie:** `git revert` commitów etapu, wydanie poprawkowe 0.20.2 albo backup add-onu. Brak zmian schematu i encji.

## Poza zakresem
Dzwonek w nagłówku i nawigacja główna (`base.html`), ekrany Wydatki/Cykliczne/Kategorie/Konta/Import/Bank, nowe funkcje.

## Wynik kroków 1–2 (2026-10-05, lokalnie, bez commita)

Zmiany: `static/app.css` (blok „M13 E3b”), `home.html` (`class="button tap"` na „Ustaw budżet”), `_charts.html`, `charts.py` (`LEFT` 30 → 4).
Pomiar 360, 390 i 1280 px na kopii księgi, **bez wykluczania `.month-nav`**: `/`, `/?month=2026-09` i `/review` bez elementów
< 44 px (strzałki miesięcy, „Status”, linki pod kartami, „Do decyzji”), bez przepełnienia poziomego, konsola bez błędów.
Słupki wykresu: 22 → 24,5 px przy 360 px (33,6 px przy 1280). 510 testów, ruff, mypy czyste.

Odstępstwa i ustalenia:
- Pierwsza wersja (etykiety osi po lewej, nad linią) nie działała: nachodziły na pierwsze słupki, górna była ucięta, a lewą
  część zakrywało wypełnienie zaznaczonej kolumny. Wersja końcowa: etykiety 25k/50k po prawej, pod linią siatki, bez „0”,
  rysowane za kolumnami z `pointer-events: none`. Ryzyko: wysoki słupek w ostatniej kolumnie przykryje etykietę (obrys w kolorze karty).
- Poza zakresem, do osobnej decyzji: `/spending` (ok. 25 linków 19–23 px) i `/budget` (wiersze podkategorii 23 px, linki 16 px,
  pola 43 px), wykryte przy pomiarze; w E3 `.month-nav` był wykluczony z pomiaru (strzałki Do przejrzenia 23 px) — poprawione tu.

## Wydanie

Wydane jako 0.20.1 (jedno wydanie E3b + E3c, 2026-10-05).
