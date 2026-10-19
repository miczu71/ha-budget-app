# M22 — Agent inwestycyjny (+ M17 tracker promocji jako E5)

Repo: `/config/addons/ha-budget-app` (gałąź `main`, na produkcji 0.56.2, ostatnia migracja 022).
Plan zaakceptowany 2026-10-19 (wywiad, decyzja 30 w `ROADMAP.md`).

## Context

M22 w ROADMAP to pomysł z 2026-10-10: agent, który mówi, ile i w co odkładać, w zestawieniu z nadpłatą kredytu.
Wywiad 2026-10-19 rozszerzył go do pełnego doradcy i dołączył M17 (śledzenie warunków promocji).

**Streszczenie wywiadu (kto, co automatycznie, co za zgodą, sukces):**
1. **Kto korzysta:** domownicy w zakładce „Inwestycje”, w dzwonku, w miesięcznym pushu po wypłacie i w czacie (decyzja 24).
2. **Automatycznie:** add-on raz dziennie pobiera oprocentowanie obligacji, ranking lokat i kont oraz RSS blogów.
   Liczy trzy koszyki i zysk netto każdej opcji, a LLM streszcza wpisy z blogów. Wyłącznie doradztwo, żadnych operacji na kontach.
3. **Tylko ręcznie (użytkownik):** lista aktywów (obligacje, IKE, ETF, akcje, lokaty), banki, w których jest lub był
   klientem, założenia ETF, mnożnik poduszki, „Skorzystaj” przy ofercie (start śledzenia promocji w E5).
4. **Sukces:** zysk netto 3 opcji (lokata, EDO, nadpłata) z ekranu = ręczne przeliczenie ±1 zł, a oprocentowanie
   obligacji = oficjalna strona. Z 10 ofert wyciągniętych przez LLM z blogów ≥ 8 ma poprawną stawkę, limit i termin.

**Decyzja 30 (do ROADMAP):**
- Instrumenty: konta oszczędnościowe, lokaty, obligacje skarbowe (też w IKE), premie bankowe, nadpłata kredytu, ETF i akcje.
- **Trzy koszyki:**
  1. Poduszka = mnożnik (domyślnie 3) × miesięczne wydatki (stałe z serii + mediana Flex, jak M18). Liczą się do niej
     konto oszczędnościowe M10 i wolne środki ponad bufor M8. Skarbonki się nie liczą.
  2. Cele 1–5 lat = skarbonki M10 i ich terminy.
  3. Długi termin = reszta, w tym EDO/IKE, ETF i nadpłata.
  Rekomendacja zawsze najpierw dopełnia koszyk 1.
- **Nowe pieniądze = nadwyżka miesiąca z M18** po skarbonkach i buforze. Przy deficycie agent nie poleca nowych
  wpłat, tylko optymalizuje to, co już leży, i mówi wprost, że nadwyżki nie ma.
- **ETF:** 3 scenariusze zwrotu z ustawień (domyślnie 0/6/9% rocznie) minus TER, netto po Belce albo w IKE.
  ETF tylko w koszyku 3.
- **Liczy add-on deterministycznie.** LLM tylko streszcza wpisy i pisze 2–3 zdania uzasadnienia. Do LLM idą tylko
  kwoty zbiorcze (decyzja 23), bez nazw kont i transakcji.
- **Źródła:** obligacje z obligacjeskarbowe.pl (parsowane bez LLM), ranking lokat i kont z jednej strony,
  RSS 2–3 blogów. Oferta z LLM ma status „do sprawdzenia”, dopóki użytkownik jej nie potwierdzi.
- **Promocje:** oferty „tylko dla nowych” z banków z listy użytkownika są ukryte, a warunki liczone jako „jeśli spełnisz”.
  Śledzenie warunków to E5 (dawne M17). Postęp z księgi działa tylko dla 3 kont Millennium (decyzja 1), w innych bankach warunki odhacza się ręcznie.

## Do wykorzystania (istniejący kod, `budget/app/src/budget/`)

- `loan_sim.simulate` / `variants` — zysk z nadpłaty w horyzoncie (porównanie w koszyku 3).
- `savings.net` (Belka), `savings.estimate`, `savings.overview` — saldo i odsetki konta M10.
- `piggy.py` — skarbonki (koszyk 2), `year.build` → `Projection` (nadwyżka, koszyk 1: wydatki miesięczne).
- `forecast.py` (bufor M8, wolne środki).
- `wibor.py` i `promo_watch.py` — wzorzec pobrania przez httpx, `parse()` + `refresh(conn, now)`, błąd w kv
  i dostawca dzwonka `wibor_error`. Harmonogram w `service.py` (ok. linii 257/270, `daily_tick`).
- `inbox.PROVIDERS` — nowi dostawcy dzwonka.
- `summary.py` (`Message`, `due`, `mark_sent`) — push po wypłacie.
- `ask/sources.py` (`run`, `prompt_lines`) — źródło czatu `invest`.
- `suggest` (klient freellmapi, `metered_call`, limit dzienny) — streszczenia blogów.
- `nav_layout.TABS` — nowa zakładka „Inwestycje” (`/invest`); `routes_loan.py` / `routes_piggy.py` jako wzór tras.

## Etapy (każdy: `tdd`, ruff + mypy + pytest, UI na devserve 390/1280 px, `simplify` przed commitem, `stage-end`)

### E1 — Aktywa, koszyki, kalkulator netto (bez sieci)
- Migracja `023_invest.sql`: `invest_asset` (typ: obligacje/lokata/konto/ETF/akcje/inne, nazwa, kwota, data,
  oprocentowanie lub wartość bieżąca, `ike`, zapadalność), `invest_bank` (bank, od kiedy). Ustawienia w `kv`:
  mnożnik poduszki, zwroty ETF 0/6/9, TER, inflacja do obligacji indeksowanych (domyślnie 3%).
- `invest.py`: `buckets(snap, today)` → koszyk 1/2/3 (cel, stan, luka), `options(...)` → zysk netto w horyzoncie
  dla: konta M10, lokaty (stawka, okres), EDO/COI/ROR/DOR/TOS (pierwszy rok + marża × inflacja; COI z wypłatą roczną,
  EDO kapitalizacja), ETF (3 scenariusze), nadpłaty (`loan_sim`). `recommend(...)` → kwoty per opcja wg koszyków;
  przy deficycie M18 tylko „optymalizacja istniejących”.
- Na start oferty wpisywane ręcznie w formularzu (stawka, limit, termin, warunki tekstem). E2 i E3 tylko je zasilają.
- Ekran `/invest`: koszyki (paski), rekomendacja, ranking opcji (netto zł/rok, płynność), aktywa (dodaj/edytuj/archiwizuj), ustawienia.
- Weryfikacja: testy jednostkowe 3 scenariuszy liczonych ręcznie (lokata, EDO 10 lat, nadpłata) ±1 zł.
- Rollback: `git revert` commitów E1 (migracja 023 addytywna, niewydana).

### E2 — Obligacje i ranking lokat/kont z sieci → **wydanie 0.57.0**
- Krok 0 (sonda): pobrać stronę oferty obligacji i jedną stronę rankingu (np. Bankier: lokaty + konta
  oszczędnościowe), sprawdzić strukturę i robots/warunki. Fixture w repo tylko z neutralnymi nazwami.
  Jeśli ranking nie jest stabilny do parsowania, **staję i pytam** (zmiana założenia z wywiadu).
- `invest_sources.py`: `parse_bonds(html)`, `parse_ranking(html)` + `refresh(conn, now)` raz dziennie (wzór `wibor`),
  tabela `invest_offer` (źródło, bank, typ, stawka, limit, okres, warunki, `nowi_klienci`, status, url, data).
  Błąd → kv + dostawca dzwonka `invest_source_error`.
- Filtr nowego klienta po `invest_bank`.
- Wydanie: `code-review` → `release` 0.57.0. Na żywo: stawki obligacji = obligacjeskarbowe.pl, 3 opcje = przeliczenie ręczne ±1 zł.
- Rollback: backup add-onu z `ha_manage_updates` (backup=true) albo cofnięcie do 0.56.2.

### E3 — RSS blogów + streszczenia LLM
- Krok 0: sprawdzić kanały RSS 2–3 blogów (kandydaci: jakoszczedzacpieniadze.pl, subiektywnieofinansach.pl,
  bankier.pl/promocje) — lista do potwierdzenia w raporcie etapu. Parser RSS na stdlib `xml.etree` (bez nowej zależności).
- Nowe wpisy → LLM (`suggest.metered_call`, osobny limit dzienny `invest_daily_calls`) → JSON wg schematu:
  bank, typ, stawka, limit, okres, warunki, `nowi_klienci` → `invest_offer` ze statusem „do sprawdzenia” i linkiem do artykułu.
  Do LLM idzie tylko treść wpisu, bez danych użytkownika.
- UI: sekcja „Z blogów” (streszczenie, „Potwierdź / Popraw / Odrzuć”). Do rankingu wchodzą tylko potwierdzone oferty.
- Pomiar: karta na Status „Oferty z blogów — trafność” (potwierdzone bez poprawek / wszystkie); cel ≥ 8/10.
- Rollback: `git revert`; opcja wyłączenia źródeł blogów w ustawieniach.

### E4 — Dzwonek, push po wypłacie, czat → **wydanie 0.58.0**
- Dostawcy dzwonka: `invest_better_offer` (oferta bije obecne miejsce o ≥ X zł/rok, X w ustawieniach,
  domyślnie 200 zł), `invest_maturity` (koniec lokaty lub wykup obligacji w ciągu 14 dni).
- `summary`: wiadomość `invest_monthly` w dniu wypłaty (seria `payday_series_id`) przez istniejącą opcję
  `summary_notify_service` (alias `notify.family`): „odłóż X: A tu, B tam” albo „nadwyżki brak”.
- `ask/sources.py`: źródło `invest` (koszyki, rekomendacja, top 3 opcje; tylko kwoty).
- LLM: 2–3 zdania uzasadnienia rekomendacji (wejście = wynik silnika, zbiorczo).
- Wydanie: `code-review` → `release`. Na żywo: dzwonek, podgląd treści pusha bez wysyłki, 1 pytanie do czatu = ekran.
- Rollback: backup add-onu, cofnięcie do 0.57.0.

### E5 — Śledzenie promocji (dawne M17) → **wydanie 0.59.0**
- Migracja 024: `promo_track` (oferta, bank, okres, start/koniec, premia, status), `promo_condition`
  (typ: liczba płatności kartą / suma wpływów / saldo na dzień / ręczny krok, próg, okres).
- „Skorzystaj” przy ofercie tworzy śledzenie z warunkami wstępnie wyciągniętymi z tekstu oferty (LLM jako propozycja,
  edytowalne). Postęp z księgi tylko dla kont Millennium (uogólniony licznik z `card.py`), dla innych banków ręczne odhaczanie.
- Przypomnienia przed końcem okresu (dzwonek + push, jak M15 E1), rejestr należnych i wypłaconych premii.
  Wypłacona premia trafia do `invest_asset` albo do wpływów.
- Wydanie: `code-review` → `release`. Na żywo: jedna promocja testowa z warunkiem ręcznym i z licznikiem z księgi.
- Rollback: backup add-onu, cofnięcie do 0.58.0.

## Weryfikacja (każdy etap)
- `cd budget/app && uv run pytest -q && uv run ruff check && uv run mypy src`
- devserve na kopii księgi w scratchpadzie (kopię skasować po teście), Playwright 390/1280 px,
  `scrollWidth ≤ innerWidth`, konsola czysta.
- Po wydaniu: `update.budzet_domowy_update`, stopka wersji, `/invest` 200 przez Ingress (playwright-ha).

## Ryzyka
- Scraping rankingu może się zepsuć przy zmianie strony. Wtedy błąd idzie do dzwonka, a ranking działa dalej na ofertach ręcznych i potwierdzonych.
- Słaba ekstrakcja przez qwen: status „do sprawdzenia” i pomiar trafności. Gdy wynik < 8/10, staję i pytam (inny model albo tylko linki).
- Hook prywatności: nazwy banków i miast w fixture'ach → nazwy neutralne („Bank A”).
- Okno 02:45–03:15 bez commitów i pushy.
