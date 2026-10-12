-- M10 E1 (decyzja 25): skarbonki na kontach-celach w banku. Enable Banking kont-celów nie widzi,
-- więc saldo = `opening_balance` + przelewy z rachunków w księdze na `account_number` i z niego.
-- Skarbonka z serią (`series_id`) bierze cel i termin z serii (kwota, następna płatność), bez niej
-- z `target`/`due_date`. `txn.piggy_id` = wydatek ręcznie przypisany do skarbonki (poza pulą Flex).
-- Numer konta tylko w bazie. Addytywna — starsza wersja add-onu ją ignoruje.
CREATE TABLE piggy (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    account_number TEXT NOT NULL UNIQUE,  -- 26 cyfr NRB, bez spacji i prefiksu kraju
    target TEXT,
    due_date TEXT,
    series_id INTEGER REFERENCES series (id) ON DELETE SET NULL,
    opening_balance TEXT NOT NULL DEFAULT '0',
    created_at TEXT NOT NULL,
    archived_at TEXT
);

ALTER TABLE txn ADD COLUMN piggy_id INTEGER REFERENCES piggy (id) ON DELETE SET NULL;
