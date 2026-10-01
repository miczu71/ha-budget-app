import json
import stat
from pathlib import Path

import httpx
import jwt
import pytest
import respx
from cryptography import x509

from budget import cli
from budget.eb_client import EBClient, load_private_key
from budget.keys import generate_key_and_cert


def test_keygen_files_and_permissions(tmp_path: Path) -> None:
    key_path, crt_path = generate_key_and_cert(tmp_path / "eb", bits=2048)
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    key = load_private_key(key_path.read_bytes())
    cert = x509.load_pem_x509_certificate(crt_path.read_bytes())
    assert cert.public_key().public_numbers() == key.public_key().public_numbers()
    # JWT podpisany kluczem weryfikuje się kluczem publicznym z certyfikatu (to dostaje EB)
    token = EBClient("kid", key_path.read_bytes()).token()
    jwt.decode(token, cert.public_key(), algorithms=["RS256"], audience="api.enablebanking.com")


def test_keygen_does_not_overwrite(tmp_path: Path) -> None:
    generate_key_and_cert(tmp_path / "eb", bits=2048)
    with pytest.raises(FileExistsError):
        generate_key_and_cert(tmp_path / "eb", bits=2048)


@pytest.fixture
def dev_env(tmp_path: Path, private_pem: bytes, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "eb.pem").write_bytes(private_pem)
    monkeypatch.setenv("BUDGET_OPTIONS_PATH", str(tmp_path / "none.json"))
    monkeypatch.setenv("BUDGET_ENV_FILE", str(tmp_path / "none.env"))
    monkeypatch.setenv("BUDGET_EB_APPLICATION_ID", "kid")
    monkeypatch.setenv("BUDGET_EB_PRIVATE_KEY_FILE", "eb.pem")
    monkeypatch.setenv("BUDGET_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("BUDGET_EB_BASE_URL", "https://eb.test")
    monkeypatch.setenv("BUDGET_DEV_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


@respx.mock
def test_cli_auth_flow_saves_full_session(
    dev_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    respx.get("https://eb.test/aspsps").mock(
        return_value=httpx.Response(200, json={"aspsps": [{"name": "Mock ASPSP", "country": "PL"}]})
    )
    respx.get("https://eb.test/application").mock(
        return_value=httpx.Response(200, json={"redirect_urls": ["http://localhost:8099/callback"]})
    )
    auth = respx.post("https://eb.test/auth").mock(
        return_value=httpx.Response(200, json={"url": "https://mock/auth"})
    )
    session = {
        "session_id": "s-9",
        "aspsp": {"name": "Mock ASPSP", "country": "PL"},
        "access": {"valid_until": "2027-01-01T00:00:00Z"},
        "accounts": [
            {
                "uid": "u",
                "identification_hash": "hash123456789",
                "account_id": {"iban": "PL61109010140000071219812874"},
                "currency": "PLN",
            }
        ],
    }
    respx.post("https://eb.test/sessions").mock(return_value=httpx.Response(200, json=session))

    def fake_input(_: str) -> str:
        state = json.loads(auth.calls.last.request.content)["state"]
        return f"http://localhost:8099/callback?code=c0de&state={state}"

    monkeypatch.setattr("builtins.input", fake_input)
    assert cli.main(["auth", "--aspsp", "mock", "--country", "PL"]) == 0
    out = capsys.readouterr().out
    assert "https://mock/auth" in out
    assert "PL61109010140000071219812874" not in out  # IBAN zamaskowany
    assert json.loads((dev_env / "sessions" / "s-9.json").read_text()) == session
    assert (dev_env / "current_session").read_text() == "s-9"
    assert not (dev_env / "pending_auth.json").exists()


def test_cli_without_session(dev_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["balances"]) == 1
    assert "najpierw `auth`" in capsys.readouterr().err
