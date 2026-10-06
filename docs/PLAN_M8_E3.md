# M8 E3 — czytelniejsza sekcja „Do wypłaty”

## Po co
Sekcja „Do wypłaty” na Podsumowaniu (0.25–0.26) jest nieprzejrzysta (przegląd na telefonie 412 px, 2026-10-06):
- dwie konkurujące odpowiedzi: na górze najniższy punkt (czerwony), na dole saldo w dniu wypłaty; żadna nie mówi,
  co zrobić;
- rozbicie to osiem wierszy tabeli o tej samej wadze, serie i wpływy w dwóch osobnych „pokaż…”;
- checkbox z przyciskiem „Zastosuj” stoi w środku karty;
- wykres jest mały i niemy: widać skok, ale nie wiadomo, co go powoduje (brak zdarzeń i dat, brak strefy poniżej zera).

Decyzje użytkownika (wywiad 2026-10-06): (1) na górze werdykt i dzienny limit; (2) rozbicie jako oś czasu zdarzeń —
większy wykres ze znacznikami, pod nim jedna chronologiczna lista, liczby równania w zwartym pasku; (3) przełącznik
zadłużenia karty w stopce, bez „Zastosuj”.

Sukces: jedno spojrzenie na telefonie odpowiada „starczy czy nie i ile mogę dziennie”, a skok na wykresie da się
przypisać konkretnej serii. Encje MQTT i dzwonek bez zmian.

## Układ (telefon, od góry)
```
Do wypłaty · 24.10 (za 18 dni)
Zabraknie 150 zł                      (Serif, --neg)  albo „Starczy · zapas 200 zł” (--pos)
22.10 saldo spadnie poniżej zera.
Wydawaj do 190 zł dziennie, żeby wyjść na zero (teraz 200 zł)
pasek: Wolne dziś │ Serie − │ Flex − │ Wpływy +   → = saldo w dniu wypłaty
wykres: linia, strefa < 0, kreska bufora, znaczniki zdarzeń, etykieta najniższego punktu   (E3b)
lista chronologiczna serii i wpływów z saldem po zdarzeniu, wiersz dna wyróżniony           (E3b)
stopka: saldo − karta · data sald · EUR · przełącznik „Odejmij zadłużenie karty”
```
Copy:
- **Zabraknie** (dno < bufor, limit > 0): „Zabraknie {deficyt}”, „{dzień} saldo spadnie poniżej zera/bufora.”,
  „Wydawaj do {limit} dziennie, żeby wyjść na zero/bufor (teraz {tempo}), przy równym tempie.”
- **Zabraknie nawet bez Flex** (limit ≤ 0): „Zabraknie {deficyt}”, „Same płatności cykliczne przekraczają wolne środki.”
- **Starczy:** „Starczy · zapas {saldo w dniu wypłaty}”, „Możesz wydawać do {limit} dziennie (teraz {tempo}).”
- Bez dni Flex (wypłata jutro / koniec miesiąca dziś): bez wiersza limitu.

## E3a — werdykt, limit dzienny, pasek równania, stopka z przełącznikiem (0.27.0)
1. `forecast.py`: czysta funkcja `safe_per_day(days, today, per_day, buffer) -> Decimal | None` =
   `min` po dniach `d > today` z `per_day + (saldo_d − bufor) / (d − today)`, w dół do grosza; `None` bez dni Flex.
   W `Forecast`: `safe_per_day`, `shortfall = max(bufor − dno, 0)`, `days_left`; ustawiane w `build()`.
2. `_forecast.html`: nagłówek „za N dni”, blok werdyktu (trzy warianty copy), pasek równania, stopka z saldami,
   datą migawki, EUR i przełącznikiem. Dotychczasowe rozbicie (`dl.fc-kv`, dwa `<details>`) zostaje do E3b.
3. Przełącznik: `<input type="checkbox" role="switch">` w formularzu z `hx-post` i `hx-trigger="change"`, trasa
   `POST /forecast/card-debt` bez zmian; bez JS działa `<noscript>` z przyciskiem.
4. `app.css`: `.fc-verdict`, `.fc-strip`, `.fc-foot`, `.switch` (tokeny z DESIGN.md, cele dotyku ≥ 44 px);
   usunąć osierocone `.fc-opts`.
5. Testy: `test_forecast.py` (dno ujemne, starczy, limit ≤ 0, bufor > 0, brak dni Flex), `test_web_home.py`
   (trzy warianty copy, `role="switch"`, brak „Zastosuj”).
6. Weryfikacja i wydanie: pytest, ruff, mypy; zrzuty 412 i 1280 px + konsola; `impeccable detect`; `simplify`;
   skill `release` (0.27.0, opublikowany); instalacja z backupem; zrzut na produkcji.
   Cofnięcie: `git revert` + wydanie 0.27.1 albo backup add-onu (bez migracji bazy).

## E3b — wykres osi czasu i chronologiczna lista (0.29.0; 0.28.0 zajęte przez M16)
1. `charts.forecast_line`: wyższy wykres, strefa poniżej zera, znaczniki (wpływy + 3 największe wydatki), etykieta
   najniższego punktu, etykieta „wypłata” na osi X.
2. `_charts.html`: strefa, znaczniki z `<title>`, etykiety; nowe unikalne klasy (`fc-zone`, `fc-mark`, `fc-mark-in`).
3. `_forecast.html`: jedna lista `ul.rows` po dniach (data, nazwa, kwota, „saldo po”), wiersz dna wyróżniony,
   powyżej 8 zdarzeń reszta w `<details>`; wiersze linkują do `/recurring/{id}`.
4. Testy: `test_web_charts.py`, `test_web_home.py`; wydanie jak w E3a.

## Poza zakresem
Encje i dzwonek, logika prognozy poza `safe_per_day`, karta „Co jeszcze zejdzie” (po E3b zgłoszę częściowe
dublowanie), DESIGN.md (w E3b dopiszę tylko sekcję wykresu prognozy).

## Ryzyka
- Limit dzienny zakłada stałe tempo Flex do wypłaty, także w następnym miesiącu — stąd „przy równym tempie”.
- Lokalna kopia księgi może nie mieć świeżych sald: zrzuty lokalne na danych syntetycznych, wygląd na żywo
  dopiero po instalacji.
- WebView cache: statyki z nowym `?v=`, HTML `no-store` (już jest).

## Wynik E3a (2026-10-06)

- **0.27.0 wydane** (release `v0.27.0`, nie draft), zainstalowane z backupem add-onu; 608 testów, ruff i mypy czyste.
- Na produkcji: stopka `v0.27.0`, statyki `?v=0.27.0`, werdykt i dzienny limit widoczne, przełącznik
  zadłużenia karty zapisuje się sam (htmx, bez przeładowania), 0 błędów konsoli (telefon 390 px).
- Odstępstwo od planu: przy „Starczy” zapas to **najniższy punkt** (nie saldo w dniu wypłaty), bo to on
  decyduje, ile naprawdę zostaje; saldo w dniu wypłaty zostaje w wierszu wyniku pod paskiem.
- Pasek równania zastąpił tabelę od razu (zamiast dublować liczby do E3b); listy serii i wpływów nadal
  w dwóch `<details>`, do zastąpienia w E3b.
- Na desktopie wykres zajmuje ok. połowy szerokości karty (stały `viewBox`) — do poprawy w E3b.

## Wynik E3b (2026-10-06)

- **0.29.0 wydane** (release `v0.29.0`, nie draft), CI zielone, zainstalowane z backupem add-onu; 626 testów, ruff i mypy czyste.
- Na produkcji: stopka `v0.29.0`, statyki `?v=0.29.0`, jedna lista `ul.fc-list` (0 starych `<details>`), strefa poniżej zera,
  znaczniki, wiersz dna wyróżniony, 0 błędów konsoli. Telefon 390 px: czytelne; desktop 1280 px: wykres 640×356 px,
  czcionka osi ok. 12 px, bez poziomego przewijania.
- Odstępstwa od planu: (1) wykres ma `max-width: 640px` i na ekranach ≥ 720 px czcionkę osi 7 jednostek SVG — pełna szerokość
  karty rozciągała tekst do ok. 40 px; (2) zwinięta część listy otwiera się sama, gdy chowa wiersz dna;
  (3) lista `events` w `project()` jest źródłem znaków kwot, a `delta` liczy się z niej; (4) `impeccable detect` pominięty — narzędzia
  nie ma w tej instalacji, zrzuty i pomiary robione ręcznie.
- Instalacja: `ha_manage_updates` przerwało się timeoutem klienta po ok. 5 min, aktualizacja dokończyła się po stronie HA
  (sprawdzone na encji `update.*`, bez ponawiania).
- Do zgłoszenia: karta „Co jeszcze zejdzie” częściowo dubluje listę zdarzeń pod wykresem (nie ruszana).
- **Czeka checkpoint użytkownika.**

