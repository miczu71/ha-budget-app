-- M22 E1: agent inwestycyjny. Aktywa wpisane ręcznie, oferty (E1 ręczne, E2/E3 dopisują z sieci i blogów:
-- `source`, `status`, `url`) i banki, w których użytkownik jest klientem (filtr „tylko dla nowych”, E2).
-- Ustawienia (mnożnik poduszki, zwroty ETF, TER, inflacja) w `kv`. Addytywna.
CREATE TABLE invest_asset (
    id            INTEGER PRIMARY KEY,
    kind          TEXT NOT NULL,           -- bonds | deposit | account | etf | stock | other
    name          TEXT NOT NULL,
    amount        TEXT NOT NULL,           -- wartość bieżąca, PLN
    rate          TEXT,                    -- % rocznie (informacyjnie)
    start_date    TEXT,
    maturity_date TEXT,
    ike           INTEGER NOT NULL DEFAULT 0,
    archived_at   TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE invest_offer (
    id               INTEGER PRIMARY KEY,
    kind             TEXT NOT NULL,        -- deposit | account | edo | coi | tos | ror | dor
    bank             TEXT NOT NULL,
    rate             TEXT NOT NULL,        -- % rocznie (obligacje: pierwszy rok)
    margin           TEXT,                 -- obligacje indeksowane: marża ponad inflację, p.p.
    limit_amount     TEXT,                 -- stawka obowiązuje do tej kwoty
    months           INTEGER,              -- lokata: okres; konto: długość promocji
    conditions       TEXT NOT NULL DEFAULT '',
    new_clients_only INTEGER NOT NULL DEFAULT 0,
    source           TEXT NOT NULL DEFAULT 'manual',    -- manual | bonds | ranking | blog
    status           TEXT NOT NULL DEFAULT 'confirmed', -- confirmed | review | rejected
    url              TEXT,
    fetched_at       TEXT,
    archived_at      TEXT,
    created_at       TEXT NOT NULL
);

CREATE TABLE invest_bank (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    since      TEXT,
    created_at TEXT NOT NULL
);
