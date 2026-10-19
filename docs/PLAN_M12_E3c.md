# Budżet: domknięcie M18 + M12 E3c (pytania z dwóch źródeł stanu)

## Context
Na produkcji jest 0.55.1 (M31 zamknięty). Dwie rzeczy wiszą: checkpoint M18 (prognoza roczna 0.53.0:
pomiar ±10%, ocena tabeli miesięcy, pytanie do czatu o rok) i kandydat M12 E3c: czat odpowiada „nie umiem”
na pytania łączące dwa źródła stanu. Decyzja usera (2026-10-19): **E3c = do 2 źródeł stanu w jednym
pytaniu** (bez mieszania z transakcjami, bez dowolnego N).

Podsumowanie wywiadu:
- Kto korzysta: domownicy w zakładce „Zapytaj”.
- Automatycznie: model zwraca w planie drugie źródło, add-on liczy oba, jedno zdanie odpowiedzi + dwie tabele.
- Za zgodą: nic nowego (bez migracji, bez nowych encji); wydanie 0.56.0 po review bez pytania.
- Sukces: 3 pytania złożone na żywo trafiają w oba źródła, liczby zgodne z ekranami co do grosza;
  pytanie z jednego źródła działa jak dotąd; nadal 2 wywołania LLM na pytanie.

Repo: `/config/addons/ha-budget-app` (gałąź `main`), kod `budget/app/src/budget/ask/`.

## Etap 0 — checkpoint M18 (odczyty na żywo, bez zmian kodu)
1. playwright-ha → panel przez Ingress: Status → karta „Prognoza roczna — pomiar” (odchylenie vs ±10%),
   `/year` tabela miesięcy vs nadchodzące serie i data wypłaty z „Do wypłaty”/„Cykliczne”.
2. Jedno pytanie w czacie o rok (np. „ile zostanie na koniec roku?”) → porównanie z `sensor.budget_year_end`.
3. Wynik do `docs/PLAN_M18.md` § Checkpoint i ROADMAP (M18). Pomiar poza ±10% albo rozjazd tabeli =
   stop i pytanie do usera (zgodnie z PLAN_M18); ocenę tabeli i tak potwierdza user.

## Etap 1 — M12 E3c (TDD, jeden commit + docs)
Pierwszy krok: ten plan → `docs/PLAN_M12_E3c.md`, wiersz M12 w ROADMAP.

Zmiany:
- `ask/query.py` `SCHEMA`: nowe pole `source2` (enum `""` + `sources.NAMES`), dopisane do `required`
  (schemat strict). `query.parse` go ignoruje.
- `ask/engine.py`:
  - `plan_prompt`: linijka o `source2` („drugie źródło stanu, gdy pytanie łączy dwa ekrany, np. ile do
    wypłaty i ile w skarbonkach → payday + savings; inaczej puste”) + wskazówka, że Karta ma i licznik
    płatności, i kwotę do spłaty (przypadek z E3b).
  - `Answer.source_result` → `source_results: list[SourceResult]` (pusta = transakcje).
  - `_run`: `source2` brane tylko, gdy `source` ≠ transactions i `source2` ≠ `source`; `_run_source`
    liczy 1–2 źródła (`sources.run` bez zmian), błąd któregokolwiek = „Nie udało się odczytać źródła”.
  - Wszystkie wyniki z `note` → tekst = notatki, bez drugiego wywołania. Inaczej payload
    `{"results": [r.for_llm(), …]}` (z `note`, gdy jedno źródło nie ma danych) do `_answer`.
  - Kolizja etykiet (`[Seria i]` w `recurring` i `year`): drugi wynik dostaje etykiety z przyrostkiem
    (`[Seria 1b]`) przed `for_llm`/`labels` — mała funkcja w engine, `restore` bez zmian.
  - `answer_prompt`: zdanie, że wynik może mieć `results` z dwóch źródeł — odpowiedz na obie części.
  - `_log`: `how` = filtry wszystkich wyników.
- `web/templates/_ask_turn.html`: gałąź źródeł pętlą po `a.source_results` (tabela faktów + link
  ekranu na każde źródło, jedno „Jak policzono”). Sprawdzić inne użycia `source_result` (`grep -rn`).
- Testy: `tests/test_ask_engine.py` (dwa źródła → 2 wywołania LLM, oba wyniki; kolizja etykiet
  odtwarzana poprawnie; jedno źródło z note; oba note → 1 wywołanie; transactions + source2 → source2
  pominięte; source2 == source → jedno), `tests/test_ask_query.py` (schemat), `tests/test_web_ask.py`
  (render dwóch sekcji).

Weryfikacja lokalna: `uv run pytest`, `ruff`, `mypy` w `budget/app`; panel dev (devserve na kopii
księgi w scratchpadzie, atrapa routera) 390/1280 px: dwie tabele, 0 błędów konsoli, ≥ 44 px.
Potem `simplify`, commit (polski opis, Co-Authored-By).

## Wydanie 0.56.0
`code-review` → skill `release` (bump, CHANGELOG, published release, aktualizacja z backupem add-onu).
Na żywo (Ingress): stopka v0.56.0; pytania: „ile do wypłaty i ile w skarbonkach”, „ile płatności kartą
i ile do spłaty”, „jakie mam serie i ile zostanie na koniec roku” (kolizja etykiet) + jedno pytanie
z jednego źródła (regresja). Liczby zestawione z ekranami. Potem ROADMAP, `PLAN_M12_E3c.md` § Wynik,
notatka `project_budget_app`.

## Rollback
Bez migracji i bez nowych encji: `git revert` commitu E3c, albo przywrócenie backupu add-onu z
aktualizacji do 0.56.0 (Supervisor → Kopie zapasowe → „Budżet Domowy 0.55.1”).

## Wynik (2026-10-19)
- **0.56.0 wydane i zainstalowane** (v0.56.0, 896e4f5; backup add-onu przy aktualizacji; `update.budzet_domowy_update` = 0.56.0).
  954 testy, mypy czysty; ruff: jedyna uwaga `tests/test_web.py:98` sprzed zmiany.
- Zakres jak w planie: `source2` w schemacie planu, `merge_results` (litera przy kolidujących etykietach), `source_results`
  w `Answer`, szablon z tabelą i linkiem na źródło. Po `code-review`: nota przy źródle bez danych, unikalne linki,
  odporny sufiks etykiety. Pominięte świadomie: jeden wspólny `month` dla obu źródeł, wspólna lista „Jak policzono”.
- Dev (kopia księgi, atrapa routera): 2 tabele, 2 linki, 390/1280 px bez przepełnienia, cele ≥ 44 px, 0 błędów konsoli.
- Na żywo (Ingress, prawdziwy model): stopka v0.56.0; Karta + Do wypłaty, Cykliczne + Rok (kolizja `[Seria n]` — brak
  nieprzepisanych etykiet), Skarbonki + Do wypłaty: wszystkie trafiły w oba źródła; „Ile zostało do wypłaty?” = 1 tabela.
  Liczby z tabel zgodne z ekranami; „koniec roku” = `sensor.budget_year_end` co do grosza.
- Uwaga z pomiaru: pierwszy skrypt czytał pierwszą sekcję odpowiedzi zamiast kolejnych (błąd pomiaru, nie produktu).
