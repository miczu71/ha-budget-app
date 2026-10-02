# Plan M4a — Kategoryzacja v1: silnik reguł + ekran „Wydatki”

Zakres: [`ROADMAP.md`](ROADMAP.md#m4a--kategoryzacja-v1-silnik-reguł--ekran-wydatki).
Plan zaakceptowany 2026-10-02. **Start implementacji po checkpoincie M3** (doba obserwacji
synchronizacji) i jawnym „go”.

## Kontekst

M3 daje add-on z synchronizacją 3×/dobę, panelem i encjami sald. Księga jest bez duplikatów, ale
żadna transakcja nie ma kategorii — nie da się odpowiedzieć „gdzie idą pieniądze”.

Decyzje (wywiad 2026-10-02):
1. **Cel pierwszy: „gdzie idą pieniądze”** — wydatki miesiąca w kategoriach.
2. **Widok w panelu add-onu.** Wszystkie wizualizacje w panelu, bez dashboardów w HA (poprawka
   do całej roadmapy).
3. **Kategorie dwupoziomowe:** ~13 głównych, ~45 podkategorii, każda z grupą Flex pod M5.
4. **Lukę po słowniku zamyka pełny silnik reguł** (nie tylko grupowe przypisywanie).
5. **Podział M4:** M4a (ten plan) — kategorie, normalizacja, silnik reguł ze słownikiem, edytor
   reguł z podglądem, ekran „Wydatki”; M4b — kolejka „do przejrzenia” w panelu.

## Projekt

### Jeden silnik, deterministyczny

Kategoria transakcji = pierwsze pasujące źródło:

1. `manual` — ręczna zmiana pojedynczej transakcji (nigdy nie nadpisywana).
2. `refund` — zwrot (`refund_of` z L3) dziedziczy końcową kategorię zakupu.
3. `rule` — reguły użytkownika wg priorytetu; wygrywa pierwsza pasująca.
4. `dictionary` — wbudowany słownik polskich sieci (tylko do odczytu, wersjonowany).
5. `kind` — domyślne kategorie typów (`cash` → Gotówka, `fee` → Opłaty bankowe, `loan` → Kredyt).
6. Brak dopasowania → nieskategoryzowana.

Przelewy wewnętrzne (`transfer_group`, w tym spłaty karty) nie dostają kategorii; „Wydatki”
wykluczają je z sum.

**`recategorize(conn)` przelicza od zera wszystkie transakcje bez `manual`** — wzorzec
`ledger.rebuild_links`. Wywołanie po każdej synchronizacji i imporcie CSV (za `rebuild_links`)
oraz po zapisie reguły.

**Odstępstwo od ROADMAP:** bez osobnego przycisku „zastosuj do historii”. Bezpiecznikiem jest
podgląd przed zapisem reguły: ile transakcji zmieni kategorię, ile ręcznych zostanie pominiętych.

**Pamięć poprawek = reguły.** Po ręcznej zmianie kategorii panel proponuje „Zawsze dla
«Sprzedawca»” → reguła `merchant equals X`. Bez osobnej tabeli pamięci.

### Normalizacja sprzedawcy

- `txn.merchant` wyliczane przy `recategorize`: BLIK i przelewy — `counterparty_name`; karta —
  opis przez `normalize.merchant_tokens` / `merchant_ident` (te same co L3, `ledger._merchant_text`).
- Słownik nadaje nazwę marki (`ZABKA Z1234 UL…` → „Żabka”); reguła może nadać własną (`rename`).

### Słownik sieci

- `categorize/merchants_pl.toml` (stdlib `tomllib`) z polem `version`; wpis: wzorce (słowa /
  prefiksy po `fold`), nazwa marki, slug podkategorii. Dłuższy wzorzec wygrywa
  („ORLEN PACZKA” przed „ORLEN”).
- **Wyłącznie sieci ogólnopolskie i marki.** Lokalne firmy → reguły użytkownika w bazie.
  Pre-commit skan pilnuje tego automatycznie; diff słownika przeglądany przed commitem.
- Test: każdy slug ze słownika istnieje w taksonomii, brak zdublowanych wzorców.

### Taksonomia (seed w migracji)

Przychody · Jedzenie (Spożywcze, Restauracje i kawiarnie, Dostawy) · Dom (Media i energia,
Internet i telefon, Wyposażenie i remont, Ogród) · Transport (Paliwo, Komunikacja, Parking i opłaty
drogowe, Auto: serwis i ubezpieczenie) · Zdrowie i uroda · Dzieci · Zakupy (Ubrania, Elektronika,
Zakupy online, Inne) · Rozrywka i hobby (Subskrypcje, Kultura, Sport) · Podróże · Finanse (Kredyt,
Opłaty bankowe, Ubezpieczenia, Podatki i urzędy) · Rodzina i prezenty · Gotówka · Oszczędności ·
Wyłączone / jednorazowe.

Każda podkategoria ma `flex_group` (`income`, `fixed`, `flexible`, `non_monthly`, `savings`,
`excluded`) pod M5; w M4a wpływa tylko na układ ekranu. Wyłączenie z budżetu = kategoria z grupy
`excluded` (nie `budget_flag`). W panelu: dodanie i zmiana nazwy podkategorii; pełne zarządzanie
(przenoszenie, usuwanie, grupy) w M5.

### Reguły

- **Warunki (AND):** `merchant` / `description` / `counterparty_name` / `counterparty_account`
  z operatorem `contains` / `equals` / `starts_with` (po `fold`); `account`; `kind`; kierunek
  (wydatek/wpływ); kwota min/max (wartość bezwzględna).
- **Akcje:** kategoria (wymagana), opcjonalnie `rename` sprzedawcy.
- `priority` (kolejność na liście, przesuwana w panelu), `enabled`, liczba trafień.
- Walidacja: co najmniej jeden warunek tekstowy albo kontrahent/konto — żadnej reguły „wszystko”.

### Ekran „Wydatki” (nowy)

- Miesiąc kalendarzowy (←/→); data transakcji = `tx_date`, a bez niej `booking_date`.
- Podsumowanie: wpływy, wydatki, oszczędności, bilans, pokrycie kategoriami (% transakcji / % kwoty).
- Kategorie główne malejąco po kwocie: kwota, udział (pasek), zmiana vs poprzedni miesiąc;
  rozwinięcie (htmx) → podkategorie; kliknięcie → „Transakcje” z filtrem kategorii i miesiąca.
- Zwroty odejmują się w swojej kategorii (kwota netto).
- „Nieskategoryzowane: X zł (n)” → przefiltrowana lista.
- Konta nie-PLN poza sumami, z dopiskiem (przeliczenie NBP → M9).

### Zmiany w istniejących ekranach

- **Transakcje:** kolumna kategorii ze źródłem (ręczna / reguła / słownik / typ / zwrot); filtr
  kategorii i „nieskategoryzowane”; zmiana kategorii inline (htmx) z propozycją reguły.
- **Reguły (nowy):** lista z liczbą trafień; edytor z **podglądem na żywo** (ile pasuje, suma,
  10 przykładów, ile zmieni kategorię, ile ręcznych pominie); włącz/wyłącz, kolejność, usuń;
  zakładka „Słownik” tylko do odczytu z wyszukiwarką i trafieniami.

### Trwałość przy przelinkowaniu

`ledger._drop_csv_txn` przenosi ręczny `kind` i `budget_flag` na następcę z API — tak samo
przeniesie `category_id` z `category_source = 'manual'`. Inaczej ręczne kategorie z historii CSV
ginęłyby przy wejściu transakcji w okno API.

## Pliki (`budget/app/src/budget/`)

| Plik | Zmiana |
|---|---|
| `storage/migrations/003_categories.sql` | `category` (id, parent_id, slug UNIQUE, name, flex_group, sort, is_seed), `rule` (id, priority, enabled, conditions JSON, actions JSON, hits, created_at, updated_at), `txn` + `category_id`, `category_source`, `rule_id`, `merchant`; seed taksonomii |
| `categorize/__init__.py`, `taxonomy.py` | Drzewo kategorii, dodanie i zmiana nazwy podkategorii |
| `categorize/merchants.py` + `merchants_pl.toml` | Ładowanie i walidacja słownika, dopasowanie, nazwa marki, `merchant_name(txn)` |
| `categorize/rules.py` | Model reguły (dataclass), walidacja, `matches(rule, txn)`, CRUD, kolejność |
| `categorize/engine.py` | `recategorize(conn)`, `preview(conn, rule)` → dataclass |
| `spending.py` | Agregacja miesiąca → dataclass (wzorzec `report.py`) |
| `ledger.py` | `_drop_csv_txn` przenosi ręczną kategorię |
| `sync_service.py`, `service.py` | `recategorize` po `rebuild_links` |
| `web/app.py` → `web/routes_*.py` | Wydzielenie routerów; nowe `routes_spending.py`, `routes_rules.py`; transakcje z kategoriami |
| `web/templates/` | `spending.html`, `rules.html`, `rule_form.html`, partiale htmx; `transactions.html` |
| `cli.py` | `categorize-report --db …`: pokrycie % transakcji / % kwoty, top nieskategoryzowanych (tylko lokalnie) |
| `budget/config.yaml`, `CHANGELOG.md`, `DOCS.md`, `README.md` | 0.2.0; kategorie, reguły, słownik |

Do ponownego użycia: `normalize.fold` / `merchant_tokens` / `merchant_ident`,
`ledger.transaction()`, wzorzec `ledger.rebuild_links`, wzorzec dataclass z `report.py`,
middleware Ingress i cache z M3, `fmt_money`.

## Kolejność (commit na krok, TDD, CI zielone, pre-commit skan)

0. Ten plan + ROADMAP (M4 → M4a/M4b, wizualizacje w panelu).
1. Migracja 003 + taksonomia, testy (seed, drzewo, dodanie i zmiana nazwy).
2. Słownik + `merchants.py`; testy na syntetycznych opisach (karta, BLIK, opis z eksportu
   karty z przecinkami) i spójność slugów. Lokalnie `categorize-report` na prawdziwej księdze:
   cel ≥ 67% transakcji / ≥ 53% kwoty.
3. `rules.py` + `engine.py`: kolejność źródeł, zwroty, przelewy bez kategorii, `manual`
   nietykalne, podgląd, przeniesienie przy `_drop_csv_txn`.
4. `spending.py`: zwroty netto, wykluczenia, nie-PLN, granice miesiąca, zmiana m/m.
5. Panel: wydzielenie routerów (bez zmiany zachowania), „Wydatki”, „Reguły”, kategorie
   w „Transakcjach”; testy klientem ASGI.
6. Lokalnie na syntetycznej bazie: Playwright desktop i 390×844, 0 błędów konsoli.
7. Wydanie 0.2.0 (skill `release`), aktualizacja przez Supervisor; migracja 003 i `recategorize`
   przy starcie.
8. Na żywo: Playwright przez Ingress, `categorize-report` (liczby lokalnie), sesja reguł
   z użytkownikiem (~1 h: top sprzedawcy i odbiorcy przelewów) → checkpoint.

## Weryfikacja / akceptacja M4a

- CI zielone: ruff, mypy strict, pytest, docker build.
- Bez reguł: pokrycie **≥ 67% transakcji / ≥ 53% kwoty** (wydatki bez przelewów wewnętrznych).
- Po sesji reguł: **≥ 85% transakcji i ≥ 85% kwoty**.
- Suma kategorii + nieskategoryzowane = wydatki miesiąca z księgi (bez przelewów wewnętrznych)
  na 3 miesiącach.
- Ręczna kategoria przetrwa synchronizację, ponowny import CSV i przelinkowanie CSV → API.
- Podgląd reguły zgodny z wynikiem po zapisie.
- Panel przez Ingress na telefonie: plakietka 0.2.0, „Wydatki” / „Reguły” / „Transakcje”,
  Playwright z 0 błędów konsoli.
- Synchronizacja z M3 bez regresji (sloty, licznik zapytań).

## Ryzyka

- **Słownik przemyci lokalne firmy do publicznego repo** → zasada „tylko sieci ogólnopolskie”,
  pre-commit skan, przegląd diffu słownika.
- **Przelewy do osób niosą dużą część kwot** → KPI 85% kwoty wymaga sesji reguł użytkownika.
- **Pełne przeliczanie zmienia kategorie historyczne po edycji reguły** → podgląd zmian przed
  zapisem, `manual` nietykalne.
- **Rozmiar etapu** → commity per krok; kolejka przeglądu celowo w M4b.
