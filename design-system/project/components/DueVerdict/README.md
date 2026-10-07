Werdykt spłaty karty kredytowej (`card-due`) z limitem (`card-limit`) i licznikiem płatności.

`fc-verdict.due-verdict` dziedziczy układ werdyktu „Do wypłaty”: klasa `bad` oznacza minięty termin, `ok` zapas. Kwota do spłaty w `hero-amount`. Karta Limit ma formularz `form.rename` (pole i przycisk w jednym wierszu). Licznik płatności używa `div.stats` i `span.warn-text`, gdy brakuje płatności do darmowej karty.

- Konsument dostarcza kwoty, terminy i teksty; tekst „liczone ostrożnie” zostaje.
