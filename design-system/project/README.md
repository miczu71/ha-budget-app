# Budżet Domowy — Monarch

System designu panelu add-onu „Budżet Domowy” (Home Assistant, Ingress). Jasny wygląd w stylu Monarch z jednym pomarańczowym akcentem; wybrany 2026-10-05 po porównaniu z Copilot Money.

**To lustro kodu, nie źródło prawdy.** Tokeny i zasady żyją w `budget/app/src/budget/web/static/app.css` (`:root`) i `DESIGN.md` repozytorium `miczu71/ha-budget-app`. Zmiany stylu robimy w kodzie, a ten system aktualizujemy po nich (procedura „Re-sync” w `DESIGN.md`). Używaj go do makiet nowych ekranów i planowania refaktorów, nie do wymyślania nowego stylu.

## Produkt i kontekst

- Jedna osoba, jedno gospodarstwo domowe. Panel otwierany głównie na telefonie w aplikacji Home Assistant Companion (WebView), czasem na komputerze.
- Cel: jedno spojrzenie odpowiada „ile zostało i czy jestem na tempie”; przegląd transakcji zajmuje minuty.
- Zasady: najpierw odpowiedź, potem szczegóły; telefon jest głównym urządzeniem; liczby są bohaterem; kolor niesie znaczenie, nie dekorację; nic zewnętrznego w renderowaniu (bez CDN i zewnętrznych fontów, wykresy to SVG liczone po stronie serwera).
- Interfejs po polsku, kwoty w PLN. W makietach używaj neutralnych danych (Sklep X, Osoba 1, Miasto A), nigdy prawdziwych nazw.

## Kolory

Jeden wypełniony kolor akcji. Tło strony to `canvas` (Linen), karty to `surface-1` (Paper), hairline to `border`.

| Token | Rola |
|---|---|
| `canvas`, `surface-1`, `surface-2`, `surface-3` | tło strony, karty i pola, elementy zagnieżdżone i najechanie, zaznaczenie |
| `border`, `control-border` | hairline kart i separatorów, ramka pól (ok. 3:1) |
| `text`, `text-2`, `text-3` | treść, drugorzędna, podpisy (≥ 4,5:1 także na `canvas`) |
| `accent`, `on-accent` | jedyny wypełniony kolor akcji; tekst na nim to Ink, nie biel (biel dawała 2,9:1) |
| `link` | linki w Ink z podkreśleniem; pomarańcz nie jest kolorem tekstu |
| `pos`, `neg`, `warn` | wpływ i „dobrze”, przekroczenie i „źle”, ostrzeżenie |
| `chart-1` … `chart-8`, `chart-other`, `chart-unc` | kategorie na wykresach, „Inne”, „Bez kategorii” |

Reguły:
- Kwota wydatku w wierszu jest neutralna (`text`); kolor mają wpływy (`pos`) i przekroczenia (`neg`).
- Kolory znaczeniowe (`pos`, `neg`, `warn`) nie służą kategoriom.
- Kolor kategorii jest stały (`id % 8`); kolizja w jednym wykresie przesuwa mniejszy wycinek na następny wolny kolor.
- Stare nazwy z poprzedniej wersji CSS (`--bg`, `--card`, `--muted`, `--line`, `--ok`, `--error`) istnieją tylko dla starych reguł; w nowym kodzie używaj nazw z tej tabeli.

## Typografia

- **Nagłówki i duże liczby:** Source Serif 4 przycięty do łaciny, w CSS pod nazwą „Serif Display”. Waga 350–400, tracking od −0,02 do −0,035 em (nie niżej niż −0,04 em).
- **UI i treść:** Inter, waga 350 (małe teksty i etykiety 400, nawigacja 500), `letter-spacing: −0.01em`, liczby `tabular-nums`.
- Separator tysięcy w kwotach (U+202F) w szeryfie jest zbyt wąski przy ciasnym trackingu, więc ten jeden znak bierzemy z Inter przez `unicode-range`. W kodzie to dwa `@font-face` o tej samej nazwie; `tokens.json` opisuje tylko jedną ścianę, więc pełne zachowanie daje `components/bundle.css`.
- Bez nadtytułów (eyebrow) nad nagłówkami.
- Fonty lokalnie (woff2, licencja OFL), `font-display: swap`. Pliki: `fonts/InterVariable.woff2`, `fonts/SourceSerif4-latin.woff2`.

## Kształt i głębia

Karty r12 (20 na telefonie), pola r8, przyciski i chipy w kształcie pigułki. Płasko: hairline `border` i lekki dwuwarstwowy cień `elev`. Siatka 4 px, padding karty 20 px (16 na telefonie), odstęp elementów 16 px.

## Zasady układu i interakcji

- Cele dotyku ≥ 44 px (`tap`): pola i przyciski mają to globalnie; link samodzielny dostaje klasę `tap`; link w zdaniu ma obszar dotyku przez `::after`, żeby wiersz tekstu nie rósł.
- Nawigacja: Podsumowanie · Budżet · Wydatki · Cykliczne · Transakcje, dzwonek, menu ⚙ (`<details>`, bez JS): Do przejrzenia · Reguły · Konta · Import CSV · Bank · Status (ostatni). Aktywna zakładka ma pomarańczowe podkreślenie. Na telefonie pasek przewija się poziomo. Wersja add-onu w stopce.
- Jedna animacja: wjazd wycinków wykresu kołowego, wyłączona przy `prefers-reduced-motion`.
- Nowe elementy SVG dostają unikalne nazwy klas (stare `.bar` nadpisywało wysokość `rect`).

## Wykresy

SVG po stronie serwera, bez JS i bibliotek. Wycinki i słupki ≥ 3:1 względem karty, tekst ≥ 4,5:1; wycinek i legenda są linkami; wiersze legendy ≥ 44 px. Słupki: wpływy `bar-income`, wydatki `bar-expense`. Porównania liczone rzetelnie: bieżący (niepełny) miesiąc vs ten sam zakres dni poprzedniego, podpis mówi to wprost.

Wykres prognozy „Do wypłaty”: linia salda dzień po dniu, strefa poniżej zera w `neg` przy kryciu 0,08, kreska bufora w `warn`, znaczniki zdarzeń (wpływy `pos`, trzy największe wydatki `neg`), pod wykresem chronologiczna lista.

## Ikony i grafika

Wszystko w SVG, bez PNG, Unicode i emoji. Ikony: Lucide (ISC) przez iconify.design, inline albo jako maska CSS (`--i-chevron`, `--i-check`). Animacje wyłącznie jako Lottie, lokalnie. Zestaw używanych ikon: grupa Ikony.

## Cache WebView

HTML i API serwowane z `Cache-Control: no-store`, statyki wersjonowane `?v=<wersja>` z `immutable`, wersja widoczna w stopce. Każda zmiana HTML/JS/CSS wymaga bumpu wersji add-onu.

## Użycie w makietach

1. Zacznij od `canvas` jako tła i kart w `surface-1`; dodaj akcent tylko na jednej akcji głównej na ekranie.
2. Liczby w Serif Display z `tabular-nums`, reszta w Inter.
3. Sprawdź cele dotyku (≥ 44 px) i układ przy 390 px szerokości.
4. Nowych komponentów nie wymyślaj: najpierw szukaj istniejącego w `components/`.
