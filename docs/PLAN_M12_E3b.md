# M12 E3b — rejestr źródeł danych dla czatu (ha-budget-app 0.46.0)

## Context
Czat „Zapytaj” (M12 E1–E3a, 0.34–0.35.1) rozumie tylko transakcje (`ask/query.py`). Decyzja 24:
zamiast dopisywać pola do języka zapytań — **rejestr źródeł**: każda funkcja panelu z własnymi danymi
dostaje źródło (nazwa, jedno zdanie opisu dla modelu, funkcja zwracająca wynik zbiorczy liczony tym
samym kodem co jej ekran). Szczegółowego planu E3b nie było (`PLAN_M12_E3.md` nie powstał) — ten plan go tworzy.

## Wywiad 2026-10-12 — ograniczenia
1. **Zakres:** wszystkie 6 źródeł w jednym wydaniu: Do wypłaty, Karta, Budżet (Flex), Cykliczne,
   Oszczędności i skarbonki, Kredyt (+ dzisiejsze `transactions`).
2. **Prywatność:** do LLM idą kwoty zbiorcze (salda, zadłużenie karty, kapitał kredytu — nowość), ale
   **nie nazwy**: osoby z karty, konta, skarbonki, kredyty, odbiorcy przelewów w seriach → etykiety
   (`[Osoba 1]`, `[K1]`, `[S1]`, `[O1]`…) podmieniane lokalnie jak dziś `Result.labels`/`restore`.
   Nazwy sprzedawców z karty/BLIK jak decyzja 12. Numerów kont/kart nigdy.
3. **Parametry:** jedno źródło na pytanie; miesiąc tam, gdzie ekran ma przełącznik (Budżet, Karta,
   Cykliczne); Do wypłaty, Oszczędności, Kredyt = stan na dziś. Bez łączenia źródeł.
4. **Automatycznie:** wybór źródła i odpowiedź; czat dalej tylko czyta. Nadal 2 wywołania LLM na pytanie.
5. **Sukces:** 12 prawdziwych pytań (po 2 na źródło) — ≥ 80% liczb zgodnych z ekranem źródła;
   pytania spoza źródeł → „nie umiem”, nie zmyślona liczba; pytania o transakcje działają jak dotąd.

## Projekt
- **`ask/sources.py` (nowy):** `Source(name, label, description, monthly, screen, build)`;
  `build(conn, snap, month, today) -> SourceResult`. `SourceResult`: lista faktów
  (`label`, `value` — kwota/liczba/data/tekst, `llm_label`), `filters` („jak policzono”), `link` do ekranu,
  `labels` (etykieta → nazwa), `for_llm()` (tylko po redakcji). Wspólny pomocnik etykiet dla redakcji.
  Źródła wołają istniejące funkcje ekranów, bez nowej logiki liczenia:
  - `payday` → `forecast.build` (jak `routes_home`): data wypłaty, wolne środki dziś, dno i jego data,
    werdykt, limit dzienny, zadłużenie karty odjęte, tygodnie (M21 E4);
  - `card` → `card.month_status(conn, month)` + `card.due_status(conn, today)`: płatności per osoba vs 5,
    kwota do spłaty i termin, limit;
  - `budget` → `flex.build(snap, month, today)`: pula, wydane, zostało, na dzień, stałe/elastyczne;
  - `recurring` → `schedule.for_month(snap, month, today)`: pozycje z kwotą, terminem, statusem;
  - `savings` → `savings.overview` / `monthly_rates` + `piggy.statuses`: salda, odsetki, stopa oszczędności,
    stan skarbonek;
  - `loan` → `loan.summary(lo, loan.schedule(lo), today)` dla każdego kredytu: kapitał, rata, stopa,
    koniec, odsetki do końca, najbliższa zmiana WIBOR.
- **`ask/query.py`:** w `SCHEMA` nowe pola `source` (enum: `transactions` + nazwy z rejestru) i `month`
  (RRRR-MM, puste = bieżący); oba w `required` (bez unii — Gemini). `parse` dla `transactions` bez zmian.
- **`ask/engine.py`:** `plan_prompt` dostaje listę źródeł z rejestru (nazwa + zdanie opisu + czy ma miesiąc)
  i przestaje wymieniać „salda, prognoza” jako `unsupported`; `_run` rozgałęzia: `transactions` → dzisiejszy
  `query.execute`, inne → `sources.run`; `answer_prompt` opisuje oba kształty wyniku. `Answer` dostaje
  `source_result`; `_log` zapisuje `how` z obu. Kontekst rozmowy (E2) niesie `source`/`month`.
- **Panel:** `_ask_turn.html` — gałąź źródła: zdanie, tabela faktów (prawdziwe nazwy), „Jak policzono”,
  link „Otwórz ekran …” zamiast „Pokaż transakcje”. 5 przykładowych pytań w `ask.html` rozszerzone o
  źródła. Bez nowych statyk (jeśli zmienię CSS → `?v=` jak zwykle). Skill `impeccable` przy zmianie UI.
- Bez migracji schematu; cofnięcie = poprzednia wersja / backup add-onu.

## Etapy (commity; jedno wydanie na koniec)
0. Ten plan → `docs/PLAN_M12_E3b.md`, wiersz M12 w `docs/ROADMAP.md` („E3b w toku”), commit.
1. Rejestr + schemat/prompt + gałąź w silniku + szablon + źródło **Do wypłaty** (dowód fundamentu).
2. Źródła **Karta** i **Budżet** (z miesiącem).
3. Źródła **Cykliczne**, **Oszczędności i skarbonki**, **Kredyt**.
4. `simplify`, wydanie **0.46.0** skillem `release` (backup, published release, aktualizacja przez
   Supervisor, stopka v0.46.0), checkpoint na żywo.

Testy (TDD, każdy etap): `tests/test_ask_sources.py` — każde źródło: wartości = wartości z funkcji ekranu
na danych syntetycznych, `for_llm()` bez nazw osób/kont/skarbonek/kredytów i bez numerów; parsowanie
`source`/`month` (nieznane źródło, miesiąc dla źródła bez miesiąca → ignorowany); `test_ask_engine.py` —
zamockowany LLM wybiera źródło → odpowiedź z podmienionymi etykietami; `transactions` bez regresji;
`test_web_ask.py` — render gałęzi źródła i linku do ekranu.

## Repo / gałąź / komendy
`/config/addons/ha-budget-app`, `main`; `uv run pytest` (venv jak w notatce `budget_app_dev_environment`),
hook pre-commit (skaner prywatności — fixtures z „Osoba 1”, „Konto A”), `git -C … push`; poza 02:45–03:15.

## Ryzyka
- Model źle wybiera źródło (np. „ile zostało” → budget vs payday) → opisy źródeł w prompcie + przykłady;
  mierzymy na checkpoincie.
- Nowe kwoty (salda/kapitał) wychodzą do zewnętrznych modeli — zgoda z wywiadu (pkt 2).
- `forecast.build` zwraca `None` bez salda/wypłaty → źródło zwraca „brak danych” zamiast `unsupported` od modelu.
- Długość promptu rośnie (6 opisów) — kilka zdań, w limicie.

## Weryfikacja
- Lokalnie: pełne `pytest` zielone; devserver + Playwright (360/390 px): odpowiedź źródła, tabela,
  link do ekranu, 0 błędów konsoli, cele dotyku ≥ 44 px.
- Na żywo (playwright-ha, Ingress `/app/a9413a25_budget`): stopka v0.46.0, `/ask` `no-store`; 12 pytań
  (po 2 na źródło) porównane z ekranami → odsetek trafień w `PLAN_M12_E3b.md` § Wynik (bez kwot w repo);
  karta „Czat — ostatnie pytania” na Status pokazuje źródło.
- Po wszystkim: ROADMAP (M12 E3b), notatka pamięci `project_budget_app`.
