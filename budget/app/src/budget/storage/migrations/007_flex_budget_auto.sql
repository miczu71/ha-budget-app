-- M5a etap 3: pusta kwota = „wróć do puli automatycznej (z dochodu)” od `month_from`.
CREATE TABLE flex_budget_new (
    month_from TEXT PRIMARY KEY,
    amount TEXT,
    updated_at TEXT NOT NULL
);
INSERT INTO flex_budget_new (month_from, amount, updated_at)
    SELECT month_from, amount, updated_at FROM flex_budget;
DROP TABLE flex_budget;
ALTER TABLE flex_budget_new RENAME TO flex_budget;
