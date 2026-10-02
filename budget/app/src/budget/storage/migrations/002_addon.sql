-- M3: add-on — stan sesji, przebiegi synchronizacji, licznik zapytań PSD2, stan pomocniczy.

-- Bieżąca sesja jest jedna; poprzednie zostają jako historia (status z `GET /sessions`)
ALTER TABLE eb_session ADD COLUMN status TEXT NOT NULL DEFAULT 'AUTHORIZED';
ALTER TABLE eb_session ADD COLUMN is_current INTEGER NOT NULL DEFAULT 0;
ALTER TABLE eb_session ADD COLUMN checked_at TEXT;

ALTER TABLE sync_log ADD COLUMN trigger TEXT NOT NULL DEFAULT 'schedule';
ALTER TABLE sync_log ADD COLUMN new_txn INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sync_log ADD COLUMN updated_txn INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sync_log ADD COLUMN requests INTEGER NOT NULL DEFAULT 0;
CREATE INDEX sync_log_started ON sync_log (started_at);

-- Zapytania do banku per dzień lokalny, konto i endpoint (każda strona transakcji osobno);
-- `psu` = wysłane z nagłówkami PSU (użytkownik obecny — poza limitem 4/dobę)
CREATE TABLE api_request (
    day TEXT NOT NULL,
    account_id INTEGER NOT NULL REFERENCES account (id),
    endpoint TEXT NOT NULL CHECK (endpoint IN ('balances', 'transactions')),
    psu INTEGER NOT NULL DEFAULT 0,
    n INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, account_id, endpoint, psu)
);

-- Drobny stan add-onu (oczekująca autoryzacja, ostatnie powiadomienia) jako JSON
CREATE TABLE kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
