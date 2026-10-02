# Changelog

## 0.4.0

Podpowiedzi kategorii z AI — silnik i pomiar trafności (etap M4c/2, `docs/PLAN_M4c.md`).

- Nowe opcje: `ai_base_url`, `ai_api_key`, `ai_model`, `ai_daily_calls` (puste `ai_base_url` =
  wyłączone). Router zgodny z OpenAI (np. freellmapi), odpowiedź według schematu JSON.
- Po każdej synchronizacji, w tle: podpowiedzi dla sprzedawców z kolejki bez podpowiedzi
  (do 3 wywołań po 40, w limicie dobowym); odpowiedzi sprawdzane (istniejąca podkategoria,
  wydatek nie dostaje kategorii przychodu), zapisywane raz na sprzedawcę i kierunek.
- Minimalizacja danych: karta/BLIK — sprzedawca i opis; przelewy — tylko tytuł bez nazwy
  odbiorcy; kwota jako przedział; wycinane numery, e-maile, telefony, kody, daty.
- Status: karta **Podpowiedzi AI** (wywołania, błędy, liczniki), **Podpowiedz teraz**,
  **Zmierz trafność** (próbka sprzedawców z kategorią, trafność wg progu pewności).
- Klucze API maskowane w logach.
- Bez zmian w kolejce i transakcjach — zatwierdzanie podpowiedzi w 0.5.0.

## 0.3.1

Kolejka „Do przejrzenia” dla wybranego miesiąca (etap M4c/1, `docs/PLAN_M4c.md`).

- „Nieskategoryzowane” (i „bez kategorii” we Wpływach) na ekranie **Wydatki** otwiera kolejkę
  tylko z pozycjami z oglądanego miesiąca — zamiast całej kolejki.
- Widok miesiąca: nagłówek z miesiącem, przejście « » do sąsiednich miesięcy, link „wszystkie
  miesiące”; pokrycie i licznik w nagłówku liczone dla miesiąca (licznik w nawigacji — cały).
- Zapis jak dotąd: domyślnie reguła dla sprzedawcy (działa we wszystkich miesiącach — podgląd
  mówi, ile pozycji z innych miesięcy obejmie); „tylko te transakcje” = kategoria ręczna
  wyłącznie dla zaznaczonych pozycji z miesiąca.

## 0.3.0

Kolejka „Do przejrzenia” (etap M4b, `docs/PLAN_M4b.md`).

- Nowa zakładka **Do przejrzenia** z licznikiem w nawigacji: transakcje bez kategorii
  w grupach, pokrycie wydatków kategoriami w nagłówku.
- Grupy sprzedawców/odbiorców (z kierunkiem): kategoria dla całej grupy zapisuje regułę
  „sprzedawca równa się … + kierunek” z podglądem skutku; „tylko te transakcje” albo
  odznaczenie pozycji ustawia kategorię ręcznie, bez reguły.
- Grupy krajów dla sporadycznych płatności kartą za granicą (kraj z opisu, ISO 3166-1, albo
  waluta oryginalna); stali sprzedawcy zagraniczni (≥ 3 miesiące) zostają grupą sprzedawcy.
- „Nieskategoryzowane” na ekranie Wydatki prowadzi do kolejki.

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
