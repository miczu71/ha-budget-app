-- M2: rdzeń danych. Kwoty wyłącznie jako tekst (Decimal w Pythonie), daty ISO.

CREATE TABLE account (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('current', 'card', 'fx', 'savings', 'other')),
    iban TEXT UNIQUE,
    currency TEXT NOT NULL,
    product TEXT,
    display_name TEXT,
    include_in_budget INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

-- Identyfikatory zewnętrzne konta: hash/uid z Enable Banking, numery kart z CSV
CREATE TABLE account_alias (
    source TEXT NOT NULL CHECK (source IN ('eb_hash', 'eb_uid', 'csv_number')),
    value TEXT NOT NULL,
    account_id INTEGER NOT NULL REFERENCES account (id),
    PRIMARY KEY (source, value)
);

CREATE TABLE import_batch (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL CHECK (source IN ('eb', 'csv')),
    account_id INTEGER REFERENCES account (id),
    file_name TEXT,
    fetched_at TEXT NOT NULL,  -- moment pobrania danych z banku / eksportu
    date_from TEXT,
    rows_total INTEGER NOT NULL DEFAULT 0,
    rows_new INTEGER NOT NULL DEFAULT 0,
    rows_updated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE txn (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES account (id),
    status TEXT NOT NULL CHECK (status IN ('BOOK', 'PDNG')),
    booking_date TEXT,
    value_date TEXT,
    tx_date TEXT,
    amount TEXT NOT NULL,  -- ze znakiem: + wpływ, − wydatek
    currency TEXT NOT NULL,
    orig_amount TEXT,
    orig_currency TEXT,
    description TEXT NOT NULL DEFAULT '',
    counterparty_name TEXT,
    counterparty_account TEXT,
    kind TEXT NOT NULL,
    kind_source TEXT NOT NULL CHECK (kind_source IN ('csv', 'heuristic', 'manual')),
    balance_after TEXT,
    fingerprint TEXT NOT NULL,
    occurrence INTEGER NOT NULL DEFAULT 0,
    transfer_group TEXT,
    refund_of INTEGER REFERENCES txn (id) ON DELETE SET NULL,
    budget_flag TEXT,
    source TEXT NOT NULL CHECK (source IN ('eb', 'csv')),  -- źródło kwoty i dat (API wygrywa)
    raw_json TEXT,
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX txn_account_date ON txn (account_id, booking_date);
CREATE INDEX txn_account_fingerprint ON txn (account_id, fingerprint);
CREATE INDEX txn_transfer_group ON txn (transfer_group);

-- Referencje zewnętrzne transakcji; przenumerowana referencja dochodzi jako kolejny wiersz
CREATE TABLE txn_ref (
    account_id INTEGER NOT NULL REFERENCES account (id),
    source TEXT NOT NULL CHECK (source IN ('eb_entry', 'eb_txid')),
    ref TEXT NOT NULL,
    txn_id INTEGER NOT NULL REFERENCES txn (id) ON DELETE CASCADE,
    batch_id INTEGER REFERENCES import_batch (id),
    PRIMARY KEY (account_id, source, ref)
);
CREATE INDEX txn_ref_txn ON txn_ref (txn_id);

-- Wszystkie wiersze z importów CSV (per numer z pliku). Powiązanie z księgą (`txn_id`,
-- `status`) jest przeliczalne — kolejność importów CSV i API nie ma znaczenia.
CREATE TABLE csv_row (
    id INTEGER PRIMARY KEY,
    number TEXT NOT NULL,
    row_key TEXT NOT NULL,  -- odcisk wiersza + numer wystąpienia w obrębie numeru
    tx_date TEXT NOT NULL,
    settle_date TEXT NOT NULL,
    kind_raw TEXT NOT NULL,
    kind TEXT NOT NULL,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    balance_after TEXT,
    description TEXT NOT NULL,
    counterparty_name TEXT,
    counterparty_account TEXT,
    orig_amount TEXT,
    orig_currency TEXT,
    occurrence INTEGER NOT NULL,
    seq INTEGER NOT NULL,  -- kolejność w pliku (rosnąco = od najnowszych)
    batch_id INTEGER NOT NULL REFERENCES import_batch (id),
    txn_id INTEGER REFERENCES txn (id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'inserted', 'enriched', 'unmatched', 'duplicate', 'unmapped')),
    UNIQUE (number, row_key)
);
CREATE INDEX csv_row_txn ON csv_row (txn_id);

CREATE TABLE balance_snapshot (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES account (id),
    balance_type TEXT NOT NULL,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    reference_date TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE (account_id, balance_type, fetched_at)
);

CREATE TABLE eb_session (
    session_id TEXT PRIMARY KEY,
    aspsp TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    created_at TEXT NOT NULL,
    raw_json TEXT
);

CREATE TABLE sync_log (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    detail TEXT
);
