"""CLI deweloperskie do ręcznego przejścia flow Enable Banking (Sandbox / sonda produkcyjna).

Uruchomienie: `BUDGET_ENV_FILE=/ścieżka/.env python -m budget.cli <komenda>`.
Stan CLI (sesje, oczekująca autoryzacja, zrzuty) trafia do `BUDGET_DEV_DIR`
(domyślnie `<data_dir>/cli`) — to są dane bankowe, nigdy do repo.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from budget.eb_client import EBAuthError, EBClient, EBError, find_aspsp, parse_redirect
from budget.keys import generate_key_and_cert
from budget.logging_utils import mask_iban, setup_logging
from budget.settings import Settings, SettingsError, load_settings, resolve_private_key_path


class CliError(Exception):
    pass


def _state_dir(settings: Settings) -> Path:
    path = Path(os.environ.get("BUDGET_DEV_DIR") or settings.data_dir / "cli")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def _write_private(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def _client(settings: Settings) -> EBClient:
    if not settings.eb_application_id:
        raise CliError("brak eb_application_id (BUDGET_EB_APPLICATION_ID w .env)")
    pem = resolve_private_key_path(settings).read_bytes()
    return EBClient(settings.eb_application_id, pem, base_url=settings.eb_base_url)


def _current_session(state: Path, session_id: str | None) -> dict[str, Any]:
    if session_id is None:
        current = state / "current_session"
        if not current.is_file():
            raise CliError("brak zapisanej sesji — najpierw `auth`")
        session_id = current.read_text(encoding="utf-8").strip()
    path = state / "sessions" / f"{session_id}.json"
    if not path.is_file():
        raise CliError(f"brak pliku sesji {path}")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _accounts(session: dict[str, Any], index: int | None) -> list[dict[str, Any]]:
    accounts: list[dict[str, Any]] = session.get("accounts", [])
    if index is None:
        return accounts
    if not 0 <= index < len(accounts):
        raise CliError(f"konto #{index} nie istnieje (jest {len(accounts)})")
    return [accounts[index]]


def _print_accounts(accounts: Sequence[dict[str, Any]]) -> None:
    for i, acc in enumerate(accounts):
        iban = (acc.get("account_id") or {}).get("iban")
        print(
            f"  #{i} {mask_iban(iban) or '(brak IBAN)'} {acc.get('currency')} "
            f"{acc.get('cash_account_type') or ''} {acc.get('product') or ''} "
            f"hash={str(acc.get('identification_hash'))[:12]}…"
        )


# --- komendy ------------------------------------------------------------------


def cmd_keygen(args: argparse.Namespace) -> None:
    key, crt = generate_key_and_cert(Path(args.out), common_name=args.cn)
    print(f"Klucz prywatny: {key} (0600 — nie wysyłaj nigdzie)")
    print(f"Certyfikat do wklejenia w Control Panelu Enable Banking: {crt}\n")
    print(crt.read_text(encoding="ascii"))


async def cmd_app(settings: Settings, args: argparse.Namespace) -> None:
    async with _client(settings) as eb:
        app = await eb.get_application()
    print(f"Aplikacja: {app.name} | środowisko: {app.environment} | aktywna: {app.active}")
    print(f"Redirect URL: {', '.join(app.redirect_urls) or '(brak)'}")
    print(f"Kraje: {', '.join(app.countries) or '(wszystkie / brak danych)'}")


async def cmd_aspsps(settings: Settings, args: argparse.Namespace) -> None:
    async with _client(settings) as eb:
        aspsps = await eb.get_aspsps(args.country)
    for a in aspsps:
        if args.name and args.name.casefold() not in a.name.casefold():
            continue
        days = (a.maximum_consent_validity or 0) // 86400
        psu = ",".join(a.required_psu_headers) or "-"
        print(
            f"{a.country} | {a.name} | zgoda max {days} d | PSU: {psu}{' | beta' if a.beta else ''}"
        )


async def cmd_auth(settings: Settings, args: argparse.Namespace) -> None:
    state_dir = _state_dir(settings)
    async with _client(settings) as eb:
        aspsp = find_aspsp(await eb.get_aspsps(args.country), args.aspsp, args.country)
        redirect = settings.eb_redirect_url or (await eb.get_application()).redirect_urls[0]
        valid_until = (
            datetime.now(UTC) + timedelta(days=args.days) if args.days is not None else None
        )
        auth, state, valid_until = await eb.start_auth(aspsp, redirect, valid_until=valid_until)
        _write_private(
            state_dir / "pending_auth.json",
            {"state": state, "aspsp": aspsp.model_dump(), "valid_until": valid_until.isoformat()},
        )
        print(f"Bank: {aspsp.name} ({aspsp.country}), zgoda do {valid_until:%Y-%m-%d %H:%M} UTC")
        print(f"Otwórz w przeglądarce i przejdź logowanie + SCA:\n\n{auth.url}\n")
        pasted = input("Wklej adres, na który zostałeś przekierowany (albo sam kod): ")
        result = parse_redirect(pasted, expected_state=state)
        session = await eb.create_session(result.code)

    # Pełna odpowiedź — część danych EB zwraca tylko tutaj (SPEC §2.2 pkt 4)
    _write_private(state_dir / "sessions" / f"{session.session_id}.json", session.raw)
    (state_dir / "current_session").write_text(session.session_id, encoding="utf-8")
    (state_dir / "pending_auth.json").unlink(missing_ok=True)
    print(f"\nSesja {session.session_id} zapisana, ważna do {session.access.valid_until}.")
    print(f"Konta ({len(session.accounts)}):")
    _print_accounts(session.raw.get("accounts", []))


async def cmd_session(settings: Settings, args: argparse.Namespace) -> None:
    state_dir = _state_dir(settings)
    session_id = _current_session(state_dir, args.id)["session_id"]
    async with _client(settings) as eb:
        if args.delete:
            await eb.delete_session(session_id)
            (state_dir / "current_session").unlink(missing_ok=True)
            print(f"Sesja {session_id} zamknięta (DELETE).")
            return
        info = await eb.get_session(session_id)
    left = info.access.valid_until - datetime.now(UTC)
    print(
        f"Sesja {session_id}: {info.status}, ważna do {info.access.valid_until} "
        f"({left.days} d), kont: {len(info.accounts)}"
    )


async def cmd_balances(settings: Settings, args: argparse.Namespace) -> None:
    state_dir = _state_dir(settings)
    session = _current_session(state_dir, args.id)
    dump: dict[str, Any] = {}
    async with _client(settings) as eb:
        for acc in _accounts(session, args.account):
            balances = await eb.get_balances(acc["uid"])
            dump[acc["identification_hash"]] = [b.raw for b in balances]
            iban = (acc.get("account_id") or {}).get("iban")
            print(f"{mask_iban(iban)} ({acc.get('currency')}):")
            for b in balances:
                print(
                    f"  {b.balance_type:5} {b.balance_amount.amount:>14} "
                    f"{b.balance_amount.currency} {b.reference_date or ''} {b.name or ''}"
                )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    _write_private(state_dir / "dumps" / f"balances_{stamp}.json", dump)


async def cmd_transactions(settings: Settings, args: argparse.Namespace) -> None:
    state_dir = _state_dir(settings)
    session = _current_session(state_dir, args.id)
    date_from = (
        date.fromisoformat(args.date_from)
        if args.date_from
        else datetime.now(UTC).date() - timedelta(days=args.days)
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    async with _client(settings) as eb:
        for acc in _accounts(session, args.account):
            pages = 0
            raw: list[dict[str, Any]] = []
            async for page in eb.iter_transaction_pages(acc["uid"], date_from):
                pages += 1
                raw.extend(t.raw for t in page.transactions)
            short = str(acc["identification_hash"])[:8]
            _write_private(
                state_dir / "dumps" / f"transactions_{short}_{stamp}.json",
                {"date_from": date_from.isoformat(), "pages": pages, "transactions": raw},
            )
            iban = (acc.get("account_id") or {}).get("iban")
            print(f"{mask_iban(iban)}: {len(raw)} transakcji, {pages} stron(y) od {date_from}")
            _print_summary(raw)


def _print_summary(txns: Sequence[dict[str, Any]]) -> None:
    """Fakty potrzebne do §11 SPEC (dedup, MCC, głębokość historii) — bez danych osobowych."""
    if not txns:
        return
    n = len(txns)

    def share(key: str) -> str:
        have = sum(1 for t in txns if t.get(key))
        return f"{have}/{n}"

    dates = sorted(d for t in txns if (d := t.get("booking_date") or t.get("transaction_date")))
    statuses = Counter(t.get("status") for t in txns)
    indicators = Counter(t.get("credit_debit_indicator") for t in txns)
    print(f"  daty: {dates[0] if dates else '?'} … {dates[-1] if dates else '?'}")
    print(f"  status: {dict(statuses)} | strona: {dict(indicators)}")
    print(
        f"  transaction_id: {share('transaction_id')} | entry_reference: "
        f"{share('entry_reference')} | MCC: {share('merchant_category_code')} | "
        f"balance_after: {share('balance_after_transaction')}"
    )


# --- main ---------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m budget.cli", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    k = sub.add_parser("keygen", help="wygeneruj klucz RSA + self-signed cert dla EB")
    k.add_argument("--out", required=True, help="prefiks ścieżki, np. /data/home/budget_dev/eb")
    k.add_argument("--cn", default="ha-budget-app", help="Common Name certyfikatu")

    sub.add_parser("app", help="GET /application — weryfikacja klucza i redirect URL")

    a = sub.add_parser("aspsps", help="lista banków")
    a.add_argument("--country", default="PL")
    a.add_argument("--name", help="filtr po fragmencie nazwy")

    au = sub.add_parser("auth", help="autoryzacja: POST /auth → SCA → POST /sessions")
    au.add_argument(
        "--aspsp", required=True, help="nazwa banku (dokładna lub jednoznaczny fragment)"
    )
    au.add_argument("--country", default="PL")
    au.add_argument("--days", type=int, help="ważność zgody (domyślnie maksimum banku)")

    s = sub.add_parser("session", help="status zapisanej sesji")
    s.add_argument("--id", help="session_id (domyślnie ostatnia)")
    s.add_argument("--delete", action="store_true", help="zamknij zgodę (DELETE /sessions)")

    b = sub.add_parser("balances", help="salda kont z sesji")
    b.add_argument("--id")
    b.add_argument("--account", type=int, help="numer konta z listy (domyślnie wszystkie)")

    t = sub.add_parser("transactions", help="transakcje → zrzut JSON + podsumowanie")
    t.add_argument("--id")
    t.add_argument("--account", type=int)
    t.add_argument("--days", type=int, default=90)
    t.add_argument("--date-from", help="YYYY-MM-DD (nadpisuje --days)")
    return p


_ASYNC = {
    "app": cmd_app,
    "aspsps": cmd_aspsps,
    "auth": cmd_auth,
    "session": cmd_session,
    "balances": cmd_balances,
    "transactions": cmd_transactions,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.cmd == "keygen":
            cmd_keygen(args)
            return 0
        settings = load_settings()
        setup_logging(settings.log_level)
        asyncio.run(_ASYNC[args.cmd](settings, args))
    except (CliError, SettingsError, EBError, EBAuthError, LookupError, FileExistsError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
