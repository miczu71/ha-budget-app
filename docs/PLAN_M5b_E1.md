# M5b E1 (0.14.0) — dzwonek + wykrywanie serii cyklicznych

Plan etapu E1 z [`PLAN_M5b.md`](PLAN_M5b.md) (decyzja 16). Zaakceptowany 2026-10-04; E1 jako jeden etap (bez podziału na dzwonek / serie).

## Kontekst

M5a zamknięty 04.10; M5b zaplanowany w `docs/PLAN_M5b.md` (decyzja 16, commit 9a1397a). Następny
krok wg roadmapy: plan etapu E1 do akceptacji. User zdecydował: **E1 jako jeden etap (0.14.0)**,
bez dzielenia na dzwonek / serie. Wartość etapu: jedno miejsce „co czeka na mnie” (dzwonek)
+ pierwsze propozycje płatności cyklicznych do potwierdzenia. Pula Flex bez zmian (to E4).

Repo: `miczu71/ha-budget-app`, klon `/config/addons/ha-budget-app/`, gałąź `main`.
Kod: `budget/app/src/budget/`.

## Kroki

0. **Plan do repo:** ten plik, commit (skan pre-commit), dopiero potem kod.

1. **Migracja `storage/migrations/009_series.sql`** — tabela `series` wg PLAN_M5b §Dane:
   `id, name, direction, cadence (M/Q/Y), matcher_json, expected_amount, tolerance,
   anchor_day, status (proposed/active/rejected/ended), origin (detected/manual),
   group_key` (znormalizowany sprzedawca|kierunek — detektor pomija grupy z serią w dowolnym
   statusie, więc odrzucona nie wraca), `created_at, decided_at`. `series_ack` dopiero w E3.

2. **`recurring/series.py`** — CRUD + przynależność liczona od zera: `Conditions.from_json`
   (`categorize/rules.py`) na `engine.facts(...)` (`categorize/engine.py`); przy kilku
   pasujących seriach wygrywa najbliższa `expected_amount`. Dopasowanie propozycji wykrytej:
   `merchant equals` + kierunek (bez zakresu kwoty — zmiana ceny to „inna kwota” w E3).

3. **`recurring/detect.py`** — czysta funkcja: transakcje BOOK, bez `transfer_group`, PLN,
   konta `include_in_budget`, nieobjęte istniejącą serią → grupy (sprzedawca/kontrahent,
   kierunek) → kadencja z mediany odstępów (M 26–35, Q 80–100, Y 350–380; ≥70% w oknie;
   min. M/Q 3, Y 2 z dopiskiem „mało historii”), kwota = mediana ost. 6, tolerancja
   max(10%, 5 zł) albo rozrzut historii, `anchor_day` = mediana dnia; tylko serie żywe.
   Zapis nowych jako `proposed`. Wywołanie: `Service.detect_later()` po `sync` (obok
   `suggest_later`) + przycisk „Wykryj teraz”.

4. **`inbox.py`** — `Item(kind, title, count, link, severity)`, dostawcy:
   - nieskategoryzowane bieżącego miesiąca (i poprzedniego, dopóki >0) → `/review?month=`
     (zapytanie jak `review.pending_count` z `PENDING_WHERE` + filtr daty jak „Wydatki”);
   - operacyjne: `notifications.evaluate(...)` z `warning_days=30`, `failures_to_alert=1`
     + `ledger.check_balances` (pozycje nie-OK) → `/` / `/bank`;
   - nowe serie (`status='proposed'`) → `/recurring`.

5. **Panel:**
   - `base.html`: licznik z „Do przejrzenia” → dzwonek (inline SVG) z liczbą kart, link
     `/inbox`; nowa zakładka „Cykliczne”. `Panel.render` (`web/common.py`) podaje `inbox_count`
     zamiast `pending`.
   - `web/routes_inbox.py` + `inbox.html` — karty (tytuł, liczba, opis, link).
   - `web/routes_recurring.py` + `recurring.html`, `_series_form.html`: propozycje (kadencja,
     kwota, wystąpienia, ostatnie transakcje; „Potwierdź” z edycją nazwy/kwoty/kadencji/
     warunków przez `_rule_conditions.html` + `web/rule_form.py`, „Odrzuć”), lista serii
     aktywnych/zakończonych, edycja + podgląd dopasowanych transakcji, „Zakończ”/„Przywróć”,
     „Wykryj teraz”.

6. **Encja** `sensor.budget_inbox` w `ha_publisher.build_entities` (stan = liczba kart,
   atrybut `items` = [rodzaj, tytuł, liczba]); odświeżana istniejącym `refresh`/`refresh_soon`.

7. **Testy** (pytest, `budget/app/tests/`): `test_recurring_detect.py` (M/Q/Y, zmienne kwoty,
   przerwy, odrzucone, Y z 2 wystąpieniami, serie martwe), `test_recurring_series.py`
   (przynależność, najbliższa kwota), `test_inbox.py`, `test_web_recurring.py` (każdy POST),
   encja w `test_ha.py`. Ruff/mypy jak dotąd.

8. **Wydanie 0.14.0** skillem `release` (bump, README: encja + ekrany, release notes z tabelą),
   update add-onu przez Supervisor, `ROADMAP.md` + § Wynik, memory.

## Ryzyka

- **Koszt dzwonka na każdej stronie** (wolny CPU AMD GX-415GA): `check_balances` + zapytania
  przy każdym renderze. Zmierzyć na kopii księgi; jeśli >~50 ms → pamięć podręczna wyniku
  unieważniana po POST i po synchronizacji.
- Detektor po synchronizacji = CPU w pętli asyncio (panel stoi w trakcie) — zmierzyć; cel <1 s.
- Dwie subskrypcje u jednego sprzedawcy (różne kwoty) detektor zleje w jedną grupę o
  nieregularnej kwocie — obejście: ręczna edycja warunków (zakres kwoty) / seria ręczna w E2.
- Repo publiczne: testy tylko na syntetycznych nazwach (hook pre-commit), żadnych liczb usera.
- Nawigacja ma już 9 zakładek — sprawdzić mobile (pasek przewijany) na Playwright.

## Weryfikacja

- `pytest` całość zielona.
- Panel dev (`devserve.py` w scratchpadzie, kopia `/data/home/budget_dev/prod/ledger.db`
  + `engine.recategorize`): detektor na kopii vs sonda (~9 serii wydatkowych, ~4 wpływów),
  czasy detektora i renderu z dzwonkiem; Playwright mobile — dzwonek, /inbox, Cykliczne,
  potwierdzenie/odrzucenie, 0 błędów konsoli. Kopię usunąć po weryfikacji.
- Na żywo po update: Ingress (LLAT → `/app/a9413a25_budget` → ingress_entry), `/inbox`,
  `/recurring`, `sensor.budget_inbox` przez `ha_get_device` (nie od razu `ha_get_state`).
- **Checkpoint E1:** user przegląda propozycje na żywo; E2 dopiero po „go”.

## Wynik

—
