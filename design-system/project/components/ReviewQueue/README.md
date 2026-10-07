Kolejka „Do przejrzenia”: pokrycie kategoriami, zakładki widoku i grupy transakcji bez kategorii z formularzem reguły.

`section.card.rv-head` mówi, ile wydatków ma kategorię. `nav.tabs.rv-tabs` przełącza Wydatki i Wpływy, `rv-sort` zmienia sortowanie. Grupa to `li.rv-group` z `<details>` (htmx doładowuje `rv-body` po otwarciu): nagłówek ma nazwę (`cat-name`), kwotę (`cat-amount`) i podpis (`cat-meta`). W środku `form.rv-form`: kategoria, „utwórz regułę”, Zapisz i pole reguły (`rv-rulebox`) z rozwijanymi dodatkowymi warunkami (`rv-more`, `rule-fields`, `cond`).

- Cele dotyku ≥ 44 px dla zakładek, nagłówków grup i pól.
- Konsument dostarcza grupy, kwoty i opcje kategorii.
