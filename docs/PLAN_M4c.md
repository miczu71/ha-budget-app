# Plan M4c — kolejka miesiąca + podpowiedzi kategorii z AI

Zakres: [`ROADMAP.md`](ROADMAP.md#m4c--kolejka-miesiąca--podpowiedzi-ai-poza-planem-2026-10-02).
Plan zaakceptowany 2026-10-02, poza kolejnością roadmapy (checkpointy M3/M4a/M4b nadal otwarte).
Każdy etap osobno: plan → „go” → wykonanie → checkpoint.

## Kontekst

1. Na „Wydatkach” wiersz „Nieskategoryzowane” prowadzi do całej kolejki `/review`, a przegląd
   ma dotyczyć tylko oglądanego miesiąca.
2. Podpowiedź kategorii z LLM, znająca kategorie użytkownika, zatwierdzana jednym dotknięciem —
   przez lokalny router OpenAI-compatible (freellmapi). To przenosi część LLM z M7 i zmienia
   decyzję 5 (zakres danych: decyzja 12 w ROADMAP).

## Decyzje (wywiad 2026-10-02)

| Pytanie | Decyzja |
|---|---|
| Zapis w widoku miesiąca | Lista tylko z miesiąca, zapis jak dotąd: domyślnie reguła dla sprzedawcy (obejmie też inne miesiące); „tylko te” = kategoria ręczna wyłącznie dla pozycji z miesiąca |
| Dane do LLM | Karta/BLIK: sprzedawca + opis po wycięciu IBAN/numerów kart/e-maili/telefonów; przelewy: tylko tytuł, bez nazwy odbiorcy; kwota jako przedział |
| Kiedy liczyć | W tle po synchronizacji (cache w bazie) + przycisk „podpowiedz teraz” |
| Gdzie zatwierdzać | Kolejka „Do przejrzenia” (✓ = reguła dla grupy) i lista Transakcji (✓ = kategoria ręczna jednej transakcji) |

## Etap 1 — 0.3.1: kolejka dla miesiąca

- `review.all_groups(conn, month=None)`: stali sprzedawcy zagraniczni (≥ 3 miesiące) liczeni na
  całej historii, filtr miesiąca (data transakcji, jak na „Wydatkach”) stosowany na pozycjach
  dopiero potem; puste grupy odpadają. `queue(…, month)`, `group(conn, key, month)`.
- `parse_month` / `month_label` przeniesione do `budget.spending`, wspólne dla obu ekranów.
- Trasy `/review*` przyjmują `month`; zaznaczone pozycje muszą należeć do grupy w tym miesiącu.
- Ekran: nagłówek z miesiącem, nawigacja « », link „wszystkie miesiące”; podgląd reguły mówi,
  ile transakcji z innych miesięcy obejmie.
- „Wydatki”: „Nieskategoryzowane” → `/review?month=…`, „bez kategorii” we Wpływach →
  `/review?direction=in&month=…`.

## Etap 2 — 0.4.0: silnik podpowiedzi (bez zatwierdzania w UI)

- Opcje: `ai_base_url` (puste = wyłączone), `ai_api_key`, `ai_model`, `ai_daily_calls`.
- `budget/suggest/`: `redact` (wejście per sprzedawca + kierunek wg decyzji 12), `client`
  (httpx, `json_schema` tylko na nazwanym modelu, `max_tokens ≥ 1500`, ponowienia 429/502),
  `job` (po udanej synchronizacji, w limicie dziennym; błąd AI nie psuje synchronizacji).
- Prompt: podkategorie użytkownika + przykłady z istniejących reguł; paczki ≤ 40 grup →
  `{i, category_id, confidence}`; walidacja id i zgodności kierunku z grupą Flex.
- Migracja `004`: tabela `suggestion` (sprzedawca, kierunek, kategoria, pewność, model, status).
- CLI `suggest-eval`: trafność na już skategoryzowanych sprzedawcach (wynik tylko lokalnie) —
  punkt decyzji przed etapem 3.
- Karta „AI” na ekranie Status.

## Etap 3 — 0.5.0: do 3 podpowiedzi per sprzedawca (zmienione 2026-10-02)

Pierwszy pomiar na żywo (0.4.0): trafność pojedynczej odpowiedzi na kategoriach użytkownika
~25% podkategorii / ~33% kategorii głównej (≥ 0,9 pewności: ~40%) — za mało na zatwierdzanie
jednym dotknięciem. Decyzja użytkownika: **podpowiedzi per sprzedawca, decyzja zawsze jego**,
**do 3 kandydatów**, dotknięcie = wybór w formularzu (zapis jak dotąd), kolejka **i** Transakcje.

- Model zwraca do 3 kandydatów (`category_id`, pewność) — walidacja każdego jak dotąd;
  migracja `005`: kolumna `candidates` (JSON), stare oczekujące podpowiedzi usunięte (liczone
  od nowa).
- Kolejka: pod wierszem grupy sprzedawcy chipy „AI: […] […] […]”; dotknięcie renderuje grupę
  rozwiniętą z wybraną kategorią i podglądem reguły. Grupy krajów: kandydaci per sprzedawca
  jako tekst (kategoria wybierana dla całej grupy). „Podpowiedz teraz” na `/review`.
- Transakcje: chipy w formularzu kategorii (ustawiają wybór, zapis jak dotąd).
- Zapis kategorii dla sprzedawcy oznacza podpowiedź jako przyjętą (wybrano kandydata) albo
  odrzuconą (inna kategoria); statystyka na Status.
- Pomiar: dodatkowo trafność „w top 3”.

## Weryfikacja

`pytest`, `ruff`, `mypy`; panel dev na kopii księgi (bez harmonogramu i zapytań do banku);
Playwright (desktop + telefon, konsola bez błędów); po wydaniu aktualizacja przez Supervisor
i sprawdzenie przez Ingress.

## Wynik

- **Etap 1 — 0.3.1 wydane i zainstalowane 2026-10-02** (`2dd12cb`, release `v0.3.1`, CI zielone,
  310 testów). Na żywo przez Ingress: „Nieskategoryzowane” we wrześniu → `/review?month=2026-09`,
  wszystkie pozycje z września, liczba wydatków w kolejce = liczba w wierszu „Nieskategoryzowane”
  (nagłówek liczy oba kierunki), konsola bez błędów. Na kopii księgi: podgląd reguły podaje liczbę
  pozycji z innych miesięcy. Checkpoint etapu 1 zamknięty („go” na etap 2).
- **Etap 2 — 0.4.0 wydane 2026-10-02** (`ceda366`, `af0fc61`, release `v0.4.0`, CI zielone,
  331 testów). Odstępstwo od planu: pomiar trafności to przycisk **Zmierz trafność** na Status
  (w add-onie, z kluczem z opcji), nie CLI — klucz routera nie jest kopiowany do środowiska
  deweloperskiego. Redakcja obsługuje odmianę nazwiska w tytule (rdzeń słowa). Czeka: klucz
  w opcjach add-onu (użytkownik), pierwszy pomiar trafności → decyzja o progu chipa w etapie 3.
  Zainstalowane i sprawdzone przez Ingress: v0.4.0, karta „Podpowiedzi AI” (wyłączona bez opcji).
  Pierwszy pomiar na żywo (80 sprzedawców z kategoriami użytkownika): trafność pojedynczej
  odpowiedzi za niska na zatwierdzanie jednym dotknięciem → etap 3 zmieniony (wyżej).
- **Etap 3 — 0.5.0 wydane i zainstalowane 2026-10-02** (`2a58b09`, `d8b6d91`, release `v0.5.0`,
  CI zielone, 341 testów). Na żywo: pomiar z kolumną „wśród 3” — właściwa podkategoria wśród
  propozycji u ok. połowy sprzedawców (pierwsza propozycja ok. ćwierć); „Podpowiedz teraz” —
  3 wywołania, 120 sprzedawców z propozycjami w ~30 s; chipy w kolejce na telefonie, konsola
  bez błędów. Model często podaje 1–2 propozycje zamiast 3. Czeka checkpoint etapu 3
  (używanie przez kilka dni, liczniki przyjętych/odrzuconych na Status).
