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
