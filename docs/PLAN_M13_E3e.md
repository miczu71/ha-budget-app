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

## Wynik kroku 0 (2026-10-05)
- **Diagnoza 43 px potwierdzona na żywo** (Ingress, 390 px, tylko GET): „Wpływy (…)” to `.cats summary` w `ul.cats.pool` —
  `padding: 10px 0` + `line-height: 22.5px` = 42,5 px, `min-height: 0`, nie pasuje do `details.small summary`. Reguła E3c
  `details.small summary` działa na „wydane w poprzednich miesiącach” (44 px) — nie jest martwa, zostaje.
- Wydatki na żywo: wszystkie `.cats summary` mają 72 px → `min-height: var(--tap)` dla `.cats summary` ich nie zmieni.
- **Kopia księgi:** sekcje „Wpływy” i „Koszty stałe” nie renderowały się, bo kopia (sprzed kategoryzacji wpływów) nie ma żadnej
  transakcji w podkategoriach grupy `income`. W samej kopii (scratchpad) większe uznania bez kategorii z ostatnich miesięcy
  dostały ręcznie podkategorię przychodów → obie sekcje się renderują. Pomiar na kopii przy 390 px: jedyny element < 44 px to
  summary „Wpływy” (42,5 px), jak na żywo; linki w zdaniu trafiają w ±20 px przez `::after`; Koszty stałe: 5 wierszy z
  `form.move`.

## Wynik kroków 1–4 (2026-10-05, lokalnie, niewypchnięte)
1. Pusty stan Reguł: „zaznacz «utwórz regułę»”; test w `test_nav_and_empty_pages` (czerwony przed zmianą).
2. `.cats summary { min-height: var(--tap) }`: „Wpływy” 42,5 → 44 px. Zrzuty 390/1280: Wydatki i Budżet 1280 identyczne,
   Budżet 390 zmieniony tylko pod wierszem „Wpływy” (+1,5 px). Pułapka pomiaru: szewrony mają `transition` obrotu —
   `reducedMotion` jej nie wyłącza; skrypt zrzutów wstrzykuje `transition: none`.
3. Koszty stałe: `details.leaf` (summary = nazwa + mediana; rozwinięcie = kategoria główna, „Transakcje”, „Przenieś”), wcięcie
   22 px. Przy okazji szewron `.cats details[open] > summary` (bez `>` zagnieżdżone wiersze w otwartych „Kosztach stałych”
   miały obrócony szewron). Wydatki i Kategorie: zrzuty identyczne; 5 wierszy po 44 px; „Przenieś” klikiem w przeglądarce
   działa (303, wiersz znika), przywrócone przez „Dodaj do stałych”.
4. `a.tap` (jedna reguła) zamiast linków w listach selektorów E3–E3d; `tx-link` → `tap` (była tylko celem dotyku);
   konwencja w `DESIGN.md`. Kopia przygotowana tak, by objąć możliwie wszystkie stany: wykryte serie (6 potwierdzonych,
   13 propozycji) i syntetyczne podpowiedzi AI (12 sprzedawców, z „więcej”). 29 widoków × 390/1280 px: **58/58 zrzutów
   identycznych co do bajtu**, style obliczone 1620 linków identyczne. Pomiar powtarzalny dopiero po: `networkidle` po otwarciu
   `<details>` i pominięciu `details[hx-get]` (leniwe grupy kolejki — bez linków objętych zmianą). Niewyrenderowane na kopii:
   sekcja „Zmiany” w Cyklicznych (link „Edytuj i potwierdź”) — klasa dopisana w szablonie, sprawdzenie na żywo.
511 testów zielonych po każdym kroku.

## Wynik kroku 5 — wydanie 0.20.3 (2026-10-05)
`simplify` (4 przeglądy): `min-height` w głównej regule `.cats summary` (przy okazji link „Nieskategoryzowane” w Wydatkach
dostał `min-height: 44px` — ma 64 px, piksele bez zmian), `.pool > li > details > :is(.flex-lines, p, form)` zamiast
`.pool details > …` (wcięcie liścia tylko z `.leaf form`), osierocone klasy `rule-link`/`rv-links` usunięte, nieaktualne
komentarze sekcji poprawione; 58/58 zrzutów identycznych. Pominięte (poza zakresem albo zmiana wyglądu): scalenie list
przycisków/summary/`label.check`, globalne `summary { min-height }`, zawężenie `.cats summary` do pierwszego poziomu.
Bump 0.20.2 → 0.20.3 (`889a598`), 511 testów, ruff, mypy czyste, CI zielone, release `v0.20.3` opublikowany, backup add-onu
`7a357d6a` („Budżet Domowy 0.20.2”), update przez `update.budzet_domowy_update` → zainstalowane 0.20.3. Na żywo przez Ingress
(tylko GET): 15 ekranów przy 390/1280 px — stopka v0.20.3, `app.css?v=0.20.3`, bez przepełnienia i błędów konsoli, **0 elementów
< 44 px** (jedyne trafienia pomiaru to checkboxy 20 px w `label.check` 44 px na Kontach — projekt E3d). Budżet: „Wpływy” 44 px,
wiersz Kosztów stałych 44 px bez kotwicy w summary, po dotknięciu „Transakcje” i „Przenieś” (44 px). Kopia księgi usunięta.

## Weryfikacja
`BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, `ruff check`, `ruff format --check`, `mypy`; pomiar Playwright
jak w E3c (wysokość < 44 px = 0, przepełnienie, konsola); sprzątanie: kill po PID, usunięcie kopii księgi.

## Ryzyka
- `.cats summary` jest też w Wydatkach → zrzuty przed/po.
- Refaktor dotyka ~12 szablonów → warunek identyczności bajtowej zrzutów.
- „Koszty stałe” mogą się nie renderować na kopii → kroki 2–3 potwierdzone dopiero na żywo.

## Cofnięcie
Każdy krok osobnym commitem (`git revert <sha>`); po wydaniu przywrócenie backupu add-onu (0.20.2).
