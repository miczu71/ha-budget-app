-- M10 E2–E3 (decyzja 26): konto oszczędnościowe poza Enable Banking. Saldo = `opening_balance` na
-- dzień `opening_date` + przelewy z rachunków w księdze na `account_number` i z niego po tej dacie
-- + szacowane odsetki. Stopa bazowa i promocja (stawka do limitu kwoty i daty) są opcjonalne,
-- w procentach rocznych. Numer konta tylko w bazie. Addytywna — starsza wersja add-onu ją ignoruje.
CREATE TABLE savings_account (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    account_number TEXT NOT NULL UNIQUE,  -- 26 cyfr NRB, bez spacji i prefiksu kraju
    opening_balance TEXT NOT NULL DEFAULT '0',
    opening_date TEXT NOT NULL,
    base_rate TEXT,
    promo_rate TEXT,
    promo_limit TEXT,
    promo_until TEXT,
    created_at TEXT NOT NULL,
    archived_at TEXT
);
