# Design — Budżet Domowy

Wygląd: [Monarch z Refero](https://styles.refero.design/style/a9dd8050-c03a-4901-b7fa-a9cc0ca54812), jasny, jeden
pomarańczowy akcent (decyzja użytkownika 2026-10-05 po porównaniu z Copilot Money; historia w `docs/PLAN_M13_E1b.md`).
Jeden wygląd, bez przełącznika. Tokeny w `static/app.css` (`:root`).

## Kolory
| Token | Wartość | Rola |
|---|---|---|
| `--canvas` | `#efecea` | tło strony i paska (Linen) |
| `--surface-1` | `#fff` | karty, panele, pola formularzy (Paper) |
| `--surface-2` | `#f7f5f3` | zagnieżdżone elementy, najechanie |
| `--surface-3` | `#e7e3df` | zaznaczenie |
| `--border` | `#dcd9d6` | hairline (Stone) |
| `--control-border` | `#8c8782` | ramka pól, ok. 3:1 |
| `--text` / `--text-2` / `--text-3` | `#22201d` / `#4a4743` / `#6b6763` | treść (Ink) / drugorzędna / podpisy (≥ 4,5:1 także na Linen) |
| `--accent` | `#ff692d` | jedyny wypełniony kolor akcji (Ember) |
| `--on-accent` | `#22201d` | tekst na akcencie (biały dawał 2,9:1) |
| `--link` | `#22201d` | linki w Ink z podkreśleniem (pomarańcz nie jest kolorem tekstu) |
| `--pos` / `--neg` / `--warn` | `#15702d` / `#c2331f` / `#8a5a00` | wpływ i „dobrze” / przekroczenie i „źle” / ostrzeżenie |

Kwota wydatku w wierszu jest neutralna (Ink); kolor mają wpływy i przekroczenia.

## Typografia
- Nagłówki i duże liczby: Source Serif 4 (przycięty do łaciny, alias „Serif Display”), waga 350–400, tracking −0,02 do
  −0,035 em (nie niżej niż −0,04 em). Separator tysięcy w kwotach (U+202F) bierzemy z Inter przez `unicode-range`.
- UI i treść: Inter, waga 350 (małe teksty i etykiety 400), `letter-spacing: −0.01em`, liczby `tabular-nums`.
- Bez nadtytułów (eyebrow) nad nagłówkami. Fonty lokalnie (`static/fonts/`, woff2, OFL), `font-display: swap`.

## Kształt i głębia
Karty r12 (20 na telefonie), pola r8, przyciski i chipy w kształcie pigułki. Płasko: hairline `--border` i lekki
dwuwarstwowy cień (`--elev`). Siatka 4 px, padding karty 20 px (16 na telefonie), odstęp elementów 16 px.

## Zasady
- Jeden wypełniony kolor akcji (`--accent`); żadnego drugiego koloru przycisków.
- Ikony i grafiki zawsze SVG: Lucide (ISC, https://github.com/lucide-icons/lucide) przez iconify.design, osadzane inline
  albo jako maska CSS (`--i-chevron`, `--i-check`). Animacje wyłącznie jako Lottie, lokalnie.
- Nawigacja: Podsumowanie · Budżet · Wydatki · Cykliczne · Transakcje, dzwonek, menu ⚙ (`<details>`, bez JS): Do przejrzenia ·
  Reguły · Konta · Import CSV · Bank · Status (ostatni). Aktywna zakładka ma pomarańczowe podkreślenie. Na telefonie pasek
  przewija się poziomo (zanik krawędzi jako wskazówka). Wersja add-onu w stopce strony.
- Nowe elementy SVG dostają unikalne nazwy klas (stare `.bar` nadpisywało wysokość `rect`).
- Cele dotyku ≥ 44 px (`--tap`): pola i przyciski mają to globalnie; link samodzielny dostaje klasę `tap`; link w zdaniu
  ma obszar dotyku przez `::after` (lista selektorów w `app.css`), żeby wiersz tekstu nie rósł.

## Wykresy (M13 E2)
- SVG po stronie serwera (`web/charts.py` liczy geometrię, `_charts.html` składa SVG), bez JS i bez bibliotek.
- **Kolor kategorii jest stały** (`id % 8`), kolizja w jednym wykresie przesuwa mniejszy wycinek na następny wolny kolor.
  Kod nie zna palety: klasy `c1…c8`, `other`, `unc` mapują tokeny `--chart-1…8`, `--chart-other`, `--chart-unc`.
- Paleta (ciepłe ziemie, pochodna, bo Monarch nie ma kolorów kategorii): ember, ink, terakota, przygaszony niebieski,
  szałwia, oliwka, śliwka, ciepły brąz; „Inne” = kamień; „Bez kategorii” = `--warn`.
- Kolory znaczeniowe (`--pos`, `--neg`, `--warn`) nie służą kategoriom. Słupki: wpływy `--pos`, wydatki Ink.
- Wycinki i słupki ≥ 3:1 względem karty, tekst ≥ 4,5:1; wycinek i legenda są linkami; wiersze legendy ≥ 44 px.
- Jedna animacja: wjazd wycinków (dasharray), wyłączona przy `prefers-reduced-motion`.
- Porównania liczone rzetelnie: bieżący (niepełny) miesiąc vs ten sam zakres dni poprzedniego, podpis mówi to wprost.
