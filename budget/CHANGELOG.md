# Changelog

## 0.1.0

Pierwsza instalowalna wersja (etap M3, `docs/PLAN_M3.md`).

- Panel w Ingress: Status, Bank (klucz, przeniesienie sesji z CLI, połączenie/odnowienie zgody),
  Import CSV z raportem deduplikacji, Konta, Transakcje z filtrami.
- Synchronizacja 3×/dobę z licznikiem zapytań PSD2 per konto i endpoint; „Synchronizuj teraz”
  z panelu z nagłówkami PSU (poza limitem).
- Encje MQTT: dostępne środki per konto, dni zgody, ostatnia synchronizacja, problem,
  zapytania dziś, przycisk synchronizacji.
- Powiadomienia operacyjne: zgoda wygasa / nieaktywna, 3 nieudane synchronizacje, okno ponad
  limit.
