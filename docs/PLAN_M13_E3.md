# M13 E3 — Ekrany robocze (0.20.0)

Do akceptacji. Bez kodu przed „go”. Zakres z wywiadu 2026-10-05: tylko wygląd i ergonomia **Do przejrzenia**,
**Transakcji** i **Reguł** na telefonie. Bez nowych funkcji, bez zmian logiki, encji MQTT i schematu bazy.

## Ograniczenia (potwierdzone)
1. Korzysta jedna osoba, głównie telefon w HA Companion (Ingress WebView), czasem desktop.
2. Automatycznie dzieje się tylko render istniejących danych; wydanie dopiero po „go” na etap.
3. Wygląd = Monarch (jeden, bez przełącznika), `DESIGN.md` obowiązuje; HTML `no-store`, statyki `?v=`, wersja w stopce.
4. **Sukces:** cele dotyku ≥ 44 px (chipy, `rv-accept`, przyciski w tabelach, `form.move`, `form.rename`), ekrany spójne
   z resztą Monarch, zrzuty 360 i 1280 px bez przepełnienia poziomego i bez błędów w konsoli, testy zielone, zrzuty
   przed/po różne tylko tam, gdzie zmiana zamierzona.

## Stan wyjściowy (z `static/app.css`, odczyt statyczny)
Za małe cele dotyku (padding w px, bez `min-height`): `button.chip`/`a.chip` (3×10, 13 px), `button.rv-accept` (3×12),
`table.rules .actions button` (4×10), `form.rename button` (6×10), `form.move button`/`select` (3×8, 3×6), `.rv-f-more summary`
(2 px), `a.button` (8×14). Jedyny wzorzec ≥ 44 px to `.legend-item a` (`min-height: 44px`). Pomiar rzeczywisty w kroku 0.

## Kroki (jedno wydanie 0.20.0, checkpoint po każdym kroku)

**Krok 0 — pomiar (odczyt).** Kopia księgi w scratchpadzie, `devserve.py` (`create_app(dev=True)`, PID zapisany w tym samym
podpowłoce), Playwright 360 px: `getBoundingClientRect` dla `button, a.chip, summary, select, a.button` na `/review`,
`/transactions`, `/rules`, `/rules/new`; lista elementów < 44 px po wysokości. Wynik wpisuję do tego pliku. Cofnięcie: skasować
kopię i proces. Zrzuty „przed” do `/home/claude/.playwright-mcp`.

**Krok 1 — Do przejrzenia** (`review.html`, `_review_group.html`, `_review_li.html`, `_review_preview.html`, CSS `rv-*`,
`.cat-form`). Chipy AI i filtr, `rv-accept`, `rv-f-more summary`, wiersz reguły, „+ więcej warunków”: wysokość ≥ 44 px, odstępy
między celami ≥ 8 px, wiersz grupy czytelny w 360 px. Zmiana wspólnych selektorów (`button.chip`) dotyka też Transakcji,
dlatego robię ją tu i sprawdzam oba ekrany.

**Krok 2 — Transakcje** (`transactions.html`, `_txn_category.html`, `_txn_rule_preview.html`, `table.tx`). Wiersz księgi na
360 px (siatka, kwota i kategoria bez ściskania), select kategorii i pole reguły ≥ 44 px, stronicowanie i filtr.

**Krok 3 — Reguły** (`rules.html`, `rule_form.html`, `_rule_conditions.html`, `_rules_tabs.html`, `table.rules .actions`).
Tabela reguł jako karty na wąskim ekranie, akcje ≥ 44 px, warunki w formularzu bez poziomego przewijania. Wspólny
`_rule_conditions.html` używa też kolejka (krok 1), więc po zmianie powtarzam test kolejki.

**Krok 4 — wydanie** (tylko po „go” na kroki 1–3): `simplify` przed commitem; bump 0.19.1 → 0.20.0 w `config.yaml`,
`__init__.py`, `pyproject.toml`; CHANGELOG; push; CI dla sha; `gh release create v0.20.0` (nie draft); backup add-onu;
update `update.budzet_domowy_update`; weryfikacja na żywo (stopka `v0.20.0`, 390 i 1280 px, konsola). Skan prywatności:
w tekstach i fixture'ach tylko neutralne nazwy.

## Weryfikacja
`BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, `ruff check`, `ruff format --check`, `mypy`; ponowny
pomiar z kroku 0 (zero elementów interaktywnych < 44 px na czterech ekranach); zrzuty przed/po na każdy krok; detektor
impeccable bez nowych ostrzeżeń.

## Ryzyka
- Wspólne selektory (`button.chip`, `button`) dotykają innych ekranów → po każdym kroku zrzuty wszystkich ekranów, nie tylko
  zmienianego.
- Zbyt wysokie chipy wydłużą kolejkę (mniej grup na ekranie): kompromis wysokość/odstęp oceniasz na checkpoincie kroku 1.
- WebView cache: podbić `?v=` (wersja w stopce potwierdza).
- Skaner pre-commit (nazwy miejsc/ulic): teksty i testy syntetyczne.
- **Cofnięcie:** `git revert` commitów kroku; po wydaniu wydanie poprawkowe albo przywrócenie backupu add-onu. Brak zmian
  schematu i encji.

## Poza zakresem
Nowe funkcje, zmiana logiki reguł/kolejki, ekrany Kategorie/Słownik/Konta/Import/Bank (osobna decyzja, jeśli po E3
będą odstawać), M5c/M6/M8.

## Wynik kroku 0 (2026-10-05, pomiar na kopii księgi, 360 px, bez zmian w kodzie)

Wysokości z `getBoundingClientRect`, poza `nav`/`header`/`footer`. Żaden z czterech ekranów nie ma przepełnienia poziomego.

| Ekran | Elementy < 44 px (liczba, najmniejsza wysokość) |
|---|---|
| Do przejrzenia | `select` 65 × 41 px, `button` 65 × 41 px, `button.link.small` 69 × 23 px, pole wyboru pozycji 479 × 13 px, link `a` 1 × 19 px; `summary` grupy 64 px (OK) |
| Transakcje | `button.cat-chip` 48 × 26 px (w tym 19 `.empty`), `a.small` 48 × 16 px, `select` 4 × 38 px, `input[date]` 2 × 42 px, `input[search]` 40 px |
| Reguły (lista) | `a.button` 39 px; tabeli akcji nie zmierzono (kopia nie ma reguł) |
| Reguły (nowa) | `select` 10 × 38 px, `input[text]` 6 × 40 px, `button` 41 px |

Wnioski:
- Prawdziwy problem to pola i małe akcje, nie przyciski: `cat-chip` w Transakcjach (26 px), `a.small` (16 px), `button.link.small` (23 px)
  i pola wyboru pozycji (13 px) w kolejce. Pola formularzy mają 38–42 px, czyli brakuje im 2–6 px.
- `table.rules .actions button`, `button.chip`, `rv-accept`, `form.move` i `form.rename` w tej kopii nie występują:
  brak reguł i podpowiedzi AI. W kroku 1 i 3 dosieję syntetyczne reguły i podpowiedzi (neutralne nazwy) do kopii, żeby zmierzyć
  także te elementy; do tego czasu opieram się na paddingach z `app.css` (3–6 px).
- Pole wyboru 13 px: duży cel to zwykle cały wiersz (`label`), więc najpierw sprawdzę, czy wiersz już jest klikalny.
- Zrzuty „przed”: ze względu na brak danych (reguły, podpowiedzi) zrobię je w kroku 1 po zasileniu kopii.

## Wynik kroku 1 (Do przejrzenia, 2026-10-05, lokalnie, bez commita)

Zmiany: `static/app.css` (blok „M13 E3: cele dotyku”, `--tap: 44px`, reguły tylko dla klas `rv-*`, `.rule-fields`) i `review.html`
(klasa `rv-links` na dwóch akapitach z linkami). Pomiar 360 px na kopii z syntetycznymi podpowiedziami AI i regułami:
przed — chipy 28 px, `a.on` 34 px, linki 19 px, `select`/`button` 41 px, `summary` 24 px, `button.link.small` 23 px, `label.check` 20 px;
po — wszystko ≥ 44 px (chipy i `rv-accept` min. 44 px, 43 elementów), same pola wyboru 20 px, ale ich `label` ma 44 px
(cały wiersz jest celem). Bez przepełnienia poziomego, konsola bez błędów, 510 testów, ruff i mypy czyste.
Uwaga: Playwright trzymał stary `app.css?v=0.19.1` (`immutable`), więc „po” zmierzyłem po `fetch(..., {cache: "reload"})`.
Odstępstwo: odstęp `.rv-ai`/`.rv-ai-filter` 6 → 8 px dotyczy też wiersza podpowiedzi AI w Transakcjach (`.cat-form .rv-ai`).

## Wynik kroku 2 (Transakcje, 2026-10-05, lokalnie, bez commita)

Krok 1 scommitowany lokalnie po `simplify` (scalone reguły, `--tap` w tokenach `:root`, gap zmieniony w oryginalnych regułach).
Zmiany kroku 2: `static/app.css` (blok „M13 E3: Transakcje”, `.cat-form` gap 6 → 8 px w oryginale), `transactions.html`
(klasa `tx-link` na `a.badge` „cykliczna”, „to się powtarza” i „wyczyść filtry”). Pomiar 360 px: lista i otwarty formularz edycji
kategorii bez elementów < 44 px (poza celowo ukrytym przyciskiem „Filtruj” i polem wyboru 20 px, którego `label` ma 44 px);
bez przepełnienia poziomego, konsola czysta, stronicowanie obecne. Regresja `/review?ai=…` po scaleniu reguł: bez zmian
(rv-accept 2, tylko pola wyboru 20 px). 1280 px: układ tabeli bez zmian. 510 testów, ruff, mypy czyste.
Do oceny: wiersze z „to się powtarza” w kolumnie „Szczegóły” są wyższe (link 44 px), więc lista jest dłuższa.

## Wynik kroku 3 (Reguły, 2026-10-05, lokalnie, bez commita)

Kroki 1 i 2 scommitowane lokalnie (bez pusha). Zmiany kroku 3: `static/app.css` (blok „M13 E3: Reguły” z kartami wiersza
na ≤ 640 px; `table.rules .actions` bez zawijania), `rules.html` (klasy `rule-link`, `tap`, `cond-cell`, `tx-link`),
`rule_form.html` („Anuluj” z `tx-link`), `_rules_tabs.html` (klasa `rules-tabs`). Pomiar 360 px na kopii z 8 regułami
(w tym wyłączona i z nazwą): przed — tabela przewijała się poziomo o 63 px, przyciski akcji 29 px, zakładki i linki 41 px,
„+ Nowa reguła” 39 px; po — brak przewijania, wszystkie elementy ≥ 44 px (lista, lista z filtrem bez przycisków przesuwania,
nowa reguła, edycja reguły; poza ukrytym „Filtruj” i polem wyboru 20 px z labelem 44 px). Słownik, Do przejrzenia, Transakcje,
Cykliczne, Kategorie odpowiadają. 1280 px: akcje w jednym rzędzie, tabela bez zmian układu. 510 testów, ruff, mypy czyste,
konsola bez błędów. Do oceny: lista reguł na telefonie to teraz karty (warunki, kategoria + trafienia, rząd czterech przycisków).

## Wynik kroku 4 (wydanie 0.20.0, 2026-10-05)

Przed tagiem: kopia księgi, 390×844 i 1280×900, ekrany `/review` (z otwartą grupą), `/transactions`, `/rules`, `/rules/new`: bez
przepełnienia poziomego, bez elementów < 44 px (poza polami wyboru, których `label` ma 44 px), konsola bez błędów.
Poza zakresem E3: na Podsumowaniu (`/`) zostały małe linki (16–23 px) i `a.button` 39 px — kandydat na osobny drobny etap.
