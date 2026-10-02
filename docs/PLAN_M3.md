# Plan M3 — Add-on w HA: pierwsze uruchomienie

Zakres i kryteria akceptacji: [`ROADMAP.md`](ROADMAP.md#m3--add-on-w-ha-pierwsze-uruchomienie).
Plan zaakceptowany 2026-10-02.

## Kontekst

M2 jest zrobiony i wypchnięty (99d8ab8, CI zielone). Księga bez duplikatów działa na prawdziwych
danych, na razie tylko z CLI w kontenerze Claude Code. M3 zamienia ją w add-on HA, który:
- sam synchronizuje się z bankiem 3 razy na dobę,
- ma panel w Ingress,
- publikuje encje przez MQTT.

To fundament dla M4 (poprawianie kategorii wymaga panelu) i M5 (encje budżetu).

Decyzje (wywiad 2026-10-02):
- **Całe M3 jako jeden etap** z jednym checkpointem.
- **Stos async wg SPEC §3:** FastAPI + uvicorn + Jinja2/htmx + APScheduler (AsyncIOScheduler) +
  aiomqtt, wszystko w jednej pętli asyncio. Wzorce z `nokia_tracker` przenoszę w wersji ASGI.

Checkpoint M2 zamknięty 2026-10-02. Jego jedyny otwarty punkt, czyli
suma kontrolna karty i konta EUR (wymaga drugiej migawki ITBD), przechodzi do akceptacji M3.

## Decyzje projektowe (moja rekomendacja, do akceptacji razem z planem)

1. **Obraz:** `FROM python:3.12-alpine3.22` z przypiętą wersją, bez `build.yaml` i bez `image:`.
   Supervisor buduje lokalnie, tak jak w pozostałych add-onach; host to x86_64. Rozstrzyga to
   otwarty punkt „obraz bazowy” w ROADMAP.
2. **Przeniesienie z CLI bez nowego SCA.** Z tego kontenera nie widać `/addon_configs`, więc
   wszystko wgrywasz przez panel, ekran „Bank”:
   - klucz `eb_prod.pem` zapisywany do `/config/enablebanking.pem` (0600);
   - plik `sessions/<id>.json`, bo tylko odpowiedź `POST /sessions` ma szczegóły kont. Add-on
     sprawdza go przez `GET /sessions/{id}`; to zapytanie do Enable Banking, nie do banku, więc
     nie zużywa limitu;
   - historię odtwarzasz importem tego samego CSV w panelu. Import jest idempotentny i nie zależy
     od kolejności, co M2 dowiódł, więc **nie przenoszę `ledger.db`**.

   **Po migracji CLI `--live` przestaje być używane.** Wspólna sesja oznacza wspólny limit
   zapytań.
3. **Limit PSD2 (4 na konto na dobę):**
   - Okno przyrostowe: transakcje od `max(ostatnie księgowanie − 10 d, dziś − 90 d)`, czyli zwykle
     jedna strona.
   - Licznik w tabeli `api_request` liczy per (dzień, konto, endpoint), uwzględnia każdą stronę
     i oznacza, czy zapytanie wysłano z nagłówkami PSU.
   - Domyślnie przy 3 synchronizacjach wychodzi 3 zapytania o salda + 3 o transakcje na konto.
   - Strażnik nie wyśle zapytania, które przekroczyłoby limit 4. Pełnego okna 90 dni nie ma
     w harmonogramie; robi się tylko po nowej sesji albo ręcznie.
   - „Synchronizuj teraz” z panelu wysyła nagłówki PSU z żądania (SPEC §2.3).
   - 429 / `ASPSP_RATE_LIMIT_EXCEEDED` → przerwanie i przejście do następnego slotu, zapis
     w `sync_log`.
   - Nie wiadomo, czy bank liczy limit per endpoint, czy łącznie. Rozstrzygnie to obserwacja
     przy akceptacji.
4. **Encje MQTT:**
   - Discovery w stylu `nokia_tracker`: jedno urządzenie, LWT `budget/availability`,
     wiadomości retained, `object_id` przypina entity_id.
   - Salda: `sensor.budget_saldo_{current_pln|fx_eur|card_pln}`, wartość ITAV z fallbackiem na
     ITBD, `device_class: monetary`, `state_class: total`; w atrybutach zamaskowany IBAN i data.
   - Pozostałe: `sensor.budget_last_sync` (timestamp), `sensor.budget_consent_days_left`,
     `sensor.budget_requests_today` (diagnostyczna), `binary_sensor.budget_sync_problem`,
     `button.budget_sync_now` (subskrypcja tematu komend).
   - **„Liczbę do przejrzenia” przesuwam do M4.** Kolejka przeglądu powstaje dopiero tam, więc
     teraz encja byłaby pusta.
5. **Powiadomienia operacyjne:**
   - Zdarzenia: zgoda wygasa w ciągu `consent_warning_days` (raz na dobę), sesja wygasła lub
     cofnięta, 3 nieudane synchronizacje z rzędu.
   - Kanały: zawsze `persistent_notification` z linkiem do panelu. Dodatkowo opcja
     `notify_service` (alias osoby, np. `notify.<osoba>`, nigdy `mobile_app_*`; domyślnie pusta).
   - Deduplikacja wg `fuel_tracker/notifications.py`.
6. **Panel:**
   - Środowisko: htmx dostarczany lokalnie w `static/` (nie z CDN), mobile-first, wspólny
     `base.html` z plakietką wersji.
   - Ekrany:
     - **Status:** zgoda, ostatnia synchronizacja, liczniki dnia, przycisk sync, 20 ostatnich
       przebiegów, wynik kontroli sald z `check_balances`;
     - **Bank:** klucz, import sesji z CLI, „Połącz bank / Odnów zgodę” (link SCA, wklejenie
       URL-a lub kodu, `create_session`, backfill);
     - **Import CSV:** upload, raport L0–L3 i statusy `csv_row`, mapowanie niezmapowanego numeru
       karty;
     - **Konta:** `display_name`, `include_in_budget`;
     - **Transakcje:** filtry konto/okres/typ/tekst, stronicowanie, oznaczenia przelewów,
       zwrotów i źródła.
   - Ingress: `root_path` z `X-Ingress-Path`, wszystko spoza `172.30.32.2` odrzucane (w trybie dev
     wyłączone), `Cache-Control: no-store` na HTML i API, `?v=<wersja>` + `immutable` na statykach.

## Pliki (`budget/app/src/budget/` w repo `miczu71/ha-budget-app`, gałąź `main`)

| Plik | Zmiana |
|---|---|
| `report.py` (nowy) | Zapytania z `cli._print_report` (cli.py:351-410) wydzielone do funkcji zwracającej dataclass; CLI i panel używają tej samej |
| `storage/migrations/002_addon.sql` (nowy) | `eb_session.status`, `sync_log` + trigger/new/updated/error, `api_request(day, account_id, endpoint, n, psu)`, `notify_state` |
| `sessions.py` (nowy) | Import sesji z pliku JSON i zapis po `create_session`: `eb_session` + `upsert_eb_account` (ledger.py:74); stan `pending_auth` w bazie |
| `sync_service.py` (nowy) | Harmonogram z `sync_times`, strażnik limitu, okno przyrostowe, `ledger.ingest_api` / `ingest_balances` bez plików zrzutów (logika z cli.py:296 bez dump-ów), obsługa `EBRateLimited` / `EBSessionExpired`, `sync_log` |
| `ha_publisher.py` (nowy) | aiomqtt discovery i stany, przycisk `sync_now`, poświadczenia z `http://supervisor/services/mqtt` |
| `ha_client.py` (nowy) | Supervisor Core API (`SUPERVISOR_TOKEN`): `persistent_notification`, `notify.*` |
| `notifications.py` (nowy) | Reguły i deduplikacja powiadomień operacyjnych |
| `web/app.py`, `web/routes_*.py`, `web/templates/*.html`, `web/static/{app.css,htmx.min.js}` (nowe) | Fabryka FastAPI, middleware ingress / allowlista / cache, ekrany |
| `__main__.py` | Tryb serwera: uvicorn + scheduler + publisher w jednej pętli; CLI zostaje dostępne |
| `cli.py` | `report` przez `report.py`; `ingest-eb` współdzieli kod pobierania z `sync_service` |
| `settings.py` | `db_path` (`/data/budget.db`), `notify_service`, flaga `dev` (bez allowlisty) |
| `pyproject.toml` | Nowe zależności: fastapi, uvicorn, jinja2, python-multipart, apscheduler 3.x, aiomqtt; dev: httpx ASGI test client |
| `budget/Dockerfile`, `budget/run.sh`, `budget/apparmor.txt`, `budget/requirements.txt` (nowe) | Wzór: `nokia_tracker/nokia_tracker/Dockerfile` i `run.sh` (jq z `/data/options.json`, `exec python -m budget serve`). AppArmor z zapisem tylko do `/data`, `/config`, `/tmp` |
| `budget/config.yaml` | Wersja 0.1.0, `mqtt:need` (rezygnacja z fallbacku REST z SPEC §6.1), `panel_admin`, opcja `notify_service`, aktualny nagłówek |
| `budget/DOCS.md`, `CHANGELOG.md`, `README.md` | Instalacja, wgranie klucza i sesji, ostrzeżenie: kopia HA zawiera dane finansowe, encje |
| `.github/workflows/ci.yml` | Nowy job `docker build` (amd64), który łapie problemy z kołami pod musl |
| `docs/PLAN_M3.md` (nowy), `docs/ROADMAP.md` | Ten plan; M2 ✅, decyzja o obrazie, odstępstwa (liczba do przejrzenia → M4, `mqtt:need`) |

Do ponownego użycia bez zmian:
- `eb_client.py`: async, ponowna próba po 401, typy błędów, `parse_redirect`, `start_auth`,
  `create_session`;
- `ledger.ingest_*`, `check_balances`, `transaction()`;
- `storage/db.connect`: WAL, 0600, migracje;
- `logging_utils.setup_logging` / `RedactingFilter`.

## Kolejność (commit na krok, TDD, CI zielone)

0. `docs/PLAN_M3.md` (kopia tego planu) + ROADMAP: M2 ✅, M3 w toku.
1. `report.py` + migracja 002 + `sessions.py`, z testami.
2. `sync_service`: testy respx dla okna przyrostowego, licznika (strony, PSU), 429, wygasłej sesji
   i backfillu.
3. `ha_client` + `notifications` + `ha_publisher`: testy na fałszywym brokerze i fałszywym
   Supervisorze.
4. Panel: middleware, ekrany, testy klientem ASGI (root_path, allowlista, nagłówki cache, `?v=`).
5. Pakowanie (Dockerfile, run.sh, AppArmor, config.yaml, DOCS) + job CI `docker build`.
6. Uruchomienie lokalne w kontenerze Claude Code na **syntetycznej bazie** (fixture'y Mock ASPSP
   + zanonimizowany CSV) i Playwright: zrzuty desktop i 390×844, 0 błędów konsoli. Zrzuty idą do
   `/config/playwright/`, bez prawdziwych danych.
7. Wydanie 0.1.0 przez skill `release` (oba pliki wersji, opublikowane wydanie, nie szkic).
8. Instalacja na żywo (każdy krok mutujący dopiero po jawnym „go”):
   - dodanie repozytorium w Supervisorze, instalacja, opcje (prod app id, redirect,
     `notify_service`);
   - w panelu: wgranie klucza i pliku sesji, import CSV, pierwsza synchronizacja;
   - Playwright przez direct-IP kontenera.
9. Obserwacja przez ≥ 1 pełną dobę (3 sloty), potem checkpoint.

Przed każdym commitem obowiązuje blokujący skan diffu na nazwy i miejsca z prawdziwych danych:
`! git diff --cached | grep -iE '…' && git commit`.

## Weryfikacja / akceptacja M3

- CI zielone: ruff, mypy strict, pytest, docker build.
- Add-on zainstalowany w Supervisorze, uruchamia się, w logu nie ma IBAN-ów, tokenów ani adresu.
- Sesja przeniesiona **bez nowego SCA**. `consent_days_left` zgadza się z 2027-03-30.
- Księga w add-onie po imporcie CSV i synchronizacji odpowiada wynikowi M2: 7/7 spłat, 0
  rozbieżnych dni salda, migawka ITBD rachunku co do grosza. **Nowe:** po drugiej migawce ITBD
  zgadza się suma kontrolna karty i konta EUR (zaległość z M2).
- Doba z 3 slotami: 3 udane przebiegi, 0 odpowiedzi 429, `requests_today` ≤ 4 na
  (konto, endpoint). Odpowiedź, czy bank liczy limit per endpoint, wpisuję do
  `FINDINGS_millennium.md`.
- Encje widoczne w HA, `button.budget_sync_now` uruchamia synchronizację (z PSU, poza limitem).
- Testowe powiadomienie przez `persistent_notification` i skonfigurowany alias `notify.*` dochodzi.
- Panel przez Ingress na telefonie (WebView): plakietka 0.1.0, wszystkie 5 ekranów, Playwright
  z 0 błędów konsoli.
- Pełny flow SCA „Połącz bank” sprawdzony testami i lokalnie na Sandboxie (Mock ASPSP). Na
  produkcji nie odpalam go, żeby nie zastąpić działającej zgody.

## Ryzyka

- **Bank liczy limit łącznie, a nie per endpoint.** Wtedy 3 przebiegi × 2 zapytania dają 6 na
  dobę. Strażnik nie przekroczy 4, ale ostatni slot dostanie same salda. Rozwiązanie po obserwacji:
  transakcje 2 razy na dobę.
- **Koła musl:** pydantic-core i cryptography mają koła musllinux dla x86_64. Job CI
  `docker build` wyłapie regresję.
- **Ingress + FastAPI `root_path`:** linki w htmx muszą być względne. Pokrywają to testy
  i Playwright przez prawdziwy Ingress.
- **Dane finansowe w kopiach HA:** opisane w DOCS.md. Zrzuty Playwright na żywo nie trafiają
  do repo.
- **Rozmiar etapu (jeden checkpoint):** łagodzą to commity per krok i zielone CI na każdym.

## Odstępstwa od planu (wykonanie 2026-10-02)

- **Harmonogram bez APScheduler:** własna pętla `next_run()` na `sync_times` w strefie HA (test
  na zmianie czasu) — mniej zależności, nic do typowania.
- **Przycisk `button.budget_sync_now` liczy się do limitu:** z HA nie ma danych użytkownika
  (IP, przeglądarka), a podrabianie nagłówków PSU byłoby nieuczciwe wobec banku. Poza limitem
  działa tylko „Synchronizuj teraz” z panelu.
- **CLI `ingest-eb --live` bez zmian** (nie współdzieli kodu z `sync_service`) — po przeniesieniu
  sesji do add-onu nie jest używane.
- **`default_entity_id` zamiast `object_id`** w discovery — od HA 2026.4 `object_id` jest
  ignorowane.
- **Encje sald jako „Dostępne — …” (ITAV):** dla karty kredytowej ITAV > ITBD i oba dodatnie,
  więc ITAV to dostępny limit, nie saldo. ITBD idzie w atrybutach; znaczenie ITBD karty
  rozstrzygnie suma kontrolna przy drugiej migawce (akceptacja M3), zadłużenie karty → M9.
- **Synchronizacja obejmuje wszystkie konta ze zgody**; „w budżecie” dotyczy tylko budżetu
  (M5).
- **Lokalny serwer dev z `env -u SUPERVISOR_TOKEN`**: wewnątrz innego add-onu token istnieje,
  więc serwer dev wysyłałby powiadomienia do prawdziwego HA.
- **Do M4:** heurystyka typu z API na danych Mock ASPSP oznacza „Płatność kartą” na rachunku
  jako BLIK (na prawdziwych danych zgodność 90%).
