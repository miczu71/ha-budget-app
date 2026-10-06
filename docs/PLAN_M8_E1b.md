# M8 E1b — wypłata wskazana przez użytkownika, przełącznik zadłużenia karty (0.25.1)

Z checkpointu M8 E1 (2026-10-06): (1) dzień resetu = wypłata użytkownika (główne źródło, ~24.),
a nie „seria o największej kwocie”; (4) checkbox „uwzględnij zadłużenie karty”.

- **Wypłata:** przełącznik „To moja wypłata (dzień resetu prognozy)” na ekranie aktywnej serii
  przychodów, zapis w `kv` (`payday_series_id`, jedna seria naraz, bez migracji). Gdy seria nie jest
  ustawiona albo przestała być aktywną serią przychodów — dotychczasowa reguła (największa kwota).
  Po dniu wypłaty horyzont przechodzi na jej termin w następnym miesiącu.
- **Karta:** checkbox w sekcji „Do wypłaty”, zapis w `kv` (`forecast_card_debt`, domyślnie włączony).
  Wyłączony: wiersz karty zostaje (z dopiskiem „nie odjęte”), ale nie pomniejsza wolnych środków.
- Wydanie 0.25.1; cofnięcie: `git revert` + wydanie albo backup add-onu (bez migracji).
