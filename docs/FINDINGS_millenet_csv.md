# Eksport CSV z Millenetu („Historia transakcji”) — format i porównanie z API (przygotowanie M7)

Data: 2026-10-01. Jeden plik eksportu (rachunek bieżący + karta kredytowa), ~3000 wierszy,
ok. 21 miesięcy dla rachunku. Plik surowy leży tylko lokalnie; fixture testowy powstaje narzędziem
`budget/app/tools/anonymize_millenet.py` i trafia do repo dopiero po przeglądzie użytkownika.

## Format pliku

- Nazwa: `Historia_transakcji_YYYYMMDD_HHMMSS.csv`.
- **UTF-8 z BOM**, końce linii **CRLF**, separator `,`, **wszystkie pola w cudzysłowach**,
  brak pól wielolinijkowych.
- Nagłówek (11 kolumn):
  `Numer rachunku/karty, Data transakcji, Data rozliczenia, Rodzaj transakcji, Na konto/Z konta,
  Odbiorca/Zleceniodawca, Opis, Obciążenia, Uznania, Saldo, Waluta`
- Daty ISO `YYYY-MM-DD`. Kwoty z **kropką** dziesiętną, bez separatora tysięcy; `Obciążenia`
  **ujemne** (`-12.34`), `Uznania` dodatnie; zawsze wypełniona dokładnie jedna z nich
  (2 wiersze bez żadnej kwoty — do pominięcia/zalogowania).
- `Numer rachunku/karty`: rachunek jako `PL99 9999 …` (IBAN ze spacjami), karta jako zamaskowany
  numer (8 znaków). `Na konto/Z konta`: numer NRB ze spacjami (bez `PL`), tylko przy przelewach.
- `Saldo`: wypełnione dla rachunku, **puste dla kart**.
- Wiersze od najnowszych.
- `Odbiorca/Zleceniodawca` łączy nazwę i adres separatorem `\xa0` (twarda spacja).
- `Opis` dla kart zawiera kwotę i walutę oryginalną (np. `… , <miasto> , <kod> -12.3 EUR`).

## „Rodzaj transakcji” — cenne pole, którego API nie ma

26 wartości, m.in.: `ZAKUP - FIZ. UŻYCIE KARTY`, `PŁATNOŚĆ KARTĄ W INTERNECIE`,
`PRZELEW NA TELEFON`, `PŁATNOŚĆ BLIK W INTERNECIE`, `PRZELEW PRZYCHODZĄCY`,
`PRZELEW WEWNĘTRZNY PRZYCHODZĄCY/WYCHODZĄCY`, `WYPŁATA BLIK Z BANKOMATU`,
`STAŁE ZLECENIE ZEWNĘTRZNE/WEWNĄTRZ BANKU`, `…ZWROT`, `WCZEŚN.SPŁ.KARTY:`, `PROWIZJA`,
`OPERACJE SO NA KREDYTACH`, `POLECENIE ZAPŁATY`; puste dla wszystkich wierszy kart.
W API (`remittance_information`) typ pojawia się tylko sporadycznie (8/370).
→ W M7 zapisywać do osobnej kolumny (np. `kind`), przydatne w regułach (zwroty, spłaty karty).

## Porównanie z API (okno 90 dni, w którym są oba źródła)

**Rachunek bieżący — zgodność 1:1:** 370/370 transakcji pasuje po
(`Data rozliczenia` == `booking_date`, kwota ze znakiem); opis CSV zawarty w `remittance` API
w 354/370. `Data transakcji` == `Data rozliczenia` dla rachunku. (`value_date` z API nie pasuje
do żadnej daty z CSV.)

**Karta kredytowa — rozjazdy:**
- Eksport zawiera kartę **dwa razy** pod dwoma numerami: jeden blok (77 wierszy) jest w całości
  kopią drugiego (106) → **deduplikacja wewnątrz pliku** konieczna.
- Spośród 107 transakcji karty z API: 72 pasują kwotą 1:1, **28 to te same zakupy z inną kwotą
  PLN** (mediana różnicy 2 %, do 43 %) — transakcje walutowe, przeliczone inaczej w CSV niż
  w zaksięgowanej kwocie z API; 7 to spłaty karty, które w CSV są tylko po stronie rachunku
  (`WCZEŚN.SPŁ.KARTY:`).
- `Data transakcji` ≠ `Data rozliczenia` dla kart.

## Wniosek dla M7 (propozycja do potwierdzenia)

Zamiast dopasowywać CSV do API transakcja po transakcji (§5.2: data+kwota+kontrahent), co dla
kart walutowych nie zadziała: **CSV importujemy per rachunek tylko dla dat wcześniejszych niż
najstarsza transakcja z API** (granica ustalana przy imporcie), plus deduplikacja wewnątrz pliku.
W oknie, gdzie są oba źródła, wygrywa API. Dla rachunku bieżącego można dodatkowo sprawdzić
zgodność 1:1 na zakładce granicznej jako test spójności.
