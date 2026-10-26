# M32 cd. 2 — Velobank w Oszczędnościach i prognozie (E10–E15, wydanie 0.65.0)

## Context
Po wydaniu 0.64.0 i dodaniu edycji Velo w „Promocje w toku” (14.10–13.01.2027, próg 5) user zgłosił 4 sprawy.
Fakty z produkcji (2026-10-26, odczyt przez Ingress) i z kodu:

1. **5 BLIK-ów w październiku są w Transakcjach** (konto #5 „Konto rozliczeniowe”, 22.10, 5 × −1 zł Siepomaga),
   ale z typem `transfer_out`. Weszły na 0.63.0, przed poprawką E6 (`kinds.from_api` zdejmuje prefiks „BLIK:”), a
   `promo_track.count_cashless` liczy tylko BLIK/kartę, stąd 0/5. `ledger.ingest_api` przy syncu nadpisuje `kind`
   z heurystyki, a okno syncu to ostatnie księgowanie − 5 dni (`sync_service.OVERLAP_DAYS`). Sync 13:30 powinien więc
   przestawić typ i dać 5/5. **Bez kodu, tylko weryfikacja.**
2. **Velo jako „parking” KOP Millennium.** `savings_account` id 2 ma `parking_for` = id 1. Formularz „Aktywuj promocję
   Nowe środki (Profit)” renderuje się dla każdego konta. Push Profit przez `savings.parked` → `summary._parked_note`
   każe przelać 67 130 zł z Velo na Profit, co przeczy rotacji z E4.
3. **Brak sekcji Velo.** Monitor `promo_watch_velo` (E3) widać tylko jako kartę dzwonka `velo_new_edition`, która
   nie da się zamknąć, wisi do `ends_by` i linkuje do `#promo` (sekcja Profit).
4. **Konta.** #5 ROR Velo ma `include_in_budget=1` (OK), #4 oszczędnościowe ma `include_in_budget=0` (OK), ale
   `kind='current'`. `forecast.read_balances` bierze saldo tylko z pierwszego konta `current` PLN (Millennium #1).

Przy okazji (code-review #2 z wydania): `rotation.recommend` liczy koniec z `Offer.ends_by()` = 12.11 + 92 = 12.02.2027,
a edycja usera kończy się 13.01.2027. Okno 14 dni zaczęłoby się po końcu promocji, więc rekomendacja przyszłaby za późno.

## Decyzje usera (2026-10-26)
- Velo = zwykłe konto promocyjne: zdjąć parking. Przelewy między dowolnymi kontami oszczędnościowymi w ≤7 dni
  liczą się jako „przeniesienie”. Push Profit nie dopisuje Velo (wynika z pustego `parked`).
- Karta Velo: formularz Profit tylko dla kont Millennium. Na karcie Velo promocja z „Promocje w toku” (koniec edycji,
  stawka z regulaminu, licznik X/5). Ręczne „Promocja do” nie jest źródłem dla Velo.
- Sekcja „Promocja Nowe środki w VeloBanku” + push o nowej edycji + karta dzwonka z „Widziałem”.
- Saldo „Konto”/„Wolne dziś” = suma rachunków PLN `current` z „w budżecie”.
- (po odrzuceniu planu) Przelewy między WŁASNYMI kontami (5 kont z API + ręczne konta oszczędnościowe: KOP Profit,
  Velo) wykrywane automatycznie i kategoryzowane jako **wewnętrzne** albo **na oszczędności** — etap E10b.

## Stan dziś (kod + produkcja)
- `ledger.rebuild_links` (L2): „własne” = tylko `account.iban`; para ±kwota ≤3 dni z sygnałem → `transfer_group`
  → bez kategorii i poza wszystkimi widokami (`spending`, `flex`, `review`, `recurring` filtrują `transfer_group IS NULL`).
- Skutek 1: 14.10 360° −67 130 → Velo oszczędnościowe (#4, poza budżetem) zniknęło jako „przelew własny”, choć z punktu
  widzenia budżetu to odłożenie pieniędzy. Sekcja „Oszczędności” w Wydatkach go nie widzi.
- Skutek 2: KOP Profit nie jest w księdze, więc 14.10 +67 130,98 „Przelew własny” z KOP nie ma pary ani sygnału; łapie go
  reguła usera „Nazwa właściciela + wpływ → Przelewy na oszczędności” (działa przypadkiem, po nazwisku, nie po numerze).
- Skutek 3: `promo_track` (warunek „wpływy” Millennium) liczy wpływ z KOP jako wpływ — zawyża postęp warunku.
- Stopa oszczędności (`savings.monthly_rates`) już działa po numerach (`piggy.transfers`), od kategorii nie zależy.

## Etapy
Repo `/config/addons/ha-budget-app`, `main`. Kod w worktree z `wt new`, test w worktree z `PYTHONPATH=src`, venv
`budget/app/.venv`: `pytest -q`, `ruff check src tests`, `mypy src`. Każdy etap to commit bez wydania.
Pierwszy krok implementacji: ten plan → `docs/PLAN_M32_E10.md` + wiersz w `docs/ROADMAP.md` (M32 cd. 2).

### E10 — Dane i weryfikacja licznika (bez kodu, ja przez panel)
1. Po syncu 13:30: „Promocje w toku” ma pokazać 5/5, a transakcje 22.10 typ BLIK. Jeśli nie → `diagnose` (stop).
2. Konto #4 na `/accounts`: rodzaj „oszczędnościowe” (`kind=savings`). Cofnięcie: z powrotem „rachunek”.
3. Po wydaniu 0.65.0 (wymaga E11): „Zmień” konto Velo w Oszczędnościach → „Parking dla: — zwykłe konto —”.
   Cofnięcie: ustawić z powrotem „Oszczędności Wspólne”.

### E10b — Automatyczne przelewy własne: wewnętrzne / na oszczędności (sonnet-worker, „ryzyko”: pieniądze)
**STATUS: ZROBIONE 2026-10-26, commit bee794c** — verifier ACCEPT; pytest 1277 passed (+8), ruff czysty, mypy 1 błąd baseline (`routes_home.py:121`). Do sprawdzenia na żywo po wydaniu: 14.10 i 22.10 oraz `include_in_budget=1` karty (spłata karty).
Cel add-onu: budżet pokazuje, ile wydaję i ile odkładam. Przesunięcie między rachunkami „w budżecie” to nic
(wewnętrzne). Wyjście pieniędzy do oszczędności to oszczędzanie, a powrót z oszczędności to jego odwrócenie; oba
mają być widoczne w sekcji „Oszczędności”, nie znikać i nie udawać przychodu.

Klasyfikacja kont (w kodzie, bez konfiguracji):
- **strona budżetowa** = konto księgi z `include_in_budget=1 AND kind != 'savings'` (360°, karta, EUR, ROR Velo);
- **strona oszczędności** = konto księgi poza budżetem albo `kind='savings'` (Velo #4) **oraz** numery
  `savings_account.account_number` (KOP Profit, który nie jest w księdze). Numery porównywane jako 26 cyfr NRB
  (jak `piggy.normalize_number` / `savings.linked_ledger_id`: bez spacji i „PL”).

Reguły (deterministyczne, w `ledger`):
1. Sygnał przelewu własnego (`_transfer_signal`) rozszerzony o numery `savings_account` (kontrahent = inny własny numer).
2. Para L2 (jak dziś: ±kwota, ≤3 dni, sygnał) **obie strony budżetowe** → `transfer_group` (wewnętrzny, bez kategorii) —
   bez zmian dla 360°↔ROR Velo, spłaty karty, WCZESN.SPL.
3. Para L2 **budżetowa ↔ oszczędności** → bez `transfer_group`; strona budżetowa = „przelew na oszczędności”.
4. Transakcja na koncie budżetowym bez pary, której kontrahent to numer strony oszczędności → „przelew na oszczędności”.
5. Obie strony poza budżetem → `transfer_group` jak dziś (poza widokami i tak).
- Nowa funkcja `ledger.savings_transfer_ids(conn) -> set[int]` (reguły 3–4; jedna wspólna funkcja par użyta też przez
  `rebuild_links`, żeby obie ścieżki nie rozjechały się).

Kategoryzacja (`categorize/engine.py`):
- `_load` oznacza `savings_transfer` z `ledger.savings_transfer_ids`; w `_classify` po `manual`, przed `transfer`/`rule`:
  kategoria slug `oszczednosci-przelewy` („Przelewy na oszczędności”, grupa `savings`), źródło `kind` (wbudowana
  kategoria, jak gotówka/opłaty — **bez migracji**, bo `category_source` ma CHECK). Kierunek wynika ze znaku: wypłata
  z oszczędności w sekcji „Oszczędności” odejmuje się (ta sama kategoria netto, jak dziś przez regułę usera).
- Ręczne kategorie zostają (manual wygrywa). Reguła usera „Nazwa właściciela…” zostaje, ale dla wpływów z KOP wygrywa teraz
  numer; dalej łapie przelewy z kont spoza listy (np. 14.09 +11 541,87).
- Docstring modułu: kolejność źródeł + „przelew na/z oszczędności (numer własnego konta)”.

`promo_track` (warunek „wpływy”): pomija `savings_transfer_ids` — przelew z własnych oszczędności nie jest wpływem.

Oczekiwany efekt na żywo (październik): 14.10 −67 130 (360°→Velo #4) i +67 130,98 (KOP→360°) w „Oszczędnościach”
z kategorią „Przelewy na oszczędności” (źródło „typ”), netto ≈ −0,98 zł; 22.10 −5/+5 (360°↔ROR Velo) dalej wewnętrzne.

- Testy (`tests/test_ledger*.py`, `tests/test_categorize*.py`, `tests/test_promo_track.py`), fixtures z neutralnymi
  numerami: (a) budżet↔budżet = grupa, bez kategorii; (b) budżet → konto księgi poza budżetem = bez grupy,
  kategoria oszczędności, źródło `kind`; (c) wpływ z numeru `savings_account` spoza księgi = kategoria oszczędności;
  (d) para bez numeru kontrahenta, sygnał po stronie oszczędności → strona budżetowa = oszczędności; (e) ręczna
  kategoria nie jest nadpisana; (f) reguła usera przegrywa z numerem; (g) warunek „wpływy” pomija wpływ z oszczędności;
  (h) spłata karty i WCZESN.SPL bez zmian.
- **Wykonawca:** pliki `src/budget/ledger.py`, `src/budget/categorize/engine.py`, `src/budget/promo_track.py`, testy j.w.
  DONE: nowe testy (a)–(h) zielone, cały `pytest -q` bez nowych faili, `ruff`, `mypy` czyste. NIE RÓB: migracji,
  zmian `category_source` CHECK, `savings.py`, `piggy.py`, szablonów, nowych kategorii, commitów.
- Rollback: revert commitu (bez migracji; `rebuild_derived` przelicza grupy i kategorie od zera przy syncu).

### E11 — Przeniesienia między wszystkimi kontami oszczędnościowymi (haiku-worker)
- `savings._paired(rows, parking)` → parowanie dowolnych dwóch RÓŻNYCH kont z `rows`: przeciwne kwoty, ≤ `PARK_DAYS`,
  |suma| ≤ `PARK_TOLERANCE`, każdy ruch w jednej parze. Usunąć parametr `parking` i jego budowę w `monthly_rates`.
  Docstringi i komentarz `Move.transfer` mówią „między kontami oszczędnościowymi”.
- Pole `parking_for`, `savings.parked` i `_parked_note` zostają: parking nadal działa dla Profit.
- Testy (`tests/test_savings*.py`): para KOP→Velo bez `parking_for` = przeniesienie; ruchy >7 dni albo różne kwoty =
  wpłata/wypłata; istniejący test parkingu dalej zielony.
- **Wykonawca:** pliki `src/budget/savings.py`, `tests/test_savings*.py`. DONE: pytest bez nowych faili, ruff, mypy
  czyste. NIE RÓB: migracji, `summary.py`, szablonów, wersji/CHANGELOG, commitów.

### E12 — Rotacja według edycji usera (sonnet-worker, „ryzyko”: pieniądze)
**STATUS: ZROBIONE 2026-10-26, commit 8bddc07** — verifier ACCEPT; pytest 1283 passed, ruff czysty, mypy 1 błąd baseline. Dodano `Recommendation.from_user`.
- `promo_track`: funkcja `active_for_bank(conn, bank_like, today) -> Track | None`. Aktywna edycja (status `active`,
  `start ≤ today ≤ end`) banku pasującego do wzorca (`instr(lower(bank), …)`, jak `card.count_purchases`); przy kilku
  wybiera najpóźniejszy `end`.
- `rotation.recommend`: koniec = `track.end`, jeśli jest edycja Velo, inaczej `offer.ends_by()`. `Recommendation.ends_by`
  i `days_left` z tej daty. Tekst: „kończy się {dd.mm}” przy edycji usera, „najpóźniej do” przy `ends_by`.
- Testy `tests/test_rotation.py`: z edycją 14.10–13.01 rekomendacja 30.12 jest, 13.02 jej nie ma; bez edycji jak dziś.
- **Wykonawca:** `src/budget/promo_track.py`, `src/budget/rotation.py`, `tests/test_rotation.py`, `tests/test_promo_track.py`.
  NIE RÓB: `summary.py` (progi 14/7/2 biorą `days_left`), migracji, szablonów.

### E13 — Karta konta Velo w Oszczędnościach (haiku-worker)
**STATUS: ZROBIONE 2026-10-26, commit d2286af** — verifier ACCEPT; pytest 1284, ruff czysty, mypy baseline. Stawka Velo tylko dla banku z „velo” w nazwie; ręczny stat znika dla kont spoza Millennium nawet bez edycji (zgodnie ze specem).
- `savings.ledger_bank(conn, acc) -> str | None`: bank konta z księgi przez `linked_ledger_id`.
- `routes_piggy`: do szablonu per konto `bank` oraz `promo` = (`track` z `promo_track.active_for_bank(bank)`, stawka
  `promo_watch_velo.rates(conn).promo_rate` albo None) dla kont banku innego niż Millennium (`promo_track.LEDGER_BANK`).
- `piggy.html`: `<details>` „Aktywuj promocję Nowe środki (Profit)” tylko, gdy bank jest None albo zawiera „millennium”.
  Dla konta z `promo`: stat „Promocja {stawka}% do {track.end}” + „BLIK/karta w tym miesiącu {X}/{próg}” (z `track.cashless`).
  Link do `/invest#promos`. Gdy brak edycji: „Dodaj edycję w Promocje w toku”. Ręczny stat promocji tylko bez `promo`.
- Test web (`tests/test_web_piggy*.py`): konto powiązane z kontem księgi banku „VeloBank” nie ma formularza Profit, ma
  „do 13.01.2027”; konto Millennium ma formularz.
- **Wykonawca:** `src/budget/savings.py`, `src/budget/web/routes_piggy.py`, `src/budget/web/templates/piggy.html`, test web.
  NIE RÓB: zmian `savings.estimate`, migracji, sekcji Profit.

### E14 — Sekcja Velo, push o nowej edycji, „Widziałem” (sonnet-worker)
- `promo_watch_velo`: w `kv` pole `acked` (etykieta edycji). Brak `acked` przy pierwszym poprawnym odczycie → zapis
  bieżącej etykiety (12/2026 bez pusha). Funkcje `ack(conn)` i `Watch.new_edition` (`offer` jest, nie `held`,
  `offer.label != acked`).
- `inbox.velo_promo_cards`: `velo_new_edition` tylko przy `new_edition`. Link wszystkich kart Velo → `/piggy#velo`.
- `summary`: `velo_edition_messages(watch)` → `Message(VELO_EDITION, offer.label, "Velobank — nowa edycja promocji {label}",
  stawki/termin/okres)`, wpięte obok `rotation_messages` (dedup przez istniejący mechanizm `mark_sent`).
  Stała `VELO_EDITION` w `notifications.py` wzorem `PROMO_CONFIRM`.
- `routes_piggy`: `POST /promo/velo/refresh` (`await promo_watch_velo.refresh(conn, now)` wzorem `/promo/refresh`),
  `POST /promo/velo/ack`.
- `piggy.html`: `<section class="card" id="velo">` „Promocja Nowe środki w VeloBanku” pod Profit. Edycja z regulaminu
  (stawki z/bez warunku, limit, wpłata do, okres, próg i sposoby), edycja usera (okres, licznik, link do
  `/invest#promos`), stan `held`/`error`, przyciski „Sprawdź teraz” i „Widziałem” (przy `new_edition`).
- Testy: `tests/test_promo_watch_velo.py` (pierwszy odczyt ustawia `acked`, nowa etykieta → `new_edition`, `ack` czyści),
  `tests/test_inbox*.py`, `tests/test_summary*.py` (push raz na etykietę), web (sekcja, oba POST).
- **Wykonawca:** pliki j.w. NIE RÓB: parsera regulaminu (`_parse*`), migracji, `rotation.py`.

### E15 — Saldo wszystkich rachunków PLN w budżecie (sonnet-worker, „ryzyko”: pieniądze)
- `forecast.read_balances`: `account` = suma po kontach `kind='current' AND currency='PLN' AND include_in_budget=1`
  (każde ITAV → ITBD). `pending` = suma (ITBD − ITAV)⁺ per konto. `fetched_at` = najstarszy. None tylko gdy żadne
  z tych kont nie ma migawki. Karta i EUR bez zmian.
- Szablon salda na Podsumowaniu („Rachunek X − karta …”): przy >1 koncie „Rachunki X”.
- Testy `tests/test_forecast*.py`: dwa rachunki w budżecie się sumują, rachunek spoza budżetu i `savings` nie,
  brak migawki jednego nie zeruje drugiego.
- **Wykonawca:** `src/budget/forecast.py`, szablon kafelka (z `routes_home.py:104–113`), testy forecast.
  NIE RÓB: `safe_per_day`, projekcji, `ha_publisher` (bierze `fc.balances`).

### Wydanie 0.65.0 (po E15, bez pytania)
`simplify` → równolegle `code-review` (high, `9724031..HEAD`) + `silent-failure-hunter` + `pr-test-analyzer` +
security (general-purpose) + druga opinia (pomiar 5/10) → poprawki BLOKUJĄCYCH → skill `release` (changelog po polsku,
neutralne nazwy, `config.yaml` + `pyproject.toml`) → `ha_manage_updates` z backupem add-onu → E10 krok 3 → weryfikacja.

## Weryfikacja na żywo (Playwright przez `/app/a9413a25_budget`, fetch w kontekście Ingress)
- „Promocje w toku”: Velo 5/5 (październik).
- Transakcje 14.10: −67 130 i +67 130,98 z kategorią „Przelewy na oszczędności” (źródło „typ”); 22.10 −5/+5 „przelew
  własny”. Wydatki 10.2026: sekcja „Oszczędności” netto ≈ −0,98 zł; brak nowych pozycji w kolejce przeglądu.
- Oszczędności: karta Velo bez formularza Profit, „Promocja 4,5% do 13.01.2027”, licznik. Sekcja `#velo` z edycją 12/2026.
  Stopa oszczędności 10.2026: 14.10 jako „przeniesienie” po zdjęciu parkingu.
- Dzwonek: brak `velo_new_edition` (12/2026 potwierdzona). „Sprawdź teraz” działa (log add-onu).
- Podsumowanie: „Konto” = Millennium + ROR Velo. `sensor.budget_forecast_free_now` zgodny. Konsola bez błędów, stopka v0.65.0.
- Rollback: reinstalacja 0.64.0 z backupu add-onu (brak migracji; `kv acked` stara wersja ignoruje), zmiany danych z E10
  cofane w panelu.
