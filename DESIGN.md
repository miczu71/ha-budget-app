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
- UI i treść: Inter, grubość 300–400 (odstępstwo od Matter Thin 100: czytelność na telefonie), liczby
  `font-variant-numeric: tabular-nums`.
- Etykiety (eyebrow): wersaliki, `0.04em`, grubość 500–600.
- Fonty lokalnie (`static/fonts/`, woff2, OFL), `font-display: swap`.

## Kształt i głębia
Karty r24, przyciski r16, chipy r20, obrazy r8. Głębia z wewnętrznych cieni (jasny inset w prawym górnym,
ciemny w lewym dolnym rogu), bez drop shadow. Sekcje rozdzielane tonem tła, nie ramkami.
Siatka 4 px, padding karty 24 px (16 px na telefonie), odstęp elementów 16 px.

## Zasady
- Jeden wypełniony kolor akcji (`--accent`); żadnego drugiego koloru przycisków.
- Kolory kategorii nigdy na jasnym tle.
- Wykresy: SVG po stronie serwera, bez biblioteki JS.
- Bez „pływających etykiet” z hero Copilota (dekoracja strony marketingowej).
- Nawigacja: Podsumowanie · Budżet · Wydatki · Cykliczne · Transakcje, dzwonek, menu ⚙ (Reguły, Konta,
  Import CSV, Bank, Status).
