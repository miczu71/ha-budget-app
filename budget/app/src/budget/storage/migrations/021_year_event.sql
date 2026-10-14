-- M18 E2: zdarzenia prognozy rocznej. `plan` zmienia prognozę bazową, `scenario` rysuje drugą linię.
-- Propozycje z historii nie są zapisywane — liczone na żywo; wiersz powstaje po zatwierdzeniu albo
-- odrzuceniu (`proposal_key` pilnuje, żeby ta sama propozycja nie wróciła). Addytywna.
CREATE TABLE year_event (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('series_amount', 'new_series', 'one_off')),
    mode TEXT NOT NULL CHECK (mode IN ('plan', 'scenario')),
    source TEXT NOT NULL CHECK (source IN ('manual', 'proposed')),
    status TEXT NOT NULL CHECK (status IN ('active', 'dismissed')),
    name TEXT NOT NULL,
    series_id INTEGER REFERENCES series (id) ON DELETE CASCADE,  -- series_amount
    direction TEXT CHECK (direction IN ('in', 'out')),  -- new_series
    amount TEXT NOT NULL,  -- series_amount/new_series: wartość bezwzględna; one_off: ze znakiem
    month_from TEXT NOT NULL,  -- RRRR-MM-01
    month_to TEXT,  -- włącznie; NULL = do końca horyzontu (one_off: równe month_from)
    proposal_key TEXT UNIQUE,
    created_at TEXT NOT NULL
);
