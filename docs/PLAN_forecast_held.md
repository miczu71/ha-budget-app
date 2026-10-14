# Prognoza: płatność zablokowana w banku, ale jeszcze niezaksięgowana

## Kontekst
W dniu terminu dużej płatności cyklicznej (rata kredytu) bank od rana trzyma ją jako blokadę:
saldo dostępne (ITAV) już spada o kwotę raty, saldo zaksięgowane (ITBD) jeszcze nie, a API
transakcji pokazuje tylko operacje zaksięgowane. Seria zostaje więc `EXPECTED` i
`forecast.project` odejmuje ją drugi raz od ITAV — „Zabraknie” skacze o całą kwotę raty
do czasu księgowania (kilka godzin).

Przykład (liczby umowne): ITAV 2 000, ITBD 7 300, rata 5 000 z terminem dziś,
zakupy kartą w drodze 300. Prognoza odejmuje 5 000 od 2 000, choć już zeszło.

Samo przejście na ITBD byłoby zbyt optymistyczne: pomija zakupy kartą w drodze (też nie ma
ich w księdze).

## Podejście
Kwota w drodze = `max(ITBD − ITAV, 0)` z tej samej migawki rachunku. Serie wydatkowe
z terminem ≤ dzień migawki i statusem `EXPECTED`/`LATE` są pokrywane z tej kwoty w kolejności
terminów, dopóki się mieszczą. W prognozie mają kwotę 0 i etykietę „zablokowane w banku”
(jak serie pokryte skarbonką). Po zaksięgowaniu seria jest „zapłacona” i mechanizm znika.

- `forecast.py`: `Balances.pending`; `read_balances` je wypełnia; czysta `held(...)`;
  `project(..., held=...)`; `Event.held`; `build` liczy i przekazuje.
- `_forecast.html`: etykieta „zablokowane w banku, czeka na zaksięgowanie”.
- Bez migracji i bez zmian encji.

## Ryzyka
- Duży zakup kartą w drodze + seria jeszcze niepobrana w dniu terminu → seria uznana za
  zablokowaną do czasu księgowania. Ograniczone do terminu ≤ dnia migawki.
- Uznania bywają w ITBD wcześniej niż w ITAV → `max(…, 0)`.

## Wydanie
Bez osobnego wydania — idzie razem z kolejnymi poprawkami (decyzja użytkownika 2026-10-14).
