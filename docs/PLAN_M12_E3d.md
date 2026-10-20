# M12 E3d — stabilność pytań z dwóch źródeł (pomiar szerszy niż jedna para)

Status: pomiar E0 częściowy (2026-10-20, produkcja 0.61.0); wspólny plan z M14 E2 → `PLAN_M14_E2.md`.
Cel: ≥ 90% odpowiedzi z obiema właściwymi tabelami (8 par × 3 próby), poprawka promptu w tym samym wydaniu, gdy poniżej.

## Pomiar E0 (iframe Ingress, POST `/ask`, `ctx=[]`)

| Para (pytanie ze słowami obu ekranów) | Próby ważne | Oba właściwe źródła |
|---|---|---|
| karta + budżet | 3/3 | 3/3 |
| budżet + cykliczne | 3/3 | 3/3 |
| rok + cykliczne | 3/3 | 3/3 |
| **kredyt + inwestycje** | 3/3 | **1/3** — próby 2 i 3 wzięły „Skarbonki” zamiast „Inwestycje” |
| majątek + skarbonki | 3/3 | 3/3 |
| majątek + kredyt | 3/3 | 3/3 |
| skarbonki + do wypłaty | 2/3 | 2/2 |
| karta + do wypłaty (kontrola) | 0/3 | — |

- Razem: 20 ważnych prób, 18 z obiema właściwymi tabelami (90%); „nie umiem”: 0; błędy techniczne: 4.
- **4 próby (ostatnia skarbonki + do wypłaty i cała karta + do wypłaty) zwróciły „Wyczerpany dzienny limit pytań
  (opcja `chat_daily_calls`)”** — pomiar zużył dzienny limit czatu; brakujące próby po resecie limitu.
- Nie porównano jeszcze liczb z ekranami (sprawdzono tylko dobór źródeł i obecność dwóch tabel).
- Wniosek wstępny: jedyna słaba para to kredyt + inwestycje (opis źródła `savings` i `invest` zachodzą na „odłożyć”).
  Poprawka (E3) dotyczy opisów źródeł w `ask/sources.py`, nie schematu; test: pytanie o „odłożyć z nadwyżki zamiast
  nadpłacać” wskazuje `invest`.
