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
