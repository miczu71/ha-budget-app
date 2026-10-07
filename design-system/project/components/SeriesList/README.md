Płatności cykliczne: podsumowanie miesiąca (`dl.kv`) i lista serii (`ul.series-list`).

`li.series-item` ma nagłówek `series-head` (link `cat-name.tap` i kwota `cat-amount`, wpływ w `pos`) oraz podpis: termin, plakietka stanu (`badge error` dla spóźnionych, zwykła dla oczekiwanych) i kierunek. Przycisk „Wykryj teraz” (`series-detect`) uruchamia wykrywanie; działa też samo po synchronizacji.

- Konsument dostarcza serie, kwoty i terminy.
