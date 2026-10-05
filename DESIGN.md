# Design — Budżet Domowy (M13)

Kierunek: [Copilot Money z Refero](https://styles.refero.design/style/91b110da-902b-4d09-8bf0-26bd1f25f8b2)
przełożony na UI narzędzia. Tylko ciemny motyw (decyzja 2026-10-05). Plan: `docs/PLAN_M13.md`.

## Kolory (tokeny `:root` w `static/app.css`)
| Token | Wartość | Rola |
|---|---|---|
| `--canvas` | `#000814` | tło strony |
| `--surface-1` | `#010d1e` | karty, panele |
| `--surface-2` | `#001533` | zagnieżdżone kontenery |
| `--surface-3` | `#00215e` | wyróżnione bloki, aktywne |
| `--border` | `#11263b` | hairline |
| `--text` | `#ffffff` | treść, nagłówki |
| `--text-2` | `#ccced0` | tekst drugorzędny |
| `--text-3` | `#999ca1` | podpisy, metadane |
| `--accent` | `#1c6cff` | jedyna wypełniona akcja |

Znaczenie: wpływ `#00cc4b`; wydatek neutralny (biały); przekroczenie tempa `#ff4433`.

Kolory kategorii głównych (stałe, przypisane w kodzie): coral `#ff4433`, lime `#00cc4b`, tangerine `#ff8833`,
hot pink `#ff33aa`, violet `#9019e6`, sunflower `#ffcc02`, sky `#00acfe`, ember `#ea687c`, olive `#94ae43`,
slate `#5c6f8a`. Tylko na ciemnym tle.

## Typografia
- Nagłówki i duże liczby: Space Grotesk (500–600), `-0.02em` od 32 px wzwyż.
- UI i treść: Inter, grubość 400 (odstępstwo od Matter Thin 100: czytelność na telefonie), liczby
  `font-variant-numeric: tabular-nums`.
- Bez nadtytułów (eyebrow) nad nagłówkami: nagłówek niesie się sam.
- Fonty lokalnie (`static/fonts/`, woff2, OFL), `font-display: swap`.

## Kształt i głębia
Karty r24 (20 na telefonie), przyciski r16, chipy r20, obrazy r8. Głębia z wewnętrznych cieni (jasny inset
w prawym górnym, ciemny w lewym dolnym rogu), bez drop shadow. Karta = ton `--surface-1` + hairline `--border`
(sam ton jest za słaby na tle `#000814`). Kontrolki formularzy mają jaśniejszą ramkę `--control-border`
(`#4a6585`, ok. 3:1) i tło `--canvas`.
Siatka 4 px, padding karty 20 px (16 px na telefonie), odstęp elementów 16 px.

## Zasady
- Jeden wypełniony kolor akcji (`--accent`); żadnego drugiego koloru przycisków.
- Kolory kategorii nigdy na jasnym tle.
- Wykresy: SVG po stronie serwera, bez biblioteki JS.
- Bez „pływających etykiet” z hero Copilota (dekoracja strony marketingowej).
- Nawigacja: Podsumowanie · Budżet · Wydatki · Cykliczne · Transakcje, dzwonek, menu ⚙ (`<details>`, bez JS):
  Do przejrzenia · Reguły · Konta · Import CSV · Bank · Status (ostatni). Na telefonie pasek przewija się
  poziomo (zanik krawędzi jako wskazówka). Wersja add-onu w stopce strony.
- Kwota wydatku w wierszu jest neutralna (biała), kolor mają wpływy (lime) i przekroczenia (coral).
- Ikony i grafiki zawsze SVG: Lucide (ISC, https://github.com/lucide-icons/lucide) przez iconify.design,
  osadzane inline albo jako maska CSS (`--i-chevron`, `--i-check`). Animacje wyłącznie jako Lottie, lokalnie.

## Wykresy (M13 E2)
- SVG po stronie serwera (`web/charts.py` liczy geometrię, `_charts.html` składa SVG), bez JS i bez bibliotek; ikony zmiany
  jako Lucide.
- **Kolor kategorii jest stały** (`id % 8`), kolizja w jednym wykresie przesuwa mniejszy wycinek na następny wolny kolor.
  Kod nie zna palety: klasy `c1…c8`, `other`, `unc` mapują tokeny `--chart-1…8`, `--chart-other`, `--chart-unc` motywu.
- **Kolory znaczeniowe są zarezerwowane** (nie służą kategoriom): wpływ/dobrze `--pos`, przekroczenie/źle `--neg`,
  ostrzeżenie `--warn` (w wykresie kołowym to „Bez kategorii”).
- Copilot: tangerine, hot pink, fiolet, sky, ember, olive + pochodne teal i jasny indygo; „Inne” = slate.
  Monarch (pochodna paleta ciepłych ziem, bo styl nie ma kolorów kategorii): ember, ink, terakota, przygaszony niebieski,
  szałwia, oliwka, śliwka, ciepły brąz; „Inne” = kamień. Słupki: wpływy `--pos`, wydatki `--accent` (Copilot) albo Ink (Monarch).
- Wycinki i słupki ≥ 3:1 względem karty, tekst ≥ 4,5:1; wycinek i legenda są linkami; legenda ma wiersze ≥ 44 px.
- Jedna animacja: wjazd wycinków (dasharray), wyłączona przy `prefers-reduced-motion`.
- Porównania zmian liczone rzetelnie: bieżący (niepełny) miesiąc vs ten sam zakres dni poprzedniego, podpis mówi to wprost.

