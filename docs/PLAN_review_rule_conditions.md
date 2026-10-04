# Plan: pełne warunki reguły w kolejce „Do przejrzenia” i na Transakcjach (M4h)

## Kontekst

W Budżecie Domowym (wersja 0.9.1)
silnik reguł już umie warunki złożone (I): do 3 warunków tekstowych (sprzedawca / opis-tytuł /
kontrahent / konto kontrahenta × równa się / zawiera / zaczyna się od) + konto, typ, kierunek,
kwota od–do, zmiana nazwy sprzedawcy (`categorize/rules.py`). Ale pełny edytor jest tylko w
zakładce Reguły. W kolejce (`/review`) grupa sprzedawcy ma jeden wiersz
„reguła: sprzedawca [op] [tekst]” z kierunkiem na sztywno; grupy krajów i Transakcje mają tylko
link do edytora wypełnionego „sprzedawca równa się X” — przeładowanie i utrata miejsca w kolejce.

Cel usera: tworzyć reguły z **dowolnych pól** (w tym kwota i fragment tytułu) i **kilku warunków
naraz (I)** bez wychodzenia z kolejki / Transakcji.

Decyzje z wywiadu (04.10):
- „złożone” = kilka warunków połączonych I (nie LUB, nie >3 warunków) — silnik bez zmian semantyki;
- edytor **w miejscu, rozwijany** („+ więcej warunków”), nie przejście do zakładki Reguły;
- reguła łapiąca **część grupy** → reszta **zostaje w kolejce** (tak rozbija się mieszanki pod
  jednym odbiorcą); podgląd oznacza, które pozycje grupy reguła złapie.

## Podejście (rekomendowane)

Jeden wspólny komponent warunków (makro Jinja + parser formularza) używany przez trzy miejsca:
edytor Reguł, grupę kolejki i formularz kategorii transakcji. Alternatywy odrzucone: osobny
„mini-edytor” ładowany htmx z własnym podglądem/zapisem (dwa systemy podglądu do utrzymania);
link do edytora z powrotem (user wybrał „w miejscu”).

### Wspólne elementy
- `web/templates/_macros.html`: makro `rule_fields(prefix_ctx…)` — 3 wiersze warunków, konto, typ,
  kierunek, kwota od/do, nazwa sprzedawcy (wyciągnięte z `rule_form.html`, który zaczyna go używać —
  zero zmian wyglądu edytora Reguł).
- `rule_from_form` + `form_context` przenieść z `web/routes_rules.py` do wspólnego miejsca
  (`web/common.py` albo nowy `web/rule_form.py`), parametr „domyślne z grupy / transakcji”.
- `categorize/engine.preview`: dodać do `Preview` zbiór `matched_ids` (id transakcji, które złapie
  kandydat) — liczone w tym samym przebiegu, bez drugiego `_load` (host = wolny CPU, M4g).

### Etap 1 (0.10.0) — kolejka, grupy sprzedawców
- `_review_group.html`: zwinięty widok bez zmian (wiersz „reguła: sprzedawca [op] [tekst]” =
  warunek 0); link „+ więcej warunków” rozwija makro `rule_fields` z wartościami: warunek 0 =
  bieżący wiersz (pole można zmienić z „sprzedawca” na inne), kierunek = kierunek grupy
  (edytowalny), reszta pusta. Nazwy pól ujednolicone na `field_i/op_i/value_i` (dziś
  `rule_op/rule_text`) — jeden parser.
- `routes_review.py`:
  - `rule_condition` → `rule_conditions(g, form)` zwracające pełne `Conditions` (+ `rename`);
    walidacja `rules.validate` + nowy warunek grupy: reguła musi złapać **≥1 pozycję tej grupy**
    (zamiast dzisiejszego „tekst musi obejmować sprzedawcę grupy”); fragment ≥3 znaki zostaje.
  - `preview_ctx`: z `matched_ids` liczy „złapie X z N pozycji grupy”, `elsewhere` po faktach
    (dowolne pole, nie tylko tekst sprzedawcy) z tego samego przebiegu; szablon oznacza pozycje
    grupy („reguła” / „zostaje w kolejce”).
  - `assign`: zapis `rules.save` z pełnymi warunkami; `suggest.decide` tylko dla sprzedawców,
    których **wszystkie** pozycje w kolejce zostały objęte (częściowe pokrycie nie zamyka
    podpowiedzi AI dla reszty); `_review_saved.html` pokazuje resztę grupy, gdy coś zostało.
  - Tryb ręczny bez zmian: „tylko te” / odznaczenie pozycji → kategoria ręczna dla zaznaczonych.
  - Przycisk ✓ filtra AI (`all=1`) bez zmian — domyślny warunek „sprzedawca równa się”.
- `_review_preview.html`: opis reguły przez wspólne `describe()` (z `routes_rules.py`, też do
  wspólnego modułu) zamiast „sprzedawca op tekst”.
- Testy: `tests/test_web_review.py` — reguła z warunkiem opisu łapiąca część grupy (reszta w
  kolejce, AI nie zamknięte), kwota od–do, zmieniony kierunek, warunek bez sprzedawcy łapiący ≥1
  pozycję, błąd gdy reguła nie łapie nic z grupy, dotychczasowe ścieżki (equals/contains/✓ AI)
  zielone; `tests/test_categorize_engine.py` — `matched_ids`.

### Etap 2 (0.10.1) — Transakcje + grupy krajów
- `_txn_category.html`: w formularzu kategorii „+ reguła” rozwija `rule_fields` z warunkiem
  „sprzedawca równa się <merchant>” i kierunkiem z kwoty; podgląd przez `engine.preview(release=txn)`;
  zapis = `rules.save` + `release_manual` + `recategorize` (jak `/rules/save`), odpowiedź = chip
  kategorii w wierszu. Link „Zawsze dla X »” otwiera ten sam rozwinięty formularz zamiast strony.
- Grupy krajów: link „reguła…” przy sprzedawcy rozwija `rule_fields` w miejscu (warunek 0 =
  ten sprzedawca), z tymi samymi zasadami (≥1 pozycja grupy, reszta zostaje).
- Testy: `tests/test_web_categorize.py`, `tests/test_web_review.py`.

## Pliki
`budget/app/src/budget/web/{routes_review.py,routes_rules.py,routes_transactions.py,common.py}`,
`web/templates/{_macros.html,rule_form.html,_review_group.html,_review_preview.html,_review_saved.html,_txn_category.html}`,
`web/static/app.css` (rozwijany blok, oznaczenia pozycji), `categorize/engine.py`,
`budget/config.yaml` + `CHANGELOG.md` + `DOCS.md`, `docs/PLAN_review_rule_conditions.md` (nowy),
`docs/ROADMAP.md` (wpis M4h). Branch: `main` (jak dotąd w tym repo).

## Kolejność wykonania
1. Pierwszy krok po akceptacji: `docs/PLAN_review_rule_conditions.md` (ten plan) + wpis w
   ROADMAP, commit.
2. Etap 1 TDD → `pytest` + ruff/mypy jak w CI → panel dev (`devserve.py` w scratchpadzie na kopii
   księgi) + Playwright 390 px i desktop, konsola bez błędów → release 0.10.0 (skill `release`,
   published) → update add-onu → weryfikacja przez Ingress → **checkpoint**.
3. Etap 2 dopiero po „go”.

## Ryzyka
- Wydajność: podgląd w kolejce już robi pełny `_classify` (~0,8 s po M4g); `matched_ids` w tym
  samym przebiegu, `elsewhere` bez drugiej pętli po regułach.
- Telefon: rozwinięty blok musi się mieścić w 390 px (pola w kolumnie).
- Hook pre-commit skanuje dane prywatne — w testach tylko syntetyczne nazwy/tytuły.
- Mobile WebView cache — wersjonowane `app.css?v=` (już jest) + badge wersji.

## Weryfikacja
- `budget/app/.venv/bin/pytest` całość zielona; ruff + mypy jak w `.github/workflows/ci.yml`.
- Dev panel: grupa z mieszanką tytułów → „+ więcej warunków” → opis zawiera X + kwota od–do →
  podgląd „złapie k z n”, oznaczenia pozycji → zapis → grupa zostaje z resztą, reguła widoczna w
  Regułach z pełnym opisem.
- Na żywo (Ingress, Playwright): to samo na prawdziwej kolejce, bez zapisu (tylko podgląd) chyba że
  user sam zapisze; konsola bez błędów; czas podglądu ≤ ~1 s.

## Wynik etapu 1 (0.10.0, 2026-10-04)

Wydane (release v0.10.0, opublikowane) i zainstalowane; zweryfikowane na żywo przez Ingress
(390 px): plakietka v0.10.0, „+ więcej warunków” rozwija pola, błąd „nie pasują do żadnej
pozycji” przy kwocie spoza grupy, podgląd z kategorią ~0,85–1,2 s, konsola bez błędów. Na żywo
tylko podgląd — reguł nie zapisywano.

Odstępstwa od planu (świadome):
- Zamiast `Preview.matched_ids` — `engine.facts(conn, ids)` dla pozycji kolejki: walidacja
  „≥1 pozycja grupy” i lista resztek działają także przed wyborem kategorii (bez pełnego
  przeliczenia księgi).
- Pozycje, które zostaną w kolejce, są wymienione w podglądzie (do 5 + „i N innych”), zamiast
  oznaczeń przy każdym checkboxie.
- Pola reguły w kolejce mają prefiks `rule_` (formularz grupy ma własne `kind`/`direction`).
- Puste dodatkowe wiersze warunków domyślnie „opis / tytuł zawiera” (także w edytorze Reguł).
- Wiersz reguły w kolejce ma też wybór pola (nie tylko „sprzedawca”).

Dev (kopia księgi, 0 reguł): reguła „sprzedawca = X i opis zawiera Y i kwota ≥ 50” złapała
część grupy, reszta została w kolejce otwarta; zapis ~1 s.

Czeka: checkpoint etapu 1 (user używa), etap 2 (Transakcje + grupy krajów) dopiero po „go”.
