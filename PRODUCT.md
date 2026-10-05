# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Jedna osoba (autor, właściciel domowego budżetu) w jednym gospodarstwie domowym. Otwiera panel głównie na
telefonie w aplikacji Home Assistant Companion (Ingress WebView), czasem na komputerze. Typowe sytuacje:
szybkie sprawdzenie „ile jeszcze mogę wydać w tym miesiącu”, przegląd kolejki nieskategoryzowanych transakcji,
okresowy przegląd kategorii i płatności cyklicznych.

## Product Purpose
Prywatny add-on Home Assistant „Budżet Domowy”: pobiera transakcje z banku (PSD2 przez Enable Banking) i z CSV,
składa jedną księgę bez duplikatów, kategoryzuje wydatki regułami i podpowiedziami AI, liczy budżet elastyczny
(Flex) i wykrywa płatności cykliczne. Sukces: jedno spojrzenie odpowiada „ile zostało i czy jestem na tempie”,
a przegląd transakcji zajmuje minuty, nie godziny.

## Positioning
Budżet lokalny w domowym HA: dane finansowe nie opuszczają domu (poza zapytaniami do banku i opcjonalnych
podpowiedzi AI bez danych osobowych), wizualizacje wyłącznie w panelu add-onu, a HA dostaje tylko encje.

## Operating Context
Panel serwowany przez Ingress (FastAPI + Jinja + htmx, bez bundlera). WebView Companion agresywnie cache'uje
HTML, więc HTML/API są `no-store`, a statyki wersjonowane `?v=<wersja>` z `immutable`. Interfejs po polsku,
kwoty w PLN.

## Capabilities and Constraints
- Ekrany: Status, Budżet, Wydatki, Cykliczne, Do przejrzenia, Transakcje, Reguły (słownik, kategorie), Konta,
  Import CSV, Bank; dzwonek powiadomień.
- Wszystko lokalnie z add-onu: bez CDN, bez zewnętrznych fontów, wykresy renderowane po stronie serwera (SVG).
- Zero danych osobowych w repo, logach, fixture'ach i dokumentach (repo jest publiczne); przykłady neutralne.
- Logika budżetu, encje MQTT i schemat bazy nie zależą od warstwy wizualnej.

## Product Principles
1. Najpierw odpowiedź („ile zostało”), potem szczegóły.
2. Telefon jest głównym urządzeniem; desktop to rozszerzenie.
3. Liczby są bohaterem: czytelne, wyrównane, bez ozdobników.
4. Kolor niesie znaczenie (kategoria, wpływ, przekroczenie), nie dekorację.
5. Prywatność ponad wygodę: nic zewnętrznego w renderowaniu strony.

## Accessibility & Inclusion
Kontrast tekstu treści co najmniej WCAG AA na jasnym tle (Linen i Paper); cele dotykowe min. 44 px na telefonie;
`prefers-reduced-motion` respektowane.
