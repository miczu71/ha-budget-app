# Changelog

## 0.2.0

Kategoryzacja v1 (etap M4a, `docs/PLAN_M4a.md`).

- Kategorie dwupoziomowe (14 głównych, 41 podkategorii z grupą budżetu pod M5); w panelu
  dodawanie podkategorii i zmiana nazw.
- Automatyczna kategoria: ręczna > zwrot dziedziczy zakup > reguły > słownik sieci > typ
  transakcji; przelewy między własnymi kontami bez kategorii. Przeliczenie po każdej
  synchronizacji, imporcie, zmianie reguł i przy starcie.
- Wbudowany słownik ~400 wzorców polskich sieci i marek (nazwa sprzedawcy + kategoria).
- Reguły użytkownika z podglądem na żywo; „Zawsze dla …” z ręcznej zmiany kategorii.
- Nowy ekran **Wydatki** (miesiąc w kategoriach, zmiana m/m, wpływy, oszczędności, poza
  budżetem, bez kategorii); **Transakcje** z kategorią w wierszu, filtrem kategorii i kierunku
  oraz datą transakcji zamiast daty księgowania.
- Ręczna kategoria przechodzi na transakcję z API, gdy wiersz z CSV wejdzie w okno API.

## 0.1.1

- Synchronizacja: Millennium ignoruje `date_from` i zawsze oddaje 90 dni (~8 stron rachunku),
  przez co okno nie mieściło się w limicie 4 zapytań/dobę. Strony przychodzą od najnowszych,
  więc stronicowanie kończy się, gdy pobrane transakcje sięgną przed początek okna (tylko przy
  potwierdzonej malejącej kolejności dat). Zakładka okna 10 → 5 dni — zwykle 1 strona na konto.

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
