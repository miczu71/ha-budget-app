-- M26 0.60.1: odtworzona historia liczyła kredyt dopiero od `principal_date`, więc zmiana m/m i r/r
-- była myląca. Kasuje wyłącznie punkty odtworzone (`approx = 1`); `backfill` zapisze je od nowa
-- przy następnym `record_networth`. Migawki dokładne zostają.
DELETE FROM networth_snapshot WHERE approx = 1;
