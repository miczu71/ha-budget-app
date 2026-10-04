# Plan: wolny zapis reguł w kolejce „Do przejrzenia” — indeks reguł (0.9.1)

## Context

User: zapis nowych reguł podczas przeglądania kolejki trwa bardzo długo. Pytanie: baza czy brak optymalizacji?

**Diagnoza (zmierzona na kopii księgi dev w scratchpadzie, ten sam host co add-on — AMD GX-415GA, 4 słabe rdzenie, ~2,9k transakcji):**

| liczba reguł | POST /review/preview | POST /review/assign (zapis) |
|---|---|---|
| 0   | ~0,75 s | ~1,7 s |
| 60  | ~2,3 s  | ~5,3 s |
| 150 | ~5,6 s  | ~10,8 s (bez profilera recategorize ~5,6–6,3 s) |

- **To nie baza.** Wszystkie zapytania SQL razem to ~0,06–0,1 s; wczytanie 3k wierszy ~0,3 s.
- **Przyczyna: algorytm.** `engine._classify` (`budget/app/src/budget/categorize/engine.py:107`) dla każdej transakcji sprawdza reguły po kolei w czystym Pythonie, aż któraś pasuje. Większość transakcji nie pasuje do żadnej, więc koszt = transakcje × reguły (150 reguł → ~425k wywołań `Conditions.matches`, ~640k `matches_text`). Każda reguła z kolejki to kolejna reguła, więc **każdy zapis spowalnia następny**.
- Ten sam pełny przebieg robią: `engine.preview` (podgląd po każdej zmianie w formularzu — htmx `change` + `keyup` w `_review_group.html:41`) i `engine.recategorize` przy zapisie (`routes_review.py` assign).
- Wzmacniacz: endpointy są `async`, a obliczenia synchroniczne → w czasie liczenia **cały panel stoi**, a kolejne podglądy (np. zmiana kategorii + odznaczenie pozycji) ustawiają się w kolejce przed zapisem.
- Odświeżanie encji po POST (`refresh_soon`) — 0,08 s, nieistotne.

W praktyce prawie wszystkie reguły to „sprzedawca równa się X” (+ kierunek) — domyślna reguła z kolejki.

## Rozwiązanie (jeden etap, wersja 0.9.1, patch — bez zmian zachowania)

**Indeks reguł w `engine._classify`**, deterministyczne przeliczenie od zera zostaje (wzorzec bez zmian):

1. W `engine.py` nowa klasa pomocnicza `_RuleIndex(rules)`:
   - aktywne reguły z pozycją wg kolejności (`all_rules` już sortuje po priority, id);
   - reguła, która ma wśród warunków (AND) `merchant equals` → do słownika `fold(wartość) → [(pozycja, reguła)]` (warunek konieczny, więc indeks nie zmienia wyniku); pozostałe (contains/starts_with/inne pola) → lista `rest`;
   - `first(facts)`: kandydaci z indeksu po `fold(facts.merchant)` (pierwszy pasujący — sprawdza pełne `conditions.matches`, bo kierunek/kwota/konto), potem `rest` tylko z pozycjami mniejszymi niż znaleziony kandydat; zwraca regułę o najniższej pozycji.
   - Normalizacja klucza tak samo jak `rules._norm("merchant", …)` (czyli `fold`) — użyć `_norm` z `rules.py`, nie pisać drugiej.
2. `_classify` używa `_RuleIndex.first` zamiast `next(r for r in active if …)`. `preview` i `recategorize` korzystają z `_classify`, więc przyspieszają oba (także przeliczenie po każdej synchronizacji/imporcie).
3. Bez zmian API `rules.py`/`Conditions.matches` (używane też w podglądzie i ekranie Reguł).

Oczekiwany efekt: `_classify` z ~5 s do ~0,1 s przy 150 regułach; zapis z kolejki ~1 s (reszta to `_load` ~0,3 s, `all_groups` ×3, `coverage`), praktycznie niezależnie od liczby reguł.

Poza zakresem (świadomie): przenoszenie obliczeń poza pętlę zdarzeń (jedno połączenie SQLite → wymagałoby blokady; po indeksie zbędne), deduplikacja trzech wywołań `review.all_groups` w assign (~0,3 s, do rozważenia tylko gdy po 0.9.1 nadal odczuwalne), znany błąd `session_watch`/`httpx.ConnectError` (osobna sprawa, czeka na osobną zgodę).

## Pliki / repo

- Repo `miczu71/ha-budget-app` (`/config/addons/ha-budget-app`), gałąź `main` (jak dotychczasowe wydania).
- `docs/PLAN_rule_index.md` — ten plan (pierwszy krok, przed kodem).
- `budget/app/src/budget/categorize/engine.py` — `_RuleIndex` + użycie w `_classify`.
- `budget/app/tests/test_categorize_engine.py` — testy (niżej).
- Bump wersji wg skilla `release` (config.yaml add-onu + wersja pakietu), CHANGELOG/notatki wydania, pomiar przed/po w sekcji „Wynik” tego pliku (`BENCHMARK.md` to przegląd aplikacji, nie wydajność).
- `docs/ROADMAP.md` — krótka notka „poza roadmapą: 0.9.1 wydajność reguł”.

## Testy (TDD)

1. Test równoważności: na syntetycznym zbiorze (mock dataset / fixture) mieszanka reguł — equals/contains/starts_with na różnych polach, warunek kierunku/kwoty/konta, wyłączone reguły, `rename`, dwie reguły equals na tego samego sprzedawcę z różnym kierunkiem, reguła contains wyżej niż equals i odwrotnie — wynik `_classify` z indeksem == wynik naiwnej pętli (referencja w teście).
2. Test priorytetu: reguła `contains` wyżej na liście wygrywa z `equals` niżej i odwrotnie.
3. Istniejące testy silnika, kolejki i reguł przechodzą bez zmian.
4. Pomiar: skrypt w scratchpadzie (jak diagnoza: kopia lokalnej księgi dev (poza repo), 60/150 syntetycznych reguł) — czasy preview/assign przed/po.
5. Hook pre-commit (skaner danych prywatnych) musi przejść — w testach tylko syntetyczne nazwy.

## Wydanie i weryfikacja na żywo

- Skill `release`: bump, testy, opublikowane wydanie GH (nie draft), aktualizacja przez Supervisor, sprawdzenie `/info`.
- Na żywo przez Ingress (Playwright, jak przy wcześniejszych weryfikacjach): zmierzyć czas `POST /review/preview` (nie zapisuje nic) przed aktualizacją i po; zrzut ekranu + konsola bez błędów. Zapisu reguły nie robię za usera — user sam sprawdza, czy zapis jest szybki.
- Checkpoint: user przegląda kolejkę i ocenia.

## Wynik (0.9.1)

Pomiar na kopii księgi dev (~2,9k transakcji, syntetyczne reguły „sprzedawca równa się”), ten sam
host co add-on; host współdzielony z HA, więc czasy wahają się o kilkadziesiąt procent.

| liczba reguł | podgląd przed → po | zapis z kolejki przed → po |
|---|---|---|
| 60  | ~2,3 s → ~0,5 s | ~5,3 s → ~0,6 s |
| 150 | ~5,6 s → ~0,85 s | ~10,8 s → ~1,5 s |

Na żywo przed wydaniem (0.9.0, ~130 reguł, przez Ingress): sam podgląd reguły w kolejce ~9,3–10,2 s
(3 próby) — zapis liczy to samo i jeszcze przelicza całą księgę.

Test równoważności (`test_rule_index_same_as_linear_scan`) porównuje indeks z dawną pętlą na
mieszance reguł w obu kolejnościach; celowo zepsuty warunek pozycji w indeksie test łapie.
