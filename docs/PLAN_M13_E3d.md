# M13 E3d — cele dotyku na pozostałych ekranach

Status: **plan zaakceptowany 2026-10-05**, kroki 0–4 po kolei, checkpoint po każdym kroku, wydanie po osobnym „go”.
Zależy od 0.20.1 (E3b + E3c). Zasady jak w `PLAN_M13_E3.md`: bez nowych funkcji, bez zmian logiki, encji i schematu.

## Ograniczenia
1. Korzysta jedna osoba, głównie telefon w HA Companion; czasem desktop.
2. Automatycznie dzieje się tylko render istniejących danych; wydanie dopiero po „go”.
3. Wygląd = Monarch (`DESIGN.md`); statyki `?v=` rosną z wersją.
4. **Sukces:** na **wszystkich** ekranach panelu przy 360, 390 i 1280 px zero linków/przycisków/pól < 44 px (pomiar bez
   wykluczeń), bez przepełnienia poziomego, konsola czysta; testy, `ruff`, `mypy` zielone; zrzuty przed/po ekranów niezmienianych
   bez regresji.

## Decyzja (wywiad 2026-10-05)
Wiersz podkategorii na `/categories` = **rozwijany wiersz** (`<details>`, bez JS): `summary` pokazuje nazwę, grupę budżetu i liczbę
transakcji; po rozwinięciu trzy istniejące formularze (nazwa, grupa, przenieś) w 44 px. Odrzucone: podniesienie formularzy w
miejscu (lista ~2× dłuższa) i zostawienie gęstych.

## Stan wyjściowy (pomiar kroku 0 E3c, 2026-10-05, 360 px, kopia księgi)
| Ekran | Elementy < 44 px |
|---|---|
| `/categories` | `input` 70 × 43 px, `button` 55 + 15 × 43 px, **`form.move` w listach: `select` 82 × 26 px i `button` 82 × 26 px** |
| `/accounts` | `input` 3 × 40, `button` 3 × 41 |
| `/bank` | `input` 3 × 40, `button` 3 × 41 |
| `/import` | `input` 1 × 41, `button` 1 × 41 |
| `/status` | link 1 × 19, `button` 3 × 41 |
| `/recurring` | `button.secondary` 1 × 41 |
| `/dictionary`, `/inbox` | bez uwag |
Poza tym: strony ze szczegółami serii (`series.html`, `series_new.html`) i nawigacja główna / dzwonek (`base.html`) — nie zmierzone.

## Kroki

**Krok 0 — pomiar pełny (odczyt, kopia w scratchpadzie).** `devserve.py` na kopii `~/budget_dev/prod/ledger.db`, zasiew brakujących
stanów (Bank, Import, seria cykliczna `series.html`/`series_new.html`, nawigacja i dzwonek `base.html`), pomiar Playwright bez
wykluczeń na wszystkich ekranach, zrzuty „przed” 360 i 1280 px. Wynik wpisuję tutaj. Cofnięcie: niepotrzebne (kopia usuwana).

**Krok 1 — reguła globalna** (`static/app.css`, blok „M13 E3d”):
```css
input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"]):not(.visually-hidden),
select, textarea, button { min-height: var(--tap); }
```
Selektory z E3/E3b/E3c, które ta reguła zastępuje, usuwam tylko gdy zrzuty zostają identyczne co do piksela. Regresja: zrzuty
przed/po **każdego** ekranu. Cofnięcie: `git revert`.

**Krok 2 — Kategorie** (`templates/categories.html`, `app.css`, testy `/categories`): `<li>` → `<details class="leaf">`,
`summary` = nazwa + etykieta grupy + liczba tr.; w środku trzy istniejące formularze bez zmian `action`/`name` (trasy POST
nietknięte). Akcje „Zmień”/„Ustaw”/„Przenieś” sprawdzone POST-em na kopii; zrzuty `/budget` (wspólna `form.move` w `.pool`).
Cofnięcie: `git revert`.

**Krok 3 — resztki z pomiaru:** link na Statusie (19 px), Cykliczne/serie, nawigacja, dzwonek — dokładnie to, co pokaże krok 0.

**Krok 4 — wydanie 0.20.2** (po osobnym „go”): skill `simplify`, skill `release` (bump `config.yaml`/`__init__.py`/
`pyproject.toml`, CHANGELOG, push, CI, `gh release create v0.20.2`), backup add-onu, update w HA (`update.budzet_domowy_update`),
weryfikacja przez użytkownika na telefonie. Cofnięcie: przywrócenie backupu add-onu.

## Weryfikacja
`BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, `ruff check`, `ruff format --check`, `mypy`; pomiar Playwright jak
w E3c (wysokość < 44 px = 0, przepełnienie, konsola); zrzuty przed/po 360 i 1280 px; cache: `fetch(app.css, {cache: "reload"})`;
sprzątanie: kill po PID, usunięcie kopii księgi.

## Ryzyka
- Reguła globalna zmienia każdy formularz naraz → regresja wszystkich ekranów, nie tylko zmienianych.
- `form.move` wspólna z `/budget` (`.pool`) → po kroku 2 zrzuty Budżetu.
- „Koszty stałe” nie renderują się na kopii (jak w E3c) → potwierdzenie na prawdziwych danych w HA.
