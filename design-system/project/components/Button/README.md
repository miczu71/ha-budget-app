Przyciski w kształcie pigułki: główny (pomarańczowy), `secondary` (neutralny) i link wyglądający jak przycisk.

Na ekranie jest najwyżej jedna akcja główna w kolorze `accent`; pozostałe to `button.secondary`. Link-przycisk to `a.button.tap`. Wszystkie mają wysokość co najmniej 44 px. Tekst na akcencie jest w Ink (`on-accent`), nie w bieli.

- Stany: `:disabled` jest wyszarzony, `:focus-visible` ma obrys 2 px w Ink.
- Konsument dostarcza etykietę i akcję (`hx-post` lub zwykły formularz).
