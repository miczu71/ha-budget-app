-- M23 E1 (wycofane w 0.52.0): kursy NBP. Tabela nieużywana; plik zostaje, bo bazy po 0.51.0 mają
-- schemat w wersji 20, a `migrate` odmawia startu przy brakującej migracji.
CREATE TABLE fx_rate (
    currency TEXT NOT NULL,
    day TEXT NOT NULL,
    mid TEXT NOT NULL,
    PRIMARY KEY (currency, day)
);
