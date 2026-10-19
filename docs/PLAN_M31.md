# M31 — Budżet: usuwanie kart, kafelki sald, tydzień z dniem wypłaty, skarbonki w pełnych złotych

## Kontekst
Cztery prośby usera do add-onu Budżet Domowy (`/config/addons/ha-budget-app`, 0.54.0 na produkcji):
1. Karty „Do decyzji” można tylko ukryć (wracają po zmianie tytułu, są w „Przywróć ukryte”) — user chce je **usuwać na zawsze**.
2. Na Podsumowaniu nad hero **małe kafelki sald**: konto główne, karta kredytowa, suma oszczędności.
3. „Ten tydzień” kończy się dzień przed wypłatą — a wypłata przychodzi po południu, więc **dzień wypłaty należy jeszcze do starego okresu**.
4. Diagnoza „brakujących 0,02 zł” (zrobiona na żywo, `/piggy` przez Ingress): skarbonka Nabu — cel 330,23 zł / 11 mies. do 23.09.2027 = 30,0209 → zalecane 30,02 zł, user przelał 30,00 → „przelej 0,02 zł”. To zaokrąglenie, nie błąd danych. Decyzja usera: **zalecane odłożenie zaokrąglać w górę do pełnych złotych**.

Decyzje z wywiadu: Usuń = na zawsze (klucz karty rodzaj+tytuł), bez przywracania. Kafelki: konto = dostępne saldo, karta = bieżące zadłużenie, oszczędności = konta oszczędnościowe (z szac. odsetkami) + skarbonki; na kafelku podpis „w tym skarbonki X zł”, po najechaniu/dotknięciu lista skarbonek z kwotami.

Kto korzysta: user (panel w HA, telefon). Automatycznie: nic nowego poza przeliczeniem. Za zgodą: wydanie 0.55.0 (zgoda na plan obejmuje wydanie po ostatnim etapie). Sukces: przycisk „Usuń” działa i karta nie wraca; kafelki widoczne nad hero (telefon 390 px bez przewijania poziomego); tydzień kończy się w dniu wypłaty; Nabu pokazuje 31 zł zalecane.

Repo: `miczu71/ha-budget-app`, gałąź `main`, testy `cd budget/app && BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, ruff, mypy. Hook pre-commit prywatności musi istnieć (`test -x .git/hooks/pre-commit`). Krok 0: skopiować ten plan do `docs/PLAN_M31.md` i dopisać wiersz M31 do `docs/ROADMAP.md`. TDD w każdym etapie. Etapy = commity, jedno wydanie 0.55.0 na końcu.

## E1 — Usuń kartę „Do decyzji” na zawsze
- `budget/inbox.py`: nowy klucz kv `DELETED_KEY = "inbox_deleted"`; `delete(conn, key)` dopisuje klucz (bez przycinania — karty o stałym tytule, np. „Nowe płatności cykliczne”, wróciłyby po zniknięciu; to świadomie oznacza, że usunięcie karty o stałym tytule wycisza ją na stałe — opisane w tekście pomocy). `visible()` filtruje ukryte ∪ usunięte. `restore()` nie rusza usuniętych; `hidden_count` w `routes_inbox.py` liczy tylko ukryte (bez usuniętych).
- `web/routes_inbox.py`: `POST /inbox/delete` (key, back) jak `inbox_dismiss`.
- `web/templates/_macros.html`: makro `inbox_dismiss` dostaje drugi przycisk „Usuń” (ikona kosza SVG, `aria-label`, potwierdzenie `hx-confirm`/`onclick confirm` zgodnie z wzorcem w repo — sprawdzić, czego używa reszta panelu). Używane w `inbox.html` i kafelku `home.html`.
- `inbox.html`: tekst pomocy dopisuje „Usunięta nie wraca”.
- Encja HA `sensor.budget_inbox` korzysta z `service.inbox()` → `visible()`, więc usunięte znikną też tam.
- Testy: `test_web_home.py`/nowe w stylu istniejącego (l. 484): usunięta niewidoczna, nie wraca po `restore`, nie liczy się do „Przywróć ukryte”; route 303.
- Rollback: `git revert`; klucz kv `inbox_deleted` nieszkodliwy.

## E2 — Tydzień z dniem wypłaty
- `budget/forecast.py` `weeks()`: okres tygodni = **(dzień ostatniej wypłaty, dzień wypłaty]** — pętla `while ws <= payday`, `we = min(niedziela, payday)`; pierwszy tydzień zaczyna się dzień po `start` (dzień wypłaty należy do poprzedniego okresu). Zgodne z prognozą, która już liczy dzień wypłaty jako dzień wydatków (`project`: `while day <= end`, `safe_per_day` dzieli przez dni do wypłaty włącznie).
- `build()`: `weeks(start + 1 dzień, ...)` tylko dla tygodni i `spent_since`; `period_start` (etykieta „Od wypłaty 24.09”, `period_elapsed`) i `piggies_from` bez zmian (przelewy do skarbonek w dniu wypłaty dalej liczą się do nowego okresu). `period_plan` dalej kluczowany `start`.
- Skutek brzegowy: w dniu wypłaty po zaksięgowaniu pensji nowy okres nie ma jeszcze tygodnia „bieżącego” — linijka „Ten tydzień” znika do północy (akceptowalne, opisać w docstringu).
- Testy w `test_forecast.py` (l. 450–510): ostatni tydzień kończy się w dniu wypłaty, pierwszy zaczyna dzień po ostatniej wypłacie, limit bieżącego tygodnia liczy dzień wypłaty; poprawić istniejące asercje dat.
- Rollback: `git revert`.

## E3 — Zalecane odłożenie do skarbonki w pełnych złotych
- `budget/piggy.py` `statuses()`: `monthly = min(ceil((target − before) / months_left), target − before)` w pełnych złotych (`quantize(Decimal(1), ROUND_CEILING)`), ostatni miesiąc dobiera resztę z groszami (bo `before` rośnie, a `min` z brakującą kwotą). Bez zmian w `to_transfer`/`total_to_transfer`.
- Skutek na żywo: Nabu → zalecane 31 zł, przelane 30 → „przelej 1 zł” w tym okresie (user zdecydował, ostrzegę w raporcie).
- Testy `test_piggy.py` (l. 71 `316.67` → `317`, l. 87 itp.) + przypadek ostatniego miesiąca z groszami.
- Rollback: `git revert`.

## E4 — Kafelki sald nad hero
- `web/routes_home.py`: w bieżącym miesiącu przekazać `balances` (z `fc.balances`, gdy prognoza jest; inaczej `forecast.read_balances(conn)`), `sv` już jest (ale z `n=1` — użyć `sv.total`), `fc.piggies` (już policzone `piggy.statuses`) → suma sald skarbonek i lista (nazwa, saldo). Brak prognozy → skarbonki przez `piggy.statuses(snapshot, today, month_start)`.
- Nowy partial `web/templates/_balance_tiles.html` wstawiony w `home.html` tuż przed hero (tylko bieżący miesiąc i gdy są salda): trzy małe kafelki w rzędzie (siatka 3 kolumny, na telefonie też 3 wąskie — sprawdzić 390 px; fallback 2+1): „Konto” (dostępne), „Karta” (zadłużenie; bez karty — kafelek pominięty), „Oszczędności” (konta oszcz. + skarbonki, podpis „w tym skarbonki X zł”). Szczegóły skarbonek: `<details>`/popover otwierany hoverem na desktopie i dotknięciem na telefonie (CSS `:hover`/`:focus-within` + `tabindex`), lista nazwa–kwota. Każdy kafelek linkuje: konto → `/transactions`, karta → `/card`, oszczędności → `/piggy`.
- CSS w `web/static/app.css` (unikalne klasy `bal-tiles`, `bal-tile`, `bal-pop`), tokeny istniejące; projekt wg skilla `impeccable` z design systemem `design-system/` (Budżet — Monarch). Ikony tylko SVG.
- Kafelki nie są elementem układu `home_layout` (stałe nad hero, jak prosi user).
- Testy `test_web_home.py`: kafelki w HTML z kwotami, bez karty brak kafelka karty, lista skarbonek; w poprzednim miesiącu brak kafelków.
- Weryfikacja wizualna: devserve (skrypt w scratchpadzie wg notatki `budget_app_dev_environment`), Playwright 390 px i 1280 px, `scrollWidth <= innerWidth`, konsola bez błędów.
- Rollback: `git revert`.

## Wydanie 0.55.0
`simplify` → `code-review` → skill `release` (bump `budget/config.yaml`, CHANGELOG, opublikowany release, update przez `ha_manage_updates install backup=true` dla `update.budzet_domowy_update`), weryfikacja na żywo przez Ingress (pomiary w iframe, bez zrzutów z danymi): stopka v0.55.0, kafelki obecne, `/inbox` ma „Usuń”, „Ten tydzień” kończy się w dniu wypłaty, Nabu 31 zł. Bez commitów 02:45–03:15. Rollback: Supervisor przywraca backup add-onu albo wydanie 0.55.1 z revertem.

## Weryfikacja (każdy etap)
pytest + ruff + mypy zielone; commit z hookiem prywatności; raport + `stage-end` po każdym etapie.
