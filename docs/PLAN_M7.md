# M7 — Kategoryzacja v2: mniej pracy z kolejką (ha-budget-app)

## Kontekst
Roadmapa zakładała dla M7 lokalny klasyfikator z KPI „≥ 92% automatycznie”, ale reguły, słownik i przeglądy
dają już ~97% pokrycia (M4a), więc ten KPI niczego nie mierzy. Wywiad 2026-10-06 (decyzja 20):
- **cel = mniej pracy z kolejką „Do przejrzenia”** (nie lepsze podpowiedzi, nie wykrywanie błędów);
- pewne przypadki **przypisywane od razu, ale oznaczone do zerknięcia** (sekcja w kolejce, ✓ hurtem,
  poprawka jednym dotknięciem);
- kolejność **pomiar → pamięć sprzedawcy → klasyfikator** (klasyfikator tylko, gdy pomiar go uzasadni).

Obserwacja z kodu: od 0.11.0 zapis w kolejce domyślnie nie tworzy reguły (`engine.set_manual`), więc
powracający sprzedawca wraca do kolejki przy każdej transakcji — pamięć sprzedawcy z ręcznych decyzji może
zdjąć dużą część pracy bez ML. Bazy produkcyjnej nie da się pobrać (add-on nie ma eksportu, lokalna kopia
sprzed kategorii), więc pomiar działa w add-onie (wzorzec „Zmierz trafność” z M4c).

## Ograniczenia
1. Korzysta: użytkownik w panelu (kolejka; Budżet i Wydatki liczą auto-kategorie od razu).
2. Automatycznie: przypisanie z pamięci sprzedawcy (E2) i ewentualnie klasyfikatora (E3) — zawsze osobne
   źródło, nigdy nie nadpisuje `manual`/`rule`/`dictionary`/`kind`.
3. Za zgodą: progi (k decyzji, próg pewności) ustalane na checkpoincie E1 z liczb; E3 tylko przy precyzji ≥ 95%.
4. Sukces: pozycji trafiających do kolejki tygodniowo o ≥ 50% mniej, precyzja auto-przypisań ≥ 95%
   (< 5% poprawianych w sekcji „przypisane automatycznie”).
5. Żadne dane nie wychodzą poza add-on (bez LLM w M7).

## Repo / gałąź
`/config/addons/ha-budget-app`, gałąź `main`. Wersje: E1 0.31.0, E2 0.32.0, E3 0.33.0 (skill `release`).

## E1 — pomiar (0.31.0), punkt decyzji
- Nowy `src/budget/categorize/learn.py`:
  - `memory(conn, k)` — dla (`txn.merchant`, kierunek): kategoria, jeśli ≥ k ręcznych decyzji i wszystkie
    zgodne (spójność chroni przed przelewami do osób z mieszanymi kategoriami);
  - `backtest(conn)` — chronologicznie po transakcjach `category_source = 'manual'` (data transakcji jako
    przybliżenie czasu decyzji — znacznika decyzji nie ma): czy pamięć z wcześniejszych decyzji by zadziałała
    (pokrycie = oszczędzona praca) i czy trafnie (precyzja), dla k = 1, 2, 3; oraz naive Bayes (n-gramy nazwy
    sprzedawcy + `kind` + przedział kwoty, czysty Python) uczony na `manual` + `rule` sprzed daty, oceniany
    tylko na sprzedawcach widzianych pierwszy raz, przy progach 0,8 / 0,9 / 0,95;
  - `queue_share(conn)` — jaka część dzisiejszej kolejki (pozycje i grupy) ma wcześniejsze ręczne decyzje.
- `web/routes_status.py` + szablon Status: karta „Kategoryzacja — pomiar” z przyciskiem „Zmierz” (POST,
  wynik w tabeli, bez zapisu do bazy).
- Przy okazji (TODO z M15): atrybut `available` w `sensor.budget_card_due` → `available_bank`
  (`ha_publisher.card_entities`) + CHANGELOG.
- Testy pytest dla `learn.py` (dane syntetyczne, nazwy neutralne); `simplify` przed commitem; wydanie,
  aktualizacja add-onu, pomiar na żywo przez Ingress, wynik w § Wynik E1.
- **Checkpoint:** liczby → decyzja: k dla pamięci, czy E3 w ogóle. Cofnięcie: release 0.30.0 (pomiar nic
  nie zapisuje).

## E2 — pamięć sprzedawcy (0.32.0) — dokładne kroki przed startem
- `categorize/engine._classify`: nowe źródło `learned` po `kind` (wypełnia tylko luki), deterministyczne
  z ręcznych decyzji w bazie (zgodne z przeliczeniem od zera w `recategorize`).
- Kolejka: zwinięta sekcja „Przypisane automatycznie (N)”: ✓ hurtem = `set_manual` z tą samą kategorią
  (umacnia pamięć), zmiana = `set_manual` z inną kategorią (spójność pęka → pamięć przestaje działać dla tego
  sprzedawcy).
- Licznik poprawek vs ✓ na Status (precyzja na żywo).

## E3 — klasyfikator dla nowych sprzedawców (warunkowo, 0.33.0)
Tylko jeśli E1 pokaże precyzję ≥ 95% przy sensownym pokryciu; źródło `model` po `learned`, ta sama sekcja
„przypisane automatycznie”. W przeciwnym razie M7 zamykamy po E2.

## Weryfikacja
- `uv run pytest` w `budget/app` (pełny zestaw) przed każdym wydaniem.
- Na żywo: wersja w panelu, „Zmierz” daje tabelę, brak błędów w konsoli i w logu add-onu; encja
  `sensor.budget_card_due` z atrybutem `available_bank`.

## Wynik E1 (0.31.0, 2026-10-06)
Wydane i zainstalowane 2026-10-06 (backup add-onu przed aktualizacją, 647 testów). Pomiar na produkcji przez
Ingress, 23 miesiące historii:

- **Kolejka dziś:** 109 pozycji w 56 grupach; **53% pozycji (20 grup) to sprzedawcy z wcześniejszą ręczną
  decyzją** — hipoteza „kolejka to w dużej części powracający sprzedawcy” potwierdzona.
- **Pamięć sprzedawcy (backtest, 312 ręcznych pozycji / 287 decyzji):**

  | min. decyzji | przypisane | trafne | kolejka dziś |
  |---|---|---|---|
  | 1 | 19% | 87% | 42 z 109 (39%) |
  | 2 | 9% | 85% | 28 (26%) |
  | 3 | 6% | 100% (19 pozycji) | 9 (8%) |

- **Naive Bayes dla nowych sprzedawców (240 pozycji):** trafność 25–30% przy każdym progu (0,8–0,99) —
  daleko od 95%. **E3 odpada** w tej postaci.

Wnioski: (1) pamięć z k = 1–2 trafia w ~85–87%, poniżej progu 95% z decyzji 20; (2) różnica między 53%
„znanych” a 39% przypisanych przy k = 1 to sprzedawcy z niespójną historią (różne kategorie); (3) backtest
zaniża pokrycie względem dzisiejszej kolejki, bo przed 0.11.0 zapis w kolejce tworzył reguły (sprzedawca
z regułą nie wraca jako ręczna decyzja). Do decyzji na checkpoincie: próg k i czy najpierw rozbić trafność
pamięci według typu transakcji (karta/BLIK vs przelewy), żeby ograniczyć pamięć do typów, gdzie trafia ≥ 95%.
