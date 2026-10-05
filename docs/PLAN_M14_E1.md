# M14 E1 — Ledger snapshot (wydajność panelu)

Status: **plan zaakceptowany 2026-10-05**, kroki 1–5 lokalnie (bez pushu i wydania); wydanie (0.21.0) po osobnym „go”.
Zakres szeroki (seria + sumy + kategorie naraz) to decyzja użytkownika; rekomendacja była węższa (E1 tylko seria + inbox).

## Pomiar bazowy (produkcja, 0.20.3, 2026-10-05)
GET z iframe Ingress, mediana z 5 prób, czas do pierwszego bajtu.

| Ekran | ms | | Ekran | ms |
|---|---|---|---|---|
| `/healthz` (podłoga) | 22 | | `/review` | 715 |
| `/status` | 464 | | `/inbox` | 853 |
| `/spending` | 474 | | `/accounts` | 1126 |
| `/rules` | 534 | | `/budget` | 1320 |
| `/transactions` | 563 | | `/` | 1425 |
| wyszukiwanie w Transakcjach | 748 | | `/recurring` | 1698 |

Wnioski: (1) stały koszt ~450 ms na każdej stronie (`/status` prawie nic nie liczy) — zgodne z `inbox()` w `Panel.render`;
(2) `/healthz` w trakcie `/recurring` odpowiada po 1,5–2,5 s (pętla zdarzeń zablokowana — to kandydat 2, poza E1);
(3) na kopii dev (0 reguł, ~3 tys. transakcji) wszystko < 60 ms, więc pomiary robimy na produkcji.

## Ograniczenia
1. Wynik czytają: każda strona (dzwonek), Podsumowanie, Budżet, Cykliczne, publikator encji MQTT.
2. Automatycznie: cache unieważnia się sam. Push, release, backup i update add-onu dopiero po „go”.
3. **Sukces:** mediana z 5 prób na produkcji < 400 ms na każdym ekranie, `/` i `/recurring` < 600 ms (cache zimny po zapisie
   i ciepły mierzone osobno); w testach ≤ 1 przejście po księdze na stronę.
4. Bez zmian logiki, schematu i encji.

## Decyzje (wywiad 2026-10-05)
- **Sygnatura gruba:** `conn.total_changes` + `PRAGMA data_version` + dzień. Każdy zapis przez połączenie unieważnia całość;
  zmiana dnia też (inbox i „dziś” zależą od daty). Add-on ma jedno połączenie i jest jedynym pisarzem księgi.
- **Zakres:** przynależność do serii (`candidates` + `assign` + `facts`), `sums(start, end, skip)`, drzewo kategorii.
- **Kształt:** cache jako `service.snapshot`, funkcje przyjmują go jako parametr (bez ukrytego stanu globalnego przy `conn`).

## Kroki
1. Dokumenty: ten plik, wiersz M14 w `ROADMAP.md`, `CONTEXT.md` („Ledger snapshot”).
2. Testy najpierw: ≤ 1 `candidates`/`facts` na dwa renderowania `/`; zapis (reguła, seria, kategoria, kwota Flex) unieważnia;
   zmiana dnia unieważnia; zwrócone struktury nie dają się zmutować przez wywołującego.
3. Moduł `budget/snapshot.py` (sygnatura + trzy zapamiętane wyniki), własność `Service`.
4. Przepięcie wywołań, osobny commit na grupę: `flex.py`, `recurring/changes.py`, `recurring/schedule.py`,
   `web/routes_recurring.py`, `spending.py`, `inbox.py`, `ha_publisher.py`; z wywołań `taxonomy.*` tylko gorące ścieżki.
5. Weryfikacja: pytest, ruff, mypy, skill `simplify`, hook prywatności. Stop, pokazuję wynik.
6. (po „go”) 0.21.0: bump, CHANGELOG, push, CI, `gh release create`, backup add-onu, update, pomiar na produkcji.

## Cofanie
Kroki 1–5: lokalne commity (`git reset`/`revert`). Po wydaniu: backup add-onu z kroku 6 albo 0.21.1 z revertem.

## Ryzyka
Duży diff (commity per grupa wywołań); stare liczby przy błędnej sygnaturze (gruba sygnatura = małe ryzyko);
pierwszy odczyt po zapisie liczy „zimno”, jak dziś.

## Wynik lokalny (kroki 1–5, commit `945ca58`, bez pushu i wydania)
**Korekta zakresu (weryfikacja decyzji):** pomiar na kopii z 19 syntetycznymi seriami pokazał, że kosztuje `S.candidates`
(~14 ms, składnik każdego ciężkiego wywołania), a nie sumy (`sums` 0,4 ms, 12 miesięcy 4,4 ms) ani drzewo kategorii (0,2 ms).
Zakres zawężony do przynależności do serii; sumy i kategorie nie są cache'owane. Sygnatura bez dnia: nic zapamiętanego od
daty nie zależy. `Snapshot` nie zapisuje wyniku wewnątrz transakcji (`total_changes` nie maleje po ROLLBACK).
- Test stron: 6 żądań = 18 przebiegów po księdze przed, **1** po. 516 testów, ruff, mypy czyste.
- Lokalnie (ciepły cache): `inbox.items` 16,6 → 3,2 ms, `schedule.for_month` 14,4 → 1,7 ms, `flex.build` 19,1 → 5,6 ms.
- Świadomie pominięte po `simplify`: memo `assign` (≈1,3 ms lokalnie; zmierzyć na produkcji po wydaniu), `detect.run`
  (raz na sync), wspólny helper seedu w testach, scalenie z `BalanceMemo`.
- Do zmierzenia na produkcji po wydaniu: kryterium sukcesu z sekcji „Ograniczenia”.

## Wynik wydania 0.21.0 (2026-10-05, produkcja)
Wydane i zainstalowane (release v0.21.0, sha `5d96e74`, backup add-onu przed aktualizacją, `/healthz` = 0.21.0, konsola bez
błędów). Strony przed i po zrenderowane na kopii księgi z 19 seriami: 10 z 10 identyczne co do bajtu. CI: pierwszy run
anulowany przez GitHub po 15 min bez runnera (kolejka), ponowiony — zielony.

Pomiar GET z iframe Ingress, mediana z 5 prób (ms), przed → po:

| Ekran | przed | po | | Ekran | przed | po |
|---|---|---|---|---|---|---|
| `/` | 1425 | 440 | | `/transactions` | 563 | 244 |
| `/budget` | 1320 | 324 | | `/rules` | 534 | 212 |
| `/recurring` | 1698 | 318 | | `/status` | 464 | 258 |
| `/inbox` | 853 | 203 | | `/spending` | 474 | 267 |
| `/review` | 715 | 445 | | `/accounts` | 1126 | 865 |

`/healthz` w trakcie `/recurring`: 1,5–2,5 s → ~210 ms (zniknęło zamrażanie od tego żądania).

**Kryterium (< 400 ms, `/` i `/recurring` < 600 ms): spełnione na 8 z 10 ekranów.** Poza progiem: `/review` 445 ms (kandydat
„kolejka Do przejrzenia”) i `/accounts` 865 ms (nie dotknięte E1; przyczyna nieznana — do zdiagnozowania). Pomiar bywa
zaszumiony: pojedyncze piki 1,7–2 s (`/spending`, `/review`) w pierwszej minucie po restarcie add-onu.
Następne do decyzji: `/accounts`, kolejka Do przejrzenia, handlery poza pętlą zdarzeń, PRAGMA/indeksy.

## Wynik wydania 0.21.1 (2026-10-05, produkcja) — E1b: Konta i Import
Diagnoza `/accounts` (865 ms): ekran budował `report.build` (pełny raport dla CLI, m.in. `ledger.check_balances` = 72% czasu
na kopii), a szablon używał tylko listy kont. Poprawka: `report.accounts(conn)` dla Kont; `report.build(conn, balance_checks)`
z wynikiem z `BalanceMemo` dla Importu (CLI liczy sam). Testy: `/accounts` i `/import` po rozgrzaniu memo nie wołają
`check_balances` (czerwone przed, zielone po). 518 testów; `/accounts` i `/import` identyczne co do bajtu z 0.21.0.
Wydane: release v0.21.1 (sha `946d2ce`), CI zielone, backup add-onu przed aktualizacją, `/healthz` = 0.21.1, konsola bez błędów.

Pomiar GET z iframe Ingress, mediana z 5 prób (ms), 0.20.3 → 0.21.1:

| Ekran | 0.20.3 | 0.21.1 | | Ekran | 0.20.3 | 0.21.1 |
|---|---|---|---|---|---|---|
| `/` | 1425 | 438 | | `/transactions` | 563 | 238 |
| `/budget` | 1320 | 351 | | `/rules` | 534 | 217 |
| `/recurring` | 1698 | 308 | | `/status` | 464 | 130 |
| `/inbox` | 853 | 293 | | `/spending` | 474 | 183 |
| `/review` | 715 | 393 | | `/accounts` | 1126 | 125 |
| `/import` | — | 155 | | `/healthz` | 22 | 17 |

**Kryterium (< 400 ms, `/` i `/recurring` < 600 ms) spełnione na wszystkich 11 ekranach.** Pomiar zaszumiony (pojedynczy pik
2 s na `/inbox`; `/review` 445 w poprzednim pomiarze, 393 w tym — tuż pod progiem). Dalej do decyzji: kolejka Do przejrzenia
(najbliżej progu), handlery poza pętlą zdarzeń, PRAGMA/indeksy, zimny dzwonek po zapisie (`check_balances`).
