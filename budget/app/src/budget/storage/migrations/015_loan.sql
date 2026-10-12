-- M9 E1 (decyzja 28): kredyt hipoteczny wpisany ręcznie. Stan = `principal` (kapitał do spłaty) na
-- dzień `principal_date`; stopa = stawka referencyjna (WIBOR/WIRON) + marża, w procentach rocznych.
-- Nowe saldo albo nowa stopa to korekta wiersza (nadpisanie), jak w `savings_account`.
-- `series_id` wiąże kredyt z serią rat w księdze (E2). Addytywna — starsza wersja add-onu ją ignoruje.
CREATE TABLE loan (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    principal TEXT NOT NULL,
    principal_date TEXT NOT NULL,
    reference_rate TEXT NOT NULL,
    margin TEXT NOT NULL,
    installment_kind TEXT NOT NULL CHECK (installment_kind IN ('equal', 'decreasing')),
    last_payment_date TEXT NOT NULL,
    payment_day INTEGER NOT NULL CHECK (payment_day BETWEEN 1 AND 31),
    series_id INTEGER,
    created_at TEXT NOT NULL,
    archived_at TEXT
);
