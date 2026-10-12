# M29 — Podział transakcji na kategorie + paragony Lidl Plus

## Context
Transakcja ma jedną podkategorię (`txn.category_id`), więc zakup w Lidlu ląduje w całości w „Spożywcze”, choć paragon
zawiera też drogerię (papier, dezodorant) i rzeczy dla dzieci (pieluszki, chusteczki). Cel: zakup rozbity na
podkategorie, każda część liczy się w swojej kategorii **wszędzie** (limity, wydatki, Podsumowanie, czat, oszczędności).
Add-on Lidl wystawia kategorię każdego produktu; Budżet sam dopasowuje paragon do płatności, linkuje paragon i dzieli zakup.
Realizuje pierwszą część M24 (paragony); inflacja osobista zostaje w M24. Po stronie Lidla: etap E6 (`ha-lidl-app`,
`docs/PLAN_E6_budzet.md`).

Decyzje (wywiad 2026-10-12, AskUserQuestion):
1. Podział na poziomie **podkategorii**; części liczą się we wszystkich wyliczeniach.
2. Ręczny podział: dowolna liczba wierszy, licznik „zostało do przydzielenia” na żywo, **„Zapisz” zablokowane, dopóki
   reszta ≠ 0,00 zł**.
3. Lidl wystawia 4 kategorie produktu (`food`, `drugstore`, `kids`, `nonfood`); Budżet mapuje je na podkategorie
   (domyślnie Spożywcze, Drogeria, Zakupy dla dzieci, Inne zakupy), mapa edytowalna.
4. Dopasowanie (kwota co do grosza, data ±3 dni, jedno trafienie) → link + podział **automatycznie**; ręczna kategoria
   lub ręczny podział nigdy nie są nadpisywane; niejednoznaczne → wybór w karcie transakcji.
5. Transport: plik `/share/lidl/receipts.json` zapisywany przez Lidl, czytany przez Budżet.
6. Zakres: cała wspólna historia, po backupie i z raportem przesunięć między podkategoriami.

Wydania: grupa A (E1–E3) = 0.49.0; grupa C (E4–E6) = 0.50.0 po wydaniu Lidla (E6 tam) z eksportem.

## E1 — Dane podziału (commit)
- Migracja `018_split.sql`: `txn_split(txn_id INTEGER NOT NULL REFERENCES txn(id) ON DELETE CASCADE, line INTEGER NOT NULL,
  category_id INTEGER NOT NULL REFERENCES category(id), amount TEXT NOT NULL, source TEXT NOT NULL CHECK (source IN ('manual','lidl')),
  PRIMARY KEY (txn_id, line))`. Addytywna (stara wersja wstaje).
- `split.py`: `get(conn, txn_id)`, `save(conn, txn_id, parts, source)` — walidacja: ≥ 2 części, każda podkategoria (liść),
  kwota ≠ 0 i ze znakiem transakcji, suma = `txn.amount` co do grosza, transakcja nie jest przelewem własnym;
  `txn.category_id` = część o największej |kwocie|, `category_source='manual'`, `rule_id=NULL`; `clear(conn, txn_id)` usuwa
  podział i przywraca kategorię automatyczną (jak `engine.set_manual(…, None)`).
- `categorize.engine`: transakcja z podziałem nie uczy pamięci sprzedawcy (`decided`) — zbiór `split_ids` w `_load`.
- Zmiana kategorii zwykłym selectem na podzielonej transakcji usuwa podział (jedna prawda).
- Testy: walidacje, największa część, recategorize nie rusza, pamięć sprzedawcy pomija.

## E2 — Wyliczenia po częściach (commit)
- `spending._rows`: `LEFT JOIN txn_split s ON s.txn_id = t.id`, `coalesce(s.amount, t.amount) AS amount`,
  `coalesce(s.category_id, t.category_id) AS category_id` — jedna zmiana obejmuje `sums` (flex, Podsumowanie, oszczędności,
  wykres miesięcy) i czat (`ask.query.execute`). `coverage.txns` liczy transakcje, nie części (`distinct id`).
- Lista transakcji (`web/routes_transactions.py` ~82): filtr kategorii trafia też w części (`EXISTS` na `txn_split`).
- Test niezmienniczy: suma `sums().balance` z podziałem = bez podziału; Drogeria rośnie dokładnie o kwotę części.

## E3 — UI podziału (commit)
- Karta transakcji: „Podziel na kategorie” → formularz wierszy (select podkategorii + kwota), „Dodaj wiersz”, licznik
  „Zostało do przydzielenia: X zł” liczony w przeglądarce (bez zapytań), „Zapisz” `disabled`, dopóki reszta ≠ 0,00;
  serwer waliduje to samo. „Usuń podział”. Na liście transakcji znacznik podziału i nazwy części w podpisie.
- `impeccable` przed makietą; weryfikacja Playwright na 390 px i desktopie (screenshot + konsola), cache-busting `?v=`.
- Wydanie 0.49.0: `simplify` → `code-review` → `release`, weryfikacja na żywo (podział jednej transakcji Lidl ręcznie).

## E4 — Odczyt paragonów i dopasowanie (commit)
- `config.yaml`: `map: share:ro`. `lidl_link.py`: odczyt `/share/lidl/receipts.json` przy synchronizacji (brak pliku = nic).
- Dopasowanie: wydatek (BOOK, nie przelew) z |kwota| = `paid`, `coalesce(tx_date, booking_date)` w `day` ±3 dni; jeden
  kandydat po obu stronach → `txn_lidl(txn_id PK, ticket_id UNIQUE, status CHECK IN ('auto','chosen'))`; wielu → lista do wyboru.
- Mapa kategorii Lidl → podkategoria w `kv` (`lidl_category_map`) + edycja w ustawieniach.
- Testy na fixture'ach z neutralnymi danymi.

## E5 — Auto-podział i link (commit)
- Paragon z jedną kategorią → zwykła kategoria; z wieloma → `split.save(…, source='lidl')`. Pomija transakcje z ręczną
  kategorią/podziałem użytkownika (`category_source='manual'` bez `txn_split.source='lidl'`).
- Karta transakcji: „Paragon Lidl” → `/app/f0987e0f_lidl/paragony/<id>` (`target="_top"`); wybór paragonu przy niejednoznacznych.

## E6 — Historia (commit + wydanie 0.50.0)
- Backup add-onu, przebieg na całej historii, raport: dopasowane/niedopasowane, zł przesunięte ze Spożywczych do innych podkategorii.
- `simplify` → `code-review` → `release`, weryfikacja na żywo (5 transakcji Lidl: link, części = sumy paragonu).

## Ryzyka
- E2 dotyka limitów i prognozy → test niezmienniczy + porównanie ekranów przed/po na kopii księgi.
- Przeliczenie historii zmienia średnie limitów auto → raport przed/po, backup.
- Zwrot podzielonego zakupu dziedziczy kategorię największej części (świadome uproszczenie).
- Płatności gotówką/z innego konta nie dopasują się — w raporcie jako niedopasowane.
