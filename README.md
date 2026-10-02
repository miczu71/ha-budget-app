# Budżet Domowy — add-on Home Assistant

Budżet domowy liczony lokalnie w Home Assistant z transakcji pobieranych automatycznie z banku
(PSD2 przez [Enable Banking](https://enablebanking.com), tryb Restricted Production — tylko
własne, podlinkowane rachunki). Tylko odczyt (AIS), żadnych płatności.

> **Status:** wersja 0.2.0 (etap M4a) — synchronizacja z bankiem, panel, encje w HA,
> automatyczna kategoryzacja (słownik sieci + reguły) i ekran „Wydatki”.
> Budżet Flex i kolejne etapy: [`docs/ROADMAP.md`](docs/ROADMAP.md),
> specyfikacja: [`docs/SPEC.md`](docs/SPEC.md).

## Instalacja

Ustawienia → Dodatki → Sklep z dodatkami → ⋮ → Repozytoria → dodaj
`https://github.com/miczu71/ha-budget-app`, zainstaluj **Budżet Domowy**. Konfiguracja,
pierwsze uruchomienie, limit zapytań banku i encje: [`budget/DOCS.md`](budget/DOCS.md).

> Kopia zapasowa Home Assistant zawiera bazę add-onu, czyli Twoje dane finansowe.

## Rozwój

```bash
cd budget/app
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest
```

Panel lokalnie (bez Supervisora, allowlista Ingress wyłączona):

```bash
env -u SUPERVISOR_TOKEN BUDGET_OPTIONS_PATH=/nonexistent BUDGET_ENV_FILE=~/budget_dev/.env \
  BUDGET_DATA_DIR=/tmp/budget BUDGET_DEV=1 BUDGET_PORT=8199 python -m budget
```

`env -u SUPERVISOR_TOKEN` ma znaczenie wewnątrz innego add-onu — inaczej lokalny serwer wysyłałby
powiadomienia do prawdziwego Home Assistant.

Konfiguracja dev: bez `/data/options.json` ustawienia czytane są z `.env`
(`BUDGET_ENV_FILE`, zmienne `BUDGET_*`, np. `BUDGET_EB_APPLICATION_ID`,
`BUDGET_CONFIG_DIR` — katalog z kluczem `.pem`). Klucze, `.env` i dane bankowe nigdy nie trafiają
do repo (zob. `.gitignore`).

> **Pułapka:** uruchamiając CLI wewnątrz innego add-onu (np. Claude Code), `/data/options.json`
> istnieje i należy do *tamtego* add-onu. Ustaw `BUDGET_OPTIONS_PATH=/nonexistent`, żeby wymusić
> `.env`.

### Flow Enable Banking z CLI (Sandbox)

```bash
export BUDGET_OPTIONS_PATH=/nonexistent BUDGET_ENV_FILE=~/budget_dev/.env BUDGET_DEV_DIR=~/budget_dev
python -m budget.cli keygen --out ~/budget_dev/eb_sandbox   # .crt wklej w Control Panelu EB
python -m budget.cli app                                    # weryfikacja klucza i redirect URL
python -m budget.cli aspsps --country PL
python -m budget.cli auth --aspsp "Mock ASPSP" --no-prompt  # otwórz URL, przejdź SCA
python -m budget.cli finish --url '<adres z paska po przekierowaniu>'
python -m budget.cli balances
python -m budget.cli transactions --days 90                 # zrzut JSON + podsumowanie pól
```

Mock ASPSP (Sandbox) jest pusty, dopóki nie wgrasz danych w zakładce *Mock ASPSP* Control Panelu:
`python tools/make_mock_dataset.py --out mock.json` generuje syntetyczne polskie konto
(karta + MCC, BLIK, wypłata, przelewy własne, PDNG, bliźniacze transakcje).
