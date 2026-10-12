# M9 — Hipoteka: nadpłacać czy oszczędzać

## Context
Kolejny etap roadmapy budżetu wybrany 2026-10-12: M9. Prawdziwy cel z wywiadu: **rozstrzygnąć, czy
wolną gotówkę nadpłacić w kredycie hipotecznym, czy odłożyć na konto oszczędnościowe** (Profit, M10).
Harmonogram i pozostały kapitał to tylko podstawa tego wyliczenia. Majątek netto wypada z M9 do nowego
etapu M26 (backlog).

### Ograniczenia z wywiadu (2026-10-12)
1. **Kto korzysta:** użytkownik na ekranie „Kredyt” w panelu; jeden rozbudowany kalkulator scenariuszy
   (suwaki: nadpłata jednorazowa/miesięczna, zmiana WIBOR, zmiana marży, stopa oszczędności) → korzyść
   z nadpłaty (oba warianty: krótszy okres / niższa rata) obok odsetek netto z oszczędności + tabela
   wariantów WIBOR. Bez powiadomień o decyzji.
2. **Dane:** parametry wpisane ręcznie (kapitał na dzień, WIBOR/WIRON + marża — oprocentowanie zmienne,
   raty równe/malejące, data końca lub liczba rat). Add-on sam liczy harmonogram, przy założeniu stałej
   bieżącej stopy.
3. **Automatycznie:** raty z księgi (seria `loan`) zmniejszają kapitał według harmonogramu; gdy rata w
   księdze odbiega od wyliczonej ponad próg → dzwonek „zmieniła się stopa? wpisz nową”. Korekta salda
   ręcznie w każdej chwili. Encje HA `sensor.budget_loan_*`.
4. **Stopa porównawcza:** domyślnie efektywna z konta oszczędnościowego (promocja do końca okresu i do
   limitu kwoty, potem stopa bazowa, po Belce 19%) + pole do nadpisania inną stopą + checkbox „zawsze
   korzystam z promocji” (stawka promocyjna przez cały horyzont, do limitu kwoty).
5. **Sukces:** harmonogram zgodny z parametrami (rata wyliczona = rata z banku ±1 zł); po wpisaniu kwoty
   widzę jednoznacznie, która opcja daje więcej i o ile (zł w horyzoncie + stopy obok siebie).

Poza zakresem: majątek netto (→ M26), źródło dla czatu (→ dopisane do listy M12 E3b), parser PDF
harmonogramu, prognoza WIBOR, prowizja za nadpłatę (po 3 latach przy zmiennej = 0; jeśli trzeba — pole w E3).

## Repo i gałąź
`/config/addons/ha-budget-app` (miczu71/ha-budget-app), gałąź `main`. Kod w `budget/app/src/budget/`.

## Etapy (commity; jedno wydanie 0.43.0 na koniec, razem z niewydanym `f044cef`)
**E0 — dokumenty (pierwszy krok, przed kodem):** `docs/PLAN_M9.md` (ten plan + wywiad), w `docs/ROADMAP.md`
przepisany wiersz i sekcja M9, nowy wiersz M26 „Majątek netto”, kredyt dopisany do źródeł M12 E3b,
nowa decyzja (28) „nadpłata vs oszczędności”; przy okazji statusy checkpointów M10 E1 i M21 E5 → zamknięte
(wg notatki pamięci z 0.40.0 — potwierdzę z użytkownikiem). Commit.

**E1 — model kredytu i harmonogram (wartość: widzę, ile zostało):**
- migracja `015_loan.sql`: tabela `loan` (nazwa, kapitał, dzień stanu, stopa referencyjna, marża,
  rodzaj rat `equal|decreasing`, data ostatniej raty, dzień raty, `series_id` NULL, archiwum) +
  `loan_event` (korekty salda / zmiany stopy z datą) — dane tylko w bazie, nigdy w repo.
- `loan.py` (wzorzec jak `savings.py`: dataclass, `save`, `get`, `all_loans`): `schedule(loan, from_day)`
  — raty annuitetowe i malejące, odsetki dzienne/miesięczne jak w banku (30/360 vs act/365 — wybór
  w PLAN po sprawdzeniu z ratą z księgi), `summary()` → pozostały kapitał, rata, odsetki do końca, data spłaty.
- `web/routes_loan.py` + `templates/loan.html`: ekran „Kredyt” (formularz parametrów, kafelki, harmonogram
  zwinięty po 12 ratach); link w nawigacji/menu wg istniejącego wzorca (`routes_piggy.py`).
- Testy jednostkowe harmonogramu na neutralnych liczbach (znane wartości z kalkulatora annuitetu).

**E2 — połączenie z księgą + encje:**
- powiązanie z serią `loan` (wybór serii na ekranie Kredyt, jak link serii → skarbonka w Cyklicznych);
  zaksięgowane raty przesuwają stan wg harmonogramu (`loan.current(conn, loan, today)`).
- dostawca dzwonka `inbox.loan_rate_changed` (rata z księgi vs wyliczona > próg, np. 1%).
- `ha_publisher`: `sensor.budget_loan_principal` (atrybuty: rate, installment, payoff_date, interest_left).

**E3 — jeden rozbudowany kalkulator scenariuszy (wartość: decyzja)** — zmiana po wywiadzie: kalkulator
symuluje też zmiany WIBOR i marży, nie tylko nadpłatę. Bez zapisywania scenariuszy w bazie.
- **E3a silnik** `loan.simulate(loan, scenario, day)`; `Scenario` = nadpłata jednorazowa (kwota, data),
  nadpłata co miesiąc (kwota), wariant `shorten|lower_installment`, zmiana WIBOR ±pp od daty, nowa marża
  od daty, horyzont H (12 mies. / 5 lat / do końca kredytu), stopa oszczędności (efektywna z konta albo
  nadpisana) i flaga „zawsze promocja”. Wynik: rata (przed/po zmianach), data spłaty, odsetki do końca,
  odsetki uniknięte vs scenariusz bazowy, odsetki netto z tej samej kwoty na koncie w horyzoncie H
  (reużycie `savings._daily/_net`, `PROMO_FUNDS_MAX`, `PROMO_DAYS`), werdykt „nadpłata/oszczędności +X zł”
  i stopy obok siebie (próg opłacalności). Testy na neutralnych liczbach, w tym nadpłata miesięczna × zmiana WIBOR.
- **E3b ekran:** sekcja „Kalkulator” na ekranie Kredyt — suwaki/pola (htmx, przeliczenie na bieżąco
  z debounce), kafelki wyniku, pod spodem tabela wariantów: WIBOR −1 / 0 / +1 / +2 pp × bez nadpłaty /
  krótszy okres / niższa rata (rata, data spłaty, odsetki do końca), z bieżącą kwotą nadpłaty i marżą
  z suwaków. Mobile-first (360 px: tabela przewijana poziomo w swoim kontenerze), skill `impeccable`,
  weryfikacja Playwright.

**Wydanie:** skill `simplify` → `release` (0.43.0, CHANGELOG, cache-busting), weryfikacja na żywo przez
Ingress (playwright-ha): ekran Kredyt, encja w HA. Użytkownik wpisuje parametry kredytu sam w UI.

## Ryzyka
- Konwencja naliczania odsetek banku nieznana → rata może odbiegać o grosze/złotówki; E1 kalibruje na
  racie z księgi (próg ±1 zł), a w razie różnicy pytam.
- Nowa migracja addytywna (cofnięcie: zostawić tabelę; backup add-onu przed instalacją w `release`).
- Skaner prywatności: w testach/docs bez nazwy banku z kwotami użytkownika, neutralne liczby.
- Okno 02:45–03:15 bez pushy.

## Weryfikacja
- `uv run pytest` (cały zestaw, dziś 757 testów) zielony po każdym etapie.
- E1: harmonogram dla przykładu z kalkulatora annuitetu zgodny co do grosza; na kopii księgi
  (`~/budget_dev`) rata wyliczona vs rata z serii `loan` ±1 zł.
- E3: ręczne przeliczenie jednego scenariusza (X, H, stopy) zgodne z wynikiem ekranu.
- UI: devserve na kopii księgi + Playwright (screenshot telefon/desktop, konsola bez błędów), potem
  na żywo po wydaniu.

## Wynik (2026-10-12)
- **E0** dokumenty: commit 9838745 (plan, decyzja 28, M26, kredyt w źródłach M12 E3b).
- **E1** 336b990: migracja 015 (`loan`), `loan.py` (rata równa/malejąca, odsetki act/365, ostatnia rata
  domyka saldo), ekran `/loan`, zakładka „Kredyt”. Odstępstwo od planu: bez tabeli `loan_event` — nowy
  kapitał lub stopa to korekta wiersza (jak w `savings_account`).
- **E2** 8969be3: stan na dziś z harmonogramu, wybór serii rat, dzwonek `loan_rate` (rata w księdze inna niż
  w harmonogramie o > 1%), encja `sensor.budget_loan_principal`.
- **E3a** 92c0dd0: `loan.run` (wspólny silnik rat i scenariuszy), `loan_sim` (porównanie z oszczędnościami,
  tabela WIBOR × wariant). Stopa z dnia raty obowiązuje za cały okres. `savings.daily/net` są publiczne.
- **E3b**: formularz i wynik htmx na `/loan` (`GET /loan/{id}/calc`), weryfikacja na 360 i 1280 px.
- Otwarte: kalibracja z prawdziwą ratą z banku (±1 zł) po wpisaniu kredytu przez użytkownika.
- **Wydanie 0.43.0** 2026-10-12: tag v0.43.0 na 3ee791f (zawiera też f044cef), migracja 015 sprawdzona na kopii księgi
  z 2.10, na żywo stopka v0.43.0 i `/loan` 200 `no-store`.
