Karta „Do wypłaty”: werdykt, pasek składowych, wykres salda dzień po dniu i lista zdarzeń.

`fc-verdict` (klasy `ok` / `warn` / `bad`) odpowiada, czy starczy do wypłaty. `svg.fc-line`: linia salda (`fc-path`), strefa poniżej zera w `neg` przy kryciu 0,08, kreska bufora w `warn`, znaczniki zdarzeń (wpływy `pos`, 3 największe wydatki `neg`; nazwa i kwota w `<title>`), etykieta „najniżej dd.mm”, oś X „dziś” i „wypłata dd.mm”. Pod wykresem `ul.rows.fc-list`: chronologiczna lista, wiersz najniższego punktu na `surface-2`.

- Stopka `fc-foot` ma przełącznik zadłużenia karty (`label.check.switch`).
- Konsument dostarcza dni, bufor i zdarzenia (`forecast_line`).
