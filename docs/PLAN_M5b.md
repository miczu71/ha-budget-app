# M5b — płatności cykliczne + centrum powiadomień

Decyzja 16 w [`ROADMAP.md`](ROADMAP.md). Plany etapów: `PLAN_M5b_E<n>.md` (akceptowane przed
startem każdego etapu).

## Cel (wywiad 2026-10-04)

Najważniejsze dwa pytania:

- **A. „Co jeszcze zejdzie (i wpłynie) w tym miesiącu?”** — płatności cykliczne zapłacone /
  oczekiwane / spóźnione, sumy „jeszcze zejdzie” i „jeszcze wpłynie”.
- **B. „Za co płacę cyklicznie i co się zmieniło?”** — przegląd serii, nowe serie, inna kwota,
  brak płatności, seria, która ustała.

Dodatkowo: serie jako fundament kalendarza (M6) i prognozy salda (M8), oraz trafniejsza pula
Flex (stałe z serii zamiast samych median podkategorii).

## Decyzje

1. **Serie wykrywane automatycznie, potwierdzane przez użytkownika.** Tylko potwierdzone serie
   liczą się do statusów, zmian i puli. Odrzucona propozycja nie wraca.
2. **Wydatki i wpływy** (np. wypłata) — oba kierunki.
3. **Kadencje: miesięczna, kwartalna, roczna.** Historia w księdze jest krótsza niż dwa lata,
   więc seria roczna ma najwyżej dwa wystąpienia — detektor proponuje ją z dopiskiem „mało
   historii”, a główną drogą dla rocznych jest **seria ręczna z transakcji** („to się powtarza”).
4. **Seria zastępuje medianę w puli** (uzupełnia decyzję 15): stałe = oczekiwane kwoty aktywnych
   serii wydatkowych w przeliczeniu na miesiąc (Q = ⅓, Y = 1/12) + mediany podkategorii „stałe”
   z transakcji spoza serii. Transakcje serii wydatkowej nie wchodzą do „wydane” elastycznych,
   nawet gdy ich podkategoria jest elastyczna. Seria, której ostatnia transakcja ma kategorię z grupy oszczędności,
   przychodów albo „poza budżetem”, nie wchodzi do puli (wywiad E4 2026-10-05, zgodnie z decyzją 14). Serie wpływów **nie zmieniają puli** (decyzja 14
   bez zmian) — służą do „jeszcze wpłynie” i zmian.
5. **Zmiany: panel + encja w HA** (alerty push w czasie rzeczywistym zostają w backlogu —
   automatyzację na encji użytkownik może zrobić sam).
6. **Centrum powiadomień (dzwonek)** w pasku panelu: jedno miejsce na wszystko, co czeka na
   decyzję — nowe serie, zmiany serii, nieskategoryzowane bieżącego miesiąca (i poprzedniego,
   dopóki ma nieskategoryzowane), sprawy operacyjne (zgoda < 30 dni, nieudane synchronizacje,
   rozbieżność uzgodnienia salda). Bez „tempa budżetu”. Licznik przy „Do przejrzenia” w pasku
   przechodzi do dzwonka.
7. **UI w obecnym stylu**; całkowity refaktor (M13) obejmie te ekrany później.
8. **Bez LLM** — heurystyka odstępów i kwot, dane nie wychodzą z add-onu.

## Projekt

### Dane

- Migracja `009_series.sql`:
  - `series` — `id`, `name`, `direction` (`out`/`in`), `cadence` (`M`/`Q`/`Y`), `matcher_json`
    (warunki jak reguły kategorii: `rules.TextCondition`, kierunek, konto, zakres kwot),
    `expected_amount`, `tolerance`, `anchor_day`, `status` (`proposed`/`active`/`rejected`/
    `ended`), `origin` (`detected`/`manual`), `created_at`, `decided_at`.
  - `series_ack` (od E3) — decyzja dla okresu: (seria, okres, rodzaj) → „jednorazowo”,
    „pomiń ten okres”, „zostaw”.
- **Przynależność transakcji do serii liczona od zera** z `matcher` (wzorzec kategorii M4a),
  bez zapisu; przy kilku pasujących wygrywa najbliższa oczekiwanej kwocie. Edycja warunków
  działa od razu wstecz.

### Detektor (`recurring/detect.py`)

- Po synchronizacji (obok `suggest_later`) i na żądanie.
- Grupy: (sprzedawca albo kontrahent, kierunek); bez przelewów wewnętrznych, tylko PLN, bez
  transakcji objętych istniejącą serią.
- Kadencja z mediany odstępów: M 26–35 dni, Q 80–100, Y 350–380; ≥ 70% odstępów w oknie;
  minimum wystąpień: M/Q 3, Y 2.
- Oczekiwana kwota = mediana ostatnich 6 wystąpień; tolerancja = max(10%, 5 zł), szersza dla
  serii o zmiennej kwocie (rozrzut z historii).
- Tylko serie żywe (ostatnie wystąpienie w kadencji + zapas); grupy odrzucone pomijane.

### Statusy i zmiany

- Termin: M — `anchor_day` (mediana dnia miesiąca), Q/Y — ostatnie wystąpienie + kadencja;
  okno ±5 dni.
- Status w miesiącu: **zapłacone** (dopasowana transakcja), **oczekiwane** (przed końcem okna),
  **spóźnione** (po oknie bez transakcji). Sumy „jeszcze zejdzie / jeszcze wpłynie”.
- Zmiany (liczone na bieżąco, decyzja zapisana): nowa propozycja (potwierdź z edycją / odrzuć),
  inna kwota (przyjmij nową / jednorazowo), spóźniona (pomiń ten okres), ustała — 2 kolejne
  terminy bez płatności (zakończ / zostaw).

### Centrum powiadomień

- `inbox.py`: niezależni dostawcy zwracają `Item(kind, title, count, link, severity)`; nowe
  źródło = jedna funkcja. Stan liczony na bieżąco, bez „przeczytane” — karta znika po
  załatwieniu sprawy.
- Ikona dzwonka (inline SVG — czcionka kontenera nie ma emoji) z licznikiem w pasku; strona
  `/inbox` z kartami (tytuł, liczba, opis, akcja/link).
- Istniejące powiadomienia push (zgoda, błędy synchronizacji) bez zmian.

### Ekrany

- **„Cykliczne”**: „Ten miesiąc” (sumy + lista po terminie ze statusem) i „Wszystkie serie”
  (aktywne/zakończone, edycja warunków przez `_rule_conditions.html`, kwota, tolerancja,
  kadencja, podgląd dopasowanych transakcji). Formularz potwierdzenia propozycji — tu, kartą
  z dzwonka.
- **Budżet**: rozwinięcie stałych także na serie; linia „stałe: zapłacone X / jeszcze Y”.
- **Transakcje**: plakietka serii, „to się powtarza” (seria ręczna, od razu aktywna).

### Encje (MQTT)

| Encja | Stan |
|---|---|
| `sensor.budget_inbox` | liczba pozycji w dzwonku; atrybut: lista (rodzaj, tytuł, liczba) |
| `sensor.budget_fixed_paid` | wydatki z serii zapłacone w tym miesiącu |
| `sensor.budget_fixed_planned` | wydatki z serii, które jeszcze zejdą w tym miesiącu |
| `sensor.budget_income_planned` | wpływy z serii, które jeszcze wpłyną w tym miesiącu |

## Etapy

| Etap | Wersja | Wartość |
|---|---|---|
| E1 | 0.14.0 | Dzwonek (nieskategoryzowane, operacyjne, nowe serie) + `sensor.budget_inbox`; migracja, detektor, zakładka „Cykliczne”, potwierdzanie/odrzucanie propozycji, lista serii. Pula bez zmian. |
| E2 | 0.15.0 | Ten miesiąc: zapłacone / oczekiwane / spóźnione, „jeszcze zejdzie / wpłynie”, seria ręczna z transakcji, encje `fixed_paid` / `fixed_planned` / `income_planned`. |
| E3 | 0.16.0 | Zmiany serii w dzwonku (inna kwota, spóźniona, ustała) + `series_ack`. |
| E4 | 0.17.0 | Pula: stałe z serii, wyłączenie serii z „wydane”; porównanie puli z 0.13.0 na checkpoincie. |

E1 jest największy — jeśli plan etapu pokaże, że za duży, dzieli się na E1a (dzwonek) i E1b
(serie).

## Testy i weryfikacja

- Detektor na danych syntetycznych: kadencje, zmienne kwoty, przerwy, odrzucone, roczne z dwoma
  wystąpieniami.
- Statusy na granicach okna; pula bez podwójnego liczenia (seria w podkategorii „stałe” i
  w elastycznej); testy web dla każdego POST.
- Panel dev na kopii księgi + Playwright (mobile, 0 błędów konsoli); na żywo przez Ingress.

## Wynik

2026-10-05: M5b zamknięty przez użytkownika (E1 0.14.0 … E4 0.17.0, poprawka 0.17.1). Szczegóły i pomiary w `PLAN_M5b_E1.md`–`PLAN_M5b_E4.md`.
