Dodatki kolejki „Do przejrzenia”: podpowiedzi AI, filtr po propozycji, lista pozycji grupy, podgląd reguły i potwierdzenie zapisu.

Statyczne odwzorowanie szablonów (w dev AI jest wyłączone). `form.rv-ai-run` uruchamia podpowiedzi; `nav.rv-ai-filter` z chipami `.chip.rv-f.tap` (`on` = aktywny) i rozwijanym `details.rv-f-more`. W nagłówku grupy `span.rv-ai` ma przycisk zatwierdzenia `rv-accept` i chipy propozycji `.chip`. Rozwinięta grupa: `ul.rv-items` z polami wyboru (`rv-desc`, data, kwota `num`), `div.rv-preview` z podglądem, `div.rv-sub` przy grupie krajowej. Po zapisie `li.rv-done` z plakietką `badge ok`. Sekcja `rv-learned` zbiera pozycje przypisane przez pamięć sprzedawcy.

- Konsument dostarcza propozycje, kwoty i teksty; cele dotyku ≥ 44 px.
