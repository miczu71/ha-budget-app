-- M5b E3: decyzje użytkownika o zmianach serii (karty w dzwonku). Zmiany są liczone na bieżąco,
-- a zapisuje się tylko decyzja dla (seria, okres terminu, rodzaj zmiany):
--   amount/once   — „inna kwota: jednorazowo”
--   late/skip     — „spóźniona: pomiń ten okres” (okres nie liczy się do „jeszcze zejdzie”)
--   stopped/keep  — „ustała: zostaw” (następny brak tworzy nową kartę)
-- `period` = RRRR-MM terminu. Tabela jest addytywna — starsza wersja add-onu ją ignoruje.
CREATE TABLE series_ack (
    series_id INTEGER NOT NULL REFERENCES series (id),
    period TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('amount', 'late', 'stopped')),
    decision TEXT NOT NULL CHECK (decision IN ('once', 'skip', 'keep')),
    decided_at TEXT NOT NULL,
    PRIMARY KEY (series_id, period, kind)
);
