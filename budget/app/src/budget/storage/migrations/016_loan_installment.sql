-- Rata równa wg banku (opcjonalna): bank przelicza ratę przy zmianie WIBOR po swojemu, wzór annuitetowy
-- różni się o kilkanaście groszy. NULL = rata ze wzoru. Addytywna — starsza wersja add-onu ją ignoruje.
ALTER TABLE loan ADD COLUMN installment TEXT;
