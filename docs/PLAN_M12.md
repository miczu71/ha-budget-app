# M12 — Czat AI z danymi (ha-budget-app)

## Kontekst
Panel odpowiada na stałe pytania (Wydatki, Budżet, Do wypłaty, Karta). M12 ma odpowiadać na pytania
**ad hoc**, dla których nie ma ekranu: „ile kosztuje nas samochód rocznie?”, „który miesiąc był
najdroższy i dlaczego?”, „ile wydaliśmy na restauracje w 2026 vs 2025?”. Wywiad 2026-10-06 (decyzja 23).

Add-on ma już klienta zgodnego z OpenAI (`suggest/client.py`, freellmapi, odpowiedź wg schematu JSON,
ponowienia 429/502/503) i redakcję danych (`suggest/redact.py`) — M12 z nich korzysta.

## Ograniczenia
1. Korzysta: użytkownik w panelu (nowa zakładka „Zapytaj”); bez encji i powiadomień w HA.
2. Automatycznie: tłumaczenie pytania na zapytanie (LLM), wykonanie zapytania (lokalnie), zdanie
   odpowiedzi (LLM). Nic nie zmienia księgi — czat tylko czyta.
3. Do LLM wychodzą: pytanie, lista kategorii (nazwy + grupy), opis języka zapytań, poprzednie plany
   zapytań rozmowy (E2) oraz **wyniki zbiorcze** (sumy, liczby, średnie). Nie wychodzą pojedyncze
   transakcje. Nazwy sprzedawców z płatności kartą/BLIK mogą wyjść (jak decyzja 12); odbiorcy przelewów
   → etykiety `[O1]`, `[O2]`… (zmiana w trakcie E1: „Odbiorca N” model odmienia, nawias przetrwa),
   podmieniane na prawdziwe nazwy lokalnie — w tabeli i w zdaniu odpowiedzi.
4. Liczby muszą zgadzać się z panelem: zapytanie liczy ten sam zbiór transakcji co „Wydatki”
   (`spending._rows`: zaksięgowane, bez przelewów własnych, konta w budżecie, PLN; kwoty ze znakiem netto,
   więc zwroty pomniejszają kategorię).
5. Sukces: z 10–15 prawdziwych pytań użytkownika ≥ 80% dostaje poprawną odpowiedź (sprawdzoną ręcznie
   z panelem); pytania spoza języka dostają „nie umiem”, nie zmyśloną liczbę.

## Repo / gałąź
`/config/addons/ha-budget-app`, gałąź `main`. Wersje: E1 0.34.0, E2 0.35.0, E3 (warunkowo) kolejna wolna.
Wydanie skillem `release`; przed commitem kodu skill `simplify`.

## Etapy
| Etap | Wartość | Wersja |
|---|---|---|
| E1 | Pojedyncze pytanie → odpowiedź z liczbami, „jak policzono” i linkiem do transakcji | 0.34.0 |
| E2 | Rozmowa z kontekstem („a w 2025?”, „bez paliwa”) + historia rozmów | 0.35.0 |
| E3 | (warunkowo) Rozszerzenia języka zapytań — tylko te, o które padły pytania („nie umiem” w logu) | — |

## E1 — pojedyncze pytanie (0.34.0)

### Język zapytań (`src/budget/ask/query.py`)
Plan zapytania = JSON wg schematu (bez unii typów — Gemini, zob. `suggest/client.py`):
- `periods`: 1–2 okresy `{from: RRRR-MM, to: RRRR-MM}` (miesiące kalendarzowe, decyzja 4; dwa = porównanie);
- `categories`: id podkategorii lub kategorii głównych (główna = wszystkie jej podkategorie), puste = wszystkie;
- `groups`: grupy Flex (`fixed`, `flexible`, `irregular`, `income`, `savings`, …), puste = wszystkie;
- `merchant_contains`: tekst (dopasowanie `fold` jak wyszukiwanie na żywo, M4e), pusty = bez filtra;
- `direction`: `out` / `in` / `any`;
- `group_by`: `none` / `month` / `category` / `main_category` / `merchant`;
- `metric`: `sum` / `count` / `avg_per_month`;
- `limit`: top N wierszy (domyślnie 10, max 50) przy `group_by` innym niż `none`/`month`;
- `unsupported`: tekst — LLM ustawia go zamiast planu, gdy pytanie nie mieści się w języku.

`execute(conn, plan, today) -> Result` (czysty Python, bez LLM): walidacja (id kategorii istnieją,
okres ≤ 60 mies.), wiersze z `spending._rows` + filtry, agregacja; `Result` = wiersze (etykieta, kwota,
liczba), suma, liczba transakcji, pominięte w innej walucie, opis filtrów „jak policzono”, parametry linku
do `/transactions`. Wyrażenie kwot jak w „Wydatkach” (wydatki dodatnie w tabeli).

### Prywatność (`src/budget/ask/redact.py`)
- `group_by=merchant`: sprzedawca, którego transakcje w wyniku to wyłącznie karta/BLIK → nazwa;
  w przeciwnym razie „Odbiorca N” (mapa etykieta → nazwa zostaje w pamięci żądania).
- Do LLM w kroku 3 idzie tylko `Result` po redakcji (wiersze, sumy, opis filtrów).
- Test: wynik z przelewem do osoby nie zawiera jej nazwy w treści wysłanej do LLM.

### LLM (`src/budget/ask/engine.py`)
- Krok 1 `plan(question, categories)`: prompt z opisem języka i listą kategorii (id, nazwa, główna,
  grupa) + dzisiejsza data → plan lub `unsupported`.
- Krok 2 `execute` lokalnie.
- Krok 3 `answer(question, result)`: 1–3 zdania po polsku, wyłącznie z liczb w wyniku (instrukcja: nie
  liczyć niczego samemu, nie dopowiadać przyczyn spoza danych).
- Limit: nowa opcja `chat_daily_calls` (domyślnie 40, `int(0,500)`) w `config.yaml` + `Settings`;
  licznik w `kv` jak `suggest.engine.usage`, pod osobnym kluczem; po wyczerpaniu komunikat w panelu.
- Bez `ai_base_url` zakładka pokazuje „skonfiguruj router AI w opcjach”.
- Log lokalny w `kv` (`ask_log`, ostatnie 100 pytań): czas, pytanie, surowy plan od LLM, `unsupported`,
  błąd — do E3 i checkpointu; bez wyników kwotowych. **Zmiana w trakcie E1:** zamiast migracji 013 —
  `db.migrate` starszej wersji odmawia startu na nowszej bazie, a `kv` nie zmienia schematu.

### Panel
- `web/routes_ask.py` + `templates/ask.html`: zakładka „Zapytaj” w pasku (po „Karta”), pole pytania
  (htmx POST, wskaźnik ładowania — odpowiedź trwa kilka–kilkanaście s), pod odpowiedzią: zdanie, tabela
  (prawdziwe nazwy), „jak policzono”, link „pokaż transakcje”; 5 przykładowych pytań do dotknięcia.
- `/transactions` dostaje filtry potrzebne do linku, jeśli ich brak (zakres miesięcy, kategoria główna)
  — sprawdzę przed implementacją, co już jest.
- Cele dotyku ≥ 44 px, 360 px bez przewijania w poziomie (zasady M13), weryfikacja Playwright.

### Testy
- `tests/test_ask_query.py`: każde pole planu; suma dla miesiąca = suma kategorii z `spending.build`
  na tych samych danych syntetycznych; zwroty netto; przelewy własne pominięte; walidacja błędnych id.
- `tests/test_ask_redact.py`: etykiety odbiorców, brak nazw osób w treści do LLM.
- `tests/test_ask_engine.py`: LLM zamockowany (transport httpx) — plan → wynik → odpowiedź,
  `unsupported`, limit dzienny, błąd routera.
- `tests/test_web_ask.py`: zakładka, brak konfiguracji, odpowiedź htmx.

### Weryfikacja i checkpoint E1
Na żywo przez Ingress: użytkownik podaje 10–15 pytań, ja zestawiam odpowiedź czatu z liczbą z panelu
(tabela wyników bez kwot w repo — tylko odsetek trafień w § Wynik). Decyzje na checkpoincie: czy idziemy
w E2, co z log „nie umiem” trafia do E3.

### Cofnięcie
Bez migracji schematu — wystarczy zainstalować poprzednią wersję albo przywrócić backup add-onu
robiony przy aktualizacji; klucze `ask_*` w `kv` starsza wersja ignoruje.

## Wynik E1 (2026-10-06)
- 0.34.0 wydane i zainstalowane (release v0.34.0, backup add-onu przy aktualizacji); 678 testów, CI zielone.
- Na żywo (Ingress, 390 px): pytanie „Ile wydaliśmy na jedzenie w tym roku?” → plan: kategoria główna
  Jedzenie, styczeń–październik 2026; odpowiedź po ~13 s; suma i liczba transakcji **zgodne co do grosza**
  z sumą 10 miesięcy z ekranu „Wydatki”. 0 błędów konsoli, brak przewijania w poziomie, cele dotyku ≥ 44 px.
- Zmiany w trakcie: log w `kv` zamiast migracji 013; etykiety `[O1]` zamiast „Odbiorca N”; licznik wywołań
  wspólny z podpowiedziami (`suggest.metered_call`, osobny klucz) — nieudane wywołanie też liczy się do limitu.
- Do sprawdzenia na checkpoincie: podział „po sprzedawcy” zależy od pola `merchant` — na starej kopii
  księgi raty kredytu miały w nim cały opis (każda rata osobnym wierszem); sprawdzić na produkcji.
- Simplify pominął świadomie: jedno zapytanie dla dwóch okresów, liczenie poza pętlą zdarzeń
  (`to_thread`), wspólne fikstury AI w testach, wspólny formatter kategorii do promptów.
- ~~Czeka checkpoint~~ 10–15 prawdziwych pytań użytkownika, cel ≥ 80% poprawnych.
- 0.34.1 (2026-10-06): opisowe komunikaty błędów AI. Przyczyna pierwszego błędu 429: `gemini-3.1-flash-lite`
  ma w routerze jedną trasę z limitem 20 zapytań na dobę, dzieloną z innymi klientami. Szybki test 8 kandydatów
  (te same prompty, kategorie domyślne): `qwen/qwen3.8-27b` 5/5 (~0,4 s), `@cf/openai/gpt-oss-120b` 5/5,
  `openai/gpt-oss-120b` 4/5, reszta 0–1/5 → `ai_model` = `qwen/qwen3.8-27b` (ustawione przez użytkownika).
- ✅ Checkpoint E1 zamknięty przez użytkownika 2026-10-06 („działa ok”).

## E2 — rozmowa z kontekstem (0.35.0)
Zakres do potwierdzenia na checkpoincie E1: rozmowa = lista tur (pytanie, plan, wynik zredagowany) w
bazie; krok 1 dostaje poprzednie pytania i plany (bez wyników), krok 3 — bieżący wynik; „nowa rozmowa”;
historia ostatnich rozmów w zakładce. Szczegóły w `PLAN_M12_E2.md` po checkpoincie E1.

## E3 — źródła danych dla czatu (decyzja 24)
Uzgodnione 2026-10-06: zamiast dopisywać pojedyncze pola do języka zapytań — **rejestr źródeł**.
Każda funkcja panelu z własnymi danymi (Do wypłaty, Karta, Budżet/pula Flex, Cykliczne, później
M9–M11) dostaje źródło: nazwa, jedno zdanie opisu dla modelu, funkcja zwracająca wynik zbiorczy
liczony tym samym kodem co jej ekran. Plan wskazuje źródło (`transactions` = dzisiejszy język).
- E3a (0.35.1): karta „Czat — ostatnie pytania” na Status (log `ask_log`: pytanie, tura, plan
  w skrócie / „nie umiem” / błąd; bez kwot) — podstawa do wyboru kolejności źródeł.
- E3b+: rejestr + pierwsze źródła, kolejność po przejrzeniu logu (`PLAN_M12_E3.md`).
