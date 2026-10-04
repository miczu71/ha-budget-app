# Bank Millennium przez Enable Banking — wyniki sondy produkcyjnej (M1b)

Data: 2026-10-01. Aplikacja Production w trybie **Restricted** (3 podlinkowane rachunki), jedna
zgoda (SCA w aplikacji mobilnej), odczyt CLI tuż po `POST /sessions`. Surowe zrzuty leżą wyłącznie
lokalnie (`/data/home/budget_dev/prod/`), tutaj tylko fakty o strukturze — bez danych osobowych.

## Odpowiedzi na SPEC §11

| Pytanie | Wynik |
|---|---|
| Nazwa ASPSP | `Bank Millennium` (PL), flaga `beta: true`, `psu_types: [personal]`, `auth_methods: REDIRECT` |
| `maximum_consent_validity` | 15552000 s = **180 dni** |
| `required_psu_headers` | **brak** (pusta lista) |
| Głębokość historii | **dokładnie 90 dni** (od dziś − 90) — mimo `date_from` = dziś − 730 i mimo `strategy=longest`, zaraz po świeżym SCA |
| `transaction_id` | **nigdy** (0/477) |
| `entry_reference` | zawsze (477/477), unikalne w zrzucie, **stabilne między dniami** (drugi zrzut po ~17 h: 466/466 w oknie wspólnym bez zmian — patrz niżej) |
| `merchant_category_code` | **nigdy** (0/477) |
| `bank_transaction_code` | **nigdy** |
| Typy sald | `ITBD` (Interim booked) i `ITAV` (Interim available) na każdym koncie |
| Dostępne konta | rachunek bieżący PLN (`Konto 360°`), rachunek walutowy EUR, **karta kredytowa** (`Visa Impresja`) — wszystkie jako `cash_account_type: CACC` |
| PDNG (oczekujące) | **żadnych** — tylko `BOOK` |

## Szczegóły istotne dla projektu

### Rachunek bieżący (370 transakcji / 90 dni, 8 stron paginacji)
- Paginacja `continuation_key` działa naprawdę (8 stron) — ścieżka testowana dotąd tylko mockami.
- `entry_reference` ma postać złożoną: `<6 liter>|<IBAN własnego rachunku>|<data księgowania>|<n>`,
  gdzie **`n` to numer kolejny w obrębie dnia, malejąco** (np. 10…1). Wygląda na identyfikator
  syntetyczny (EB lub bank), więc **może się przenumerować**, jeśli do już pobranego dnia dojdzie
  transakcja zaksięgowana później. **Drugi zrzut (2026-10-02, ~17 h później):** w oknie wspólnym
  466/466 referencji (rachunek + karta) z identyczną treścią, 0 przenumerowanych, 0 znikniętych;
  2 transakcje dopisane do dnia 01.10 po pierwszym zrzucie dostały kolejne numery (istniejące
  się nie przesunęły). M2 i tak dopasowuje zapasowo po odcisku + numerze wystąpienia.
- Strony transakcji: przy wydatku (`DBIT`) `debtor` = właściciel rachunku (imię, nazwisko,
  **adres** w `postal_address`), `creditor` tylko przy przelewach (34/326); przy wpływie (`CRDT`)
  `debtor` = nadawca (44/44).
- Numer konta kontrahenta **nie jest w `iban`**, tylko w `other.identification` ze schematem
  `BBAN` (wartość ma postać `PL` + 26 cyfr). Poprawione w `GenericIdentification.number`.
- Płatności kartą (większość wydatków) **nie mają kontrahenta ani MCC** — nazwa sklepu jest tylko
  w `remittance_information` (zawsze dokładnie 1 linia), np. „<SKLEP> <MIASTO>”.
- Brak `transaction_date`; `value_date` ≠ `booking_date` (w każdej transakcji).
- Kwoty jako string, czasem z jedną cyfrą po przecinku (`"120.0"`) — `Decimal` to obsługuje.

### Karta kredytowa (107 transakcji, 3 strony)
- Brak jakichkolwiek danych stron (`creditor`/`debtor`/rachunki = null).
- `entry_reference` = `<6 liter>|<IBAN karty>|<data>|<referencja banku>` — tu ostatni człon to
  prawdziwa referencja (nie licznik), więc stabilna.
- Spłaty karty widoczne jako opis „WCZESN.SPL.Z RACHUNKU: …” — po stronie rachunku bieżącego
  przelew na kartę nie ma numeru konta karty, więc **przelewów własnych nie da się wykryć po IBAN**.
- Dane zaczynają się później niż 90 dni wstecz (karta używana od połowy lipca).

### Rachunek walutowy EUR
- 0 transakcji w 90 dniach, salda zwracane.

### Stronicowanie i `date_from` (add-on, 2026-10-02)

- **`date_from` jest ignorowane, gdy jest późniejsze niż 90 dni wstecz:** synchronizacja z oknem
  od 21.09 zwróciła rachunek za pełne 90 dni (8 stron), tak jak zapytanie od 04.07.
- **Strony przychodzą od najnowszych** (daty ściśle nierosnąco w obu zrzutach rachunku i karty);
  pierwsza strona rachunku obejmuje ~10 dni, karty ~17 dni.
- Konsekwencja: przy limicie 4 zapytań na konto na dobę pełne okno rachunku (8 stron) nie mieści
  się w harmonogramie. Add-on (0.1.1) kończy stronicowanie, gdy pobrane transakcje sięgną przed
  początek okna (ostatnie księgowanie − 5 dni), przy potwierdzonej malejącej kolejności —
  zwykle 1 strona na konto na przebieg.

### Salda karty i limit zapytań (checkpoint M3, 2026-10-03)

- **ITBD karty = bieżące zadłużenie** (dodatnie). Pierwsza migawka równała się dokładnie jednej
  obciążającej transakcji, a druga zmieniła się prawie o kwotę zwrotu zaksięgowanego w międzyczasie.
  Różnica < 2 zł, najpewniej opłata jeszcze niewidoczna w transakcjach API. Obserwujemy przy
  kolejnych migawkach; zadłużenie karty w budżecie → M9.
- **ITAV karty jest opóźnione:** nie zmieniło się między migawkami, choć ITBD się zmieniło.
- **Limit zapytań:** doba 02.10 (2 sloty z harmonogramu + synchronizacja z panelu z PSU) przeszła
  bez 429; licznik w add-onie max 2 na (konto, endpoint). **Rozstrzygnięte 03.10: limit liczony
  per endpoint** — doba z 3 slotami (06:30, 13:30, 21:30) dała 6 zapytań na konto łącznie
  (3 × salda + 3 × transakcje), wszystkie `ok`, 0×429; licznik add-onu max 3 na (konto, endpoint).
  Przy limicie łącznym 4 na konto slot 21:30 skończyłby się 429. Harmonogram 3×/dobę ma zapas
  1 zapytania na (konto, endpoint) — synchronizacja z przycisku w HA (bez PSU) mieści się raz.

## Konsekwencje dla kolejnych etapów (do decyzji w checkpoincie)

1. **M7 (import CSV) jest potrzebny**, jeśli budżet ma obejmować więcej niż 90 dni wstecz — PSD2
   w Millennium nie da starszej historii nawet przy świeżej zgodzie. Potem historia rośnie
   sama, bo synchronizujemy co dzień.
2. **Deduplikacja (§5.2):** klucz `sha256(account | "eb" | entry_reference)` jest poprawny dla karty;
   dla rachunku bieżącego zależy od stabilności licznika `n` — drugi zrzut: stabilny. M2: referencja
   jako klucz główny, odcisk (data, kwota, opis) + numer wystąpienia jako zapas (przenumerowana
   referencja dochodzi jako alias).
3. **PDNG → BOOK (§5.2):** Millennium nie zwraca oczekujących — logika zostaje (tania), ale nie
   jest krytyczna.
4. **Kategoryzacja (§5.3):** krok MCC nie zadziała w Millennium. Podstawą muszą być reguły na
   opisie (`description`), bo kontrahent jest tylko przy przelewach.
5. **Przelewy własne (§5.3 pkt 2):** wykrywanie po numerze konta działa dla przelewów między
   rachunkami, ale **nie dla spłat karty** — potrzebna reguła na opis (np. „WCZESN.SPL.Z RACHUNKU”,
   „SPŁATA KARTY”) albo dopasowanie par kwota+data między rachunkiem a kartą.
6. **Karta kredytowa w budżecie:** wydatki kartą + spłata z rachunku = **podwójne liczenie**, jeśli
   spłata nie zostanie oznaczona jako transfer. To najważniejsza pułapka dla `budget_engine`.
7. **Prywatność:** `debtor.postal_address` zawiera adres właściciela — `raw_json` w bazie
   (lokalnie) OK, ale nigdy w logach, encjach HA ani fixture'ach.
8. **Saldo do sensora:** `ITAV` (dostępne), z `ITBD` jako zapasem.
