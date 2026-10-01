# Roadmap — Budżet Domowy

Pełna specyfikacja: [`SPEC.md`](SPEC.md). Każdy etap kończy się zielonymi testami, commitem
i checkpointem (przegląd użytkownika + jawne „go” przed kolejnym etapem).

| Etap | Zakres | Status |
|---|---|---|
| M0 | Szkielet repo, pyproject, ruff/mypy/pytest, CI, `settings.py`, maskowanie w logach | zrobione — czeka na checkpoint |
| M1 | Klient Enable Banking (JWT, AIS, PSU, paginacja), modele pydantic, CLI, flow na **Sandboxie** | — |
| M1b | Sonda Production Restricted na realnym Millennium → `docs/FINDINGS_millennium.md` (§11) | — |
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
- **Do rozstrzygnięcia w M8:** obraz bazowy (`ghcr.io/home-assistant/base` wg SPEC
  vs `python:3.12-alpine` jak w innych add-onach autora).
