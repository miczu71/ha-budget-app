# Ikony

Ikony używane w panelu „Budżet Domowy”: dzwonek i menu ⚙ w nawigacji, strzałki zmiany (↗ ↘) przy porównaniach, strzałki i oko w trybie edycji układu ekranu głównego, szewron i ptaszek (w CSS jako maski `--i-chevron`, `--i-check`) oraz lupa pola wyszukiwania.

- Źródło: Lucide (licencja ISC, https://github.com/lucide-icons/lucide) przez iconify.design. Wyjątek: `search.svg` to własny rysunek 16 px z `app.css` (tło pola wyszukiwania), nie Lucide.
- Pliki są kopiami ścieżek z szablonów i `app.css` bez zmian geometrii. W panelu ikony używają `currentColor`; tutaj mają wpisany kolor Ink (`#22201d`), bo obraz w `<img>` nie dziedziczy koloru (lupa: `#999ca1`).
- Zasada: tylko SVG, 24 × 24, obrys 2 px, zaokrąglone końce. W kodzie panelu osadzaj je inline albo jako maskę CSS, nie jako PNG ani glif Unicode.
- Przed użyciem w publicznym repo sprawdź licencję zestawu.
