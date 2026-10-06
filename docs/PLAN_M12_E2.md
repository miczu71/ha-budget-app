# M12 E2 — rozmowa z kontekstem (0.35.0)

Cel: pytania doprecyzowujące bez powtarzania całego pytania („a w 2025?”, „bez paliwa”, „rozbij na
miesiące”). Plan zaakceptowany 2026-10-06; całość M12: [`PLAN_M12.md`](PLAN_M12.md).

## Decyzje
- **Kontekst w stronie, nie w bazie** (uproszczenie względem `PLAN_M12.md` § E2): ukryte pole formularza
  z ostatnimi turami (pytanie + surowy plan od LLM, najwyżej 4), podmieniane przez htmx po każdej
  odpowiedzi. Odświeżenie strony albo „Nowa rozmowa” zaczyna od nowa. Bez migracji; historia = lista
  „Ostatnie pytania” (log z E1).
- Do LLM dochodzą wcześniejsze pytania i plany — bez wyników; żadnych nowych danych z księgi.
- Kontekst z formularza traktowany jak dane od klienta: zły JSON / zły kształt → pusty kontekst.

## Kroki
1. `ask/engine.py`: `ask(..., context=[{q, plan}])`; prompt planu z sekcją „Wcześniejsze pytania w tej
   rozmowie” i instrukcją „zmień tylko to, o co prosi bieżące pytanie”; `Answer.context` = kontekst po
   turze (przycięty do 4); log z numerem tury.
2. `ask/query.py`: pole `exclude_categories` (główne albo podkategorie) w schemacie, `parse`, `execute`
   i „Jak policzono” („Bez kategorii: …”).
3. Panel: odpowiedzi dopisywane pod poprzednimi (`hx-swap="beforeend"`), ukryte pole kontekstu
   podmieniane `hx-swap-oob`, pole pytania czyszczone po wysłaniu, „Nowa rozmowa”; przykłady i
   „Ostatnie pytania” zaczynają nową rozmowę.
4. Testy: prompt z poprzednim planem, przycięcie do 4 tur, `exclude_categories`, kontekst w odpowiedzi
   panelu, odporność na zły kontekst.
5. `simplify`, panel dev na kopii księgi (390 px + desktop), skill `release` 0.35.0, na żywo rozmowa
   2–3 tury na `qwen/qwen3.8-27b`.

## Cofnięcie
Instalacja 0.34.1 (bez zmian schematu).

## Wynik (2026-10-06)
- 0.35.0 wydane i zainstalowane (release v0.35.0, backup add-onu przy aktualizacji); 685 testów, CI zielone.
- Na żywo (Ingress, `qwen/qwen3.8-27b`): „Ile wydaliśmy na jedzenie w tym roku?” → „a w 2025?” → „bez
  restauracji” — model poprawnie zmienił tylko okres, potem dodał wykluczenie podkategorii; 2–3 s na turę,
  kontekst 3 tury, 0 błędów konsoli, brak przewijania w poziomie.
- Simplify: stan rozmowy w jednym partialu z flagą `oob` (`_ask_state.html`), zwięzłe plany w kontekście
  (bez pustych pól), jedno miejsce przycinania, przykłady zaczynają nową rozmowę własnymi atrybutami
  htmx (bez `HX-Reswap` w trasie), dopytania poza „Ostatnimi rozmowami”. Pominięte: kontekst po stronie
  serwera z logu (zmiana projektu; dziś plan z formularza jest walidowany i ograniczony rozmiarem).
- **Czeka checkpoint E2** (dopytania użytkownika), potem decyzja: E3 albo zamknięcie M12.
