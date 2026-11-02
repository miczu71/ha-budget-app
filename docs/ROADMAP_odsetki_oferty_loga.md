# Budżet: odsetki automatycznie, zwięzłe oferty, loga banków

Repo `/config/addons/ha-budget-app` (PUBLIC, gałąź `main`, na produkcji 0.70.1). Jedno wydanie na koniec: **0.71.0**.

## Status
- **E1 ZROBIONE 2026-11-02** (commit a72df9b, lokalnie, bez pusha): typ `interest`, kategoria Odsetki (id 103), migracja 030, `ledger._analyze` pomija `interest`. Weryfikacja: verifier APPROVE, pytest 1350 ok, ruff i mypy czyste.
- **Znany czerwony test sprzed E1:** `tests/test_invest_blogs.py::test_expired_blog_offers_are_archived` pada też na czystym main (data testu? dziś 2026-11-02). Do zbadania i naprawienia PRZED wydaniem (CI).
- **E1b ZROBIONE 2026-11-02** (commit a33a69f, lokalnie, bez pusha): migracja 031 `savings_interest`, `savings.record_interest/delete_interest/interest_entries`, `estimate()` używa wpisu zamiast `net(gross)`, formularz na `/piggy`, karta w dzwonku 1.–7. dnia. Weryfikacja: verifier APPROVE (mutacje wykryte), pytest 1357 ok + 1 znany czerwony, ruff i mypy czyste. Odstępstwa: `CREATE TABLE IF NOT EXISTS` (test_sessions cofa user_version), lista 6 wpisów. Nieblokujące: brak walidacji miesiąca przed `opening_date`; testy inbox w `test_savings.py`.
- E2, E3, wydanie 0.71.0: do zrobienia.

## Kontekst
1. 31.10 VeloBank zaksięgował na koncie oszczędnościowym „Odsetki - Kapitalizacja odsetek” +149,03 zł i „Podatek od odsetek” −28,32 zł. Add-on uznaje je za zwykłe przelewy (`Kind.TRANSFER_IN/OUT`), więc user skategoryzował oba ręcznie. Decyzja: oba wpisy automatycznie trafiają do nowej podkategorii **Przychody → Odsetki**, więc kategoria pokazuje kwotę netto po podatku Belki.
2. Inwestycje → Oferty → „Do sprawdzenia”: każdy wiersz pokazuje od razu formularz z 5 polami i przyciskami, przez co sekcja jest zbyt rozbudowana. Docelowo każdy wiersz to kilka krótkich wierszy, a reszta jest rozwijana.
3. Logo banku przy każdej nazwie banku w panelu. Decyzja: prawdziwe loga w SVG w repo, a dla nieznanego banku monogram w SVG.

Kto korzysta: user w panelu (telefon i komputer). Automatycznie: kategoria odsetek przy każdej synchronizacji. Bez zgody: nic poza planem. Po czym poznamy sukces: oba wpisy z 31.10 mają kategorię „Odsetki” (źródło „typ”, nie „ręczna”), oferta „do sprawdzenia” zajmuje najwyżej ~4 linie i nie ma przepełnienia poziomego na 390 px, a loga są widoczne na ekranach Inwestycje, Skarbonki, Konta i Transakcje.

## Etapy (`docs/ROADMAP_odsetki_oferty_loga.md` + `docs/PLAN_odsetki_E1.md` itd., pierwszy krok implementacji)

### E1 — Odsetki: rozpoznawanie i kategoria (fundament, ryzyko: migracja → `sonnet-worker`)
- `kinds.py`: `Kind.INTEREST = "interest"` + etykieta „odsetki”. W `from_api` (przed gałęzią `counterparty_account`) i w `_CSV_FALLBACK`/`from_csv` rozpoznawać opisy `KAPITALIZACJA ODSETEK` oraz `PODATEK OD ODSETEK` (po `fold`), w obu kierunkach.
- Migracja `030_interest.sql`: podkategoria `odsetki` „Odsetki” (`parent 1`, `income`, sort 25, wolne id sprawdzić w 003). `UPDATE txn SET kind='interest'` dla pasujących opisów (bez `kind_source='manual'`). Ręczna kategoria tylko na tych wierszach zostaje zwolniona (`category_source` NULL), bo user właśnie o to prosi. Dotyczy to 2 wierszy na żywo.
- `categorize/engine.py`: `KIND_DEFAULTS[Kind.INTEREST] = "odsetki"`. Sprawdzić testem, czy wpis nie wpada wcześniej w `savings`/`transfer` (kolejność w `_classify`). Jeśli wpada, `INTEREST` musi mieć pierwszeństwo przed `t.savings`.
- Wiersz odsetek/podatku nie oferuje „ze skarbonki” (dziś podatek pokazuje wybór skarbonki), czyli `Kind.INTEREST` nie jest przelewem własnym.
- TDD: testy kinds (oba opisy, Millennium „ODSETKI:” w racie kredytu NIE jest INTEREST), migracji (schemat 30, zwolnienie ręcznej) i engine (kategoria `odsetki`, źródło `kind`).
- Rollback: `git revert`. Migracja jest addytywna, a cofnięcie oznacza ponowną ręczną kategorię 2 wpisów.

### E1b — Ręczne dopisywanie odsetek dla konta bez API (Millennium Profit; ryzyko: migracja → `sonnet-worker`)
Millennium nie udostępnia konta oszczędnościowego przez Enable Banking, więc saldo konta „Profit” to dziś wpisane saldo + przelewy po numerze + **szacunek** odsetek (`savings.estimate`, kapitalizacja na koniec miesiąca). User chce po każdej miesięcznej kapitalizacji wpisać kwotę, którą bank faktycznie dopisał.
- Migracja `031_savings_interest.sql`: tabela `savings_interest(id, account_id → savings_account, month TEXT 'YYYY-MM', amount TEXT /netto/, created_at, UNIQUE(account_id, month))`.
- `savings.py`: `record_interest(conn, account_id, month, amount)` (walidacja `Decimal` ≥ 0, upsert, tylko konta bez powiązania z księgą) i `delete_interest`. W `estimate()` przy kapitalizacji na koniec miesiąca: jeśli dla tego miesiąca jest wpis, saldo rośnie o kwotę **wpisaną** zamiast `net(gross)`. Bieżący miesiąc nadal liczy się jako szacunek `accrued`. Zmiana działa w Skarbonkach, Majątku, Inwestycjach i czacie, bo wszystkie biorą `estimate`.
- UI `/piggy` na karcie konta niepowiązanego: linia „Odsetki dopisane przez bank” z ostatnimi wpisami (miesiąc, kwota, różnica względem szacunku) i formularzem „Dopisz odsetki”. Formularz ma miesiąc (domyślnie poprzedni) i kwotę netto po Belce (podpowiedź = szacunek za ten miesiąc). Wpisy można usuwać. Trasy `POST /piggy/savings/{id}/interest` i `.../interest/{iid}/delete`.
- Dzwonek: 1.–7. dnia miesiąca, jeśli konto niepowiązane miało w poprzednim miesiącu saldo > 0 i nie ma wpisu za ten miesiąc, pojawia się „Dopisz odsetki za <miesiąc> na <konto>” (link do formularza). Bez push.
- TDD: kapitalizacja z wpisem vs bez, upsert tego samego miesiąca, odrzucenie wpisu dla konta z API, dzwonek (saldo 0 → brak, wpis istnieje → brak).
- Rollback: revert. Tabela jest addytywna, a bez wpisów wynik jest identyczny jak dziś.

### E2 — Zwięzły wiersz oferty (`web/templates/invest.html` makro `offer_row`, `app.css`)
- Widoczne zawsze (≤4 krótkie linie): logo i bank, rodzaj; stawka · okres · limit w jednej linii; warunki obcięte do jednej linii (`text-overflow: ellipsis`); źródło · „opis oferty” · plakietka „tylko dla nowych”.
- W `<details class="offer-more"><summary>Szczegóły</summary>` trafiają: pełne warunki, formularz poprawek i „Potwierdź”, „Skorzystaj”, „Odrzuć/Usuń”, notka „pominięta — jesteś klientem”.
- Dotyczy wszystkich list ofert (Do sprawdzenia, potwierdzone, Z rankingu), bo makro jest wspólne. Projekt skillem `impeccable`, nowe klasy unikalne (pułapka `.bar`/`.grid`).
- Test: szablon renderuje `<details>` z formularzem dla `status=review`, bez przepełnienia na 390 px (devserve + Playwright).
- Rollback: revert commitu.

### E3 — Loga banków (`bank_logos.py`, `web/static/banks/*.svg`, filtr Jinja)
- `budget/bank_logos.py`: lista (slug, wzorce nazw) dla ok. 20 banków z ofert i księgi: VeloBank, Millennium, Pekao, ING, mBank, Alior, Erste, BNP Paribas, Raiffeisen, Pocztowy, Inbank, Volkswagen Bank, Renault Bank, CA Auto Bank, BFF, Skarb Państwa (obligacje), PKO BP, Santander, Citi, Nest. Dopasowanie po słowach jak w `invest.is_client` („ING More”, „ING Bank” (pełna nazwa) → ing; „Bank Pekao”/„Pekao” → pekao; „VeloBank” z dopiskiem spółki → velobank).
- SVG: Simple Icons/iconify, gdzie są, a resztę z oficjalnych stron i Wikimedia Commons. Źródło i licencja każdego pliku w `web/static/banks/SOURCES.md` przed commitem. Pliki zoptymalizowane, kwadratowy kafelek 20 px.
- Filtr `bank_logo(name)` w `web/common.py` daje `<img class="bank-logo" src=static/banks/x.svg alt="">` albo inline SVG z monogramem (inicjały, kolor z hasha nazwy). Do `package-data` dodać `web/static/banks/*` (test `test_addon_config.py`).
- Użycie: Inwestycje (oferty, promocje, rotacja, Moje banki), Skarbonki (karty kont), Konta (`accounts.html`), Transakcje (bank konta w szczegółach wiersza).
- Test: mapowanie nazw, z których każda z listy wyżej trafia w plik, który istnieje; nieznana nazwa daje monogram; pakowanie.
- Rollback: revert, bo zmiana dotyczy tylko UI.

E1 i E1b robi `sonnet-worker` (ryzyko: migracja), a E2 i E3 `haiku-worker` w worktree z `wt new`. Każdy etap kończy `verifier` + claimcheck, a potem `stage-end`.

## Wydanie 0.71.0 (po E3, bez pytania)
`simplify` → `code-review` (+ `silent-failure-hunter`, `pr-test-analyzer`, security subagent na `v0.70.1..HEAD`) → skill `release` (bump `config.yaml`, opublikowany release) → `ha_manage_updates install backup=true`.

## Weryfikacja
- Lokalnie: `BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, `ruff`, `mypy` w `budget/app`.
- E1b na żywo: na `/piggy` przy koncie Profit jest formularz „Dopisz odsetki” (wpis robi user, ja nie wpisuję kwot). Po wpisie saldo = poprzednie + wpis.
- Na żywo (Ingress, playwright-ha, odczyt): `/transactions?q=odsetk` pokazuje 2 wpisy z 31.10 w kategorii „Odsetki”, źródło nie „ręczna”. `/invest#offers` przy oknie 390 px: `scrollWidth ≤ innerWidth`, wiersz „do sprawdzenia” ≤ ~120 px wysokości, w `<details>` jest formularz. Na `/invest`, `/piggy` i `/accounts` przy każdej nazwie banku jest `img.bank-logo` albo monogram, a w konsoli nie ma 404.
