Wykres kołowy wydatków według kategorii z legendą (`div.donut-wrap`): top 6 kategorii, „Inne” i „Bez kategorii”.

SVG liczy serwer (`web/charts.py`, `_charts.html`), bez JS i bibliotek. Kolor kategorii jest stały (`id % 8`), klasy `c1…c8`, `other`, `unc` mapują tokeny `chart-1…8`, `chart-other`, `chart-unc`. Na środku suma wydatków (`donut-total`) i podpis (`donut-sub`). Wycinek i wiersz legendy są linkami, wiersze legendy mają ≥ 44 px. Jedyna animacja to wjazd wycinków (dasharray), wyłączona przy `prefers-reduced-motion`.

- Kolory znaczeniowe (`pos`, `neg`, `warn`) nie służą kategoriom; „Bez kategorii” używa `warn`.
- Konsument dostarcza wycinki (`donut_slices`), adresy i tekst środka. Dane w makiecie są neutralne.
