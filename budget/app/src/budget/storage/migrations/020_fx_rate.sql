-- M23 E1: kursy średnie NBP (tabela A) dla dni transakcji walutowych; dociągane z api.nbp.pl. Addytywna.
CREATE TABLE fx_rate (
    currency TEXT NOT NULL,
    day TEXT NOT NULL,  -- effectiveDate tabeli
    mid TEXT NOT NULL,
    PRIMARY KEY (currency, day)
);
