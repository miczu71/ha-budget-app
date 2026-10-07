Karta „Podpowiedzi AI” na ekranie Status: stan, akcje, tabela trafności, podgląd podsumowania i log czatu.

Statyczne odwzorowanie szablonu. `dl.kv` pokazuje model, wywołania dziś i stan podpowiedzi. `div.ai-actions` trzyma przyciski „Podpowiedz teraz” i „Zmierz trafność” (`secondary`) z `span.htmx-indicator` (widoczny tylko w trakcie żądania). `table.ai-eval` w `table-wrap` to trafność wg progu pewności. `pre.summary-preview` pokazuje tekst tygodniowego podsumowania, `ul.rows.chat-log` ostatnie pytania czatu (log bez kwot).

- Wyłączone AI pokazuje jedno zdanie `muted` z podpowiedzią konfiguracji.
