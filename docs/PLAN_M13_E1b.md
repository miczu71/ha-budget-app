# M13 E1b — wariant Monarch i wybór motywu

Wywiad 2026-10-05, po checkpoincie E1: użytkownik chce zobaczyć drugi wariant UI (Monarch z Refero) i zdecydować, który
zostaje, **zanim** powstanie E2 (kolory wykresów i kategorii zależą od wybranego stylu).

## Zasady
- Obie wersje żyją obok siebie za przełącznikiem „Wygląd”; po decyzji (E1c) przegrany motyw i przełącznik są usuwane.
- Tylko warstwa wizualna: schemat bazy, encje MQTT i logika budżetu bez zmian. Jedyny nowy stan to klucz `ui_theme`
  w istniejącym magazynie kv (domyślnie `copilot`).
- Tryb: najpierw lokalnie i zrzuty obok siebie; wydanie 0.18.1 z przełącznikiem i update HA dopiero na „go” użytkownika.
- Ikony i grafiki zawsze SVG (Lucide), animacje jako Lottie; fonty lokalnie (OFL), bez CDN.

## Monarch: styl i adaptacje
Źródło: https://styles.refero.design/style/a9dd8050-c03a-4901-b7fa-a9cc0ca54812 (jasny).

| Element | Monarch (źródło) | Adaptacja w panelu |
|---|---|---|
| Tło / karta / linia | Linen `#efecea` / Paper `#fff` / Stone `#dcd9d6` | bez zmian |
| Tekst | Ink `#22201d`, Graphite `#777573` | dla małego tekstu na Linen ciemniejszy odcień (Graphite daje ok. 3,9:1) |
| Akcent | Ember `#ff692d`, jedyny kolor | przyciski z tekstem Ink (biały na Ember = 2,9:1); pomarańcz nie jest kolorem tekstu, linki w Ink z podkreśleniem |
| Semantyka | brak | dwa ciemniejsze odcienie: wpływ (zielony) i przekroczenie (czerwony), AA na bieli |
| Kształt | karty r12, pola r8, przyciski pill | bez zmian; cienie dwuwarstwowe, lekkie |
| Nagłówki | Copernicus 350, tracking do −0,067 em | Source Serif 4 w wadze 350, tracking nie niżej niż −0,04 em |
| Treść | ABC Oracle 350 | Inter 350 (zmienny, już w add-onie) |
| Wykresy (E2) | brak kategorii kolorów | monochromat z pomarańczowym akcentem (np. największa kategoria) |

Tylko jasny (jak Copilot jest tylko ciemny).

## Kroki
1. Dokumenty (ten plik, wiersz E1b w `ROADMAP.md`), commit.
2. Source Serif 4 (zmienny woff2 + OFL) z `adobe-fonts/source-serif` do `web/static/fonts/`.
3. `static/app.css`: blok `[data-theme="monarch"]` (tokeny, promienie, cienie, nagłówki, nawigacja, przyciski, semantyka).
4. Backend: kv `ui_theme`, `POST /theme` (dwie dozwolone wartości, powrót na tę samą stronę), `data-theme`, `color-scheme`
   i `theme-color` w `base.html`, sekcja „Wygląd” w menu ⚙. Pliki: `web/routes_theme.py`, `web/app.py`, `web/common.py`,
   `templates/base.html`.
5. Testy (domyślny motyw, zapis, odrzucenie nieznanego), pytest, ruff, mypy.
6. Weryfikacja lokalna na kopii księgi: Podsumowanie, Budżet, Transakcje, Do przejrzenia, Status; oba motywy; 360 i 1280 px;
   kontrast liczony w przeglądarce; zrzuty obok siebie dla użytkownika.
7. Na „go”: release 0.18.1 i update HA z backupem; porównanie na telefonie.
8. E1c po decyzji: usunięcie przegranego motywu i przełącznika, wydanie sprzątające.

## Cofnięcie
`git revert` commita E1b; klucz `ui_theme` w kv jest nieszkodliwy.

## Wynik lokalny (2026-10-05, bez wydania)

Zbudowane i sprawdzone na kopii księgi: 493 testy, ruff i mypy bez uwag; 12 ekranów × 360 i 1280 px × 2 motywy bez
przepełnienia poziomego i bez błędów w konsoli; kontrast liczony w przeglądarce ≥ 4,5:1 dla całego tekstu (najniżej stopka
w Monarch 4,77:1, przycisk Ink na pomarańczu 5,66:1); przełączanie z menu ⚙ w prawdziwej przeglądarce wraca na tę samą stronę.
Detektor impeccable: tylko znane ostrzeżenia „overused-font” (Inter, Space Grotesk).

Szczegóły wykonania:
- Source Serif 4 przycięty do łaciny (146 kB zamiast 429 kB, osie `wght` i `opsz` zachowane), notka o pochodzeniu przy licencji.
- Baza CSS: tokeny `--elev`, `--on-accent`, `--r-input` zamiast wartości zaszytych pod Copilota (wygląd Copilot bez zmian).
- Monarch: pola formularzy białe (jak w specyfikacji), kwota „Zostało” w Ink (jeden akcent), nagłówek miesiąca 19 px na telefonie.
- Przełącznik: klasa `theme-opt` współdzieli styl z `.chip`, ale ma własną nazwę, bo testy liczą `class="chip` na ekranie przeglądu.
