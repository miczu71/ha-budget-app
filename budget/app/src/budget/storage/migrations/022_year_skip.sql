-- M30: kategoria wyłączona z prognozy rocznej (wydatki jednorazowe, np. remont). Nie zmienia grupy
-- budżetu, więc Budżet i Wydatki liczą jak dotąd; flagę czyta tylko `year.history`. Addytywna.
ALTER TABLE category ADD COLUMN year_skip INTEGER NOT NULL DEFAULT 0;
