# M8 E2 — encje prognozy i ostrzeżenie w dzwonku (0.26.0)

- `forecast.for_today` + `ForecastMemo` (sygnatura bazy, dzień, bufor) — dzwonek liczy się na każdej
  stronie, więc prognoza jest liczona raz na zmianę bazy; `Snapshot.signature()` jest publiczne.
- Dzwonek: karta `forecast_low` (warn), gdy najniższy punkt < `forecast_buffer` (domyślnie 0).
- Encje MQTT: `sensor.budget_forecast_free_now`, `_card_debt`, `_lowest`, `_at_payday`,
  `binary_sensor.budget_forecast_shortfall` (problem). Bez `state_class`, jak encje Flex.
- Add-on niczego nie wysyła sam — powiadomienie to automatyzacja w HA na `binary_sensor`.
- Bez migracji; cofnięcie: `git revert` + wydanie albo backup add-onu.
