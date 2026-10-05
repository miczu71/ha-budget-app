# M13 E3d — cele dotyku na pozostałych ekranach (szkic, do zaplanowania)

Status: **zapisane, nie zaplanowane**. Szczegółowy plan (kroki, komendy, cofnięcie) i wywiad dopiero na polecenie; zależy od
0.20.1 (E3b + E3c, wydane 2026-10-05). Zasady jak w `PLAN_M13_E3.md`: bez nowych funkcji, bez zmian logiki, encji i schematu;
jeden etap naraz, checkpoint po każdym kroku, wydanie po osobnym „go”.

## Cel
Cele dotyku ≥ 44 px (pomiar bez wykluczeń, 360/390/1280 px) na ekranach, których nie objęły E3, E3b i E3c.

## Stan wyjściowy (pomiar kroku 0 E3c, 2026-10-05, 360 px, kopia księgi)
| Ekran | Elementy < 44 px |
|---|---|
| `/categories` | `input` 70 × 43 px, `button` 55 + 15 × 43 px, **`form.move` w listach: `select` 82 × 26 px i `button` 82 × 26 px** |
| `/accounts` | `input` 3 × 40, `button` 3 × 41 |
| `/bank` | `input` 3 × 40, `button` 3 × 41 |
| `/import` | `input` 1 × 41, `button` 1 × 41 |
| `/status` | link 1 × 19, `button` 3 × 41 |
| `/recurring` | `button.secondary` 1 × 41 |
| `/dictionary`, `/inbox` | bez uwag |
Poza tym: strony ze szczegółami serii (`series.html`, `series_new.html`) i nawigacja główna / dzwonek (`base.html`) — nie zmierzone.

## Kierunek do rozważenia
- Większość to globalny `padding: 9px 12px` dający 40–43 px. Jedna reguła `input, select, button, textarea { min-height: var(--tap) }`
  załatwiłaby je naraz (podejście „u źródła”), zamiast osobnych selektorów per ekran.
- **Decyzja projektowa (do wywiadu):** zagęszczone formularze `form.move` w listach na `/categories` (82 sztuki po 26 px). Warianty:
  podnieść do 44 px (lista wydłuży się), przenieść akcję do rozwijanego wiersza albo zostawić (kompromis względem gęstości).
- Ryzyko globalnej reguły: zmiana układu wszystkich formularzy naraz → zrzuty przed/po każdego ekranu, nie tylko zmienianego.

## Etapy (propozycja, do potwierdzenia po wywiadzie)
0. Pomiar pełny (z zasianiem danych dla Kategorii, Banku, Importu) i zrzuty „przed”.
1. Reguła globalna dla pól i przycisków + regresja wszystkich ekranów.
2. Kategorie: decyzja o `form.move`, potem implementacja.
3. Pozostałe linki (Status 19 px), seria cykliczna, nawigacja główna, dzwonek.
4. Wydanie 0.20.2 (lub kolejna wersja): bump, CHANGELOG, push, CI, release, backup add-onu, update w HA.
