-- M4c: podpowiedzi kategorii z LLM — jedna na sprzedawcę i kierunek (jak grupa kolejki).
-- `category_id` NULL = model nie wskazał kategorii (nie pytamy ponownie); odrzucona też nie
-- wraca. Wiersz bez transakcji w kolejce jest po prostu nieużywany.
CREATE TABLE suggestion (
    id INTEGER PRIMARY KEY,
    merchant TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('out', 'in')),
    category_id INTEGER REFERENCES category (id) ON DELETE SET NULL,
    confidence REAL NOT NULL DEFAULT 0,
    model TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    created_at TEXT NOT NULL,
    decided_at TEXT,
    UNIQUE (merchant, direction)
);
