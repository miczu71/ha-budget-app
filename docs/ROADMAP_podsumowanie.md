# Roadmapa: Podsumowanie — nadpłata karty, prognoza zwijana, wykres wydatków z drill-down

Cel: czytelniejsze Podsumowanie (mniej przewijania) i wykres „Gdzie poszły pieniądze”, który schodzi w głąb
(kategoria → podkategoria → transakcje) bez opuszczania strony.

Decyzje: prognoza zawsze startuje zwinięta (bez pamięci stanu), „Tygodnie okresu” zwinięte osobno; tytuł wykresu
z miesiącem w miejscowniku („w październiku”); przełącznik „od ostatniej wypłaty” tylko w bieżącym miesiącu,
domyślnie widok miesięczny; poziom 3 = pojedyncze transakcje (top 6 + „pozostałe”).

| Etap | Zakres | Wydanie |
|---|---|---|
| E1 ✅ | `card.debt_from`: nadpłata karty (ITBD = 0, ITAV > limit) jako ujemne zadłużenie w uzgodnieniu i prognozie | 0.68.1 (na żywo 2026-10-30) |
| E2 ✅ | `_forecast.html` jako `<details>`: nagłówek + wynik widoczne, reszta po rozwinięciu | 0.69.0 (po E4; commit 3273922) |
| E3 ✅ | tytuł z miesiącem, przełącznik „od ostatniej wypłaty” (fragment htmx) | 0.69.0 (po E4; commit bea6a93) |
| E4 ✅ | drill-down donuta, okruszki, „wstecz”, link do transakcji z filtrem widoku | 0.69.0 (commit b41eac1) |

Po wdrożeniu E1: na ekranie Status ustawić nową bazę uzgodnienia karty (stara baza zawierała autoryzację,
która w API pojawiła się dzień później).

Rollback: E1 — instalacja poprzedniej wersji z backupu add-onu albo revert; E2–E4 — revert commitu etapu
(UI bez migracji).

## Wynik E1 (2026-10-30)
- Wydane 0.68.1 (commit 63ade29, tag v0.68.1), 1325 testów, ruff i mypy czyste, skan prywatności i pubguard czyste.
- Na żywo: uzgodnienie karty OK po ustawieniu nowej bazy, `forecast_card_debt` = −100,00, „na dzień wypłaty” +100 zł.
- Świadomie bez zmian: majątek netto (test utrwala „nadpłata karty nie jest aktywem”) i `card.due_status`
  (do spłaty nie spada poniżej zera).
- Długi nieblokujące: limit karty z `kv` musi być aktualny (nieaktualny daje fałszywą nadpłatę); brak testu
  publishera dla ujemnego `card_debt`; ITAV czytane po tym samym `fetched_at` co ITBD.

## Wynik E2 (2026-10-30)
- Commit 3273922, bez wydania (0.69.0 po E4). 1327 testów, ruff i mypy czyste, skan prywatności czysty.
- `_forecast.html`: `<details class="fc-fold">`, summary = h2 + `.fc-result#fc-sum`, treść w `#fc-body`; „Tygodnie okresu” w `<details class="fc-weeks-fold">`. Zawsze zwinięta.
- Przełącznik karty: `hx-target/hx-select="#fc-body"` + `hx-select-oob="#fc-sum"` (details nie jest podmieniany, więc rozwinięcie przeżywa).
- Link `href="#fc"` z hero rozwija prognozę (listener w base.html).
- Do sprawdzenia wizualnie na żywo przy wydaniu (390 px, konsola, przełącznik karty przy rozwiniętej prognozie).

## Wynik E3 (2026-10-30)
- Commit bea6a93, bez wydania. 1329 testów, ruff i mypy czyste, skan prywatności czysty.
- Karta wydatków wydzielona do `_spending.html`; GET `/home/spending?month=&since_payday=1` zwraca fragment (htmx, `hx-select="#spending-card"`), bez JS działa link `/?month=&since_payday=1`.
- `spending.build(..., since=)`: okno [since, dziś], porównanie z tyloma samymi dniami przed `since` („vs N dni wcześniej”). `month_locative()` w spending.py.
- Początek okresu = `fc.period_start` (też auto-wykryta wypłata); fragment buduje prognozę sam (`payday_start`), błąd → brak przełącznika. Przełącznik tylko w bieżącym miesiącu; styl `.tabs`.
- Do sprawdzenia wizualnie na żywo przy wydaniu: przełącznik na 390 px, tytuł, konsola.

## Wynik E4 (2026-10-30)
- Commit b41eac1, plan `docs/PLAN_podsumowanie_E4.md`. 1341 testów, ruff i mypy czyste.
- Fragment `/home/spending?month=&since_payday=&cat=&sub=` (też `/?…`): poz. 1 kategorie, poz. 2 podkategorie, poz. 3 transakcje (`spending.purchases`, top 6 + „Pozostałe”). `charts.drill_slices`, `Slice.drill`.
- Zmieniona asercja `test_donut_slices_legend_and_links`: wycinek kategorii linkuje do `/?cat=` (drill), nie `/transactions`.
- `_id`: nieprawidłowe `cat`/`sub` (też „²”, 5000 cyfr) → poziom 1 (zarzut verifiera, poprawione).
- Nieblokujące: na poz. 3 środek = netto kategorii, wycinki = brutto zakupów (zwroty pominięte); klucz `txn-<id>` powtarza się przy częściach podziału; strzałki „←”/„›” to Unicode.
- Do sprawdzenia na żywo: drill na 390 px, konsola, okruszki, E2/E3.
