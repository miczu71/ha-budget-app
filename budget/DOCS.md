# Budżet Domowy

Transakcje i salda pobierane automatycznie z banku przez PSD2
([Enable Banking](https://enablebanking.com), tylko odczyt — AIS), zapisywane lokalnie
w Home Assistant w jednej księdze bez duplikatów: CSV z historią + API, spłaty karty jako
przelewy między kontami, uzgadnianie salda.

> **Prywatność:** baza (`/data/budget.db`) i klucz Enable Banking są częścią **kopii zapasowych
> Home Assistant** — kopia zawiera Twoje dane finansowe. Chroń ją hasłem i nie udostępniaj.

## Wymagania

- Aplikacja w Enable Banking Control Panel (tryb **Restricted Production** wystarcza dla
  własnych kont): identyfikator aplikacji i klucz prywatny `.pem`. Konta muszą być wcześniej
  podlinkowane w Control Panelu.
- Broker MQTT (add-on Mosquitto) — encje trafiają do HA przez MQTT Discovery.

## Pierwsze uruchomienie

1. W opcjach add-onu wpisz `eb_application_id` (i ewentualnie `eb_redirect_url`), uruchom add-on.
2. Otwórz panel **Budżet** → **Bank**:
   - wgraj klucz prywatny `.pem` (zapisany z prawami 600 w katalogu konfiguracji add-onu),
   - **przenieś sesję** z CLI (plik `sessions/<id>.json`) — bez ponownego logowania w banku,
     albo **Połącz bank**: otwórz link, potwierdź w aplikacji banku, wklej adres zwrotny.
     Po nowym połączeniu add-on pobiera 90 dni historii.
3. **Import CSV** (opcjonalnie): eksport historii z bankowości internetowej. Starsze transakcje
   uzupełniają historię sprzed 90 dni dostępnych w API. Import można powtarzać — nic się nie
   zdubluje.
4. **Status** → **Synchronizuj teraz** — pierwsze pobranie.

## Synchronizacja i limit banku

Bank może odmówić więcej niż **4 zapytań na konto na dobę** wykonanych bez Twojej obecności.
Add-on liczy każde zapytanie (salda, każdą stronę transakcji) per konto i endpoint i nie wyśle
zapytania ponad limit. Domyślne 3 synchronizacje dziennie (`sync_times`) pobierają salda
i transakcje od ostatniego księgowania − 5 dni; bank oddaje strony od najnowszych, więc
stronicowanie kończy się po pokryciu okna (zwykle jedna strona).

- **„Synchronizuj teraz” w panelu** wysyła dane przeglądarki (nagłówki PSU) — jesteś obecny,
  więc te zapytania nie liczą się do limitu.
- **Przycisk `button.budget_sync_now` w HA** nie ma tych danych — liczy się do limitu.
- Jeśli okno transakcji nie zmieści się w limicie, nie trafia do księgi (żeby nie powstała
  luka) i pojawia się prośba o synchronizację z panelu.

Jeśli wcześniej używałeś CLI (`python -m budget.cli ingest-eb --live`) na tej samej sesji, po
przeniesieniu sesji do add-onu przestań — sesja i limit są wspólne.

## Kategorie i ekran „Wydatki”

Każda transakcja dostaje podkategorię automatycznie, w tej kolejności:

1. **ręcznie ustawiona** w panelu (Transakcje → kategoria w wierszu) — nic jej nie nadpisuje,
2. **zwrot** dostaje kategorię zakupu, do którego należy,
3. **Twoje reguły** (Reguły) — wygrywa pierwsza pasująca z góry listy,
4. **słownik sieci** wbudowany w add-on (ogólnopolskie sieci i marki, np. Biedronka, Orlen,
   Rossmann) i słowa ogólne („APTEKA”, „PARKING”),
5. **typ transakcji**: wypłata z bankomatu, opłata banku, rata kredytu.

Przelewy między Twoimi podlinkowanymi kontami (np. spłata karty) nie mają kategorii i nie liczą
się do wydatków. Przelew do osoby kategoryzuje odbiorca, nie tytuł — dodaj regułę na odbiorcę
(albo zmień kategorię jednej transakcji i kliknij **Zawsze dla …**).

**Reguły** mają warunki (sprzedawca/odbiorca, opis, kontrahent, konto kontrahenta; „zawiera”,
„równa się”, „zaczyna się od”; konto, typ, kierunek, zakres kwot) i podgląd na żywo: ile
transakcji pasuje, ile zmieni kategorię i ile ma kategorię ręczną. Zapis przelicza kategorie
całej historii (ręczne zostają).

**Wydatki** pokazują miesiąc kalendarzowy (po dacie transakcji): wydatki w kategoriach z udziałem
i zmianą względem poprzedniego miesiąca, wpływy, oszczędności, transakcje poza budżetem
(kategoria „Jednorazowe / poza budżetem”) i pozycje bez kategorii. Kwoty w PLN; transakcje
w innej walucie są na razie pomijane.

## Kolejka „Do przejrzenia”

Zakładka z licznikiem w nawigacji zbiera wszystkie transakcje **bez kategorii** (to, co
skategoryzowała reguła albo słownik, nie wymaga potwierdzania). Nagłówek pokazuje pokrycie
wydatków kategoriami (% transakcji i % kwoty).

- **Sprzedawcy i odbiorcy** — grupa = sprzedawca/odbiorca + kierunek (wydatek i wpływ od tej
  samej osoby to osobne grupy), sortowanie po kwocie albo liczbie. Po wybraniu kategorii zapis
  tworzy regułę „sprzedawca równa się … + kierunek”, więc kolejne transakcje skategoryzują się
  same; podgląd ostrzega, gdy reguła zmieni też już skategoryzowane pozycje.
- **Tylko te transakcje** albo odznaczenie części pozycji — kategoria ręczna, bez reguły
  (jednorazowi sprzedawcy, odbiorca o mieszanym przeznaczeniu); odznaczone zostają w kolejce.
- **Zagranica** — sporadyczne płatności kartą za granicą, grupowane po kraju (z opisu
  transakcji) albo walucie, zwykle wyjazd: jedna decyzja, np. „Podróże”, dla całej grupy.
  Zagraniczny sprzedawca obecny w co najmniej 3 różnych miesiącach (subskrypcja, doładowania)
  jest wśród zwykłych sprzedawców.
- **Widok miesiąca** — „Nieskategoryzowane” na ekranie Wydatki otwiera kolejkę zawężoną do
  oglądanego miesiąca (`/review?month=RRRR-MM`, przejście « » między miesiącami, link „wszystkie
  miesiące”). Reguła zapisana z tego widoku działa we wszystkich miesiącach — podgląd podaje,
  ile pozycji spoza miesiąca obejmie; żeby skategoryzować tylko ten miesiąc, zaznacz „tylko te
  transakcje”.

## Podpowiedzi kategorii z AI (opcjonalnie)

Add-on może pytać model językowy o kategorię dla sprzedawców z kolejki „Do przejrzenia”,
przez router zgodny z API OpenAI (np. lokalny router freellmapi w sieci domowej).
Włączenie: opcje `ai_base_url` (np. `http://<host>:3003/v1`), `ai_api_key`, `ai_model`
(nazwany model — `auto` nie obsługuje odpowiedzi według schematu) i `ai_daily_calls`.

**Co trafia do modelu** — i nic poza tym:
- płatności kartą i BLIK: nazwa sprzedawcy i opis transakcji;
- przelewy, zlecenia, polecenia zapłaty itp.: tylko tytuł, **bez nazwy odbiorcy** (także
  odmienionej w tytule);
- zawsze: rodzaj operacji, kierunek, kwota jako przedział (np. „20–100 zł”), liczba transakcji;
- lista Twoich kategorii i przykłady „sprzedawca kartowy → kategoria” z Twoich decyzji.

Z tekstów wycinane są IBAN-y, numery kont i kart, e-maile, telefony, kody pocztowe, daty i inne
ciągi cyfr. Router może przekazywać zapytania do zewnętrznych dostawców (darmowe plany bywają
używane do trenowania modeli) — włącz tylko, jeśli to akceptujesz.

Działanie: po każdej synchronizacji, w tle, do 3 wywołań po 40 sprzedawców (w limicie
`ai_daily_calls`); o tego samego sprzedawcę nie pyta drugi raz. Karta **Podpowiedzi AI** na
ekranie Status pokazuje wywołania, ostatni błąd i liczbę podpowiedzi; **Podpowiedz teraz**
uruchamia przebieg od razu, **Zmierz trafność** pyta o do 80 sprzedawców, którzy już mają
kategorię (najpierw Twoje ręczne i reguły, potem słownik), i pokazuje trafność według progu
pewności. W tej wersji podpowiedzi są tylko liczone — zatwierdzanie jednym dotknięciem w kolejce
i na liście transakcji przyjdzie w następnej.

## Encje

| Encja | Opis |
|---|---|
| `sensor.budget_saldo_<rodzaj>_<waluta>` | Dostępne środki (ITAV) na koncie; ITBD i zamaskowany numer w atrybutach. Dla karty kredytowej ITAV to dostępny limit |
| `sensor.budget_consent_days_left` | Dni do wygaśnięcia zgody bankowej |
| `sensor.budget_last_sync` | Ostatnia udana synchronizacja (wynik ostatniej próby w atrybutach) |
| `binary_sensor.budget_sync_problem` | Brak zgody albo nieudane synchronizacje |
| `sensor.budget_requests_today` | Diagnostyka: najwięcej zapytań dziś na (konto, endpoint) bez PSU |
| `button.budget_sync_now` | Synchronizacja na żądanie (w ramach limitu) |

## Powiadomienia

Powiadomienie w HA (i opcjonalnie przez `notify_service`) gdy: zgoda wygasa w ciągu
`consent_warning_days` dni, zgoda wygasła lub została cofnięta, 3 synchronizacje z rzędu się
nie udały, okno transakcji nie zmieściło się w limicie. Aktywne powiadomienie jest
przypominane raz na dobę i znika samo, gdy problem ustąpi.

## Odnowienie zgody

Zgoda PSD2 jest ważna maksymalnie 180 dni. Przed wygaśnięciem: **Bank → Odnów zgodę** —
ten sam przepływ co „Połącz bank”; nowa zgoda zastępuje starą, historia zostaje.
