-- M9 E4: dzień ostatniej zmiany oprocentowania kredytu (np. 9.09); kolejne co 3 miesiące. Z niego add-on
-- liczy najbliższą zmianę i prognozę raty przy bieżącym WIBOR. NULL = bez prognozy.
-- Addytywna — starsza wersja add-onu ją ignoruje.
ALTER TABLE loan ADD COLUMN rate_reset_date TEXT;
