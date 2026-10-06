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

## Wynik (2026-10-06)

- **0.25.1 wydane** (release `v0.25.1`, nie draft; CI zielone), zainstalowane z backupem add-onu.
  596 testów, ruff i mypy czyste; na kopii księgi 390 px: 0 błędów konsoli, cele dotyku ≥ 44 px
  (etykiety checkboxów), brak poziomego przewijania.
- Na produkcji seria przychodów z Nokii oznaczona jako wypłata (ustawienie zapisane); checkbox
  przełącza „Wolne środki dziś” (z odjęciem karty / bez) i jest pamiętany; stan przywrócony po teście.
- Dziś wynik jest ten sam co w 0.25.0 (wypłata 24.10), bo Nokia była i tak serią o największej
  kwocie przed dniem resetu; różnica wyjdzie, gdy inna, większa seria wypadnie przed 24.
- `GET /` 455–504 ms; pojedyncze żądanie tuż po zapisie ~1,8 s (przeliczenie po zmianie bazy).
