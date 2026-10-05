# Budżet Domowy — słownik domeny

- **Księga (ledger)** — baza SQLite z transakcjami, kontami, regułami, seriami i kategoriami; jedno połączenie, jeden pisarz.
- **Seria** — wykryta lub ręczna płatność cykliczna (wydatek albo wpływ; M/Q/Y); transakcje przypisuje do niej `assign`.
- **Ledger snapshot** — zapamiętane wyniki liczone z całej księgi (przynależność do serii, sumy okresów, drzewo kategorii),
  ważne do pierwszego zapisu przez połączenie albo do zmiany dnia. Jedno źródło dla ekranów, dzwonka i encji MQTT.
- **Dzwonek (inbox)** — lista kart wymagających uwagi (uzgodnienie salda, nieskategoryzowane, nowe serie, zmiany serii).
