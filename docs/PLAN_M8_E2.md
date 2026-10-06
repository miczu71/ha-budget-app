# M8 E2 — encje prognozy i ostrzeżenie w dzwonku (0.26.0)

- `forecast.for_today` + `ForecastMemo` (sygnatura bazy, dzień, bufor) — dzwonek liczy się na każdej
  stronie, więc prognoza jest liczona raz na zmianę bazy; `Snapshot.signature()` jest publiczne.
- Dzwonek: karta `forecast_low` (warn), gdy najniższy punkt < `forecast_buffer` (domyślnie 0).
- Encje MQTT: `sensor.budget_forecast_free_now`, `_card_debt`, `_lowest`, `_at_payday`,
  `binary_sensor.budget_forecast_shortfall` (problem). Bez `state_class`, jak encje Flex.
- Add-on niczego nie wysyła sam — powiadomienie to automatyzacja w HA na `binary_sensor`.
- Bez migracji; cofnięcie: `git revert` + wydanie albo backup add-onu.

## Wynik (2026-10-06)

- **0.26.0 wydane** (release `v0.26.0`, nie draft; CI zielone), zainstalowane z backupem add-onu.
  602 testy, ruff i mypy czyste; lokalnie 0 błędów konsoli, strony 30–122 ms.
- Na produkcji: pięć encji `budget_forecast_*` w HA (w tym `binary_sensor` = on), `sensor.budget_inbox`
  = 1 (karta „Prognoza: zabraknie do wypłaty”), panel `v0.26.0`, 0 błędów konsoli.
- Czasy GET po rozgrzaniu: `/` ≈ 460 ms, `/budget` ≈ 320, `/recurring` ≈ 310, `/inbox` ≈ 205 —
  bez regresji względem E1 (memo prognozy liczy raz na zmianę bazy). Pierwsze żądanie po restarcie
  ~0,6 s.
- Bufor na produkcji bez zmian (0), więc ostrzeżenie świeci, dopóki najniższy punkt jest ujemny.
