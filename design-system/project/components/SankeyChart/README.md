Wykres przepływu pieniędzy (Sankey, M19) w sekcji „Przepływ pieniędzy” ekranu Wydatki: trzy kolumny — wpływy → grupy budżetu (stałe, elastyczne, nieregularne, oszczędności, „Bez kategorii”, „Nadwyżka”) → kategorie główne.

SVG liczy serwer (`flow.py` układa węzły i krawędzie, `web/charts.py` `sankey()` geometrię, makro `sankey_chart` w `_charts.html`), bez JS i bibliotek. Krawędź to krzywa Béziera z obrysem (`.sk-link`, `stroke-width` proporcjonalny do kwoty), węzeł to `rect.sk-node`; kolor dziedziczy `currentColor` z klas węzła: `in`, `deficit` („Z oszczędności / deficyt”, gdy wydano więcej niż wpłynęło), `surplus`, `g-fixed|g-flexible|g-non_monthly|g-savings`, `unc`, `other` i `c1…c8` (stały slot kategorii, jak w DonutChart).

- Etykieta (`.sk-label`) ma halo `paint-order: stroke` w kolorze karty; kwoty w pełnych złotych (`.sk-amount`). Za niski węzeł nie ma etykiety — kwota jest w `<title>`.
- Węzeł kategorii z `href` jest linkiem do transakcji okresu; „Inne” prowadzi do ekranu Wydatki, „Bez kategorii” do kolejki.
- Zakres przełącza `nav.tabs` (Miesiąc / Rok, parametr `flow=year`); strzałki miesięcy niosą ten parametr.
- Konsument dostarcza `Flow` i adresy. Dane w makiecie są neutralne; drugi podgląd pokazuje rok z deficytem.
