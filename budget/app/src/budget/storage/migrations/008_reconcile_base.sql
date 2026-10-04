-- Baza kontroli salda dla kont bez salda otwarcia (karta): migawka ITBD, od której liczone są
-- różnice — ustawiana z panelu, gdy pierwsza migawka złapała transakcje „w drodze”.
CREATE TABLE reconcile_base (
    account_id INTEGER PRIMARY KEY REFERENCES account (id),
    snapshot_at TEXT NOT NULL,
    set_at TEXT NOT NULL
);
