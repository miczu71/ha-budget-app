-- M5a: miesięczna kwota budżetu elastycznego, obowiązuje od `month_from` (RRRR-MM-01) do
-- następnego wpisu — zmiana „od tego miesiąca” nie przepisuje wcześniejszych miesięcy.
CREATE TABLE flex_budget (
    month_from TEXT PRIMARY KEY,
    amount TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
