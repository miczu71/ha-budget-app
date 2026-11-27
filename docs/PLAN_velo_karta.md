# Płatności kartą Velobank liczone jako przelewy

Przyczyna: `kinds.from_api` nie znał formatu „Operacja kartą … na kwotę …”, więc wiersz z kontem
kontrahenta dostawał `transfer_out` i licznik transakcji bezgotówkowych promocji go pomijał.

Poprawka: rozpoznanie tego prefiksu jako `card` / `card_refund`. Istniejące wiersze
(`kind_source = 'heuristic'`) poprawiają się przy synchronizacji, o ile są w oknie pobierania.

Cofnięcie: `git revert` i wydanie kolejnej wersji.
