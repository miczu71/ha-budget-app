# M13 E3e — domknięcie M13

Status: **plan zaakceptowany 2026-10-05**, kroki 0–5 po kolei, checkpoint po każdym kroku, wydanie (0.20.3) po osobnym „go”.
Zależy od 0.20.2 (E3d, checkpoint zamknięty przez użytkownika 2026-10-05). Zasady jak w `PLAN_M13_E3.md`: bez nowych funkcji,
bez zmian logiki, encji i schematu.

## Ograniczenia
1. Korzysta jedna osoba, głównie telefon w HA Companion (390 px); czasem desktop.
2. Automatycznie: commity lokalne, testy, panel dev na kopii księgi, odczyty na żywo przez Ingress (tylko GET). Push, release,
   backup i update add-onu dopiero po „go”.
3. Wygląd = Monarch (`DESIGN.md`); statyki `?v=` rosną z wersją.
4. **Sukces:** na żywo zero elementów < 44 px na wszystkich ekranach (390 i 1280 px); Koszty stałe zwinięte w wiersze; zrzuty
   przed/po refaktoru klasy linków identyczne co do bajtu; checkpoint użytkownika na telefonie.

## Zakres (wywiad 2026-10-05)
Wszystkie odłożone rzeczy z E3d: pusty stan Reguł (radzi nieistniejące „Zawsze dla …”), „Wpływy (…)” na Budżecie 43 px,
wspólna klasa dla linków samodzielnych zamiast list selektorów E3–E3d, kompaktowe `form.move` w Kosztach stałych.
**Decyzja:** „kompaktowe” = **rozwijany wiersz** jak w Kategoriach (E3d); link do transakcji podkategorii przechodzi z nazwy
do rozwiniętej części (summary bez kotwicy, jak w Kategoriach).

## Kroki
0. **Plan i pomiar bazowy.** Ten plik + wiersz w `ROADMAP.md`. Diagnoza 43 px na żywo (`getComputedStyle` summary „Wpływy”:
   padding, line-height, height, dopasowane reguły). Hipoteza: element to `.cats summary` w `ul.cats.pool` (`padding: 10px 0`,
   bez `min-height`), a reguła E3c `details.small summary` dotyczy innego elementu („wydane w poprzednich miesiącach”).
   Na kopii księgi: ustalić, czego brakuje, by wyrenderować sekcje „Wpływy” i „Koszty stałe” (w E3c/E3d się nie renderowały);
   jeśli się da — uzupełnić tylko w kopii.
1. **Pusty stan Reguł** (`templates/rules.html`): „zmień kategorię i zaznacz «utwórz regułę»” zamiast „Zawsze dla …”; test.
2. **„Wpływy (…)” ≥ 44 px** (`static/app.css`): punktowa reguła po potwierdzeniu przyczyny (wariant: `min-height: var(--tap)`
   dla `.cats summary`); zrzuty Wydatków i Budżetu przed/po.
3. **Rozwijany wiersz w Kosztach stałych** (`templates/budget.html`, `static/app.css`): `details.leaf` — summary = nazwa +
   mediana; rozwinięcie = kategoria główna, link „Transakcje”, `form.move` na pełną szerokość jak `.leaf form.move`. Testy
   szablonu, zrzuty Budżetu 360/1280 px, POST „Przenieś” na kopii.
4. **Wspólna klasa linków** (refaktor bez zmiany wyglądu): `a.tap { min-height; inline-flex; align-items }` (klasa `tap` jest
   dziś tylko w `a.button.tap`), dopisana do linków samodzielnych w szablonach; z list selektorów E3/E3b/E3c/E3d usunięte tylko
   linki (przyciski, summary, `label.check` zostają). Zrzuty wszystkich ekranów 360/1280 px (`reducedMotion: reduce`) tuż
   przed i po — `cmp` każdej pary identyczny; pomiar < 44 px = 0.
5. **Wydanie 0.20.3:** `simplify`, `pytest`/`ruff`/`mypy`, skill `release` (bump `config.yaml`, `__init__.py`,
   `pyproject.toml`, CHANGELOG, push, CI, opublikowany `v0.20.3`), backup add-onu, update przez `update.budzet_domowy_update`,
   pomiar na żywo 15 ekranów przy 390/1280 px.

## Weryfikacja
`BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, `ruff check`, `ruff format --check`, `mypy`; pomiar Playwright
jak w E3c (wysokość < 44 px = 0, przepełnienie, konsola); sprzątanie: kill po PID, usunięcie kopii księgi.

## Ryzyka
- `.cats summary` jest też w Wydatkach → zrzuty przed/po.
- Refaktor dotyka ~12 szablonów → warunek identyczności bajtowej zrzutów.
- „Koszty stałe” mogą się nie renderować na kopii → kroki 2–3 potwierdzone dopiero na żywo.

## Cofnięcie
Każdy krok osobnym commitem (`git revert <sha>`); po wydaniu przywrócenie backupu add-onu (0.20.2).
