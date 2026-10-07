Pula budżetu na ekranie Budżet: rozwijane składniki puli (`ul.cats.pool`), koszty stałe z edycją i formularz dodania.

Pula to lista `cats pool` z rozwijanymi wierszami: wpływy z poprzedniego miesiąca (źródła w `flex-lines`), `li.pool-row` dla pozycji poza pulą (premia, kwota `neg`) i „Pula automatyczna”. Koszty stałe: `details.leaf` z `div.leaf-meta` (rodzic i link „Transakcje”) oraz `form.move` do przeniesienia do innej grupy; `form.move.add-fixed` dodaje podkategorię do stałych. W Karcie kredytowej ten sam układ pasków: `flex-bar.limit-bar` (wypełnienie `fill`, przy przekroczeniu `over`) i `dl.fc-strip.limit-strip` z zadłużeniem, limitem i wykorzystaniem.

- Konsument dostarcza kwoty i opcje; kwoty w `cat-amount`, ujemne w `neg`.
