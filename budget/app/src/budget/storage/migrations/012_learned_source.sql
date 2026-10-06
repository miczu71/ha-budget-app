-- M7 E2: źródło kategorii `learned` (pamięć sprzedawcy z ręcznych decyzji). CHECK kolumny nie da się
-- zmienić w SQLite, a przebudowa `txn` ruszałaby tabele z ON DELETE CASCADE — więc zamiana kolumny:
-- nowa z rozszerzonym CHECK, kopia, DROP starej (jej CHECK dotyczy tylko jej samej), zmiana nazwy.
-- Nieaddytywna: starsza wersja add-onu nie wstanie na tej bazie (cofnięcie = backup add-onu).
ALTER TABLE txn ADD COLUMN category_source_v2 TEXT CHECK (
    category_source_v2 IN ('manual', 'refund', 'rule', 'dictionary', 'kind', 'learned')
);
UPDATE txn SET category_source_v2 = category_source;
ALTER TABLE txn DROP COLUMN category_source;
ALTER TABLE txn RENAME COLUMN category_source_v2 TO category_source;
