-- M5b: płatności cykliczne (serie). Przynależność transakcji liczona od zera z `matcher_json`
-- (warunki jak reguły kategorii, `categorize.rules.Conditions`) — bez zapisu w `txn`.
-- `group_key` (sprzedawca|kierunek po `fold`) — grupa detektora; seria w dowolnym statusie,
-- także odrzucona, blokuje ponowną propozycję tej grupy.
CREATE TABLE series (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('out', 'in')),
    cadence TEXT NOT NULL CHECK (cadence IN ('M', 'Q', 'Y')),
    matcher_json TEXT NOT NULL,
    expected_amount TEXT NOT NULL,  -- wartość bezwzględna
    tolerance TEXT NOT NULL,
    anchor_day INTEGER CHECK (anchor_day BETWEEN 1 AND 31),
    status TEXT NOT NULL CHECK (status IN ('proposed', 'active', 'rejected', 'ended')),
    origin TEXT NOT NULL CHECK (origin IN ('detected', 'manual')),
    group_key TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE INDEX series_status ON series (status);
CREATE UNIQUE INDEX series_group_key ON series (group_key) WHERE group_key IS NOT NULL;
