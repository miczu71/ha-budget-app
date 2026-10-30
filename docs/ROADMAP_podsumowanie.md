# Roadmapa: Podsumowanie — nadpłata karty, prognoza zwijana, wykres wydatków z drill-down

Cel: czytelniejsze Podsumowanie (mniej przewijania) i wykres „Gdzie poszły pieniądze”, który schodzi w głąb
(kategoria → podkategoria → transakcje) bez opuszczania strony.

Decyzje: prognoza zawsze startuje zwinięta (bez pamięci stanu), „Tygodnie okresu” zwinięte osobno; tytuł wykresu
z miesiącem w miejscowniku („w październiku”); przełącznik „od ostatniej wypłaty” tylko w bieżącym miesiącu,
domyślnie widok miesięczny; poziom 3 = pojedyncze transakcje (top 6 + „pozostałe”).

| Etap | Zakres | Wydanie |
|---|---|---|
| E1 | `card.debt_from`: nadpłata karty (ITBD = 0, ITAV > limit) jako ujemne zadłużenie w uzgodnieniu i prognozie | 0.68.1 |
| E2 | `_forecast.html` jako `<details>`: nagłówek + wynik widoczne, reszta po rozwinięciu | 0.69.0 |
| E3 | tytuł z miesiącem, przełącznik „od ostatniej wypłaty” (fragment htmx) | 0.69.0 |
| E4 | drill-down donuta, okruszki, „wstecz”, link do transakcji z filtrem widoku | 0.69.0 |

Po wdrożeniu E1: na ekranie Status ustawić nową bazę uzgodnienia karty (stara baza zawierała autoryzację,
która w API pojawiła się dzień później).

Rollback: E1 — instalacja poprzedniej wersji z backupu add-onu albo revert; E2–E4 — revert commitu etapu
(UI bez migracji).
