-- M29 E1: podział transakcji na podkategorie. Części sumują się do `txn.amount`; `txn.category_id`
-- = część o największej kwocie (listy, sugestie i reguły działają bez zmian). Addytywna.
CREATE TABLE txn_split (
    txn_id INTEGER NOT NULL REFERENCES txn (id) ON DELETE CASCADE,
    line INTEGER NOT NULL,
    category_id INTEGER NOT NULL REFERENCES category (id),
    amount TEXT NOT NULL,  -- ze znakiem transakcji
    source TEXT NOT NULL CHECK (source IN ('manual', 'lidl')),
    PRIMARY KEY (txn_id, line)
);
