Wyszukiwanie na żywo: pole `label.search` z lupą, filtry i licznik wyników `p.search-count`.

Używane w Transakcjach, Regułach i Słowniku (htmx odświeża listę po 200 ms od wpisania). Lupa to tło pola (SVG, 16 px), dopełnienie lewe 32 px. Licznik pod polem mówi, ile wyników pasuje.

- Konsument dostarcza adres, `hx-target` i liczbę wyników.
- Ukryty `button.visually-hidden` zapewnia wysłanie formularza klawiszem Enter.
