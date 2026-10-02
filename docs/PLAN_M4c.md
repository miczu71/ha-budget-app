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

## Etap 3 — 0.5.0: zatwierdzanie jednym dotknięciem

- Chip „AI: kategoria · pewność ✓ ✕” w nagłówku grupy kolejki (także w widoku miesiąca) i przy
  transakcji bez kategorii na liście Transakcji; preselekcja w formularzu grupy.
- „Podpowiedz teraz” na `/review`; statystyka przyjęte/odrzucone na Status.
- Próg pokazywania chipa z wyniku `suggest-eval`.

## Weryfikacja

`pytest`, `ruff`, `mypy`; panel dev na kopii księgi (bez harmonogramu i zapytań do banku);
Playwright (desktop + telefon, konsola bez błędów); po wydaniu aktualizacja przez Supervisor
i sprawdzenie przez Ingress.

## Wynik

(uzupełniane po każdym etapie)
