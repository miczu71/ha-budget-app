-- M26 E1 (decyzja 31): majątek netto. `invest_asset.savings_id` = aktywo to to samo co konto
-- oszczędnościowe M10 (liczone tam, tu pomijane); `valued_at` = dzień, na który wpisano wartość.
-- `networth_snapshot` = migawka dzienna (E2), składniki w JSON; `approx` = punkt odtworzony wstecz.
-- Addytywna — starsza wersja add-onu ją ignoruje.
ALTER TABLE invest_asset ADD COLUMN savings_id INTEGER REFERENCES savings_account (id) ON DELETE SET NULL;
ALTER TABLE invest_asset ADD COLUMN valued_at TEXT;
UPDATE invest_asset SET valued_at = substr(created_at, 1, 10);

CREATE TABLE networth_snapshot (
    day TEXT PRIMARY KEY,
    total TEXT NOT NULL,
    assets TEXT NOT NULL,
    liabilities TEXT NOT NULL,
    components_json TEXT NOT NULL,
    approx INTEGER NOT NULL DEFAULT 0
);
