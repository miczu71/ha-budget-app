Skarbonki na kontach-celach (M10 E1): karta skarbonki na ekranie, kafelek na Podsumowaniu i wybór skarbonki przy wydatku.

`section.piggy`: nazwa z zamaskowanym numerem konta-celu (`PL** **** … 1234`, pełny numer nigdy nie trafia do panelu), pasek `flex-bar` = saldo / cel, trzy `stat`: saldo, termin (z serii albo wpisany) i zalecane odłożenie w bieżącym okresie wypłaty z podpisem „przelej X” (`warn-text`) albo „odłożone” (`pos`). Akcje w `form.actions-row` (link „Zmień”, przycisk-link „Archiwizuj”).

`details.piggy-new > summary` ma wysokość celu dotyku (`--tap`). `section.piggy-tile` w siatce Podsumowania (kafelek „Skarbonki” w M16): do 3 skarbonek, pasek pod wierszem na całą szerokość, zdanie o nieprzelanej kwocie. `form.piggy-pick` w kolumnie szczegółów Transakcji zapisuje się po zmianie (htmx).

- Konsument dostarcza kwoty, procenty, zamaskowany numer i adresy.
