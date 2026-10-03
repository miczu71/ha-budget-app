# M4f — kolejka „Do przejrzenia”: edytowalny tekst reguły + filtr po podpowiedzi AI

## Kontekst

Add-on Budżet Domowy (`/config/addons/ha-budget-app`, repo `miczu71/ha-budget-app`, teraz v0.7.0).
Kolejka `/review` grupuje nieskategoryzowane po dokładnym `merchant` + kierunek + waluta, a zapis
tworzy regułę `merchant equals "<cała nazwa>"` (`web/routes_review.py: make_rule`). Przez to sieć
sklepów („ZABKA Z5512 K.1”, „ZABKA Z0071 …”) wymaga osobnej decyzji dla każdego sklepu. Do tego
podpowiedzi AI (do 3 chipów na sprzedawcę) są rozrzucone po całej liście, więc nie da się
przejść np. samych „Restauracji” jedna po drugiej.

Decyzje usera (wywiad 03.10):
- **Pkt 1:** tekst reguły da się edytować (skrócić do fragmentu) + operator zawiera / zaczyna się
  od / równa się; podgląd mówi, co jeszcze reguła złapie.
- **Pkt 2:** filtr po kategorii z **dowolnej z 3 propozycji** AI; w filtrze każdy wiersz ma
  przycisk **„✓ <kategoria>”**, który od razu zapisuje regułę (sprzedawca równa się) i chowa wiersz.
- Ponowna weryfikacja: w M4c user odrzucił „jednym klikiem” (0.4.1). Tu ✓ jest tylko w widoku,
  w którym user sam wybrał kategorię filtrem, więc decyzja nadal jest ręczna. Zgodne z celem M4c.

Silnik już obsługuje `contains`/`starts_with` (`categorize/rules.py: TextCondition`, `OPS`),
podgląd reguły (`categorize/engine.py: preview`) i kandydatów AI (`suggest/engine.py: candidates`).
Nowy silnik nie jest potrzebny, zmieniamy tylko kolejkę.

## Etapy (każdy to osobne wydanie i checkpoint)

Pierwszy krok wykonania: zapisać ten plan jako `docs/PLAN_review_rule_text.md` w repo add-onu
i dopisać wiersz do `docs/ROADMAP.md` (poza roadmapą, jak M4d/M4e).

### Etap 1 — 0.8.0: edytowalny tekst reguły w kolejce

**`web/routes_review.py`**
- `make_rule(g, cid, op="equals", text=None)`: tekst domyślnie `g.key.value`. Nowa funkcja
  `rule_text(form, g) -> (op, text) | RuleError`. Walidacja: `op` w `rules.OPS`, tekst po `fold`
  ma ≥3 znaki, a warunek musi pasować do nazwy sprzedawcy grupy (`TextCondition.matches` na
  nazwie). Inaczej błąd: „Fragment nie pasuje do «…» — reguła nie objęłaby tej grupy”.
- `preview_ctx` i `assign` biorą op/tekst z formularza (`item` dla chipu AI zostaje na equals).
- Podgląd: oprócz `p.matches/applied/others` liczy **inne grupy z kolejki**, które reguła złapie
  (oba miesiące; ten sam kierunek; `review.all_groups(conn)` + `cond.matches` na nazwie). Pokazuje
  liczbę tr. i grup oraz do 5 nazw („+ ZABKA Z0071 …, i 7 innych”).
- `assign`: `suggest.decide` dla wszystkich sprzedawców, których pozycje z kolejki zniknęły po
  zapisie (nie tylko tej grupy), żeby liczniki AI na Status się zgadzały.
- `_review_saved.html`: gdy reguła objęła inne grupy, pokazuje „złapała też N tr. z K innych grup”
  i link „odśwież listę”. Nieaktualne wiersze po rozwinięciu i tak mówią „już przejrzana”.

**Szablony**
- `_review_group.html` (tylko `g.can_rule`): wiersz „Reguła: sprzedawca [równa się ▾] [tekst]”
  z `rules.OPS`, tekst wstępnie = pełna nazwa. Podgląd: istniejący `change from:#f-…` plus
  `keyup changed delay:300ms` na polu tekstowym. Przy „tylko te” podgląd mówi „ręczna” jak dziś
  (pola są ignorowane).
- `_review_preview.html`: reguła opisana jako „sprzedawca zawiera «ZABKA»” zamiast etykiety grupy
  + blok innych grup.
- `app.css` (styl pola) → bump `?v=` przez wersję (zgodnie z regułą cache WebView).

**Testy** (`tests/test_web_review.py`, `tests/test_review.py`, nazwy syntetyczne pod skaner):
equals bez zmian jak dziś; contains z fragmentem obejmuje 2 grupy, a podgląd pokazuje obie;
fragment niepasujący do grupy → błąd; <3 znaki → błąd; decide dla połkniętych sprzedawców.

### Etap 2 — 0.8.1: filtr „propozycja AI” + ✓

**`suggest/engine.py`**: `pending_candidates(conn, direction) -> dict[str, list[Candidate]]`,
jedno zapytanie zamiast N (ta sama logika co `candidates`; `candidates` ją wywołuje).

**`review.py` / `routes_review.py`**
- `/review?...&ai=<category_id>`: z grup sprzedawców w kierunku zostają te, które mają tę
  kategorię wśród kandydatów. Sekcja „Zagranica” jest w filtrze ukryta (grupy kraju nie mają
  kandydatów). Sortowanie i „pokaż więcej” działają na przefiltrowanej liście.
- Pasek filtrów (tylko gdy `ai_on` i są kandydaci): „AI: Restauracje (12) · Spożywcze (8) …”,
  liczniki po dowolnym kandydacie, chip „wszystkie”. Parametr `ai` w linkach zakładek, sortu,
  miesięcy i „pokaż więcej”.
- `assign`: nowa flaga `all=1` zaznacza całą grupę po stronie serwera (zapis = reguła equals,
  jak domyślnie). Przycisk ✓ to mały `hx-post` w `<summary>` (`category_id`, klucz grupy, `all=1`,
  `month`), z celem `#gid` i odpowiedzią `_review_saved.html`.
- `_review_li.html`: w filtrze obok chipów AI przycisk „✓ <nazwa>” dla grup z `can_rule`.
  Rozwinięcie wiersza dalej daje pełny formularz (inna kategoria, tekst reguły z etapu 1,
  odznaczanie).

**Testy**: filtr zostawia tylko grupy z kandydatem X (też gdy X jest 2. lub 3.); liczniki paska;
`all=1` zapisuje regułę dla całej grupy i woła decide → accepted; filtr przenosi się w linkach.

## Pliki

`budget/app/src/budget/web/routes_review.py`, `review.py`, `suggest/engine.py`,
`web/templates/{review,_review_li,_review_group,_review_preview,_review_saved}.html`,
`web/static/app.css`, testy w `budget/app/tests/`, `budget/config.yaml` (wersja), `CHANGELOG`/README
wg `release` skill, `docs/PLAN_review_rule_text.md`, `docs/ROADMAP.md`.

## Weryfikacja (każdy etap)

1. `pytest` w `budget/app` (ruff/mypy jak w repo), hook pre-commit (skan danych prywatnych) czysty.
2. Dev panel: `devserve.py` na kopii księgi w scratchpadzie, Playwright: zrzut + konsola. Etap 1:
   skrócenie nazwy sieci do fragmentu → podgląd z innymi grupami → zapis → kolejka mniejsza.
   Etap 2: filtr kategorii → ✓ → wiersz znika, licznik spada. Kopię księgi usunąć po weryfikacji.
3. Wydanie wg skilla `release` (bump `budget/config.yaml`, opublikowany release, update przez
   Supervisor), potem weryfikacja na żywo przez Ingress (`http://homeassistant:8123`, `/app/a9413a25_budget`).
4. Checkpoint z userem przed etapem 2; aktualizacja memory `project_budget_app.md`.

## Ryzyka

- Za krótki fragment („BAR”) łapie za dużo. Chroni minimum 3 znaki i podgląd z nazwami innych grup
  oraz liczbą już skategoryzowanych, którym zmieni się kategoria (istniejące `others`).
- Reguła z kolejki staje się na górze listy (pierwszeństwo), jak dziś, więc szeroki `contains`
  może przebić starsze reguły. Podgląd już to pokazuje.
- Numery wersji M5a (0.7.1/0.7.2 w memory) przesuwają się na kolejne.
