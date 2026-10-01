# Budżet Domowy — aplikacja (add-on) Home Assistant

Specyfikacja projektu dla Claude Code. Stan wiedzy zweryfikowany: 2026-09-28.

> Kopia specyfikacji dostarczonej przez użytkownika 2026-10-01. Odstępstwa i decyzje podjęte
> w trakcie realizacji są w `docs/ROADMAP.md` (sekcja „Decyzje”), nie w tym pliku.

---

## 1. Cel

Aplikacja HA (dawniej „add-on”), która:

1. automatycznie pobiera transakcje i salda z Banku Millennium przez PSD2 (pośrednik: **Enable Banking**),
2. przechowuje je lokalnie (SQLite),
3. kategoryzuje przychody i wydatki regułami, z możliwością ręcznej korekty,
4. liczy budżet miesięczny per kategoria,
5. wystawia wyniki jako encje HA (MQTT Discovery) oraz panel webowy przez Ingress.

Poza zakresem: inicjowanie płatności (PIS), obsługa wielu użytkowników HA z osobnymi budżetami, wykresy w panelu (od tego są dashboardy HA).

---

## 2. Ustalenia i fakty, na których opiera się projekt

### 2.1 Dostęp do danych bankowych

- Millennium udostępnia API PSD2 (standard PolishAPI) **wyłącznie licencjonowanym TPP**, więc bezpośrednio się nie podłączymy.
- **GoCardless Bank Account Data (ex-Nordigen) — NIE używać.** Od lipca 2025 nie przyjmuje nowych kont.
- **Enable Banking — wybrany pośrednik.**
  - Darmowy tryb **Restricted Production**: aplikacja produkcyjna aktywowana przez „podlinkowanie” własnych rachunków w panelu Enable Banking. API zwraca **tylko** podlinkowane rachunki, a pozostałe są wycinane z odpowiedzi.
  - Bank Millennium jest obsługiwany. Autoryzacja odbywa się przez przekierowanie (redirect), a SCA w aplikacji mobilnej Millennium. Automatyczne przełączanie do aplikacji nie działa.
  - Produkcja wymaga redirect URL po **HTTPS**. URL **nie musi być publiczny**, bo wystarczy, że użytkownik skopiuje `code` z paska adresu.

### 2.2 Enable Banking API — szczegóły techniczne

- Base URL: `https://api.enablebanking.com`. Adres `api.tilisy.com` jest przestarzały, nie używać.
- Autoryzacja każdego requestu: nagłówek `Authorization: Bearer <JWT>`.
  - JWT header: `{"typ":"JWT","alg":"RS256","kid":"<application_id>"}`. Obsługiwany jest wyłącznie RS256.
  - JWT body: `{"iss":"enablebanking.com","aud":"api.enablebanking.com","iat":<now>,"exp":<now+ttl>}`
  - Maksymalny TTL to **86400 s**. Generować token np. na 1 h i cache'ować do wygaśnięcia.
  - Podpis kluczem prywatnym RSA (PEM) pobranym przy rejestracji aplikacji.
- Przepływ AIS:
  1. `GET /aspsps?country=PL&psu_type=personal&service=AIS` → znaleźć `name` banku (sprawdzić dokładny string, np. „Bank Millennium”), odczytać `maximum_consent_validity` (sekundy) i `required_psu_headers`.
  2. `POST /auth` z body:
     ```json
     {
       "access": {"valid_until": "<now + maximum_consent_validity, RFC3339>", "balances": true, "transactions": true},
       "aspsp": {"name": "<z /aspsps>", "country": "PL"},
       "state": "<losowy UUID, zapisany do weryfikacji>",
       "redirect_url": "<zarejestrowany HTTPS redirect>",
       "psu_type": "personal"
     }
     ```
     Odpowiedź zawiera `url`, na który trzeba wysłać użytkownika.
  3. Po logowaniu i SCA bank/EB przekierowuje na `redirect_url?code=...&state=...`, a w razie błędu `?error=...&error_description=...`.
  4. `POST /sessions` z `{"code": "..."}` → `session_id`, `accounts[]` (każde konto ma `uid`, `identification_hash`, `account_id.iban`, `currency`, `cash_account_type`) oraz `access.valid_until`.
     **Uwaga:** część danych w tej odpowiedzi jest zwracana tylko raz, więc zapisać całość.
  5. `GET /accounts/{uid}/balances` → `balances[]` (`balance_type`: CLAV, ITAV, CLBD, XPCD…, `balance_amount.amount` jako string).
  6. `GET /accounts/{uid}/transactions?date_from=YYYY-MM-DD&date_to=...&continuation_key=...`
     - Daty w UTC, zakres włącznie.
     - Paginacja: powtarzać, dopóki odpowiedź zawiera niepusty `continuation_key`.
  7. `GET /sessions/{id}` → `status` (np. `AUTHORIZED`) oraz `access.valid_until`. `DELETE /sessions/{id}` zamyka zgodę.
- `uid` konta jest ważny **tylko w obrębie autoryzowanej sesji**. Po odnowieniu zgody `uid` się zmienia, a stałym kluczem konta jest **`identification_hash`**.
- Pola transakcji, z których korzystamy: `transaction_id`, `entry_reference`, `transaction_amount{amount,currency}`, `credit_debit_indicator` (CRDT = wpływ, DBIT = wydatek), `status` (BOOK/PDNG), `booking_date`, `value_date`, `transaction_date`, `creditor.name`, `debtor.name`, `creditor_account.iban`, `debtor_account.iban`, `remittance_information[]`, `merchant_category_code`, `bank_transaction_code`, `balance_after_transaction`.
  **Kwoty są stringami, więc parsować do `Decimal` i nigdy nie używać float.**
- Próbki kodu (Python): https://github.com/enablebanking/enablebanking-api-samples
- Sandbox: osobna aplikacja typu SANDBOX z testowymi bankami i fikcyjnymi danymi. Sandbox akceptuje redirect po HTTP.

### 2.3 Ograniczenia PSD2, które trzeba obsłużyć

- **Limit zapytań bez obecności użytkownika:** do 4 razy na dobę na konto. Harmonogram domyślny to 3 synchronizacje dziennie, żeby zostawić zapas na retry.
- Gdy użytkownik ręcznie klika „Synchronizuj” w panelu, można przekazać nagłówki `Psu-Ip-Address`, `Psu-User-Agent` itd. Takie zapytanie nie liczy się wtedy do limitu. Obowiązuje zasada: albo komplet `required_psu_headers`, albo żaden, inaczej API zwróci `PSU_HEADER_NOT_PROVIDED`.
- **Zgoda wygasa** (`valid_until`, maksymalnie wg `maximum_consent_validity` banku, zwykle ok. 180 dni). Po wygaśnięciu potrzebny jest ponowny redirect i SCA. Trzeba ostrzegać z wyprzedzeniem.
- Historia transakcji dostępna bez świeżego SCA bywa ograniczona (często do 90 dni). Dlatego **pełny backfill robimy zaraz po `POST /sessions`**, a starszą historię uzupełniamy importem CSV z Millenetu.

### 2.4 Home Assistant „Apps” (dawniej add-ons) — stan na 2026

- Nazewnictwo w dokumentacji zmieniło się na „apps”. Struktura folderu pozostaje: `config.yaml`, `Dockerfile`, `DOCS.md`, `README.md`, `CHANGELOG.md`, `icon.png`, `logo.png`, `translations/`, `apparmor.txt`.
- **`build.yaml` nie jest już używany.** Od Supervisor 2026.04.0 build arg `BUILD_FROM` nie jest dostarczany, więc w Dockerfile trzeba wpisać jawne `FROM ghcr.io/home-assistant/base:<przypięta wersja>`.
- `arch`: tylko `aarch64` i `amd64`.
- `/data` to trwały wolumen. Plik `/data/options.json` zawiera opcje użytkownika.
- `map: - type: addon_config` montuje `/config` w kontenerze (na hoście `/addon_configs/<repo>_<slug>`). Tam użytkownik wrzuca plik PEM.
- `homeassistant_api: true` daje dostęp do REST API HA przez `http://supervisor/core/api` z tokenem `SUPERVISOR_TOKEN`.
- `services: - mqtt:want` pozwala pobrać dane brokera przez Supervisor API (`http://supervisor/services/mqtt`).
- Ingress: `ingress: true`, `ingress_port`, `panel_icon`, `panel_title`. Aplikacja musi obsługiwać prefiks ścieżki z nagłówka `X-Ingress-Path` i akceptować ruch tylko z `172.30.32.2`.

---

## 3. Architektura

```
┌──────────────────────────── kontener aplikacji HA ─────────────────────────────┐
│                                                                                │
│  run.sh ─► python -m budget                                                    │
│                                                                                │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐  │
│  │ eb_client   │◄──│ sync_service │──►│ storage      │◄──│ categorizer      │  │
│  │ (JWT, HTTP) │   │ (scheduler)  │   │ (SQLite)     │   │ (reguły, MCC)    │  │
│  └─────────────┘   └──────┬───────┘   └──────┬───────┘   └──────────────────┘  │
│                           │                  │                                 │
│                    ┌──────▼───────┐   ┌──────▼───────┐   ┌──────────────────┐  │
│                    │ ha_publisher │   │ budget_engine│   │ web (FastAPI)    │  │
│                    │ MQTT disc. + │◄──│ agregacje    │◄──│ Ingress UI       │  │
│                    │ HA events    │   └──────────────┘   │ auth / reguły    │  │
│                    └──────────────┘                      │ import CSV       │  │
│                                                          └──────────────────┘  │
│  /data/budget.db   /config/enablebanking.pem   /data/options.json              │
└────────────────────────────────────────────────────────────────────────────────┘
          │ HTTPS                         │ MQTT                    │ Ingress
   api.enablebanking.com          Mosquitto (HA)            panel boczny HA
```

### 3.1 Stack

- Python 3.12+ na obrazie `ghcr.io/home-assistant/base` (Alpine), z instalacją `python3` i `py3-pip` przez `apk` i virtualenvem w `/opt/venv`.
- `httpx` do HTTP, `PyJWT[crypto]` do JWT, `fastapi` i `uvicorn` do panelu, `jinja2` + **htmx** do UI (bez builda frontendu), `apscheduler` do harmonogramu, `aiomqtt` do MQTT, `pydantic` do modeli, `sqlite3` z wbudowanych bibliotek plus własne migracje.
- Testy: `pytest`, `pytest-asyncio`, `respx` (mock httpx).
- Jeden proces asyncio. Uvicorn i scheduler działają w tej samej pętli.

### 3.2 Struktura repo

```
ha-budget-app/                 # repozytorium aplikacji HA
├── repository.yaml            # name, url, maintainer
├── budget/                    # folder aplikacji (slug: budget)
│   ├── config.yaml
│   ├── Dockerfile
│   ├── apparmor.txt
│   ├── run.sh
│   ├── DOCS.md  README.md  CHANGELOG.md  icon.png  logo.png
│   ├── translations/{en,pl}.yaml
│   └── app/
│       ├── pyproject.toml
│       ├── src/budget/
│       │   ├── __main__.py
│       │   ├── settings.py        # czyta /data/options.json + env
│       │   ├── eb_client.py
│       │   ├── sync_service.py
│       │   ├── storage/{db.py, migrations/*.sql, repo.py}
│       │   ├── categorizer.py
│       │   ├── budget_engine.py
│       │   ├── ha_publisher.py
│       │   ├── csv_import.py
│       │   └── web/{app.py, routes/*.py, templates/*.html, static/}
│       └── tests/
└── .github/workflows/         # lint + testy + build multi-arch
```

### 3.3 `config.yaml` (szkic)

```yaml
name: "Budżet Domowy"
version: "0.1.0"
slug: budget
description: "Budżet domowy z automatycznym pobieraniem transakcji z banku (PSD2 / Enable Banking)"
arch: [aarch64, amd64]
init: false            # przy s6-overlay v3 z obrazu base
startup: application
boot: auto
ingress: true
ingress_port: 8099
panel_icon: mdi:wallet
panel_title: "Budżet"
homeassistant_api: true
services:
  - mqtt:want
map:
  - type: addon_config
    read_only: false
options:
  eb_application_id: null
  eb_private_key_file: "enablebanking.pem"
  eb_redirect_url: null
  sync_times: ["06:30", "13:30", "21:30"]
  currency: "PLN"
  month_start_day: 1
  consent_warning_days: 14
  log_level: info
schema:
  eb_application_id: str
  eb_private_key_file: str
  eb_redirect_url: url
  sync_times: ["match(^([01]\\d|2[0-3]):[0-5]\\d$)"]
  currency: str
  month_start_day: "int(1,28)"
  consent_warning_days: "int(1,60)"
  log_level: "list(debug|info|warning|error)"
```

Sprawdzić przy implementacji: czy `init: false` jest nadal wymagane dla bieżącego obrazu `base`. Przypiąć wersję obrazu `base` w Dockerfile i dodać `LABEL io.hass.type="app"` oraz `io.hass.arch` i `io.hass.version`.

---

## 4. Model danych (SQLite, `/data/budget.db`)

```sql
CREATE TABLE eb_session (
  id TEXT PRIMARY KEY,               -- session_id z EB
  aspsp_name TEXT NOT NULL,
  status TEXT NOT NULL,              -- AUTHORIZED / EXPIRED / REVOKED
  valid_until TEXT NOT NULL,         -- RFC3339 UTC
  created_at TEXT NOT NULL,
  raw_json TEXT NOT NULL             -- pełna odpowiedź POST /sessions
);

CREATE TABLE account (
  identification_hash TEXT PRIMARY KEY,   -- stały klucz między sesjami
  current_uid TEXT,                       -- uid w aktywnej sesji
  session_id TEXT REFERENCES eb_session(id),
  iban TEXT, name TEXT, product TEXT, currency TEXT NOT NULL,
  cash_account_type TEXT,
  display_name TEXT,                      -- nadane przez użytkownika
  include_in_budget INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE balance_snapshot (
  account_hash TEXT REFERENCES account(identification_hash),
  balance_type TEXT, amount TEXT, currency TEXT,
  reference_date TEXT, fetched_at TEXT,
  PRIMARY KEY (account_hash, balance_type, fetched_at)
);

CREATE TABLE txn (
  id TEXT PRIMARY KEY,                 -- patrz 5.2 (dedup)
  account_hash TEXT NOT NULL REFERENCES account(identification_hash),
  source TEXT NOT NULL,                -- 'eb' | 'csv' | 'manual'
  status TEXT NOT NULL,                -- BOOK | PDNG
  booking_date TEXT, value_date TEXT, transaction_date TEXT,
  amount TEXT NOT NULL,                -- Decimal jako string, ZE ZNAKIEM (+ wpływ, - wydatek)
  currency TEXT NOT NULL,
  counterparty_name TEXT, counterparty_iban TEXT,
  description TEXT,                    -- złączone remittance_information
  mcc TEXT,
  category_id INTEGER REFERENCES category(id),
  category_source TEXT,                -- 'rule' | 'manual' | 'mcc' | NULL
  is_internal_transfer INTEGER NOT NULL DEFAULT 0,
  raw_json TEXT,
  first_seen_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX txn_date ON txn(booking_date);

CREATE TABLE category (
  id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('income','expense','transfer')),
  parent_id INTEGER REFERENCES category(id), icon TEXT
);

CREATE TABLE rule (
  id INTEGER PRIMARY KEY, priority INTEGER NOT NULL DEFAULT 100,
  field TEXT NOT NULL,          -- counterparty_name | description | counterparty_iban | mcc | amount
  op TEXT NOT NULL,             -- contains | regex | equals | lt | gt
  value TEXT NOT NULL,
  direction TEXT,               -- NULL | 'in' | 'out'
  category_id INTEGER NOT NULL REFERENCES category(id),
  enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE budget (
  category_id INTEGER REFERENCES category(id),
  month TEXT NOT NULL,          -- 'YYYY-MM' lub '*' = domyślny co miesiąc
  amount TEXT NOT NULL,
  PRIMARY KEY (category_id, month)
);

CREATE TABLE sync_log (
  id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT,
  trigger TEXT,                 -- 'schedule' | 'manual' | 'backfill'
  ok INTEGER, new_txn INTEGER, updated_txn INTEGER, error TEXT
);
```

Migracje: pliki `NNN_*.sql` stosowane po kolei, a wersja trzymana w `PRAGMA user_version`.

Domyślne kategorie (seed): Wynagrodzenie, Inne wpływy, Jedzenie/zakupy spożywcze, Restauracje, Transport/paliwo, Mieszkanie/media, Energia, Zdrowie, Dzieci, Rozrywka, Subskrypcje, Ubrania, Prezenty, Kredyt/raty, Oszczędności (transfer), Przelewy własne (transfer), Inne.

---

## 5. Logika

### 5.1 Synchronizacja (`sync_service`)

1. Na starcie sprawdzić, czy jest aktywna sesja (`GET /sessions/{id}`). Jeśli nie, ustawić status „wymaga autoryzacji” i nie odpytywać banku.
2. Harmonogram według `sync_times` w strefie czasowej HA (`TZ` z kontenera). Przed każdym przebiegiem sprawdzić, czy dzisiejszy licznik zapytań do banku jest mniejszy niż 4.
3. Dla każdego konta z `include_in_budget = 1`:
   - `balances` → zapis snapshotu,
   - `transactions` z `date_from = max(ostatnia booking_date − 10 dni, dzisiaj − 90 dni)`, z paginacją do końca.
4. Po `POST /sessions` (nowa zgoda) wykonać **backfill**: `date_from` = dzisiaj − 730 dni. Bank zwróci tyle, ile pozwala, a wynik trzeba zalogować.
5. Upsert transakcji (5.2), kategoryzacja nowych (5.3), przeliczenie budżetu (5.4), publikacja do HA (6).
6. Błędy:
   - 401 na JWT → wygenerować nowy token i spróbować raz jeszcze.
   - 429 → backoff i przejście do następnego slotu.
   - Wygasła lub odwołana sesja → oznaczyć `EXPIRED`, wysłać powiadomienie, zatrzymać odpytywanie.
   - Każdy przebieg zapisać w `sync_log`.

### 5.2 Deduplikacja

- Jeśli istnieje `transaction_id` lub `entry_reference`, to `id = sha256(account_hash | "eb" | transaction_id or entry_reference)`.
- W przeciwnym razie `id = sha256(account_hash | booking_date | amount | counterparty | description | n)`, gdzie `n` rozróżnia identyczne transakcje z tego samego dnia (numer kolejny w obrębie paczki).
- **PDNG → BOOK:** transakcja oczekująca często nie ma stabilnego ID. Przy każdym syncu usunąć dotychczasowe PDNG danego konta z okna synchronizacji i wstawić aktualne. BOOK są niezmienne (upsert bez nadpisywania ręcznej kategorii).
- Import CSV: dopasowanie do istniejących BOOK po (data, kwota, kontrahent), a pozostałe wstawiane jako `source = 'csv'`.

### 5.3 Kategoryzacja

Kolejność:
1. `category_source = 'manual'` → nigdy nie nadpisywać.
2. Przelew własny: `counterparty_iban` należy do jednego z `account.iban` → `is_internal_transfer = 1` i kategoria „Przelewy własne”. Nie liczy się do przychodów ani wydatków.
3. Reguły użytkownika po `priority` rosnąco, pierwsza pasująca wygrywa. Porównania bez rozróżniania wielkości liter i bez polskich znaków (normalizacja NFKD).
4. Mapowanie MCC → kategoria (tabela w kodzie, np. 5411 → spożywcze, 5541/5542 → paliwo, 5812/5814 → restauracje, 4900 → media).
5. Brak dopasowania → `NULL` („Do skategoryzowania”).

W UI przy ręcznej zmianie kategorii proponować „utwórz regułę z tego kontrahenta”. Ponowne zastosowanie reguł do historii dotyczy tylko transakcji bez kategorii `manual`.

### 5.4 Budżet (`budget_engine`)

- Okres rozliczeniowy: miesiąc liczony od `month_start_day`. Datą transakcji jest `booking_date`, a przy jej braku `transaction_date`.
- Przychody to suma dodatnich, a wydatki suma ujemnych (wartość bezwzględna). Pomijać `is_internal_transfer` i kategorie typu `transfer`.
- Per kategoria: `spent`, `budget` (z `budget` dla danego miesiąca, inaczej `'*'`), `remaining`, `pct`.
- Prognoza końca miesiąca (prosta): `spent / dni_minione * dni_w_okresie`.
- Wszystko w `Decimal`, zaokrąglane do 0.01 dopiero przy prezentacji.

---

## 6. Integracja z Home Assistant

### 6.1 Encje przez MQTT Discovery (preferowane)

- Jeśli Supervisor zwraca usługę MQTT, publikować `homeassistant/<component>/budget/<object_id>/config` z `unique_id`, `device` (jedno urządzenie „Budżet Domowy”), `state_topic`, `json_attributes_topic` i `availability_topic` (LWT). Wszystkie wiadomości z `retain`.
- Jeśli MQTT nie jest dostępne, użyć fallbacku `POST http://supervisor/core/api/states/sensor.budget_*`. W logu i w panelu wyraźnie pokazać, że takie encje nie mają `unique_id` i znikną po restarcie HA aż do najbliższej synchronizacji.

Encje:

| object_id | typ | stan | atrybuty |
|---|---|---|---|
| `balance_<konto>` | sensor, `device_class: monetary`, `state_class: total` | saldo dostępne (CLAV/ITAV/XPCD, wg dostępności) | iban (zamaskowany), typ salda, data |
| `month_income` | sensor monetary | suma wpływów okresu | okres od–do |
| `month_expenses` | sensor monetary | suma wydatków okresu | prognoza |
| `month_net` | sensor monetary | wpływy − wydatki | |
| `category_<slug>` | sensor monetary | wydane w kategorii | budget, remaining, pct |
| `budget_used_pct` | sensor `%` | % całego budżetu wydatków | |
| `uncategorized_count` | sensor | liczba transakcji bez kategorii | |
| `consent_days_left` | sensor, `unit: d` | dni do wygaśnięcia zgody | valid_until |
| `last_sync` | sensor `device_class: timestamp` | czas ostatniego udanego syncu | ok, nowe transakcje |
| `sync_now` | button | wywołuje synchronizację | |

Waluta: `unit_of_measurement: PLN`. Konto walutowe dostaje własną walutę i nie jest sumowane z PLN (lub jest pomijane w budżecie, jeśli tak ustawiono).

### 6.2 Zdarzenia i powiadomienia

- `POST /core/api/events/budget_transaction` dla każdej nowej transakcji BOOK, z danymi: kwota, kontrahent, kategoria, konto. Pozwala to tworzyć automatyzacje, np. powiadomienie o wydatku powyżej X.
- `POST /core/api/services/persistent_notification/create` wysyłać, gdy:
  - zgoda wygasa w ciągu `consent_warning_days` (raz dziennie), z linkiem do panelu,
  - sesja wygasła lub została odwołana,
  - synchronizacja nie powiodła się 3 razy z rzędu.

---

## 7. Panel (Ingress)

Wszystkie ścieżki relatywne względem `X-Ingress-Path`. Serwer nasłuchuje na `0.0.0.0:8099` i odrzuca ruch spoza `172.30.32.2`.

Widoki:
1. **Status:** stan zgody (dni do końca), ostatni sync, liczniki zapytań dzisiaj, przycisk „Synchronizuj teraz” (z nagłówkami PSU z bieżącego requestu), log ostatnich 20 przebiegów.
2. **Połącz bank / Odnów zgodę:**
   - wybór banku z `GET /aspsps?country=PL` (domyślnie Millennium),
   - „Otwórz stronę banku” → `POST /auth` → link w nowej karcie,
   - pole „Wklej adres, na który zostałeś przekierowany (albo sam kod)” → parsowanie `code` i `state`, weryfikacja `state`, `POST /sessions`, backfill.
   - Na ekranie wyświetlić przypomnienie: w trybie Restricted konta muszą być wcześniej podlinkowane w panelu Enable Banking.
3. **Transakcje:** tabela z filtrami (okres, konto, kategoria, „bez kategorii”, tekst), zmiana kategorii inline przez htmx, „utwórz regułę”.
4. **Kategorie i budżety:** CRUD i kwoty miesięczne.
5. **Reguły:** CRUD, kolejność, podgląd „ile transakcji pasuje”, „zastosuj do historii”.
6. **Import CSV:** upload pliku z Millenetu → podgląd → import (5.2).
7. **Konta:** nazwa wyświetlana, „uwzględniaj w budżecie”.

---

## 8. Bezpieczeństwo

- Klucz prywatny EB: plik PEM w `/config/` (addon_config). Nie trzymać go w `options.json`, bo trafia do UI i kopii. Przy starcie sprawdzić, czy plik istnieje, i wypisać czytelny błąd z instrukcją.
- W logach nie logować pełnych IBAN-ów, tokenów, `code` ani JWT. Maskowanie: `PL** **** … 1234`.
- `raw_json` w bazie jest akceptowalne (lokalnie), ale trzeba pamiętać, że **backup HA zawiera dane finansowe**. Opisać to w DOCS.md.
- Tylko odczyt (AIS). Żadnych endpointów płatności w kodzie.
- `panel_admin: true` (domyślne), więc panel widzą tylko administratorzy HA.
- AppArmor: profil ograniczający zapis do `/data`, `/config` i `/tmp`.

---

## 9. Kroki, które użytkownik wykonuje ręcznie (opisać w DOCS.md)

1. Założyć konto na https://enablebanking.com/sign-in/ (logowanie linkiem e-mail).
2. W Control Panel → Applications utworzyć aplikację:
   - Environment: **Production** (osobno można założyć Sandbox do testów),
   - Redirect URL: adres HTTPS, np. `https://<twoje-HA>/budget-callback` (nie musi działać publicznie, bo kod i tak się wkleja) albo adres, który EB akceptuje,
   - klucz: „Generate in the browser” → **zapisać pobrany .pem** (nie da się go pobrać ponownie),
   - skopiować Application ID.
3. W aplikacji EB wybrać **Link accounts** → zalogować się do Millennium → zatwierdzić w aplikacji mobilnej. Aplikacja powinna mieć status „Restricted / Active”.
4. Wgrać `.pem` do `/addon_configs/<repo>_budget/enablebanking.pem` (np. przez Samba albo File editor).
5. Zainstalować aplikację w HA, wpisać Application ID i redirect URL, uruchomić.
6. W panelu „Połącz bank” przejść autoryzację i wkleić adres zwrotny.
7. (Opcjonalnie) Zaimportować CSV z Millenetu dla starszej historii.

---

## 10. Plan pracy (kamienie milowe dla Claude Code)

Każdy etap kończy się zielonymi testami i commitem.

- **M0 — szkielet:** struktura repo, `pyproject.toml`, ruff + mypy + pytest, CI (lint + testy), `settings.py` czytający `options.json` z fallbackiem na `.env` do dev.
- **M1 — klient Enable Banking:** generowanie i cache JWT, metody `get_aspsps`, `start_auth`, `create_session`, `get_session`, `delete_session`, `get_balances`, `iter_transactions` (paginacja), obsługa nagłówków PSU, typowane modele pydantic, testy na `respx`. Skrypt CLI `python -m budget.cli auth` do ręcznego przejścia flow na **Sandboxie**.
- **M2 — storage:** migracje, repozytoria, deduplikacja (5.2) z testami na przypadki PDNG → BOOK i identycznych transakcji.
- **M3 — sync:** `sync_service` z harmonogramem, licznikiem dziennym, backfillem i `sync_log`. Testy z zamockowanym klientem.
- **M4 — kategoryzacja i budżet:** `categorizer`, seed kategorii, MCC, przelewy własne, `budget_engine`. Testy jednostkowe z przykładowymi transakcjami (fixture JSON w formacie EB).
- **M5 — HA publisher:** MQTT Discovery, fallback REST, zdarzenia, powiadomienia. Test integracyjny z brokerem w dockerze (opcjonalnie).
- **M6 — panel Ingress:** widoki z sekcji 7, poprawna obsługa `X-Ingress-Path`, allowlista IP.
- **M7 — import CSV:** parser eksportu Millenetu. **Potrzebny przykładowy plik od użytkownika** (zanonimizowany), bo formatu nie zakładać z góry: kodowanie (cp1250 czy UTF-8), separator, format dat i kwot z przecinkiem.
- **M8 — pakowanie:** `config.yaml`, Dockerfile (przypięty `base`, labele), `run.sh`, AppArmor, tłumaczenia pl/en, DOCS.md, `repository.yaml`, workflow budujący obrazy amd64/aarch64. Test lokalny zgodnie z https://developers.home-assistant.io/docs/apps/testing
- **M9 — test end-to-end na produkcji** z realnym kontem Millennium w trybie Restricted.

---

## 11. Otwarte kwestie do sprawdzenia w trakcie

- [ ] Dokładna nazwa ASPSP Millennium w `GET /aspsps` oraz wartości `maximum_consent_validity` i `required_psu_headers` (odczytać z API, nie hardkodować).
- [ ] Ile historii faktycznie zwraca Millennium przy backfillu.
- [ ] Czy Millennium zwraca `transaction_id`/`entry_reference` stabilnie (wpływa na dedup) i czy podaje `merchant_category_code`.
- [ ] Które typy sald zwraca Millennium (wybór salda do sensora).
- [ ] Czy konta oszczędnościowe i karty kredytowe są dostępne przez AIS w Millennium.
- [ ] Aktualny tag obrazu `ghcr.io/home-assistant/base` i czy `init: false` jest potrzebne.
- [ ] Format CSV z Millenetu (M7).

## 12. Źródła

- Enable Banking API reference: https://enablebanking.com/docs/api/reference/
- Enable Banking FAQ (tryb restricted): https://enablebanking.com/docs/faq/
- Enable Banking — specyfika Polski: https://enablebanking.com/docs/markets/pl/
- Przykłady kodu EB: https://github.com/enablebanking/enablebanking-api-samples
- Istniejąca integracja HA (tylko salda, punkt odniesienia): https://github.com/SurfHost/ha-enablebanking
- Firefly III — konfiguracja EB w trybie restricted: https://docs.firefly-iii.org/tutorials/data-importer/eb/
- HA Apps — konfiguracja: https://developers.home-assistant.io/docs/apps/configuration
- HA Apps — komunikacja (API, MQTT, Ingress): https://developers.home-assistant.io/docs/apps/communication
