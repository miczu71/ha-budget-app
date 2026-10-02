# Plan M4b — kolejka „Do przejrzenia”

Zakres: [`ROADMAP.md`](ROADMAP.md#m4b--kolejka-do-przejrzenia). Plan zaakceptowany 2026-10-02.
Checkpoint M3 i sesja reguł M4a przesunięte za M4b — sesja reguł odbędzie się już na kolejce.

## Kontekst

M4a daje kategorie, silnik reguł i ekran „Wydatki”, ale nieskategoryzowane transakcje widać
tylko jako filtr na liście Transakcji, pojedynczo. Sesja reguł (cel 85% transakcji / 85% kwoty)
potrzebuje widoku „co zostało”, pogrupowanego tak, żeby jedna decyzja zamykała wiele pozycji.

Decyzje (wywiad 2026-10-02):
1. **Kolejka = tylko transakcje bez kategorii** (zaksięgowane, bez przelewów wewnętrznych).
   Nowe pozycje skategoryzowane regułą lub słownikiem nie wymagają potwierdzenia — bez stanu
   „przejrzane” i bez migracji. Liczba do przejrzenia (podsumowania M6) = liczba
   nieskategoryzowanych.
2. **Akcja grupy: domyślnie reguła** „sprzedawca równa się X” + kierunek → kategoria;
   przełącznik **„tylko te transakcje”** = kategoria ręczna bez reguły (jednorazowi sprzedawcy).
3. **Grupa rozwijana z checkboxami** (domyślnie wszystkie zaznaczone); odznaczenie czegokolwiek
   wymusza „tylko te” dla zaznaczonych, reszta zostaje w kolejce.
4. **Zagranica: grupy po kraju** zamiast słowników zagranicznych. Pomiar lokalny: zagraniczne
   transakcje kartą to ~1/6 nieskategoryzowanych transakcji i kilka procent kwoty wydatków,
   głównie lokale z wyjazdów, których słownik marek i tak by nie złapał; lukę kwoty w ~4/5
   tworzą przelewy do osób (→ reguły per odbiorca). Długi ogon → M7; słowniki zagraniczne →
   backlog.

**Odstępstwo od ROADMAP:** bez „nowych od ostatniego przeglądu” (decyzja 1).

## Projekt

### Grupy

- **Sprzedawca + kierunek:** klucz (`txn.merchant`, wydatek/wpływ). Wydatek i wpływ od tej samej
  osoby to osobne grupy; reguła dostaje warunek kierunku. Pusta nazwa → „(bez nazwy)”, tylko
  „tylko te”.
- **Kraj:** transakcje kartą (i zwroty na kartę) bez kategorii z kodem kraju innym niż POL —
  grupa per kraj; nie pojawiają się w grupach sprzedawców. Akcja tylko „tylko te” (np.
  Podróże → Inne w podróży); przy sprzedawcy w rozwinięciu link „reguła…” do istniejącego
  edytora (`/rules/new?txn=<id>`), np. dla subskrypcji rozliczanej za granicą.

### Kraj transakcji (`budget/countries.py`)

- Kod z opisu karty: CSV — `MiastoCCC RRRR-MM-DD` (kod sklejony z miastem, potem data); API —
  ostatni token `CCC`.
- Walidacja statyczną listą ISO 3166-1 alfa-3 z polskimi nazwami — odrzuca szum („SRL”, „SPA”,
  „.COM” na końcu nazwy domeny).
- Bez kodu, ale waluta oryginalna inna niż PLN → grupa „Zagranica (EUR)”.
- Liczone w locie, bez kolumny w bazie.
- **Stały sprzedawca zagraniczny** (transakcje w ≥ 3 różnych miesiącach) → grupa sprzedawcy,
  nie kraju (odstępstwo z wykonania: na danych lokalnych dwie grupy „krajowe” były w ~95%
  jednym sprzedawcą co miesiąc — doładowania/subskrypcje, nie wyjazd).

### Ekran `/review`

- Zakładka „Do przejrzenia (N)” w nawigacji.
- Nagłówek: pokrycie wydatków — % transakcji / % kwoty (`spending.coverage`).
- Przełącznik kierunku (domyślnie wydatki) i sortowania (kwota | liczba); top 50 grup +
  „pokaż więcej”.
- Sekcja „Zagranica” nad grupami sprzedawców.
- Wiersz grupy: nazwa, liczba, suma, zakres dat. Rozwinięcie (htmx) → transakcje z checkboxami,
  wybór podkategorii, przełącznik „tylko te”.
- Tryb reguły: podgląd z `engine.preview` — „obejmie N, w tym M skategoryzowanych inaczej”
  (ostrzeżenie przy M > 0, bo nowa reguła trafia na górę listy).
- Zapis → grupa znika, licznik i pokrycie odświeżone.
- „Nieskategoryzowane” na ekranie Wydatki i pusta lista Reguł prowadzą do kolejki.

### Moduły

| Plik | Zmiana |
|---|---|
| `countries.py` (nowy) | `card_country(...)` + tabela ISO alfa-3 → nazwa PL |
| `review.py` (nowy) | grupy sprzedawców i krajów, transakcje grupy, `pending_count` — bez stanu |
| `web/routes_review.py` (nowy) | `GET /review`, `GET /review/group`, `POST /review/preview`, `POST /review/assign` |
| `web/app.py`, `web/common.py` | router; licznik w nawigacji |
| `templates/review.html`, `_review_group.html`, `static/app.css` | ekran (mobile-first) |

Zapis: tryb reguły → `rules.save` + `engine.recategorize` (jak ekran Reguły); „tylko te” →
`engine.set_manual` dla zaznaczonych (walidacja: należą do grupy i są bez kategorii) + jedno
`recategorize`; wszystko w `ledger.transaction`.

## Kroki (commity per krok)

0. Ten plan + ROADMAP.
1. `countries.py` + testy; sprawdzenie lokalne na księdze (tylko liczby): każda transakcja
   kartą w walucie obcej dostaje kraj albo grupę walutową; 0 polskich jako zagraniczne.
2. `review.py` + testy (dane syntetyczne).
3. Router, szablony, CSS + testy panelu.
4. Linki, licznik w nawigacji, DOCS, CHANGELOG 0.3.0, wersja.
5. Wydanie (skill `release`), aktualizacja przez Supervisor, weryfikacja na żywo.

## Akceptacja

- Testy i CI zielone; panel zweryfikowany w Playwright (390 px i desktop, 0 błędów konsoli).
- Zapis reguły z kolejki zdejmuje grupę i podnosi pokrycie; „tylko te” z odznaczeniem zostawia
  odznaczone w kolejce; grupa kraju przypisuje kategorię ręczną.
- Na żywo: v0.3.0 w plakietce, kolejka gotowa do sesji reguł.
