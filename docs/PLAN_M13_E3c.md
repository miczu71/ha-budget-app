# M13 E3c — cele dotyku w Wydatkach i Budżecie (0.20.2)

Do akceptacji. Bez kodu przed „go”. Drobny etap po E3b (`PLAN_M13_E3b.md`): ten sam cel (≥ 44 px) dla ekranów
`/spending` (Wydatki) i `/budget` (Budżet). Bez nowych funkcji, bez zmian logiki, encji i schematu bazy.
Wykryte przy pomiarze E3b; zależy od E3b (wspólne `.month-link`, `--tap`) — wydanie najwcześniej po 0.20.1.

## Ograniczenia
1. Korzysta jedna osoba, głównie telefon w HA Companion; czasem desktop.
2. Automatycznie dzieje się tylko render istniejących danych; wydanie dopiero po „go”.
3. Wygląd = Monarch (`DESIGN.md`); statyki `?v=` rosną z wersją.
4. **Sukces:** na `/spending` i `/budget` (w trzech stanach: bez puli, z ustawioną pulą, z otwartymi sekcjami) przy 360, 390
   i 1280 px zero linków/przycisków/pól < 44 px wysokości, bez przepełnienia poziomego, konsola czysta, testy zielone;
   pomiar **bez wykluczeń** (E3 pominął `.month-nav`, patrz `PLAN_M13_E3b.md`).

## Stan wyjściowy (pomiar 2026-10-05, 360 px, kopia księgi, budżet nieustawiony)
- `/spending`: ok. 25 linków 19–23 px (nazwy kategorii i podkategorii w `<summary>`/liście, „wszystkie transakcje: …” 20 px,
  link „bez kategorii” 19 px, linie bilansu `dt a`).
- `/budget`: wiersze podkategorii (`a` w liście, 23 px) × 13, link „Wydatkach” 16 px, pole kwoty i przycisk „Ustaw od tego
  miesiąca” po 43 px.
- Nie zmierzone (kopia nie ma ustawionej puli ani kosztów stałych): karta Zostało na `/budget`, formularze „Przenieś”
  (`form.move` z `select` 3×6 px i `button` 3×8 px), „Dodaj do stałych”, „kwota ręczna”, „Wróć do automatycznej”, `summary` sekcji,
  „wydane w poprzednich miesiącach”.

## Kroki (jedno wydanie 0.20.2, checkpoint po każdym kroku)

**Krok 0 — pomiar pełny (odczyt, kopia w scratchpadzie).** `devserve.py` + zasiew stanu `/budget`: ustawienie puli przez
`POST /budget/amount` na kopii (kopia jest jednorazowa), rozwinięcie wszystkich `details`. Pomiar bez wykluczeń na `/spending`,
`/budget` (3 stany) oraz — tylko raport — na `/categories`, `/dictionary`, `/accounts`, `/import`, `/bank`, `/status`,
`/recurring`, `/inbox`, żeby lista pozostałych ekranów była policzona, nie zgadywana. Wynik wpisuję tutaj.

**Krok 1 — Wydatki** (`spending.html`, `app.css`): wiersze `summary` kategorii jako cele 44 px (cały wiersz już jest
rozwijany; osobny link do transakcji w środku dostaje `min-height`), linki `.small`, `dt a` w bilansie i „bez kategorii”:
`min-height: var(--tap)`, `inline-flex`, wyśrodkowanie. Klasy `tx-link`/`tap` z E3 gdzie selektor nie wystarczy.

**Krok 2 — Budżet** (`budget.html`, `app.css`): linki podkategorii i serii (`.leaf-list a`, `a` w koszcie stałym),
„Wydatkach”, `summary` sekcji, `form.move` (`select` i `button` ≥ 44 px, układ zawija się, odstęp 8 px), `form.add-fixed`,
„kwota ręczna” i „Wróć do automatycznej”, pole kwoty i przyciski (43 → 44 px), link w historii. Karta Zostało
(`_flex_hero.html`) już poprawiona w E3b — sprawdzam tylko regresję.

**Krok 3 — wydanie** (po „go”): `simplify`, bump 0.20.1 → 0.20.2 (`config.yaml`, `pyproject.toml`, `__init__.py`),
CHANGELOG, push, CI, `gh release create v0.20.2` (nie draft), backup add-onu, update w HA (limit czasu klienta MCP →
polling), weryfikacja encji `update.*`.

## Weryfikacja
`BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, `ruff check`, `ruff format --check`, `mypy`; pomiar Playwright jak
w E3b (wysokość < 44 px = 0, przepełnienie, konsola) w trzech stanach `/budget`; zrzuty przed/po 360 i 1280 px; cache:
`fetch(app.css, {cache: "reload"})`; sprzątanie: kill po PID, usunięcie kopii księgi.

## Ryzyka
- `form.move` jest wspólna dla kilku miejsc (Kategorie, Budżet): zmiana selektora dotknie też `/categories` → ograniczam do
  `.pool form.move` albo dodaję klasę, sprawdzam zrzuty obu ekranów.
- Wiersze `summary` kategorii w Wydatkach są gęste (lista ok. 25 pozycji): wyższe wiersze wydłużą stronę; kompromis oceniasz na zrzutach.
- Zasiew puli w kopii zmienia tylko kopię (jednorazową); produkcyjna księga nietknięta.
- **Cofnięcie:** `git revert` commitów etapu, wydanie poprawkowe 0.20.3 albo backup add-onu. Brak zmian schematu i encji.

## Poza zakresem
Pozostałe ekrany (lista z kroku 0), dzwonek/nawigacja główna (`base.html`), nowe funkcje, M5c/M6/M8.
