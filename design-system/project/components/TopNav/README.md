Pasek nawigacji panelu: zakładki główne, dzwonek powiadomień i menu ⚙.

Używaj go raz, na górze każdego ekranu (`header.top`, przyklejony). Aktywna zakładka ma klasę `on` i pomarańczowe podkreślenie. Menu ⚙ to `<details class="more">` bez JS; ostatni element panelu (Status) jest oddzielony `div.sep`. Na telefonie zakładki przewijają się poziomo.

- Dzwonek `a.bell` pokazuje liczbę w `span.nav-count` (pusta, gdy brak spraw).
- Ikony inline SVG (Lucide, `currentColor`), 22 px; cel dotyku 44 px.
- Konsument dostarcza adresy linków i liczbę dla dzwonka.
