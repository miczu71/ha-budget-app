-- M15 E2: osoby z kartą kredytową (główna, dodatkowa) i ręczne przypisanie płatności kartą.
-- Bank liczy warunek zwolnienia z opłaty (5 płatności w miesiącu) osobno dla każdej karty, a API
-- nie podaje numeru karty — płatność przypisuje użytkownik. `csv_number` = zamaskowany numer karty
-- z eksportu Millenetu (E3: przypisanie historii). Addytywna — starsza wersja add-onu ją ignoruje.
CREATE TABLE card_holder (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    csv_number TEXT UNIQUE,
    created_at TEXT NOT NULL
);

ALTER TABLE txn ADD COLUMN card_holder_id INTEGER REFERENCES card_holder (id) ON DELETE SET NULL;
