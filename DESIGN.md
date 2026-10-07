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

### Wykres prognozy „Do wypłaty” (M8 E3b)
- Linia salda dzień po dniu, `viewBox` 360×200, na całą szerokość karty (`.fc-line`, bez limitu 520 px).
- Strefa poniżej zera: `--neg` przy krycie 0,08, od kreski zera do osi X. Kreska bufora: `--warn`.
- Znaczniki zdarzeń na saldzie z końca dnia: wpływy `--pos` (wszystkie), wydatki `--neg` (3 największe);
  nazwa i kwota w `<title>`. Reszta zdarzeń jest tylko na liście pod wykresem.
- Etykieta „najniżej dd.mm” przy dnie, kotwica start/middle/end zależnie od położenia; oś X: „dziś” i „wypłata dd.mm”.
- Lista pod wykresem (`ul.rows.fc-list`): jedna chronologiczna, „saldo” w ostatnim wierszu dnia, wiersz dna na `--surface-2`.

## System designu w Claude Design (M20)
Przeglądalne lustro tego pliku i `app.css`: https://claude.ai/artifact/GgbLCb6vkcwtvKAEQ3wwzr (prywatny artefakt typu
Design System: tokeny, fonty, ikony, README, 36 komponentów z podglądami). Służy do makiet nowych ekranów i planowania
refaktorów. **Kod jest źródłem prawdy** (`app.css`, ten plik), artefakt nie dyktuje stylu. Źródła artefaktu leżą w
`design-system/project/` (poza kontekstem builda add-onu); plan i historia etapów: `docs/PLAN_M20.md`.

**Kiedy zrobić re-sync:** zmiana `:root` w `app.css`, nowa grupa klas albo komponent, zmiana fontów lub ikon.
1. Przeczytaj aktualny indeks artefaktu (`Artifact read`, `project/design-system.json`); strona potrafi go przepisać
   (zmiana kolejności kluczy), więc nakładaj zmianę na jej wersję, nie na starą kopię.
2. Zmień pliki w `design-system/project/`: `tokens.json` wg różnic w `:root` (nazwy tokenów = nazwy zmiennych CSS bez
   `--`); `components/bundle.css` = `app.css` bez dwóch pierwszych `@font-face` i z `url("../fonts/…")` w trzecim;
   README i `preview.html` komponentu (linia 1 `<!-- @dsCard group="…" height=N -->`). Dane w podglądach neutralne
   (Sklep X, Osoba 1), markup z prawdziwych szablonów albo z dev serwera na fixture z `tests/fixtures`, nigdy z danych
   produkcyjnych.
3. Wyrenderuj każdy zmieniony podgląd na 390 i 1280 px (Playwright z `reducedMotion`, konsola bez błędów).
4. Opublikuj tylko zmienione pliki jednym wywołaniem, indeks (`lastChange`) na końcu; w `tokens.json` ustaw
   `meta.ref` (`main@<sha>`) i `synced`.
5. Zacommituj `design-system/` (hook prywatności działa jak zawsze).

Klasy z `app.css` bez podglądu (świadomie): `buffer` (kreska bufora widoczna tylko przy ustawionym buforze), `c1`, `c2`
(sloty koloru wycinka, zależne od `id % 8`), `htmx-request` (stan biblioteki).
