# M15 — Karta kredytowa

Wywiad 2026-10-06 (dopisany do roadmapy w trakcie wywiadu M8). Kolejność: **M15 E1 → M8 → M15 E2**
— licznik jest mały, niezależny od prognozy i daje wartość już na koniec bieżącego miesiąca.

## Co daje bank (`FINDINGS_millennium.md`)

- Zakupy kartą = transakcje API na koncie karty → licznik w całości z księgi.
- `ITBD` karty = bieżące zadłużenie (używa go też M8).
- Limitu nie ma wprost; `ITAV` (dostępne) jest opóźnione, więc ITAV + ITBD to tylko przybliżenie.
- Brak daty zamknięcia cyklu, terminu spłaty i kwoty minimalnej — to muszą być ustawienia.

## E1 — licznik zakupów (0.23.0)

### Warunek banku (cennik kart kredytowych, Tabela 2)

- Karta główna Impresja: 0 PLN, „jeśli w poprzednim miesiącu zapłacisz min. 5 razy kartą”,
  inaczej 7,99 PLN; karta dodatkowa: ten sam warunek, inaczej 2,99 PLN.
- „Do warunków zwolnienia z opłaty miesięcznej nie uwzględniamy płatności BLIK.”
- Cennik nie mówi, czy liczy się data zakupu, czy księgowania.
- **Bank liczy każdą kartę osobno** — potwierdzone na danych: miesiąc, w którym jedna karta miała
  < 5 zakupów, skończył się opłatą 2,99 PLN (stawka karty dodatkowej) i równoległą „OPŁATĄ
  MIESIĘCZNĄ” 0,00 PLN dla drugiej karty. Bank księguje obie pozycje co miesiąc (~17.–18.).

### Sonda na kopii księgi (2026-10-06)

- Rozpoznanie zakupu po `kind` jest rzetelne: heurystyka API dla karty zgodna z typem z CSV
  w 105/105 transakcji. Wypłat gotówki kartą w historii brak (heurystyka by ich nie odróżniła).
- API karty podaje **tylko datę księgowania** (brak `value_date`); księgowanie zwykle 2 dni po
  zakupie (94/105), czasem 0–4, pojedyncze walutowe 10–25 dni.
- **API nie podaje numeru karty** — podziału na kartę główną i dodatkową nie da się liczyć na
  bieżąco (eksport CSV go ma, ale E1 opiera się wyłącznie na API — decyzja użytkownika).

### Cel i ograniczenia

1. **Cel:** nie płacić opłaty miesięcznej za kartę; add-on ostrzega, zanim miesiąc się skończy,
   i mówi po fakcie, gdy bank opłatę pobrał.
2. **Okres:** miesiąc kalendarzowy.
3. **Licznik wspólny dla konta karty:** zakupy = obciążenia o typie `card` (BLIK wyłączony —
   na karcie i tak nierozpoznawalny), bez spłat, opłat, odsetek; zwroty nie odejmują. Gdy razem
   < 5, obie karty na pewno nie spełniają warunku — ostrzeżenie zawsze trafne; przy ≥ 5 panel
   dopisuje, że bank liczy każdą kartę osobno.
4. **Data — ostrożnie:** warunek „spełniony” tylko gdy ≥ 5 zarówno po dacie księgowania, jak
   i po dacie księgowania − 2 dni (zgodne z obiema interpretacjami banku).
5. **Automatycznie:** 5 dni i dzień przed końcem miesiąca, gdy < 5 — powiadomienie przez
   `summary_notify_service` + wpis w dzwonku (każde raz, znacznik w `kv`). **Wykrywanie opłat:**
   nowa „OPŁATA MIESIĘCZNA” na koncie karty z kwotą ≠ 0 → powiadomienie + wpis w dzwonku
   z kwotą (7,99 = karta główna, 2,99 = dodatkowa według cennika).
6. **Sukces:** licznik zgadza się z listą zakupów w bankowości; najbliższa pobrana opłata
   zostaje zgłoszona.

### Kroki (0.23.0)

1. `budget/card.py`: `THRESHOLD = 5`, `month_status(conn, month, today)` → liczba zakupów (obie
   reguły dat), brakuje, dni do końca; `fees_since(conn, after_id)` → niezerowe opłaty miesięczne.
2. `summary.py` → `due()`: wiadomości `card-5`, `card-1` i `card-fee-<txn id>`; wysyłka istniejącą
   ścieżką M6 (`mark_sent`, `kv`, nadrabianie po restarcie); brak serwisu → nic.
3. `inbox.py`: pozycje „Karta: brakuje K zakupów” (ostatnie 5 dni) i „Bank pobrał opłatę za kartę”
   (do zamknięcia w dzwonku).
4. `ha_publisher.py`: `sensor.budget_card_purchases_month` (stan = liczba po ostrożnej regule;
   atrybuty: próg, brakuje, miesiąc, ostatnia opłata).
5. Panel: kafelek na Podsumowaniu (N/5, „spełnione” / „brakuje K, zostało D dni”, dopisek
   o osobnym liczeniu kart i ~2-dniowym opóźnieniu księgowania), link do Transakcji karty.
6. Testy `tests/test_card.py`; ruff, mypy, pytest; `simplify`; skaner pre-commit.
7. Weryfikacja UI na kopii księgi (`devserve.py`, Playwright 390/1280, konsola).
8. Wydanie skillem `release`; backup add-onu i aktualizacja w HA (restart add-onu) — tylko po
   „go” użytkownika na checkpoincie po kroku 7. Cofnięcie: revert + 0.23.1 albo backup add-onu.

### Wynik E1

- 2026-10-06: 0.23.0 wydane (v0.23.0, CI zielone) i zainstalowane z backupem add-onu (`1916b7bb`);
  554 testy. Na żywo: `sensor.budget_card_purchases_month` = 1 (brakuje 4, październik), kafelek
  na Podsumowaniu (390 i 1280 px), konsola bez błędów. Wykrywanie opłat pominięte — użytkownik
  wybrał „zwykły licznik”.
- W tym samym wydaniu: przeładowanie stron sprzed aktualizacji (`X-Panel-Version` → `HX-Refresh`).
  Powód: WebView aplikacji HA trzymał CSS z 0.19 (stary wygląd Copilot na 0.22.1) — `hx-boost`
  nie wymienia `<head>`; naprawił to dopiero reset pamięci podręcznej frontendu.
- Pierwsze możliwe przypomnienie: 26.10 o 7:00 (gdy w październiku < 5 płatności).

## E2 — osoby i ręczne przypisanie płatności (0.24.0)

Wywiad 2026-10-06 (decyzja 19, zmienia decyzję 2). Bank liczy warunek osobno dla każdej karty,
a API nie podaje numeru karty — więc każdą płatność kartą przypisuje się ręcznie do osoby, a system
liczy 5 płatności dla każdej.

### Cel i ograniczenia

1. **Przypisanie w pełni ręczne** — bez podpowiedzi i automatycznych reguł.
2. **Nieprzypisana płatność nie liczy się nikomu**; od razu karta w dzwonku „do przypisania”.
3. **Powiadomienia do obojga** (`summary_notify_service`): 5 dni i dzień przed końcem miesiąca —
   stan każdej osoby i liczba nieprzypisanych; wysyłane, gdy komuś brakuje albo coś czeka.
4. **Imiona tylko w bazie** (ekran „Karta”), nigdy w repo — w kodzie, testach i docs „Osoba 1/2”.
5. Bez osób w bazie zachowanie jak w 0.23.0 (licznik wspólny).
6. **Sukces:** liczniki per osoba zgadzają się z bankowością; przypomnienie mówi, kto ile musi
   jeszcze zapłacić.

### Zakres

- Migracja `011_card_holder.sql`: tabela `card_holder (id, name UNIQUE, csv_number UNIQUE,
  created_at)`, kolumna `txn.card_holder_id`.
- `card.py`: osoby (dodaj, zmień imię), przypisanie tylko płatności kartą, `month_status` z liczbą
  per osoba (ta sama ostrożna reguła dat) i liczbą nieprzypisanych, lista do przypisania.
- Ekran „Karta” `/card` (menu ⚙, link z kafelka): liczniki per osoba, lista „Do przypisania”
  z przyciskami osób (htmx, ≥ 44 px), przypisane w miesiącu ze zmianą osoby, sekcja „Osoby”.
- Podsumowanie: kafelek z wierszem na osobę i liczbą do przypisania. Transakcje: plakietka osoby.
- Dzwonek: „do przypisania” (warn w ostatnich 5 dniach) i „brakuje K” per osoba w ostatnich 5 dniach.
- Encja `sensor.budget_card_purchases_month` bez zmiany `entity_id`: nowe atrybuty `holders`,
  `unassigned`.

### Wynik E2

- 2026-10-06: 0.24.0 wydane (v0.24.0, CI zielone) i zainstalowane z backupem add-onu (`b4c02743`);
  564 testy. Na żywo dodane dwie osoby (karta główna, potem dodatkowa — imiona tylko w bazie);
  ekran Karta: 0/5 i 0/5, 1 płatność do przypisania; encja z atrybutami `holders`, `unassigned`;
  konsola bez błędów. Przegląd `simplify`: jeden model (bez osób = pozycja „Razem”), „do
  przypisania” tylko z bieżącego miesiąca.

## E3 — historia z CSV (0.24.1)

- Przy każdej osobie wybór numeru karty z eksportu CSV → `card_holder.csv_number`.
- Płatności bez osoby dostają osobę, której numer ma wiersz `csv_row` powiązany z transakcją —
  bezpośrednio (`txn_id`) albo przez `row_key` wiersza z bloku „całe konto” (blok jednej karty jest
  oznaczony `duplicate`; na kopii księgi dopasowanie 76/76). Ręczne przypisania wygrywają.
- Po zapisie mapowania i po każdym imporcie CSV. Kontrola: miesiąc z opłatą 2,99 PLN ma dla karty
  dodatkowej < 5 płatności.

### Wynik E3

- Ustalenie przy mapowaniu: numer karty dodatkowej to w eksporcie blok **całego konta karty**, a numer
  karty głównej — blok jej własnych płatności; reguła „najwęższy blok” daje to samo co opłaty banku
  (miesiąc z opłatą 2,99 PLN: karta dodatkowa 1 płatność w ostrożnym liczeniu).
- 0.24.1 (v0.24.1) zainstalowane; zapis drugiego numeru na produkcji → 500 „unable to open database
  file”: UPDATE potrzebuje pliku tymczasowego SQLite, bez `SQLITE_TMPDIR` SQLite wybiera `/var/tmp`
  (przechodzi test `access()`), a AppArmor add-onu pozwala pisać tylko do `/data`, `/config`, `/tmp`.
  Potwierdzone lokalnie podglądem otwartych plików (`etilqs_…`); transakcja wycofała się bez szkód.
- 0.24.2 (v0.24.2): `PRAGMA temp_store = MEMORY` w `db.connect`; 568 testów. Na produkcji oba numery
  ustawione, **101 płatności przypisanych**, 0 nieprzypisanych w historii; log bez błędów.

## E4 — ile spłacić i do kiedy (0.30.0)

Wywiad 2026-10-06 (po zamknięciu M8).

### Cel i ograniczenia

1. **Cel:** wiedzieć, ile spłacić z zamkniętego cyklu i do kiedy, żeby nie płacić odsetek.
2. **Warunki karty (od użytkownika, zgodne z ofertą):** cykl = miesiąc kalendarzowy, termin
   spłaty 20. dnia następnego miesiąca (do 51 dni bez odsetek), spłata minimalna 5%. Limit
   wpisany ręcznie na ekranie Karta (w bazie, nie w repo); dane potwierdzają limit
   (ITBD + ITAV ≈ limit).
3. **Automatycznie:** przypomnienie 5 dni i dzień przed terminem (15. i 19., 7:00) przez
   `summary_notify_service` + dzwonek — tylko gdy kwota z cyklu nie jest spłacona. Ścieżka E1
   (`summary.due()`, `mark_sent`, nadrabianie po restarcie).
4. **Sukces:** 20.10 kwota w panelu równa „kwocie do spłaty” w aplikacji banku albo nieco wyższa
   (świadomie ostrożna); przypomnienie przychodzi tylko, gdy coś zostało.

### Model

Spłaty są ręczne i nieregularne („wcześniejsza spłata z rachunku”), a API daje tylko `ITBD`
(zadłużenie teraz) i datę księgowania. Zamiast odtwarzać wyciąg:

- **Zostało do spłaty** = max(0, `ITBD` − obciążenia karty zaksięgowane w bieżącym cyklu).
  `ITBD` = wyciąg − spłaty i zwroty po zamknięciu + nowe obciążenia, więc spłaty odejmują się same.
- **Ostrożnie na granicy cyklu:** obciążenia z pierwszych `BOOKING_LAG` = 2 dni cyklu liczą się
  do wyciągu (zakup z końca miesiąca księgowany 1.–2.); `ITBD` obejmuje też autoryzacje spoza
  księgi. Oba błędy zawyżają kwotę, nigdy jej nie zaniżają.
- **Stany:** 1.–20. „do spłaty X do 20.” z liczbą dni; po 20. z resztą > 0 „po terminie”; 0 →
  „spłacone”.
- **Limit:** wykorzystanie = `ITBD` / limit, `ITAV` obok do porównania; bez limitu sekcja ukryta.
- M8 bez zmian — prognoza już odejmuje całe zadłużenie karty; zdarzenie „spłata 20.” liczyłoby
  je drugi raz.

### Kroki (0.30.0)

1. `card.py`: `DUE_DAY = 20`, limit w `kv`, `due_status(conn, today)` → kwota, termin, dni,
   po terminie, zadłużenie, dostępne, limit; `due_remind_today(today)` (15. i 19.).
2. `summary.py`: rodzaj `card_due`, wiadomość z kwotą i terminem, gałąź w `due()`.
3. `inbox.py`: pozycja „Karta: do spłaty” (warn od 15. i po terminie), link `/card`.
4. `ha_publisher.py`: `sensor.budget_card_due` (stan = zostało; atrybuty termin, dni, po terminie,
   zadłużenie, limit, wykorzystanie).
5. Panel: na ekranie Karta sekcje „Spłata” i „Limit” (pole kwoty, pasek wykorzystania);
   linia „do spłaty” na kafelku karty na Podsumowaniu.
6. Testy, ruff, mypy, `simplify`, skaner pre-commit.
7. Weryfikacja UI na kopii księgi (Playwright 390/1280, konsola).
8. Checkpoint → „go” → wydanie skillem `release`, backup add-onu, aktualizacja w HA, limit
   ustawiony przez panel. Cofnięcie: revert + 0.30.1 albo backup add-onu.

### Wynik E4

- 2026-10-06: 0.30.0 wydane (v0.30.0) i zainstalowane z backupem add-onu (`73121fd1`); 638 testów. Przegląd
  `simplify`: jeden formatter kwot PLN (`money.pl`) dla panelu, telefonu i dzwonka, `CardDue.soon`, filtr `when`.
- Na żywo (Ingress, 390 px, konsola strony bez błędów): wersja 0.30.0, „Spłata — do 20.10: Spłacone” (wrześniowy
  cykl spłacony wcześniejszymi spłatami), limit wpisany w panelu, wykorzystanie < 1%; encja `sensor.budget_card_due`
  = 0, atrybuty limit/wykorzystanie; dzwonek bez pozycji karty.
- Do poprawy: atrybut `available` nie trafia do encji (HA odrzuca tę nazwę w atrybutach MQTT) — zmiana nazwy
  przy najbliższym wydaniu innego etapu (decyzja użytkownika, bez osobnego 0.30.1).
- ✅ Checkpoint E4 zamknięty przez użytkownika 2026-10-06 — M15 zamknięty.
- Obserwacja: zakup z końca września zaksięgowany 3. dnia cyklu (poza oknem 2 dni) liczy się do nowego cyklu;
  przy niespłaconym wyciągu kwota mogłaby wyjść zaniżona. Sprawdzić 20.10 z „kwotą do spłaty” w aplikacji banku.

