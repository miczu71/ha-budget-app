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

### E1 — Aktywa, koszyki, kalkulator netto (bez sieci) — ✅ 2026-10-19 (ae7b09b, niewydane)
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

### E2 — Obligacje i ranking lokat/kont z sieci → **wydanie 0.57.0** — ✅ 2026-10-19 (22f8939, wydane)
- Krok 0 (sonda): pobrać stronę oferty obligacji i jedną stronę rankingu (np. Bankier: lokaty + konta
  oszczędnościowe), sprawdzić strukturę i robots/warunki. Fixture w repo tylko z neutralnymi nazwami.
  Jeśli ranking nie jest stabilny do parsowania, **staję i pytam** (zmiana założenia z wywiadu).
- `invest_sources.py`: `parse_bonds(html)`, `parse_ranking(html)` + `refresh(conn, now)` raz dziennie (wzór `wibor`),
  tabela `invest_offer` (źródło, bank, typ, stawka, limit, okres, warunki, `nowi_klienci`, status, url, data).
  Błąd → kv + dostawca dzwonka `invest_source_error`.
- Filtr nowego klienta po `invest_bank`.
- Wydanie: `code-review` → `release` 0.57.0. Na żywo: stawki obligacji = obligacjeskarbowe.pl, 3 opcje = przeliczenie ręczne ±1 zł.
- Rollback: backup add-onu z `ha_manage_updates` (backup=true) albo cofnięcie do 0.56.2.

### E3 — RSS blogów + streszczenia LLM — ✅ 2026-10-19 (ab5811c, wydane w 0.58.0)
- Krok 0: sprawdzić kanały RSS 2–3 blogów (kandydaci: jakoszczedzacpieniadze.pl, subiektywnieofinansach.pl,
  bankier.pl/promocje) — lista do potwierdzenia w raporcie etapu. Parser RSS na stdlib `xml.etree` (bez nowej zależności).
- Nowe wpisy → LLM (`suggest.metered_call`, osobny limit dzienny `invest_daily_calls`) → JSON wg schematu:
  bank, typ, stawka, limit, okres, warunki, `nowi_klienci` → `invest_offer` ze statusem „do sprawdzenia” i linkiem do artykułu.
  Do LLM idzie tylko treść wpisu, bez danych użytkownika.
- UI: sekcja „Z blogów” (streszczenie, „Potwierdź / Popraw / Odrzuć”). Do rankingu wchodzą tylko potwierdzone oferty.
- Pomiar: karta na Status „Oferty z blogów — trafność” (potwierdzone bez poprawek / wszystkie); cel ≥ 8/10.
- Rollback: `git revert`; opcja wyłączenia źródeł blogów w ustawieniach.

### E4 — Dzwonek, push po wypłacie, czat → **wydanie 0.58.0** — ✅ 2026-10-19 (44704c4, de614cf, 4043456)
- Dostawcy dzwonka: `invest_better_offer` (oferta bije obecne miejsce o ≥ X zł/rok, X w ustawieniach,
  domyślnie 200 zł), `invest_maturity` (koniec lokaty lub wykup obligacji w ciągu 14 dni).
- `summary`: wiadomość `invest_monthly` w dniu wypłaty (seria `payday_series_id`) przez istniejącą opcję
  `summary_notify_service` (alias `notify.family`): „odłóż X: A tu, B tam” albo „nadwyżki brak”.
- `ask/sources.py`: źródło `invest` (koszyki, rekomendacja, top 3 opcje; tylko kwoty).
- LLM: 2–3 zdania uzasadnienia rekomendacji (wejście = wynik silnika, zbiorczo).
- Wydanie: `code-review` → `release`. Na żywo: dzwonek, podgląd treści pusha bez wysyłki, 1 pytanie do czatu = ekran.
- Rollback: backup add-onu, cofnięcie do 0.57.0.

### E5 — Śledzenie promocji (dawne M17) → **wydanie 0.59.0**
- Migracja 025 (024 zajęła E3): `promo_track` (oferta, bank, okres, start/koniec, premia, status), `promo_condition`
  (typ: liczba płatności kartą / suma wpływów / saldo na dzień / ręczny krok, próg, okres).
- „Skorzystaj” przy ofercie tworzy śledzenie z warunkami wstępnie wyciągniętymi z tekstu oferty (LLM jako propozycja,
  edytowalne). Postęp z księgi tylko dla kont Millennium (uogólniony licznik z `card.py`), dla innych banków ręczne odhaczanie.
- Przypomnienia przed końcem okresu (dzwonek + push, jak M15 E1), rejestr należnych i wypłaconych premii.
  Wypłacona premia trafia do `invest_asset` albo do wpływów.
- Wydanie: `code-review` → `release`. Na żywo: jedna promocja testowa z warunkiem ręcznym i z licznikiem z księgi.
- Rollback: backup add-onu, cofnięcie do 0.58.0.

### E5 — wynik (2026-10-19, **0.59.0**)
Kroki 1–7 zrobione wg listy niżej; po `simplify` i `code-review` dodano: blokadę duplikatu śledzenia oferty, niezmienność odebranej promocji, wpływy bez przelewów własnych (`transfer_group`), obsługę `PiggyError` w trasach i propozycjach AI. Decyzje wykonawcze jak niżej. Nie zrobione świadomie: wspólny harmonogram przypomnień (dzwonek 7 dni, push 5 i 1), N+1 po warunkach.

### E5 — start (plan kroków)
Stan: `main` HEAD `d4725fe` (osobny commit `User-Agent` w `suggest/client.py`, niewypchnięty), produkcja 0.58.0.
Kolejność po odnowieniu limitu (tdd, każdy krok: pytest + ruff + mypy):
1. Migracja `025_promo_track.sql`: `promo_track` (offer_id, bank, tytuł, start, koniec, premia, `ledger`, status active/paid/failed/cancelled,
   paid_at, paid_to) i `promo_condition` (track_id, kind payments/income/balance/manual, label, target, done, proposed).
2. `card.count_purchases(conn, start, end)` — uogólniony licznik (zakupy kartą, konta current/card, BOOK, kwota ujemna); `PAYMENT_WHERE` bez zmian.
3. `promo_track.py`: start ze „Skorzystaj”, postęp (payments z licznika, income = wpływy transfer_in/other na kontach current,
   balance i manual = ręczne odhaczanie; `ledger` tylko dla banku z „millen” w nazwie), `mark_paid` (do `invest_asset` albo tylko do wpływów),
   rejestr należnych/wypłaconych.
4. Propozycja warunków i premii przez LLM (`suggest.metered_call`, klucz `invest_usage`, schemat: bonus + lista warunków; wejście tylko tekst oferty;
   błąd/AI wyłączone → śledzenie bez warunków + komunikat „dodaj ręcznie”).
5. Przypomnienia: dostawca dzwonka `promo_track` (≤ 7 dni do końca i warunki niespełnione; „odbierz premię” po spełnieniu) oraz push w `summary.due`
   (dni `card.REMIND_DAYS` = 5 i 1, rodzaj per ścieżka `promo_track_<id>`).
6. Trasy w `routes_invest.py` + sekcja „Promocje w toku” i przycisk „Skorzystaj” w `invest.html`; weryfikacja devserve 390/1280 px.
7. `simplify` → `code-review` → `release` 0.59.0 (CHANGELOG: E5 + User-Agent), test na żywo: promocja z warunkiem ręcznym i licznikiem z księgi.
Decyzje wykonawcze do odnotowania w wyniku E5: warunki liczone w okresie całej promocji (bez osobnych okresów); „saldo na dzień” tylko ręczne.
Rollback: jak w E5 wyżej (backup add-onu, 0.58.0); migracja 025 addytywna.

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

## Wynik E1 (2026-10-19, ae7b09b)
- Zrobione: migracja `023_invest.sql` (`invest_asset`, `invest_offer` z `source`/`status`/`url` pod E2/E3, `invest_bank`
  — bez UI, filtr w E2), `invest.py`, `loan_sim.overpay_gain`, trasa `/invest` (`routes_invest.py`, `invest.html`),
  zakładka „Inwestycje” po „Kredyt”. Oferty obligacji (EDO/COI/TOS/ROR/DOR) wpisywane ręcznie: stawka 1. roku + marża.
- Weryfikacja: 988 testów, ruff i mypy czyste; trzy scenariusze liczone ręcznie ±1 zł (lokata, EDO 10 lat, nadpłata =
  zaoszczędzone odsetki na całym okresie); na kopii księgi 390/1280 px bez przepełnienia, cele dotyku ≥ 44 px,
  konsola czysta; konto M10 4% na 5 lat = 3 514 zł (ręcznie), nadpłata 20 tys. przy 6% ≈ 6,8 tys. zł.
- Decyzje wykonawcze: ETF nie jest polecany automatycznie (tylko w rankingu, z oznaczeniem ryzyka); konto promocyjne
  po okresie promocji liczone bez odsetek (konserwatywnie); kwota porównania domyślnie = nadwyżka × 12 (bez
  nadwyżki 10 000 zł przykładowo), horyzont 5 lat; nadwyżka = średnia pełnych miesięcy prognozy M18 minus
  zalecane wpłaty do skarbonek.
- Uwaga: kopia księgi z 02.10 nie ma wpływów, więc nadwyżka wyszła tam ujemna (deficyt) — ścieżkę „odłóż X” sprawdzają
  testy jednostkowe, na prawdziwych danych zobaczy ją użytkownik po wydaniu 0.57.0.

## Wynik E2 (2026-10-19, wydanie 0.57.0, 22f8939)
- Zrobione: `invest_sources.py` (`parse_bonds`, `parse_margin`, `parse_ranking`, `guess_bank`, `refresh`, `due`), harmonogram
  `Service.watch_invest` (raz na dobę, `checked` tylko po pełnym sukcesie), dostawca dzwonka `invest_source_error`,
  `invest`: `all_banks/save_bank/delete_bank/confirm_offer/is_hidden`, UI: „Moje banki”, „Do sprawdzenia”, „Z rankingu”.
  Bez migracji (tabele z E1).
- Sonda (krok 0): obligacjeskarbowe.pl i bankier.pl/smart/{lokaty,konta-oszczednosciowe} są renderowane po stronie
  serwera i parsują się stabilnie (robots.txt nie blokuje; `/e/lead…` blokuje, więc zapisujemy link do opisu). **Ranking nie
  ma pola „bank”** — decyzja usera: słownik banków + slug (`guess_bank`), nierozpoznane → status „review”. Na żywo
  rozpoznano 15/20 wpisów. Opłaty za wcześniejszy wykup z `invest.BONDS` potwierdzone na stronach serii (EDO 2,00;
  COI/TOS/DOR 0,70; ROR 0,50).
- Weryfikacja: 1020 testów, ruff i mypy czyste; devserve na kopii księgi z prawdziwą siecią (390/1280 px, bez przepełnienia,
  konsola czysta, cele dotyku ≥ 44 px); na żywo przez Ingress: wersja 0.57.0, `/invest` 200, 25 ofert, stawki i marże
  obligacji = oficjalna strona. Code-review (high) → poprawki w b6ba74a (klucz oferty bez stawki, odrzucanie tylko ofert
  z rankingu, ponowienie po błędzie, niepełna strona obligacji = błąd, długość promocji tylko z fraz o oprocentowaniu).
- Znane ograniczenia: limity kwot („do 100 000 zł”) wyciągane tylko tam, gdzie są w tekście (3/20); `is_client` dopasowuje po
  słowie („Santander” ukryje też „Santander Consumer Bank”); „3 opcje = przeliczenie ±1 zł” na prawdziwych danych zobaczy
  user (kopia księgi bez wpływów).

## Wynik E3 (2026-10-19, ab5811c)
- Zrobione: `invest_blogs.py` (`parse_feed`, `wanted`, `parse_offers`, `refresh`), migracja `024_invest_blog.sql`
  (`extracted`, `verdict`), `invest.confirm_offer` z polami stawka/limit/okres/warunki i werdyktem `clean`/`fixed`,
  `invest.blog_accuracy`, opcja `invest_daily_calls` (domyślnie 10), UI „Do sprawdzenia” z formularzem poprawek,
  karta „Oferty z blogów — trafność” na Status (w sekcji AI). Odczyt razem z ofertami z sieci (raz na dobę).
- Krok 0 (sonda kanałów): działają subiektywnieofinansach.pl, jakoszczedzacpieniadze.pl (pisze rzadko), livesmarter.pl,
  jakdorobic.pl (kanał ma tylko stopkę — model widzi sam tytuł, zwykle ze stawką) i bankobranie.pl (`/rss.xml`, najlepszy:
  serwis promocji, streszczenia ~1500 znaków). Nie ma kanału bankier.pl/promocje; część blogów za Cloudflare.
  Streszczenia z RSS wystarczają (stawka, okres, limit), więc artykułów nie pobieramy. Lista `FEEDS` w kodzie.
- Pomiar na żywo (model `auto:text`, 16 ofert z 5 blogów, 2026-10-19), sprawdzone ręcznie ze źródłem: 14/16 bez poprawek
  (87,5%, cel ≥ 80%). Dwie oferty VeloBanku bez okresu („92 dni”) — prompt poprawiony (dni → miesiące, nie powtórzono pomiaru).
  Nie wyciągnięto lokat powitalnych z bankobranie (recall niemierzony). Pomiar „≥ 8/10” na ekranie Status robi user przy
  potwierdzaniu.
- Weryfikacja: 1043 testów, ruff i mypy czyste; devserve na pustej księdze z prawdziwą siecią i modelem, 390/1280 px bez
  przepełnienia, konsola czysta; przyciski i pola ≥ 44 px (zostają śródtekstowe linki „opis oferty”). Żywy test wyłapał
  błąd strefy czasowej (`Service.now()` ma strefę, RSS też — naiwne porównanie rzucało) — regresja w testach.
- Decyzje wykonawcze (poza planem): brak karty dzwonka dla błędu blogów (błąd modelu bywa chwilowy; widać go na `/invest`
  i Status); oferty z bloga starzeją się po 60 dniach (archiwizacja), wpisy starsze niż 30 dni pomijane; filtr wpisu = „lokat”
  lub „oszczędnościow” oraz „%”; blogi: 2 błędy modelu z rzędu kończą przebieg, 3 próby na wpis; kanały z DTD odrzucane (XXE).
- Pominięte z `simplify`: wspólny helper błędów źródeł (też `wibor.py`), wspólny INSERT do `invest_offer`, rejestr źródeł.

## Wynik E4 (2026-10-19, wydanie 0.58.0 razem z E3, 4043456)
- Zrobione: `invest.advice` (wspólne dla `/invest`, pusha i czatu; opcjonalna kwota i horyzont), `better_offers`/`maturities`,
  próg „lepsza oferta” w ustawieniach agenta (`better_offer`, domyślnie 200 zł/rok), dostawcy dzwonka `invest_better_offer`
  i `invest_maturity` (14 dni), `summary.invest_message` + `Service.invest_due` (push `invest_monthly` w oknie 3 dni po
  wykryciu wypłaty, raz na wypłatę), źródło czatu `invest` (do LLM rodzaje opcji, bez nazw), `invest_why` (2–3 zdania od
  modelu z kwot zbiorczych; odcisk wejścia w kv, wywołanie tylko po zmianie rekomendacji, rezerwa +1 ponad `invest_daily_calls`).
- Weryfikacja: 1060 testów, ruff i mypy czyste; devserve 390/1280 px bez przepełnienia, konsola czysta; `simplify` (4 agenci)
  i `code-review` high (10 uwag, naprawione: `error_since` po wyzdrowieniu, link tylko http(s), dedup ofert z blogów,
  okno pusha, redakcja nazw w czacie, `InvestError` przy złym limicie, try/except wokół watcherów). Na żywo (Ingress):
  0.58.0, `/invest` 200, pole progu, „Do sprawdzenia (4)”, karta „Oferty z blogów — trafność” na Status, konsola czysta.
- Do sprawdzenia przez usera: pomiar trafności „≥ 8/10” (potwierdzanie ofert z blogów); brak kart dzwonka na żywo jest
  oczekiwany (brak potwierdzonej oferty bijącej konto o ≥ 200 zł i brak terminów w 14 dni); uzasadnienie pojawi się dopiero
  przy nadwyżce (dziś deficyt −2 887 zł); pierwszy push po wypłacie — do zaobserwowania.
- Znane ograniczenia: dzwonek liczy `better_offers` przy każdym renderze (tanie przy kilku kontach/ofertach, bez memo);
  porównanie lokaty z kontem płynnym jest roczne (opis w karcie wspomina o blokadzie środków).
