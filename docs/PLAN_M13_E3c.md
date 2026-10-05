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

## Wynik kroku 0 (pomiar pełny, 2026-10-05, 360 px, kopia księgi z zasianą pulą 6000, bez wykluczeń, wszystkie `details` otwarte)

| Ekran | Elementy < 44 px (liczba × najmniejsza wysokość) |
|---|---|
| `/spending` (bez puli i z pulą) | `a` w `.cats` 17 × 23 px, `a.small` w `.cats` 9 × 20 px, link „bez kategorii” 1 × 19 px |
| `/budget` bez puli | 14 linków × 16 px, pole kwoty i przycisk 43 px |
| `/budget` z pulą | 20 linków × 16 px, pole kwoty 43 px, `button.secondary` („Zmień”) 43 px, `summary` 20 px |

Nie wystąpiły na `/budget`: `form.move`, „Dodaj do stałych”, „Wróć do automatycznej” (kopia nie ma kosztów stałych ani puli ręcznej
z wyborem) — te formularze mierzę w kroku 2 po dosianiu, albo biorę z kodu (patrz niżej).
Przy okazji (tylko raport, poza zakresem E3c; przepełnienia poziomego nigdzie nie ma, konsola czysta):

| Ekran | Elementy < 44 px |
|---|---|
| `/categories` | `input` 29 + 41 × 43 px, `button` 14 + 41 + 15 × 43 px, **`form.move` w liście: `select` 82 × 26 px i `button` 82 × 26 px** |
| `/accounts` | `input` 3 × 40, `button` 3 × 41 |
| `/bank` | `input` 3 × 40, `button` 3 × 41 |
| `/import` | `input` 1 × 41, `button` 1 × 41 |
| `/status` | link 1 × 19, `button` 2 × 41 + 1 × 41 |
| `/recurring` | `button.secondary` 1 × 41 |
| `/dictionary`, `/inbox` | bez uwag |

Wniosek: większość reszty to globalne pola i przyciski (`padding: 9px 12px` daje 40–43 px), a nie osobne klasy ekranów. Jedna
reguła `input, select, button { min-height: var(--tap) }` załatwiłaby je naraz, ale zagęszczone formularze w listach
(`form.move`, 82 szt. na `/categories`) wymagają osobnej decyzji projektowej — nie wchodzi do E3c.

## Wynik kroków 1–2 (Wydatki, Budżet; 2026-10-05, lokalnie, bez commita)

Zmiany: `static/app.css` (blok „M13 E3c”), `budget.html` (klasa `tap-form` na dwóch `form.rename`, `tx-link` na linku „Wydatkach”).
Pomiar bez wykluczeń, 360/390/1280 px, kopia księgi z pulą 6000: `/budget`, `/spending`, `/` bez elementów < 44 px, bez
przepełnienia, konsola czysta; `/categories` bez zmian (to samo co przed: 43 px pola i `form.move` 26 px — zgodnie z zakresem).
Sekcji „Koszty stałe” (`.pool form.move`, `form.add-fixed`) **nie dało się wyrenderować na kopii** (brak danych o wpływach z
poprzedniego miesiąca w grupach, więc `f.auto` jest puste); reguły sprawdzone na wiernie wstrzykniętym markupie z szablonu:
summary/link/select/button 44 px (summary 43 w wersji uproszczonej), bez przepełnienia. Do potwierdzenia na prawdziwych danych w HA.
510 testów, ruff, mypy czyste.
