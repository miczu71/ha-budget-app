# Roadmap — Budżet Domowy

Pełna specyfikacja: [`SPEC.md`](SPEC.md). Każdy etap kończy się zielonymi testami, commitem
i checkpointem (przegląd użytkownika + jawne „go” przed kolejnym etapem).

| Etap | Zakres | Status |
|---|---|---|
| M0 | Szkielet repo, pyproject, ruff/mypy/pytest, CI, `settings.py`, maskowanie w logach | zrobione — czeka na checkpoint |
| M1 | Klient Enable Banking (JWT, AIS, PSU, paginacja), modele pydantic, CLI, flow na **Sandboxie** | zrobione — czeka na checkpoint |
| M1b | Sonda Production Restricted na realnym Millennium → `docs/FINDINGS_millennium.md` (§11) | zrobione, poza drugim zrzutem (stabilność `entry_reference` po ≥ 1 dniu) |
| M2 | Storage: migracje, repozytoria, deduplikacja (PDNG→BOOK) | — |
| M3 | `sync_service`: harmonogram, licznik dzienny, backfill, `sync_log` | — |
| M4 | Kategoryzacja (reguły, MCC, przelewy własne) + `budget_engine` | — |
| M5 | HA publisher: MQTT Discovery, fallback REST, zdarzenia, powiadomienia | — |
| M6 | Panel Ingress (FastAPI + htmx) | — |
| M7 | Import CSV z Millenetu (fixture zanonimizowany narzędziem `tools/anonymize_millenet.py`) | — |
| M8 | Pakowanie add-onu (Dockerfile, AppArmor, tłumaczenia, DOCS, build multi-arch) | — |
| M9 | Test end-to-end na produkcji (Millennium, tryb Restricted) | — |

## Decyzje (odstępstwa / doprecyzowania względem SPEC)

- **2026-10-01 — add-on, nie integracja.** Encje przez MQTT Discovery (§6). Integracja
  SurfHost/ha-enablebanking tylko jako punkt odniesienia, nie instalujemy jej.
- **2026-10-01 — klucz EB generowany lokalnie** (`python -m budget.cli keygen`: RSA + self-signed
  cert), do Control Panelu EB wklejany jest tylko certyfikat. Klucz prywatny nie opuszcza HA.
  Rejestracja przez `POST /api/applications` wymaga JWT sesji Control Panelu, więc w pełni
  z CLI się nie da.
- **2026-10-01 — M1b dodany przed M2.** Deduplikacja (§5.2) zależy od stabilności
  `transaction_id`/`entry_reference` w Millennium, czego Sandbox nie pokaże.
- **Dane prywatne w dev** (PEM, `.env`, zrzuty z prawdziwego banku, surowy CSV) trzymamy poza
  repo, w `/data/home/budget_dev/` w kontenerze deweloperskim. Do repo trafiają wyłącznie dane
  syntetyczne, z Sandboxa albo zanonimizowane i przejrzane przez użytkownika.
- **2026-10-01 — M7 (CSV) warunkowy** → **potwierdzony po M1b**: Millennium przez PSD2 oddaje
  tylko 90 dni (także zaraz po SCA i ze `strategy=longest`). CSV potrzebny do starszej historii.
- **2026-10-01 — wnioski M1b do przeniesienia w M2–M4** (szczegóły: `FINDINGS_millennium.md`):
  brak MCC → kategoryzacja na opisie; spłaty karty kredytowej nie wykrywalne po IBAN → reguła
  na opis/parowanie, inaczej podwójne liczenie wydatków kartą; `entry_reference` rachunku
  bieżącego zawiera licznik w obrębie dnia (stabilność do potwierdzenia).
- **Do rozstrzygnięcia w M8:** obraz bazowy (`ghcr.io/home-assistant/base` wg SPEC
  vs `python:3.12-alpine` jak w innych add-onach autora).

## Wnioski z Sandboxa (M1, 2026-10-01)

- Aplikacja Sandbox `HA budget`, klucz z `cli keygen` przyjęty przez Control Panel
  (opcja „Generate outside the browser and import public certificate”). Pola Privacy/Terms URL
  muszą być prawdziwymi URL-ami („Invalid URL” przy `none`).
- `GET /aspsps?country=PL`: **„Bank Millennium”** (beta) i „Mock ASPSP”; oba
  `maximum_consent_validity` = 180 d, **brak `required_psu_headers`** (Sandbox — do
  potwierdzenia na produkcji w M1b).
- Sandbox Millennium: 3 konta (PLN/EUR), salda ITBD/ITAV, **zero transakcji** w każdym zakresie
  dat — do testów transakcji służy Mock ASPSP z `tools/make_mock_dataset.py`.
- Mock ASPSP: wszystkie transakcje w **jednej stronie** (bez `continuation_key`, choć docs mówią
  o paczkach po 10) — paginację pokrywają testy `respx`, nie Sandbox. Mock **gubi
  `transaction_id`** (0/78) — zostaje `entry_reference`.
- **`identification_hash` to hash z (IBAN, waluta)** — dwa konta z tym samym IBAN-em w jednej
  sesji mają ten sam hash. W M2 PK `account.identification_hash` musi to obsłużyć
  (np. ostrzeżenie + dołączenie `uid`/produktu); `uid` jest unikalny w sesji.
- Błąd po stronie banku przychodzi jako `?state=…&error=server_error` — CLI pokazuje go czytelnie.
  Link do autoryzacji utworzony *przed* wgraniem danych do Mock ASPSP kończył się
  `server_error`; nowy link zadziałał.
