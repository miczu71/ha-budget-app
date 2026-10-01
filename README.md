# Budżet Domowy — add-on Home Assistant

Budżet domowy liczony lokalnie w Home Assistant z transakcji pobieranych automatycznie z banku
(PSD2 przez [Enable Banking](https://enablebanking.com), tryb Restricted Production — tylko
własne, podlinkowane rachunki). Tylko odczyt (AIS), żadnych płatności.

> **Status: w budowie.** Add-on nie jest jeszcze instalowalny. Plan i postęp:
> [`docs/ROADMAP.md`](docs/ROADMAP.md), specyfikacja: [`docs/SPEC.md`](docs/SPEC.md).

## Rozwój

```bash
cd budget/app
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest
```

Konfiguracja dev: bez `/data/options.json` ustawienia czytane są z `.env`
(`BUDGET_ENV_FILE`, zmienne `BUDGET_*`, np. `BUDGET_EB_APPLICATION_ID`,
`BUDGET_CONFIG_DIR` — katalog z kluczem `.pem`). Klucze, `.env` i dane bankowe nigdy nie trafiają
do repo (zob. `.gitignore`).
