-- M29 E4: paragon Lidl Plus dopasowany do płatności (plik /share/lidl/receipts.json z add-onu Lidl).
-- Paragon i transakcja użyte najwyżej raz; `chosen` = wybrany ręcznie przy niejednoznacznym. Addytywna.
CREATE TABLE txn_lidl (
    txn_id INTEGER PRIMARY KEY REFERENCES txn (id) ON DELETE CASCADE,
    ticket_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('auto', 'chosen'))
);
