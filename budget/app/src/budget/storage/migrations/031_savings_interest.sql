-- E1b: odsetki dopisane przez bank na koncie oszczędnościowym bez API (wpis ręczny, netto po Belce).
-- Addytywna: nowa tabela; bez wpisów szacunek odsetek działa jak dotąd.
CREATE TABLE IF NOT EXISTS savings_interest (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES savings_account (id),
    month TEXT NOT NULL,            -- 'YYYY-MM' miesiąca kapitalizacji
    amount TEXT NOT NULL,           -- Decimal jako tekst, netto
    created_at TEXT NOT NULL,
    UNIQUE (account_id, month)
);
