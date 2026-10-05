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

## Wynik kroku 0 (pomiar pełny, 2026-10-05, kopia księgi + zasiew: „Wykryj teraz” i 3 serie potwierdzone, bez wykluczeń)

Wszystkie `details` otwarte, `input[checkbox]` mierzony po swoim `label`. 360 i 1280 px dają ten sam obraz; przepełnienia
poziomego i błędów konsoli brak na żadnym ekranie. Bez uwag: `/transactions`, `/review`, `/rules/new`, `/dictionary`,
`/recurring/new`, `/inbox` oraz nawigacja i dzwonek (`base.html`) na każdym ekranie.

| Ekran | Elementy < 44 px (liczba × najmniejsza wysokość) | Krok |
|---|---|---|
| `/categories` | `form.rename` `input` 70 × 43, `button` 70 × 43; `form.move` (grupa i przenieś) `select` 82 × 26, `button` 82 × 26 | 1, 2 |
| `/accounts` | `input[text]` 3 × 40, `button` 3 × 41, `label.check` 3 × 20 | 1, 3 |
| `/bank` | `input[file]` 2 × 41, `input[text]` 1 × 40, `button` 3 × 41 | 1 |
| `/import` | `input[file]` 1 × 41, `button` 1 × 41 | 1 |
| `/status` | link w `div.msg.warn` 1 × 19, `button` 1 × 41 | 1, 3 |
| `/recurring` | `a.cat-name` w `.series-head` do 6 × 23, link „Edytuj i potwierdź” 16 × 23, `button` 32 × 41, „Wykryj teraz” 1 × 41 | 1, 3 |
| `/recurring/{id}` | link powrotu 1 × 16, `button` 1 × 41 | 1, 3 |
| `/` (Podsumowanie) | `li > a.row` w nadchodzących seriach 1–3 × 41 (stan z seriami; E3b mierzył bez serii) | 3 |
| `/budget` | link „szczegóły” w `p.recurring-line` 1 × 16 (stan z seriami) | 3 |
| `/rules` | link „Do przejrzenia” w pustym stanie 1 × 19 (kopia bez reguł) | 3 |

Wniosek: reguła globalna (krok 1) zamyka wszystkie pola i przyciski 40–43 px; krok 2 zostaje bez zmian; krok 3 obejmuje linki
`a.row`, `a.cat-name`, „Edytuj i potwierdź”, „szczegóły”, linki w tekście (Status, Reguły, powrót z serii) i `label.check` na Kontach.

## Wynik kroku 1 (reguła globalna, 2026-10-05)

Blok „M13 E3d” na końcu `app.css`. Zrzuty 360/1280 px wszystkich 17 ekranów (z `reducedMotion: reduce` — bez tego
animacja koła na `/` dawała różne zrzuty przy tym samym kodzie): zmieniły się tylko Konta, Bank, Import, Status, Cykliczne,
seria i Kategorie (pola/przyciski 40–43 → 44 px, przegląd wzrokowy bez uwag); pozostałe 20 zrzutów identycznych co do bajtu.
Usunięte dublujące selektory z E3 (`.rv-actions`/`.rv-rule`/`.rule-fields`/`.rv-sub button.link`, `.cat-form`/`.search-form`,
`table.rules .actions button`/`.rule-form`) i E3c (`.tap-form`, `.pool form.move select/button`) oraz osierocona klasa `tap-form`
w `budget.html` — wszystkie 34 zrzuty i pomiar identyczne przed i po usunięciu. Zostało (do kroków 2–3): Kategorie
`form.move` 44 px w wierszu (krok 2), linki i `label.check` z tabeli kroku 0 (krok 3). 510 testów, ruff, mypy czyste.

## Wynik kroku 2 (Kategorie, 2026-10-05)

`categories.html`: wiersz podkategorii = `<details class="leaf">`, `summary` = nazwa + „grupa · N tr.”, w środku trzy formularze
bez zmian `action`/pól. `app.css`: szewron ze wspólnej reguły Wydatków/kolejki (`.leaf summary .cat-name::before`), blok `.leaf`
w „M13 E3d”; usunięta osierocona `form.move.group { margin-left: 0 }` (zrzut wszystkich rozwiniętych wierszy identyczny przed i po).
Bez kotwicy po zapisie (decyzja użytkownika): po POST wiersz wraca zwinięty, komunikat jak dotąd. Na kopii: POST zmiany nazwy,
grupy i przeniesienia → 303, baza zgodna. Pomiar: `/categories` 0 elementów < 44 px (zwinięte i rozwinięte), zmieniły się tylko
zrzuty Kategorii; przegląd wzrokowy 360/1280 px zwinięte i rozwinięte bez uwag. Nowy test `test_categories_leaf_row_collapses_edit_forms`;
511 testów, ruff, mypy czyste.

## Wynik kroku 3 (resztki z pomiaru, 2026-10-05)

`app.css` (blok „M13 E3d”): `a.row` 44 px (wiersze nadchodzących serii), `inline-flex` + `min-height` dla nazw i akcji serii,
linku powrotu (`p.back a`, nowa klasa `back` w `series.html`/`series_new.html`) i linków w tekście (`.recurring-line a`,
`p.muted a`, `.msg a` — jak w E3b/E3c), `label.check` 44 px z polem 20 px (Konta). Kopia z kroku 2 (restart na świeżą kopię się
nie udał — `kill` trafił w podpowłokę, nie w serwer; przed i po mierzone na tych samych danych z seriami): **0 elementów
< 44 px na wszystkich 17 ekranach przy 360/390/1280 px**, bez przepełnienia, konsola czysta; zmieniły się tylko zrzuty Podsumowania,
Budżetu, Reguł, Statusu, Kont, Cyklicznych i serii (przegląd 360 px bez uwag; linki w zdaniu podnoszą swoją linię — widać w pustym
stanie Reguł). Zgłoszone poza zakresem: pusty stan Reguł radzi „Zawsze dla …” — przycisk usunięty w M4h.

## Weryfikacja
`BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, `ruff check`, `ruff format --check`, `mypy`; pomiar Playwright jak
w E3c (wysokość < 44 px = 0, przepełnienie, konsola); zrzuty przed/po 360 i 1280 px; cache: `fetch(app.css, {cache: "reload"})`;
sprzątanie: kill po PID, usunięcie kopii księgi.

## Ryzyka
- Reguła globalna zmienia każdy formularz naraz → regresja wszystkich ekranów, nie tylko zmienianych.
- `form.move` wspólna z `/budget` (`.pool`) → po kroku 2 zrzuty Budżetu.
- „Koszty stałe” nie renderują się na kopii (jak w E3c) → potwierdzenie na prawdziwych danych w HA.
