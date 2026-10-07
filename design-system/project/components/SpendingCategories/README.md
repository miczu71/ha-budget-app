Ekran Wydatki: kafelki podsumowania (`div.grid.summary`) i lista kategorii z paskiem udziału, zmianą i podkategoriami.

Kafelki to karty z `big` (wpływy `pos`, bilans `neg`). Lista `ul.cats`: wiersz rozwijany `<details>` z nazwą, kwotą, paskiem `span.bar > span` (szerokość = udział), podpisem `cat-meta` i zmianą `span.delta` względem poprzedniego okresu (`up` = więcej wydano i kolor `neg`, `down` = mniej i `pos`, `muted` = „nowe”). Po rozwinięciu `ul.subcats` z linkami do transakcji i `li.uncat` dla „Bez kategorii” (kolor `warn`). `span.donut-chg` to podpis zmiany pod kołem na Podsumowaniu.

- `.bar` w SVG wykresów ma osobne klasy (`b-inc`, `b-exp`); ta klasa dotyczy tylko paska HTML.
