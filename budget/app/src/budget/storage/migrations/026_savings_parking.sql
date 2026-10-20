-- M26 E0b (decyzja 31): parking oszczędności. Konto z `parking_for` to drugie konto M10, na którym leżą
-- środki wyprowadzone z konta `parking_for` (np. Profit) na czas przerwy między edycjami promocji.
-- Wypłata z konta nadrzędnego i wpłata na parking w ciągu kilku dni to „przeniesienie”, nie
-- oszczędzanie ani wydatek. Addytywna — starsza wersja add-onu ją ignoruje.
ALTER TABLE savings_account ADD COLUMN parking_for INTEGER REFERENCES savings_account (id) ON DELETE SET NULL;
