# M5a — Budżet Flex: „ile mogę jeszcze wydać”

## Context

Budżet Domowy ma za sobą M0–M4e
(0.6.1 na żywo). Następny w `docs/ROADMAP.md` jest M5 „Budżet Flex”, ale to duży pakiet: grupy,
płatności cykliczne, budżet z podpowiedzią, limity, skarbonki, encje, wykresy. Wywiad 02.10 ustalił,
że **pierwszy kawałek ma odpowiadać na jedno pytanie: „ile mogę jeszcze wydać w tym miesiącu?”**.

Decyzje usera (wywiad 2026-10-02):
1. **Pula = kwota ustawiona ręcznie** (miesięczny budżet elastyczny), z podpowiedzią = mediana
   wydatków elastycznych z 6 pełnych miesięcy. Nie zależy od dnia wypłaty ani od wykrywania stałych.
2. **Do „wydane” liczy się tylko grupa `flexible`.** Stałe i nieregularne pokazane obok jako
   informacja, bez wpływu na „zostało”.
3. **Odpowiedź = kwota + tempo:** zostało X z Y, „na dzień do końca miesiąca”, pasek z kreską
   „gdzie powinieneś być dziś” (liniowo), lista podkategorii elastycznych: wydane vs mediana 6 mies.
   Bez limitów per kategoria.
4. **Wydatki bez kategorii liczą się jako elastyczne** (ostrożnie), z dopiskiem „w tym N bez
   kategorii → Do przejrzenia”.

Reszta M5 (płatności cykliczne + stałe zapłacone/planowane → **M5b**; skarbonki, trendy z wykresami,
limity, `savings_rate` → **M5c**) zostaje w roadmapie, nie w tym etapie.

Otwarte checkpointy (M3 po 03.10 06:30, sesja reguł M4a, M4b, M4c) **nie blokują** — M5a nie dotyka
synchronizacji ani silnika kategorii. Start implementacji dopiero po jawnym „go”.

## Krok 0 — utrwalenie planu (pierwsza czynność po akceptacji)

- `docs/PLAN_M5a.md` = treść tego planu (bez liczb o finansach usera).
- `docs/ROADMAP.md`: wiersz M5 → M5a/M5b/M5c, sekcja M5 podzielona, decyzja 13 (cztery punkty wyżej).
- Commit `docs(M5a): plan — „ile mogę jeszcze wydać”` (hook pre-commit skanuje diff), push.

## Etap 1 — 0.7.0: ekran „Budżet” w panelu

**Wartość:** odpowiedź „ile zostało” w panelu, od 1. dnia miesiąca.

1. **Grupa budżetu edytowalna** — zakładka Kategorie (`web/templates/categories.html`,
   `web/routes_rules.py`): `<select>` grupy przy każdej podkategorii (Przychody / Stałe / Elastyczne /
   Nieregularne / Oszczędności / Poza budżetem), POST `/categories/{id}/group`. Funkcja
   `set_flex_group` w `categorize/taxonomy.py` obok `add`/`move`. Potrzebne, bo własne podkategorie
   usera (np. rozliczenia z osobami) dostały grupę po sąsiadach (`taxonomy.py:139`).
   Zmiana grupy nie przelicza kategorii — `spending` czyta grupę na bieżąco.
2. **Migracja `006_flex_budget.sql`:** `flex_budget(month_from TEXT PRIMARY KEY, amount TEXT NOT
   NULL, updated_at TEXT)`; kwota dla miesiąca M = wiersz z największym `month_from ≤ M`
   (zmiana „od tego miesiąca” nie przepisuje historii).
3. **Moduł `budget/flex.py`** (czyste funkcje, wzorzec `spending.py`):
   - reużywa `spending._sums` (→ publiczne `spending.sums`) i `taxonomy.tree`;
   - `build(conn, month, today) -> FlexMonth`: `budget` (None, gdy nie ustawiono), `spent` =
     netto grupy `flexible` + nieskategoryzowane wydatki (`unc_out`), `uncategorized_count/amount`,
     `remaining`, `per_day` (zostało / pozostałe dni łącznie z dziś; dla miesięcy minionych brak),
     `expected_today` = budżet × dzień/dni miesiąca, `pace` (ponad/pod tempem), `fixed`,
     `non_monthly` (info), `lines` = podkategorie elastyczne: wydane + mediana 6 mies.;
   - `suggestion(conn, today)` = mediana `spent` z 6 pełnych miesięcy przed bieżącym (z listą
     miesięcy do pokazania);
   - waluty ≠ PLN pomijane jak w `spending` (licznik w notce).
4. **Ekran „Budżet”** (`web/routes_budget.py`, `templates/budget.html`, zakładka w `base.html` zaraz
   po „Status”): nawigacja miesiącami jak „Wydatki” (`spending.parse_month`/`add_months`), duża
   liczba „zostało”, pasek wydane/budżet z kreską tempa (czysty CSS, bez bibliotek), „na dzień”,
   notka o nieskategoryzowanych z linkiem `/review?month=`, karta stałe/nieregularne (info),
   lista podkategorii z medianą. Bez ustawionej kwoty: formularz z podpowiedzią medianą (jedno
   dotknięcie wypełnia pole). Edycja kwoty: „od tego miesiąca”. Mobile-first, `?v=` na CSS, plakietka.
5. **Testy** (wzorzec `tests/test_spending.py`, `tests/test_web_categorize.py`, dane syntetyczne):
   kwota obowiązuje od miesiąca; zwrot w elastycznej zmniejsza `spent`; nieskategoryzowany wydatek
   wlicza się, wpływ nie; stałe/nieregularne/oszczędności/przelewy wewnętrzne nie; `per_day` w ostatnim
   dniu = zostało; mediana z <6 miesięcy historii; zmiana grupy przenosi kwotę między sekcjami;
   ekran bez kwoty i z kwotą; POST grupy i kwoty.
6. Wydanie wg skilla `release` (bump `config.yaml`, CHANGELOG, DOCS — sekcja „Budżet”), aktualizacja
   przez Supervisor, weryfikacja przez Ingress w Playwright.

## Etap 2 — 0.7.1: encje w HA

**Wartość:** „zostało” w automatyzacjach i powiadomieniach (decyzja 10: encje tak, dashboardy nie).

- `ha_publisher.build_entities` (`ha_publisher.py:83`) dostaje 4 sensory z `flex.build(today)`:
  `budget_flex_budget`, `budget_flex_spent`, `budget_flex_remaining` (atrybuty: `per_day`,
  `expected_today`, `uncategorized_count`, `month`), `budget_flex_per_day`; `device_class: monetary`,
  `unit PLN`; bez ustawionej kwoty → `budget`/`remaining`/`per_day` = unknown.
- Odświeżanie: istniejące `Service.refresh()` (`service.py:151`, po synchronizacji i w pętli
  okresowej) + wywołanie po zapisie kwoty i zmianie grupy w panelu. Sprawdzić, czy interwał pętli
  łapie zmianę dnia dla `per_day`; jeśli nie — odświeżenie o północy.
- Testy w `tests/test_ha.py`; wydanie jak wyżej; encje sprawdzone przez `ha_search`/`ha_get_state`.

## Checkpoint po każdym etapie

Stop, zrzut ekranu „Budżet” (telefon) + stan encji, bez startu kolejnego etapu bez „go”. Po etapie 2
— checkpoint M5a i rozmowa, czy M5b (płatności cykliczne) czy M5c jest następny.

## Weryfikacja

- `budget/app/.venv/bin/python -m pytest` + ruff/mypy jak w CI; CI zielone przed wydaniem.
- Panel dev na kopii księgi (`create_app(dev=True)` bez `serve`, księga po `db.connect` +
  `engine.recategorize`) — sprawdzenie liczb przed wydaniem; liczby o finansach tylko lokalnie.
- Po wydaniu: Playwright przez Ingress , zrzut
  mobile + 0 błędów konsoli; ręczne przeliczenie „wydane” dla bieżącego miesiąca z ekranu „Wydatki”
  (suma podkategorii elastycznych + nieskategoryzowane) = wartość na „Budżet”.
- Etap 2: `sensor.budget_flex_remaining` w HA z poprawnym stanem i atrybutami.

## Ryzyka

- „Zostało” jest zaniżone, dopóki pokrycie < 85% (świadoma decyzja 4) — notka na ekranie.
- Podpowiedź mediany obejmuje miesiące z wyjazdem/słabszym pokryciem — pokazana z listą miesięcy,
  user wybiera kwotę sam.
- Dane w repo publicznym: tylko syntetyczne; hook pre-commit skanuje każdy commit.

## Wynik etapu 1 (0.7.0, 2026-10-02)

- Wydane jako GitHub release v0.7.0, zainstalowane przez Supervisor; Ingress: plakietka v0.7.0,
  `app.css?v=0.7.0`, `no-store`, 0 błędów konsoli, zrzut mobilny (390 px).
- Odstępstwo od planu: przyciski „Ustaw/Zmień od tego miesiąca” i „obowiązuje od miesiąca: …”
  zamiast odmiany nazw miesięcy (lista nazw w dopełniaczu blokowała skaner pre-commit).
- Historia w karcie „Kwota budżetu” pokazuje „w tym bez kategorii” per miesiąc — przy obecnym
  pokryciu podpowiedź (mediana) jest wyraźnie wyższa niż suma median podkategorii, bo wydatki bez
  kategorii (głównie przelewy do osób) liczą się do „wydane” (decyzja 13). Do omówienia na
  checkpoincie.
- Kwota budżetu na żywo nieustawiona — decyzja użytkownika.
