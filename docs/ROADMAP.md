# Roadmap — Budżet Domowy

Specyfikacja wyjściowa: [`SPEC.md`](SPEC.md) — **§10 (plan pracy) oraz §4, §5.2–5.4 i §6 zastępuje
ten dokument** (sekcja „Zmiany względem SPEC”). Przegląd rynku: [`BENCHMARK.md`](BENCHMARK.md).
Fakty o źródłach danych: [`FINDINGS_millennium.md`](FINDINGS_millennium.md),
[`FINDINGS_millenet_csv.md`](FINDINGS_millenet_csv.md).

Zasada pracy: etapy od fundamentu do wartości, każdy samodzielnie użyteczny. Szczegółowy plan
etapu (`docs/PLAN_<etap>.md`) jest akceptowany przed startem; po etapie checkpoint (przegląd +
jawne „go” przed następnym).

| Etap | Cel / wartość | Status |
|---|---|---|
| M0 | Szkielet repo, CI, `settings.py`, maskowanie w logach | ✅ |
| M1 | Klient Enable Banking + CLI, flow na Sandboxie | ✅ |
| M1b | Sonda Production Restricted na Millennium → `FINDINGS_millennium.md` | ✅ (drugi zrzut 2026-10-02: `entry_reference` stabilny) |
| M2 | **Rdzeń danych** — jedna księga bez duplikatów (CSV + API, karta↔konto, uzgadnianie salda) | ✅ 2026-10-02 (`PLAN_M2.md` § Wynik) |
| M3 | **Add-on w HA** — instalacja, synchronizacja 3×/dobę, panel (status, bank, import, transakcje), podstawowe encje | ✅ 2026-10-03 (`PLAN_M3.md` § Wynik; limit PSD2 liczony per endpoint) |
| M4a | **Kategoryzacja v1** — słownik polskich sieci, silnik reguł z podglądem, ekran „Wydatki” | ✅ 2026-10-04 — pokrycie wydatków 97% transakcji / 98% kwoty (KPI 85/85) (`PLAN_M4a.md`) |
| M4b | **Kolejka „do przejrzenia”** w panelu (grupy sprzedawców i krajów) | ✅ 2026-10-04 — kolejka w użyciu, zapis rozwinięty w M4f/M4h (`PLAN_M4b.md`) |
| M4c | **Poza planem (2026-10-02):** kolejka dla wybranego miesiąca + podpowiedzi kategorii z AI (freellmapi), zatwierdzane jednym dotknięciem | ✅ 2026-10-04 — 0.5.0; 84% decyzji to przyjęte podpowiedzi (`PLAN_M4c.md`) |
| M4d | **Poza planem (2026-10-02):** nowe kategorie główne, przenoszenie podkategorii, usuwanie pustej głównej | 0.6.0 (`PLAN_categories_move.md`) |
| M4e | **Poza planem (2026-10-02):** wyszukiwanie na żywo (Reguły — nowe, Słownik, Transakcje), jednolite dopasowanie bez ogonków i wielkości liter, wiele słów | 0.6.1 (`PLAN_live_search.md`) |
| M4f | **Poza planem (2026-10-03):** kolejka „Do przejrzenia” — edytowalny tekst reguły (zawiera / zaczyna się od) z podglądem innych grup; filtr po propozycji AI + „✓” | etap 1 = 0.8.0 (tekst reguły), etap 2 = 0.8.1/0.8.2 (filtr AI + zatwierdzenie) — ✅ 2026-10-04, zapis zastąpiony w M4h etap 2 (`PLAN_review_rule_text.md`) |
| M4g | **Poza planem (2026-10-04):** wydajność — zapis reguły z kolejki i podgląd zwalniały z każdą regułą (dopasowanie po kolei: transakcje × reguły); indeks reguł „sprzedawca równa się” | 0.9.1 wydane i zainstalowane 2026-10-04 — podgląd na żywo ~10 s → ~0,8 s; ✅ 2026-10-04 (`PLAN_rule_index.md`) |
| M4h | **Poza planem (2026-10-04):** pełne warunki reguły w miejscu — kolejka „Do przejrzenia” (dowolne pola, kilka warunków I, kwota, kierunek; reguła może złapać część grupy, reszta zostaje w kolejce), potem Transakcje i grupy krajów | ✅ 2026-10-04 (checkpoint zamknięty przez użytkownika) — etap 1 = 0.10.0 (kolejka); etap 2 = 0.11.0 (zapis domyślnie bez reguły — „utwórz regułę” na żądanie we wszystkich miejscach; Transakcje, grupy krajów) (`PLAN_review_rule_conditions.md`) |
| M5a | **Budżet Flex: „ile mogę jeszcze wydać”** — ręczna kwota elastyczna, tempo, ekran „Budżet”, grupy edytowalne; potem encje | etap 1 = 0.7.0 wydane i zainstalowane 2026-10-02; etap 2 = 0.9.0 (encje `budget_flex_*`) wydane i zainstalowane 2026-10-04; etap 3 = 0.12.0 pula z dochodu (decyzja 14, `PLAN_M5a_income.md`) wydane i zainstalowane 2026-10-04 (z poprawką kontroli salda karty); etap 4 = 0.13.0 składniki puli + edycja kosztów stałych na ekranie Budżet (decyzja 15, `PLAN_M5a_fixed.md`) wydane i zainstalowane 2026-10-04; ✅ 2026-10-04 — checkpoint zamknięty przez użytkownika (`PLAN_M5a.md`) |
| M5b | **Płatności cykliczne + centrum powiadomień** — wykrywane serie (wydatki i wpływy, M/Q/Y) potwierdzane przez użytkownika, „co jeszcze zejdzie / wpłynie”, zmiany serii, dzwonek w panelu, stałe w puli z serii | plan zaakceptowany 2026-10-04 (`PLAN_M5b.md`, decyzja 16): E1 0.14.0 dzwonek + detektor, E2 0.15.0 ten miesiąc, E3 0.16.0 zmiany, E4 0.17.0 pula; E1 = 0.14.0 wydane i zainstalowane 2026-10-04 (`PLAN_M5b_E1.md`), ✅ checkpoint E1 zamknięty przez użytkownika 2026-10-05; E2 = 0.15.0 wydane i zainstalowane 2026-10-05 (`PLAN_M5b_E2.md`), ✅ checkpoint E2 zamknięty przez użytkownika 2026-10-05; plan E3 zaakceptowany (`PLAN_M5b_E3.md`), E3 = 0.16.0 wydane i zainstalowane 2026-10-05, ✅ checkpoint E3 zamknięty przez użytkownika 2026-10-05; E4 = 0.17.0 wydane i zainstalowane 2026-10-05 (+ poprawka 0.17.1: wypłata w seriach wpływowych = ostatni wpływ) (`PLAN_M5b_E4.md`); ✅ M5b zamknięty przez użytkownika 2026-10-05 |
| M5c | **Skarbonki, trendy, limity** — nieregularne z celem rocznym, wykresy miesięczne, opcjonalne limity, `savings_rate` | scalony z M10 (2026-10-06): trendy są już w M13 E2, limity odrzucone w M5a |
| M6 | **Podsumowania + kalendarz płatności** — tydzień/miesiąc na telefon, kalendarz ICS | wywiad 2026-10-06 (`PLAN_M6.md`): cel = korekta wydatków w trakcie miesiąca; E1 podsumowania (poniedziałek + 1. dnia, 7:00, grupa domowników) i E2 kalendarz ICS → Remote Calendar wydane razem jako 0.22.0 i zainstalowane 2026-10-06; kalendarz zweryfikowany na żywo; 0.22.1 — link w powiadomieniu `/app/<slug>` (HA 2026.9: `/hassio/ingress/` = 404); ✅ 2026-10-06 — dostarczenie i otwieranie panelu potwierdzone przez użytkownika |
| M7 | **Kategoryzacja v2: mniej pracy z kolejką** — E1 pomiar w add-onie, E2 pamięć sprzedawcy (auto-przypisanie z ręcznych decyzji, oznaczone do zerknięcia), E3 lokalny klasyfikator dla nowych sprzedawców (warunkowo) | wywiad 2026-10-06 (`PLAN_M7.md`, decyzja 20); E1 = 0.31.0 wydane i zainstalowane 2026-10-06 — kolejka dziś: 53% pozycji od znanych sprzedawców, pamięć trafia 85–87% (k = 1–2), naive Bayes 25–30% (E3 odpada) (`PLAN_M7.md` § Wynik E1); E1b = 0.31.1 wydane i zainstalowane 2026-10-06 — przelewy 90% (k = 1), karta 79–80%, 95% tylko przelewy przy k = 3 (§ Wynik E1b); checkpoint E1b → decyzja 21; E2 = 0.32.0 wydane i zainstalowane 2026-10-06 — pamięć przejęła 43 pozycje, kolejka 109 → 66 (§ Wynik E2); E3 nie robiony (naive Bayes 25–30%); ✅ checkpoint E2 zamknięty przez użytkownika 2026-10-06 — M7 zamknięty |
| M8 | **Prognoza: czy starczy do wypłaty** — wolne środki (rachunek PLN − zadłużenie karty) dzień po dniu do najbliższej wypłaty, najniższy punkt, ostrzeżenie poniżej bufora | wywiad 2026-10-06 (`PLAN_M8.md`, decyzja 17); E1 = „Do wypłaty” na Podsumowaniu, 0.25.0 wydane i zainstalowane 2026-10-06 (`PLAN_M8_E1.md` § Wynik), E1b = 0.25.1 wydane i zainstalowane 2026-10-06 (wypłata wskazana na serii, przełącznik zadłużenia karty — `PLAN_M8_E1b.md`), ✅ checkpoint zamknięty przez użytkownika 2026-10-06; E2 = encje + dzwonek, 0.26.0 wydane i zainstalowane 2026-10-06 (`PLAN_M8_E2.md`); E3 = przebudowa widoku „Do wypłaty” (`PLAN_M8_E3.md`): E3a werdykt + limit dzienny + stopka z przełącznikiem = 0.27.0 wydane i zainstalowane 2026-10-06, E3b wykres osi czasu + lista chronologiczna = 0.29.0 wydane i zainstalowane 2026-10-06 (0.28.0 zajęte przez M16; `PLAN_M8_E3.md` § Wynik E3b); ✅ checkpoint E3b zamknięty przez użytkownika 2026-10-06 — M8 zamknięty |
| M9 | **Hipoteka: nadpłacać czy oszczędzać** — ekran „Kredyt” (parametry wpisane ręcznie: kapitał, WIBOR/WIRON + marża, raty; harmonogram liczony przez add-on; raty z księgi przesuwają stan, dzwonek przy zmianie stopy) i jeden rozbudowany kalkulator scenariuszy: nadpłata jednorazowa/miesięczna (krótszy okres albo niższa rata), zmiana WIBOR i marży, stopa oszczędności (efektywna z konta Profit albo wpisana, checkbox „zawsze promocja”) — korzyść z nadpłaty vs odsetki netto po Belce w horyzoncie; tabela wariantów WIBOR × nadpłata. Majątek netto wydzielony do M26 | wywiad 2026-10-12 (`PLAN_M9.md`, decyzja 28): E1 model i harmonogram, E2 księga + encje `sensor.budget_loan_*` + dzwonek, E3 kalkulator scenariuszy (silnik, ekran); E0–E3b zakodowane i zacommitowane 2026-10-12 (783 testy, UI sprawdzone w przeglądarce na 360 i 1280 px; `PLAN_M9.md` § Wynik), **0.43.0 wydane i zainstalowane 2026-10-12** (tag v0.43.0 na 3ee791f, backup add-onu „Budżet Domowy 0.42.0”; na żywo: stopka v0.43.0, zakładka Kredyt, `/loan` 200 `no-store`); kalibracja 0.44.1 (30/360, rata wg banku); E4 śledzenie WIBOR 3M = 0.45.0 (`PLAN_M9_wibor.md`); ✅ checkpoint zamknięty przez użytkownika 2026-10-12 — rata 4 787,42 zł zgodna z bankiem co do grosza, kapitał z raty 1 021,10 vs bank 1 021,11 zł (w ±1 zł) |
| M10 | **Oszczędności i skarbonki** — cele i postęp oszczędzania, stopa oszczędności w czasie (`savings_rate`), skarbonki wydatków nieregularnych z celem rocznym (z M5c) (zakres do wywiadu). **Konto oszczędnościowe (2026-10-10):** Enable Banking go nie widzi, więc śledzenie ręczne — przelewy na konto i z konta rozpoznawane po numerze (numer tylko w bazie/opcjach, nigdy w repo) i odfiltrowane jako przelew własny, nie wydatek/wpływ (uzupełnia decyzję 1); saldo z przelewów + parametry konta wpisane ręcznie (oprocentowanie, kapitalizacja, limity i terminy promocji), szacowane odsetki | E1 skarbonki — wywiad 2026-10-12 (`PLAN_M10_E1.md`, decyzja 25): E1a model i ekran, E1b rezerwacja w prognozie i kafelek — 0.39.0 + poprawka 0.39.1 wydane i zainstalowane 2026-10-12 (722 testy), ✅ checkpoint zamknięty przez użytkownika 2026-10-14 (pierwsza skarbonka „Nabu casa” działa: saldo, cel, termin, rezerwacja w prognozie; rozpoznawanie numeru konta-celu w przelewach z API przetestowane 2026-10-20 na kopii księgi: 38/38 numerów z API dopasowanych, format wpisu bez znaczenia); reszta M10 — wywiad 2026-10-12 (`PLAN_M10_E2.md`): E2 konto oszczędnościowe, E3 odsetki i promocja, E4 `savings_rate` + kafelek — zakodowane i zacommitowane 2026-10-12 (737 testów, UI sprawdzone w przeglądarce na kopii księgi), **czeka na zgodę na wydanie 0.40.0**; w tej samej wersji link serii → skarbonka w Cyklicznych; **0.40.0 wydane i zainstalowane 2026-10-12**. Konto Profit (Millennium) — wywiad 2026-10-12 (`PLAN_M10_E7.md`, decyzja 27): E7 monitor edycji promocji „Nowe środki na KOP” (codzienny odczyt regulaminu, prognoza okna dnia badania sald, ostrzeżenie „wyzeruj”); E5 miesiące „Stopy oszczędności” rozwijane na wpłaty/wypłaty per konto; E6 aktywacja promocji Profit w karcie konta (nowe środki, data, stawki; 91 dni) — E5–E7 zakodowane 2026-10-12 (757 testów, UI sprawdzone w przeglądarce, odczyt regulaminu zweryfikowany na żywym PDF) i wydane razem jako 0.42.0 |
| M11 | **Integracja z trackerem akcji** (osobny add-on autora) — akcje Nokia (wartość rynkowa + niezawiązane) w majątku netto M26 z encji HA, historia ze statystyk HA, dzwonek vestingu; dywidendy/środki zostają u brokera (bez wiązania z księgą) | wywiad 2026-10-20 (`PLAN_M11.md`): E0 pomiar, E1 odczyt i składnik majątku, E2 historia, E3 ekran i dzwonek → 0.61.0; plan zaakceptowany; E0 ✅ 2026-10-20 (statystyki HA tylko od 07.2026); E1 ✅ 2026-10-20 (`ca9b823`, `stocks.py` + składniki w `networth`, 1126 testów, ruff/mypy czyste; niewydane); E2 ✅ 2026-10-20 (`362f997`: `ha_client.monthly_statistics` przez WS + `stocks.backfill_history`, zależność `websockets`, 1134 testy, ruff/mypy czyste, verifier ACCEPT; sonda WS dopiero na żywo po wydaniu — błąd = log + ponowienie; niewydane); E3 ✅ 2026-10-20 (dzwonek `inbox.vest_soon` 14 dni przed vestingiem, adnotacja „brak danych o akcjach” na wykresie przed 07.2026, 1140 testów, ruff/mypy czyste; widok sprawdzony testem renderu, Playwright po wydaniu na żywo przez Ingress); **ZAMKNIĘTE: 0.61.0 wydane i zainstalowane 2026-10-20** (code-review: poprawka m/m bez akcji w starych migawkach, pusty prefiks czyści wpis, data vestingu zostaje, próg 3 dni; na żywo: Akcje 139 765 zł vs sensor 139 227 zł = +0,4%, brak ręcznego aktywa Nokia, adnotacja „brak danych o akcjach” widoczna, konsola czysta, 1144 testy) |
| M12 | **Czat AI z danymi** — pytania ad hoc o własne finanse w panelu (zakładka „Zapytaj”): LLM tłumaczy pytanie na zapytanie w języku zapytań add-onu, add-on liczy lokalnie jak „Wydatki”, LLM opisuje wynik zbiorczy; E1 pojedyncze pytanie, E2 rozmowa z kontekstem, E3 (warunkowo) rozszerzenia języka | wywiad 2026-10-06 (`PLAN_M12.md`, decyzja 23); E1 = 0.34.0 wydane i zainstalowane 2026-10-06 — na żywo suma zgodna z „Wydatkami” co do grosza (`PLAN_M12.md` § Wynik E1); 0.34.1 opisowe błędy AI, model `qwen/qwen3.8-27b`; ✅ checkpoint E1 zamknięty 2026-10-06; E2 (rozmowa z kontekstem, `PLAN_M12_E2.md`) = 0.35.0 wydane i zainstalowane 2026-10-06 — na żywo 3 tury z dopytaniami poprawne; ✅ checkpoint E2 zamknięty 2026-10-06; E3 = rejestr źródeł danych (decyzja 24), E3a 0.35.1 log na Status wydane 2026-10-06 (10 pytań, 0 „nie umiem”); E3b (rejestr źródeł, wszystkie 6 naraz, wywiad 2026-10-12) = 0.46.0 wydane i zainstalowane 2026-10-12 (`PLAN_M12_E3b.md` § Wynik; 824 testy; na żywo 5 z 6 pytań trafiło w źródło od razu); ✅ checkpoint zamknięty 2026-10-14: 6 pytań (po 1 na źródło: Do wypłaty, Karta, Budżet, Cykliczne, Skarbonki, Kredyt) zadanych w panelu v0.52.3 — 6/6 liczb zgodnych z ekranami co do grosza (cel ≥ 80%); 7 pytań usera o transakcje z 14.10 niezweryfikowanych (log bez kwot). Kandydat E3c: pytania złożone z dwóch źródeł naraz (np. „ile płatności kartą i ile do spłaty” → „nie umiem”); źródła do E3b: Do wypłaty (z tygodniami, M21 E4), Karta, Budżet, Cykliczne, Skarbonki (M10 E1), Kredyt (M9); **E3c (pytania z dwóch źródeł stanu, `PLAN_M12_E3c.md`) = 0.56.0 wydane i zainstalowane 2026-10-19** — na żywo 3 pytania dwuźródłowe trafiły w oba źródła, 1 jednoźródłowe bez regresji, liczba „koniec roku” z czatu = `sensor.budget_year_end`, 390 px bez przepełnienia, konsola czysta; M12 E3c: 0.56.1 — reguła zdania „nie starczy” działa na żywo; **pytanie złożone niestabilne: ta sama „karta + do wypłaty” dała „nie umiem” w 2 z 4 prób** (model czasem wybiera `unsupported` zamiast `source2`) — **0.56.2 (2026-10-19)**: prompt planu mówi wprost, że pytanie o dwa ekrany to `source` + `source2`; na żywo to samo pytanie **8/8** z obiema tabelami, 0 „nie umiem” (próba jednego pytania — inne pary źródeł niemierzone); **E3d 2026-10-20 (`PLAN_M12_E3d.md`)**: pomiar 8 par × 3 na 0.61.0 częściowy — 18/20 ważnych prób z obiema właściwymi tabelami, słaba para kredyt + inwestycje (1/3, model bierze „Skarbonki”); 4 próby zablokował dzienny limit czatu (`chat_daily_calls`) — do powtórzenia po resecie, potem poprawka opisów źródeł `savings`/`invest`; **0.62.1 (2026-10-21)**: opisy `savings` = stan, `invest` = decyzje; na żywo kredyt + inwestycje **2/3** (było 1/3), cel 3/3 niespełniony — druga próba w `plan_prompt` (`PLAN_M12_E3d.md` § Wynik E3), pozostałe pary niezmierzone; **0.62.2 (2026-10-21)**: `plan_prompt` rozróżnia savings/invest + przykład `loan + invest`; na żywo kredyt + inwestycje **5/5**, pary kontrolne (majątek + skarbonki, skarbonki + do wypłaty, karta + do wypłaty) bez regresji, 0 „nie umiem” — E3d zamknięte (`PLAN_M12_E3d.md` § Wynik po drugiej próbie) |
| M13 | **Całkowity refaktor UI** panelu — styl Monarch (jasny, jeden pomarańczowy akcent; wybrany 2026-10-05 spośród Copilot Money i Monarch), strona główna = podsumowanie budżetu, Status w menu ⚙ | ✅ 2026-10-06 — M13 zamknięty przez użytkownika (`PLAN_M13.md`): E1 0.18.0 fundament, nawigacja, Podsumowanie v0 ✅; E1b 0.18.1 drugi wygląd i przełącznik ✅ (`PLAN_M13_E1b.md`); E2 0.19.0 rozszerzone Podsumowanie: wykres kołowy kategorii, bilans z porównaniem, nadchodzące serie, ostatnie transakcje, wykres 12 miesięcy, przełączanie miesięcy ✅ (`PLAN_M13_E2.md`); E1c 0.19.1 jeden wygląd (Monarch), usunięty Copilot i przełącznik ✅ (wydane); E3 0.20.0 ekrany robocze (Transakcje, Do przejrzenia, Reguły): cele dotyku ≥ 44 px, wiersze na 360 px; kroki 0 pomiar, 1 Do przejrzenia, 2 Transakcje, 3 Reguły, 4 wydanie ✅ (`PLAN_M13_E3.md`, wydane 0.20.0); E3b 0.20.1 cele dotyku na Podsumowaniu, w tym słupki 12 miesięcy ≥ 24 px ✅ (`PLAN_M13_E3b.md`, wydane 0.20.1); E3c 0.20.2 cele dotyku w Wydatkach i Budżecie ✅ (`PLAN_M13_E3c.md`, wydane 0.20.1 razem z E3b); E3d 0.20.2 cele dotyku na pozostałych ekranach (reguła globalna dla pól i przycisków, rozwijany wiersz w Kategoriach, linki w zdaniu przez `::after`) — wszystkie ekrany ≥ 44 px ✅ (`PLAN_M13_E3d.md`, wydane 0.20.2; checkpoint zamknięty przez użytkownika 2026-10-05); E3e 0.20.3 domknięcie M13: pusty stan Reguł, „Wpływy” ≥ 44 px, rozwijany wiersz w Kosztach stałych, wspólna klasa linków `a.tap` — wydane 0.20.3 2026-10-05, na żywo 0 elementów < 44 px (`PLAN_M13_E3e.md`); ✅ checkpoint zamknięty przez użytkownika 2026-10-06 |
| M14 | **Wydajność panelu** — pomiar na produkcji 2026-10-05: 0,45–1,7 s na ekran, stały koszt ~450 ms (dzwonek), pętla zdarzeń blokowana przez ciężkie żądania; E1 Ledger snapshot (seria + sumy + kategorie po sygnaturze bazy), potem do decyzji: handlery poza pętlą zdarzeń, kolejka „Do przejrzenia”, PRAGMA/indeksy | E1 0.21.0 i E1b 0.21.1 ✅ wydane 2026-10-05 (`PLAN_M14_E1.md`): `/` 1425→438 ms, `/budget` 1320→351, `/recurring` 1698→308, `/accounts` 1126→125, dzwonek 853→293; wszystkie ekrany < 400 ms (`/` < 600); podgląd reguły w kolejce ~40 ms; **M14 zamknięty 2026-10-06** (decyzja użytkownika po pomiarach); niezrobione świadomie: handlery poza pętlą zdarzeń, PRAGMA/indeksy, pomiar ścieżki zapisu; **wznowiony 2026-10-20 (E2, `PLAN_M14_E2.md`)** — regres po M18–M26 na produkcji 0.61.0: `/` 1053 ms, `/status` 1090, `/invest` 767, `/networth` 754; E1 = 0.61.1 (nagłówek `Server-Timing`, wydane i zainstalowane 2026-10-20; handler `/` ~830 ms, `/status` ~780, `/invest` ~560, `/networth` ~535, dzwonek ~187 ms na każdej stronie); E2 (TDD, pomiar `Server-Timing` na żywo po każdym wydaniu): 0.61.2 memo rekomendacji (`AdviceMemo`) + kroki `h_*`/`s_*`/`p_*`; 0.61.3 `networth.compute` liczy skarbonki na `Snapshot` serwisu (`h_networth` 429→51 ms); 0.61.4 dzwonek (`changes.for_db`, `loan_rate`) i `invest_why` na pamięci `Snapshot`; **wynik 0.61.4 (mediana z 5)**: `/` 574 (próg 600 ✓), `/invest` 200, `/networth` 188, `/recurring` 274, `/inbox` 244, `/budget` 273, `/review` 251, dzwonek 119 ms; **`/status` 584 ms (próg 400 ✗)** — `s_summaries` ~367 ms (dwa podglądy `summary.build`) = E2c, następny krok; opcjonalnie `h_flex` ~127 ms na `/` |
| M15 | **Karta kredytowa** — E1 licznik płatności w miesiącu (karta bezpłatna przy 5) + ostrzeżenie przed końcem miesiąca; E2 osoby i ręczne przypisanie płatności (licznik per osoba); E3 historia z CSV; E4 limit, cykl rozliczeniowy, termin bezodsetkowy, kwota do spłaty w terminie | wywiad 2026-10-06 (`PLAN_M15.md`, decyzje 18–19); kolejność **M15 E1 → E2 → E3 → M8 → M15 E4**; E1 = 0.23.0 wydane i zainstalowane 2026-10-06 ✅ (kafelek potwierdzony przez użytkownika); E2 = 0.24.0 wydane i zainstalowane 2026-10-06, osoby dodane; E3 = 0.24.1 + poprawka 0.24.2 (pliki tymczasowe SQLite w pamięci — AppArmor) wydane, historia przypisana (101 płatności); 0.24.3 „Karta” jako główna zakładka; ✅ M15 E1–E3 zamknięte przez użytkownika 2026-10-06; E4 „ile spłacić i do kiedy” — wywiad 2026-10-06 (cykl = miesiąc kalendarzowy, termin 20. następnego, przypomnienia 15. i 19.), plan w `PLAN_M15.md` § E4; 0.30.0 wydane i zainstalowane 2026-10-06 (`PLAN_M15.md` § Wynik E4); ✅ checkpoint E4 zamknięty przez użytkownika 2026-10-06 — M15 zamknięty; porównanie z bankiem 20.10 ✅ zgodne (user 2026-10-20); atrybut `available` → `available_bank` w 0.31.0 (zweryfikowane w HA 2026-10-07) |
| M16 | **Układ ekranu głównego** — kolejność i ukrywanie 8 kafelków siatki (tryb edycji ze strzałkami ↑/↓ i okiem, układ wspólny, zapis w `kv`) | wywiad 2026-10-06 (`PLAN_M16.md`); 0.28.0 wydane i zainstalowane 2026-10-06 ✅ (617 testów; weryfikacja na żywo przez Ingress: wersja, 8 kafelków, tryb edycji); ✅ M16 zamknięte, potwierdzone przez użytkownika na telefonie 2026-10-06) |
| M17 | **Tracker warunków promocji bankowych** — konto promocyjne z listą warunków per okres (np. liczba transakcji kartą, suma wpływów, saldo na dzień, jednorazowe kroki do odhaczenia ręcznie: logowanie, zgody, otwarcie lokaty w terminie), postęp liczony z księgi, przypomnienia przed końcem okresu (dzwonek + powiadomienie, jak M15 E1), rejestr należnych i wypłaconych premii. Pytania do wywiadu: podlinkowanie nowego banku przez Enable Banking (zmienia decyzję 1 — dziś tylko 3 konta) czy import CSV; szablony promocji wpisywane ręcznie czy z opisu przez AI; uogólnienie licznika karty z M15 | scalony z M22 jako E5 (2026-10-19, `PLAN_M22.md`); podlinkowanie drugiego banku i tracker warunków → M32 (2026-10-22) |
| M18 | **Prognoza roczna i scenariusze** — 12 miesięcy do przodu z serii wpływów i wydatków (rozszerzenie M8 poza najbliższą wypłatę), znane zdarzenia w roku (np. niższa wypłata netto po przekroczeniu progu podatkowego), scenariusze „co jeśli” (nowa seria, zmiana wypłaty) | wywiad 2026-10-14 (`PLAN_M18.md`, decyzja 29); E1 silnik `year.py` + backtest + ekran `/year`, E2 zdarzenia plan/scenariusz + propozycje (migracja 021), E3 kafelek + `sensor.budget_year_end` + źródło czatu; jedno wydanie 0.53.0; E1 zrobione lokalnie 2026-10-14 (418015e, 901 testów, ekran `/year` zweryfikowany na danych syntetycznych 390/1280 px; **niewydane**) — pomiar metody na prawdziwej księdze dopiero po wydaniu (karta „Prognoza roczna — pomiar” na Status, mierzy tylko wydatki spoza serii); E2 zrobione lokalnie 2026-10-14 (zdarzenia plan/scenariusz, propozycje progu PIT i premii, migracja 021, 923 testy, ekran zweryfikowany 390/1280 px; **niewydane**); E3 zrobione lokalnie 2026-10-14 (kafelek „Rok”, `sensor.budget_year_end`, źródło czatu `year`, 929 testów; **niewydane**); **wydane 0.53.0 2026-10-14** (e86ee75, tag v0.53.0, 930 testów; na żywo: `/year` = kafelek = `sensor.budget_year_end` = −21 638,86 zł, pierwszy deficyt 10.2026, mogę wydać 697,24 zł/mies., 390/1280 px bez błędów konsoli); do checkpointu usera: pomiar ±10% (Status → „Prognoza roczna — pomiar”), ocena tabeli miesięcy, jedno pytanie do czatu o rok (✅ 2026-10-19: −1 744,20 zł = `sensor.budget_year_end`); **pomiar 2026-10-19: odchylenie −24,5% (poza ±10%)** — prognoza wydatków spoza serii 57 857 zł vs fakt 76 677 zł za I–IX, w każdym miesiącu zaniżona (−18…−36%); wg `PLAN_M18.md` stop i decyzja usera; **0.56.1 (2026-10-19)**: pominięty niepełny pierwszy miesiąc księgi → **−19,8%**, karta pokazuje składniki (Flex −30%, sezon +7,1 tys. zł zawyżony; diagnoza w `PLAN_M18.md`); ✅ checkpoint zamknięty przez użytkownika 2026-10-19 z adnotacją (pomiar opisuje skok poziomu Flex między 1. a 2. rokiem księgi; bieżąca mediana = fakt 2026; metoda bez zmian) |
| M19 | **Wykres przepływów (Sankey)** — wpływy → grupy budżetu → kategorie dla miesiąca i roku, w panelu | wywiad 2026-10-20 (`PLAN_M19.md`): sekcja w Wydatkach, miesiąc + rok, najpierw makieta B/D na danych dev (E0), potem E1 dane+geometria, E2 sekcja, E3 rok; pomysł 2026-10-07 z przeglądu rynku (raporty Monarch); E0 ✅ 2026-10-20 (makieta, układ B poziomo wybrany, `PLAN_M19.md` § Wynik E0); E1 ✅ 2026-10-20 (`flow.build` + `charts.sankey`, commit 6730fcb, 1156+ testów zielone, ruff/mypy czyste); E2 ✅ 2026-10-20 (sekcja „Przepływ pieniędzy” w Wydatkach, be886b7, 1156 testów, ruff/mypy czyste; zrzut 390 px niezrobiony — pomiar przy weryfikacji); E3 ✅ 2026-10-20 (przełącznik Miesiąc/Rok `flow=year`, 19bae8a); simplify + code-review (etykiety w pełnych zł, linki roku, strzałki niosą `flow=year`); **wydane 0.62.0 2026-10-20** (1157 testów; pomiar 390/1280 px na danych dev: bez nakładania etykiet; na żywo: sekcja renderuje się w miesiącu i roku, 8 linków do kategorii, 0 błędów konsoli); ✅ M19 zamknięte; follow-up ✅ 2026-10-20: komponent `SankeyChart` w Claude Design (M20), re-sync `bundle.css` do 0.62.0 |
| M20 | **System designu Monarch w Claude Design** — artefakt typu Design System jako lustro `app.css`/`DESIGN.md` (kod źródłem prawdy), baza makiet M18/M19 i przyszłych refaktorów; E0 dokumenty, E1 tokeny/fonty/ikony/README/okładka, E2 komponenty rdzenia, E3 wykresy i ekrany robocze, E4 procedura re-sync | wywiad 2026-10-07 (`PLAN_M20.md`); artefakt prywatny, podglądy tylko z neutralnych danych; E0–E4 wykonane 2026-10-07 (36 komponentów, 223 z 227 klas z podglądem, `PLAN_M20.md` § Wynik); ✅ M20 zamknięty przez użytkownika 2026-10-07 |
| M21 | **Okres wypłaty jako główna oś Podsumowania** — E1 ręczna data wypłaty w bieżącym okresie (prognoza, „Co jeszcze zejdzie”, ICS), E2 hero „limit do wypłaty” zamiast miesięcznego „Zostało” (miesiąc jako kafelek), E3 „wydane od wypłaty” i pasek okresu | wywiad 2026-10-09 (`PLAN_M21.md`); E1 = 0.36.0, E2 = 0.37.0, E3 = 0.38.0 (2026-10-09); E4 tydzień pon–nd w „Do wypłaty” (wywiad 2026-10-12) — 0.39.0 wydane 2026-10-12; E5 re-sync systemu designu (`.payday-hero`, tygodnie, skarbonki; 38 komponentów) wykonany 2026-10-12; ✅ checkpoint zamknięty przez użytkownika 2026-10-12 |
| M22 | **Agent inwestycyjny** — na bazie oszczędności (M10) i kredytu (M9): przegląd polskich blogów o promocjach i inwestycjach (lokaty, konta oszczędnościowe, obligacje skarbowe, promocje bankowe — styk z M17), rekomendacja ile i w co odkładać, żeby oszczędności rosły, w zestawieniu z nadpłatą kredytu; wyłącznie doradztwo, żadnych operacji na kontach. Pytania do wywiadu: źródła i częstotliwość przeglądu, profil ryzyka i horyzont, jakie dane wychodzą do LLM (decyzje 12/23), forma (dzwonek / powiadomienie / zakładka) | wywiad 2026-10-19 (`PLAN_M22.md`, decyzja 30): E1 aktywa, koszyki, kalkulator netto; E2 obligacje + ranking lokat → 0.57.0; E3 RSS blogów + streszczenia LLM; E4 dzwonek, push po wypłacie, czat → 0.58.0; E5 śledzenie promocji (dawne M17) → 0.59.0; plan zaakceptowany; E1 ✅ 2026-10-19 (ae7b09b: ekran `/invest`, koszyki, kalkulator netto, oferty ręczne; 988 testów, niewydane); E2 ✅ 2026-10-19 (0.57.0 wydane: obligacje + ranking z sieci, „Moje banki”, ranking: bank ze słownika); E3 ✅ 2026-10-19 (ab5811c: RSS 5 blogów + LLM → oferty „do sprawdzenia”, pomiar trafności na Status; migracja 024); E4 ✅ 2026-10-19 (44704c4 + poprawki de614cf; **0.58.0 wydane** wraz z E3: dzwonek lepsza oferta/termin, push po wypłacie, źródło czatu `invest`, uzasadnienie LLM); E5 ✅ 2026-10-19 (**0.59.0**: migracja 025, `promo_track.py`, „Skorzystaj” + „Promocje w toku”, dzwonek i push 5/1 dni, rejestr premii; warunki liczone w okresie całej promocji, „saldo na dzień” tylko ręcznie, wpływy bez przelewów własnych; 1081 testów) — **M22 zamknięte** |
| M24 | **Paragony Lidl Plus i inflacja osobista** — pozycje paragonów z add-onu Lidl dopasowane do płatności kartą (wydatki na poziomie produktów i grup produktów zamiast samego „Lidl”, historia cen kupowanych produktów); osobisty indeks cen z własnego koszyka (kategorie, potem produkty) porównany z CPI GUS i opcjonalnie z budżetami gospodarstw domowych GUS. Dane publiczne GUS tylko pobierane, nic nie wychodzi. Pytania do wywiadu: jak add-on budżetu czyta paragony (API add-onu Lidl / plik / MQTT), trafność dopasowania paragon↔płatność, czy zwrot kaucji i kupony wchodzą do ceny | ✅ zamknięte 2026-10-20 bez osobnej pracy (decyzja użytkownika): paragony i podział → M29 (0.50.0), historia cen i inflacja koszyka → add-on Lidl E7 (zakładka „Ceny”); porównanie z CPI GUS świadomie pominięte |
| M25 | **Rok w liczbach** — podsumowanie roku (grudzień/styczeń): największe zmiany kategorii r/r, rekordy, sprzedawcy roku, wpływy vs wydatki, stopa oszczędności (M10); ekran w panelu + powiadomienie, źródło dla czatu (decyzja 24) | — (pomysł 2026-10-10 z przeglądu rynku: Monarch Year in Review; zakres do wywiadu; termin naturalny: koniec 2026) |
| M26 | **Majątek netto** — salda kont (EUR po kursie NBP), oszczędności (M10), inwestycje z encji HA / trackera akcji (M11), minus kredyt (M9) i zadłużenie karty; historia w migawkach we własnej bazie; wydzielone z M9 | wywiad 2026-10-20 (`PLAN_M26.md`, decyzja 31): tylko majątek finansowy; E0b parking oszczędności (Profit → inny bank), E1 model + kurs NBP, E2 historia (migawki + odtworzenie wstecz), E3 ekran, E4 sensor/podsumowanie/czat/agent M22 → 0.60.0; plan zaakceptowany; E0 ✅, E0b ✅ 2026-10-20 (parking: 026), E1 ✅ 2026-10-20 (model + kurs NBP: 027; niewydane), E2 ✅ 2026-10-20 (historia: migawka dzienna + odtworzenie końców miesięcy, `077d899`, 1104 testy; niewydane), E3 ✅ 2026-10-20 (ekran Majątek + kafel + pola aktywa, `aa8d32e`, 1111 testów, Playwright 360/1280 px; niewydane)), E4 ✅ 2026-10-20 (sensor, podsumowanie, czat, agent M22); **ZAMKNIĘTE: 0.60.0 wydane i zainstalowane 2026-10-20**, 0.60.1 tego samego dnia (kredyt liczył się w historii dopiero od `principal_date` → fałszywe m/m −768 tys. zł; migracja 028; po poprawce m/m −2 833 zł, r/r −2 970 zł; 1118 testów). konto parkingowe M10 i oszczędności/aktywa wpisane przez usera ✅ 2026-10-20 |
| M27 | **Poprawki M9 i M21 (kalkulator kredytu, tygodnie prognozy)** — E1 tabela „zmiana WIBOR” zwinięta, 5 wierszy, krok 1/0,5/0,25 p.p., liczona dopiero po rozwinięciu; E2 tygodnie okresu: podpis metody, pusty pasek planu, „+X zł ponad plan”, etykieta liczby dni przyciętego tygodnia. Jedno wydanie 0.47.0. Szczegóły: [`PLAN_M9_M21_poprawki.md`](PLAN_M9_M21_poprawki.md) | E1+E2 wydane 0.47.0 (2026-10-12); poprawka układu 390 px wydana w 0.48.0 |
| M28 | **Kredyt: porządek formularza + edytowalne zakładki** — E1 seria rat w formularzu „Zmień”, opis stopy oszczędności w kalkulatorze; E2 edytor zakładek (kolejność, ukrywanie; Podsumowanie przypięte). Jedno wydanie 0.48.0 razem z poprawką układu 390 px. Szczegóły: [`PLAN_M28.md`](PLAN_M28.md) | E1+E2 wydane 0.48.0 (2026-10-12), zweryfikowane na żywo |
| M29 | **Podział transakcji na kategorie + paragony Lidl Plus** — ręczny podział transakcji na dowolną liczbę podkategorii (licznik reszty, zapis tylko przy reszcie 0), części liczą się we wszystkich wyliczeniach; dopasowanie paragonów z add-onu Lidl (plik `/share/lidl/receipts.json`, kwota + data ±3 dni), link do paragonu i automatyczny podział wg kategorii produktów. Realizuje część „paragony” z M24. Szczegóły: [`PLAN_M29.md`](PLAN_M29.md) | ✅ zakończone 2026-10-12: 0.49.0 (podział), 0.50.0 (paragony Lidl; Lidl 0.19.0–0.19.1) |
| M30 | **Prognoza roczna bez wydatków jednorazowych** — flaga kategorii „pomiń w prognozie rocznej” wyłącza ją z mediany Flex, korekty „nieregularne” i „roczne bez serii” (Budżet i Wydatki bez zmian); przełącznik w Kategoriach, linijka „Pominięte w prognozie” na ekranie „Rok”. Szczegóły: [`PLAN_M30.md`](PLAN_M30.md) | E1 ✅ 2026-10-14 (flaga + obliczenia, testy); E2 ✅ 2026-10-14 (przełącznik w Kategoriach, linijka na „Rok”); wydanie ✅ 0.54.0 (2026-10-14); flagi ustawione przez usera ✅ 2026-10-14 |
| M31 | **Poprawki panelu** — usuwanie kart „Do decyzji” na zawsze, kafelki sald nad hero (konto, karta, oszczędności), tydzień z dniem wypłaty, zalecane odłożenie do skarbonek w pełnych złotych. Szczegóły: [`PLAN_M31.md`](PLAN_M31.md) | E1 ✅ 2026-10-19 (aadd8a8; 941 testów, mypy czysty); E2 ✅ 2026-10-19 (tydzień z dniem wypłaty; 943 testy); E3 ✅ 2026-10-19 (skarbonki w pełnych zł; 944 testy); E4 ✅ 2026-10-19 (kafelki sald nad hero; 947 testów, ruff/mypy czyste, 390/1280 px bez przepełnienia); **wydane 0.55.0 2026-10-19** (v0.55.0, 948 testów; na żywo: stopka v0.55.0, 3 kafelki nad hero, „Usuń” w /inbox, tydzień kończy się w dniu wypłaty 23.10, Nabu 31 zł, konsola czysta, 390 px bez przepełnienia) — ZAMKNIĘTE; **0.55.1 2026-10-19**: kafelki sald jako pasek 42 px (było 148 px na 390 px), kwoty w pełnych zł, skarbonki w popoverze; na żywo 42 px, bez ucinania, konsola czysta (`PLAN_M31_E4b.md`) |
| M32 | **Rotacja środków między kontami promocyjnymi (Velobank + Millennium)** — podpięcie ROR Velobanku (z Elastycznym Kontem Oszczędnościowym) i system pilnujący promocji: (1) terminy — do kiedy trwa promocyjne oprocentowanie, żeby w porę przelać środki na inne konto (np. Millennium) i dalej mieć dobrą stopę; (2) warunki — licznik transakcji bezgotówkowych w miesiącu na ROR (karta do konta osobistego lub BLIK; przykład: edycja 12/2026 „Nowe środki na Elastycznym Koncie Oszczędnościowym”, 4,5% zamiast 1%, dziś 0/5, „zrób jeszcze 5 transakcji”); (3) monitor edycji i nowych edycji promocji (jak `promo_watch` dla Profit, M10 E7). Millennium bez pilnowania warunków (główne konto, transakcje i tak są) — wyjątek karta kredytowa (M15). Zależy od wielobankowości (dziś jedna sesja PSD2, jeden `aspsp_name`; limit 4 zapytań/konto/dobę liczy bank per konto) — wywiad pokaże: PSD2 drugiego banku vs konto ręczne + CSV, uogólnienie licznika karty z M15, scalenie z M17 (tracker warunków) i M10 (promocje oszczędnościowe), powiadomienia jak M15 E1. Dotyka decyzji 1 (zakres: 3 konta Millennium) | wywiad 2026-10-22 (`PLAN_M32.md`): PSD2 drugiego banku, przypomnienia + rekomendacja, parser regulaminu (auto + karta do wglądu), powiadomienia 14/7/2; etapy E0 (EB ma Velobank?) → E1 wielobankowość → E2 licznik+terminy (wydanie) → E3 monitor regulaminu → E4 rekomendacja; kod E1–E4 do chmury (`claude --remote`); E0 zrobione 2026-10-22 (VeloBank jest w Enable Banking, beta); E1 zmergowane (PR #1, 53805ba, 2026-10-26); E2 gotowe w PR #3 (czeka na CI i merge); E3 w PR #2 (czeka na review i merge); E2–E5 zmergowane; **WYDANE 0.63.0 (2026-10-26)**; uwagi z review (sync częściowy `consecutive_failures`, alerty zgód per bank, karta `velo_new_edition` bez odrzucenia, `END_PAST_DAYS`, id `promo_cashless`, atomowość `kind`, cel = konto Velo w `savings`) → follow-up; kredyt cloud 100 USD (do 5.11) NIE zszedł — `PLAN_M32.md`; **cd. 2026-10-26** (VeloBank podłączony, konta #4/#5): E6 BLIK Velo + liczniki per bank, E7 oszczędności z banku, E8 hero r/r, E9 kafelek Akcje — `PLAN_M32_E6.md`; **WYDANE 0.64.0 (2026-10-26)**, zweryfikowane na żywo; **cd. 2 (2026-10-26, zatwierdzone)**: E10 dane, E10b przelewy własne (wewnętrzne / na oszczędności) — **zrobione bee794c**, E11 przeniesienia bez parkingu — **zrobione 29d3b47 (pytest 1279, ruff, verifier ACCEPT)**, E12 rotacja wg edycji usera — **zrobione 8bddc07 (pytest 1283, ruff, verifier ACCEPT)**, E13 karta Velo, E14 sekcja Velo + push + „Widziałem”, E15 saldo rachunków w budżecie → wydanie 0.65.0 — `PLAN_M32_E10.md` |
| M33 | **Kategoria na etapie blokady** — przydzielanie kategorii transakcji od razu jako blokadzie (PDNG), zanim zostanie zaksięgowana, żeby po kilku dniach nie trzeba było zgadywać, co jest czym. Fakty (2026-10-26): Millennium przez Enable Banking zwraca wyłącznie `BOOK` (0 PDNG na ~950 transakcji w zrzutach prod, `FINDINGS_millennium.md`); Velobank (beta) nieznany do czasu połączenia; `ledger.ingest_api` kasuje i wstawia PDNG przy każdym syncu (L4), więc kategoria nadana blokadzie przepadłaby. Opcje do wywiadu: zapowiedź w panelu dopasowana do późniejszego księgowania / przeniesienie kategorii PDNG→BOOK (Velobank) / powiadomienie Companion „co to za wydatek”; najpierw sprawdzić, czy Velobank zwraca PDNG | zgłoszone 2026-10-26, po wydaniu M32; wywiad `grill-me` przed planem | **ODRZUCONE 2026-10-26** (decyzja usera): blokad nie obsługujemy, bazujemy wyłącznie na API (BOOK), kiedykolwiek pojawią się nowe kwoty |

Mapowanie starego planu (SPEC §10) na nowy: storage+dedup → M2; sync_service, panel, pakowanie,
HA publisher (podstawy) → M3; kategoryzacja → M4/M7; `budget_engine` → M5; import CSV → M2;
test end-to-end na produkcji → kryteria akceptacji M3; HA publisher (statystyki, dashboard) →
backlog (decyzja 10).

## Decyzje użytkownika (wywiad 2026-10-01)

1. **Zakres: tylko 3 podlinkowane konta** (rachunek PLN, rachunek EUR, karta kredytowa).
   Przelewy na inne konta (także własne, niepodlinkowane) są wydatkami/wpływami kategoryzowanymi
   według odbiorcy — np. „Rodzina”, „Oszczędności” (grupa oszczędności, nie wydatek elastyczny).
2. Karta kredytowa ma kartę dodatkową — **bez funkcji „kto wydał”** (API nie podaje numeru karty);
   druga karta istotna tylko dla deduplikacji importu CSV.
3. Metoda budżetu: **Flex + opcjonalne limity** (stałe / elastyczne / nieregularne).
4. Okres: **miesiąc kalendarzowy**.
5. Kategoryzacja: **lokalnie, LLM opcjonalnie** (`ai_task.generate_data`, minimalizacja danych).
   **Zmienione 2026-10-02 (M4c):** LLM przez lokalny router OpenAI-compatible (freellmapi) zamiast
   `ai_task`; zakres danych w decyzji 12.
6. Priorytety HA: **podsumowania** oraz **kalendarz płatności** (to-do „do przejrzenia” → backlog,
   decyzja 10).
7. Dalsze etapy: **prognoza przepływów**, **majątek netto + kredyt**.
8. CSV z Millenetu = historia; ponowny import dozwolony (idempotentny).
9. Fixture CSV w repo dopiero po usunięciu lokalizacji sklepów/bankomatów.
10. **(2026-10-02) Wszystkie wizualizacje w panelu add-onu, bez dashboardów w HA.** Po stronie HA
    zostają encje budżetu (automatyzacje, powiadomienia) i kalendarz płatności; HA to-do,
    statystyki długoterminowe HA i dashboard Lovelace → backlog.
11. **(2026-10-02) Kategoryzacja:** cel pierwszy „gdzie idą pieniądze” (ekran w panelu),
    kategorie dwupoziomowe, lukę po słowniku zamyka pełny silnik reguł; M4 dzielone na M4a/M4b.
12. **(2026-10-02) Dane wysyłane do LLM (M4c):** płatności kartą/BLIK — nazwa sprzedawcy i opis
    (po wycięciu IBAN-ów, numerów kart, e-maili, telefonów); przelewy — wyłącznie tytuł, bez nazwy
    odbiorcy i jej tokenów; kwota tylko jako przedział. Router przekazuje zapytania do darmowych
    chmur — zaakceptowane świadomie.
13. **(2026-10-02) Budżet Flex — pierwszy kawałek (M5a) odpowiada na „ile mogę jeszcze wydać”:**
    pula = kwota ustawiona ręcznie (podpowiedź: mediana 6 pełnych miesięcy), „wydane” = tylko grupa
    elastyczne + wydatki bez kategorii (ostrożnie, z dopiskiem); stałe i nieregularne obok jako
    informacja; odpowiedź = kwota + tempo (na dzień, kreska „gdzie powinieneś być dziś”), bez
    limitów per kategoria.
14. **(2026-10-04) Pula Flex z dochodu (M5a etap 3, zmienia decyzję 13):** pula miesiąca =
    wpływy z grupy przychody z poprzedniego miesiąca − mediana stałych (6 mies.); oszczędności
    nie są odejmowane. Pula idzie za faktyczną wypłatą (spadek po progu podatkowym obniża ją od
    następnego miesiąca) — bez średniej dochodu. Nadwyżka nietypowo wysokiego wpływu (premia)
    zostaje poza pulą. Ręcznie wpisana kwota nadpisuje automatyczną (źródła wpływów zawężone
    decyzją 22). Szczegóły:
    [`PLAN_M5a_income.md`](PLAN_M5a_income.md).
15. **(2026-10-04) Koszty stałe w puli = suma median podkategorii (M5a etap 4, zmienia sposób
    liczenia stałych z decyzji 14):** zamiast mediany miesięcznej sumy — składniki sumują się do
    kwoty w puli. Koszt stały = podkategoria z grupą „stałe” (bez ręcznych pozycji — M5b); jedno
    miejsce do przeglądu i edycji = rozwinięcie „Koszty stałe” w sekcji „Kwota budżetu”.
    Szczegóły: [`PLAN_M5a_fixed.md`](PLAN_M5a_fixed.md).

16. **(2026-10-04) Płatności cykliczne + centrum powiadomień (M5b, uzupełnia decyzję 15):**
    serie wykrywane automatycznie i potwierdzane przez użytkownika (także wpływy; kadencje
    miesięczna, kwartalna, roczna; roczne głównie ręcznie z transakcji). Stałe w puli = oczekiwane
    kwoty serii wydatkowych w przeliczeniu na miesiąc + mediany podkategorii „stałe” spoza serii;
    transakcje serii nie wchodzą do „wydane”. Serie wpływów nie zmieniają puli. Dzwonek w panelu
    zbiera wszystko, co czeka na decyzję (nowe serie, zmiany serii, nieskategoryzowane miesiąca,
    sprawy operacyjne) + encja `sensor.budget_inbox`. Szczegóły: [`PLAN_M5b.md`](PLAN_M5b.md).

17. **(2026-10-06) Prognoza (M8) odpowiada na „czy starczy do wypłaty”:** wolne środki = saldo
    rachunku PLN − bieżące zadłużenie karty (jawnie rozbite na widoku), EUR poza wynikiem;
    horyzont do najbliższej wypłaty z serii przychodów; przyszłe wydatki = serie + reszta puli
    Flex; ostrzeżenie (dzwonek + encje) poniżej bufora z opcji. Szczegóły: [`PLAN_M8.md`](PLAN_M8.md).
18. **(2026-10-06) Karta kredytowa (M15):** licznik zakupów bezgotówkowych w miesiącu
    kalendarzowym (karta bezpłatna przy 5), powiadomienie 5 dni i dzień przed końcem miesiąca,
    gdy warunek niespełniony; potem limit (ręcznie) i okres bezodsetkowy (ustawienia — API ich
    nie podaje). Kolejność M15 E1 → M8 → M15 E2. Szczegóły: [`PLAN_M15.md`](PLAN_M15.md).
19. **(2026-10-06) Płatności kartą przypisywane do osób (M15 E2, zmienia decyzję 2):** bank liczy
    5 płatności osobno dla karty głównej i dodatkowej, a API nie podaje numeru karty — każdą płatność
    kartą przypisuje się ręcznie do osoby (bez podpowiedzi), nieprzypisana nie liczy się nikomu,
    przypomnienia do obojga; historię przypisuje numer karty z CSV. Imiona tylko w bazie.
20. **(2026-10-06) Kategoryzacja v2 (M7) ma zmniejszyć pracę z kolejką „Do przejrzenia”,** nie
    podnieść pokrycie (reguły dają już ~97%). Pewne przypadki dostają kategorię od razu (osobne
    źródło, nigdy nie nadpisuje ręcznej, reguły, słownika ani typu), ale trafiają do sekcji
    „przypisane automatycznie” w kolejce (✓ hurtem, poprawka jednym dotknięciem). Kolejność:
    pomiar → pamięć sprzedawcy → klasyfikator, ten ostatni tylko przy precyzji ≥ 95%. Dane nie
    wychodzą poza add-on. Szczegóły: [`PLAN_M7.md`](PLAN_M7.md).
21. **(2026-10-06) Pamięć sprzedawcy bez progu 95% (M7 E2, zmienia decyzję 20):** pomiar E1/E1b pokazał,
    że pamięć trafia w ~87% (przelewy ~90%, karta ~80%), a 95% osiąga tylko na kilku pozycjach. Pamięć
    działa dla wszystkich typów przy jednej ręcznej decyzji (k = 1, wszystkie decyzje sprzedawcy zgodne);
    zamiast progu trafności — każde automatyczne przypisanie trafia do sekcji „przypisane automatycznie”
    do zerknięcia, a poprawka wyłącza pamięć dla tego sprzedawcy.
22. **(2026-10-06) Pulę Flex zasilają tylko „Wynagrodzenie” i „Świadczenia” (zmienia decyzję 14):**
    jednorazowe wpływy (zwroty, przelewy od znajomych) w „Inne wpływy” nie podnoszą puli następnego
    miesiąca; w raporcie „Wydatki” nadal są przychodem. Wybór po kategorii, nie po regularności
    źródła — nowy pracodawca liczy się od pierwszej wypłaty.
23. **(2026-10-06) Czat AI z danymi (M12) = analizy ad hoc, liczone lokalnie:** LLM zwraca plan zapytania
    (JSON wg schematu add-onu), add-on liczy go na tym samym zbiorze co „Wydatki”, LLM opisuje wynik.
    Do LLM wychodzą pytanie, kategorie, plany zapytań rozmowy i wyniki zbiorcze — bez pojedynczych
    transakcji; nazwy sprzedawców kart/BLIK tak (jak decyzja 12), odbiorcy przelewów jako „Odbiorca N”
    podmieniani lokalnie. Rozmowa z kontekstem (E2). Osobny limit `chat_daily_calls`. Szczegóły:
    [`PLAN_M12.md`](PLAN_M12.md).

24. **(2026-10-06) Czat poznaje nowe funkcje przez rejestr źródeł danych (M12 E3):** każda funkcja
    z własnymi danymi (prognoza, karta, pula Flex, serie, później majątek, skarbonki, akcje) dostaje
    źródło dla czatu; do modelu nadal tylko wyniki zbiorcze (decyzja 23). Szczegóły:
    [`PLAN_M12.md`](PLAN_M12.md) § E3.

25. **(2026-10-12) Skarbonki (M10 E1) = konta-cele w banku, rezerwacja w prognozie:** skarbonkę
    (nazwa, numer konta-celu, cel, termin, opcjonalnie seria) tworzy użytkownik; saldo liczy się
    z przelewów na numer konta-celu i z niego (numer tylko w bazie). Zalecane odłożenie miesięczne =
    (cel − saldo) / miesiące do terminu; nieprzelane odłożenie w bieżącym okresie wypłaty obniża
    prognozę M8 jak planowany przelew. Przelewy na konta-cele i wydatki przypisane do skarbonki nie
    liczą się do puli Flex. Szczegóły: [`PLAN_M10_E1.md`](PLAN_M10_E1.md).

26. **(2026-10-12) Konto oszczędnościowe i stopa oszczędności (M10 E2–E4):** saldo = wpisane saldo
    startowe na dzień + przelewy na konto i z konta (po numerze, jak skarbonki) + szacowane odsetki
    (stopa bazowa + promocja do limitu i daty, kapitalizacja miesięczna, Belka 19%), z ręczną
    korektą salda. `savings_rate` = (wpłaty na konto − wypłaty z niego) / wpływy miesiąca; skarbonki
    się nie liczą. Widok: ekran „Oszczędności” (dawniej „Skarbonki”) + kafelek, bez encji HA.
    Szczegóły: [`PLAN_M10_E2.md`](PLAN_M10_E2.md).

27. **(2026-10-12) Konto Profit: monitor edycji promocji (M10 E7):** dzień badania sald edycji (np. 4.09.2026
    dla ed. 77) bank publikuje 3–10 dni PO fakcie, więc nie da się go tylko „wykryć” — add-on codziennie czyta
    regulamin (stały adres, PDF) i do tego prognozuje okno badania następnej edycji: od końca przystępowania
    poprzedniej minus 6 dni do tego końca (odstępy 0/−5/−6 dni w ed. 65→66, 75→76, 76→77). Użytkownik zeruje
    Millennium w oknie, wpisuje „nowe środki” ręcznie przy aktywacji (próg = 0), warunek premii (5 płatności
    miesięcznie) zakładany jako spełniony. Szczegóły: [`PLAN_M10_E7.md`](PLAN_M10_E7.md).

28. **(2026-10-12) Hipoteka (M9) = decyzja „nadpłacać czy oszczędzać”, nie rejestr kredytu:** parametry wpisane
    ręcznie (oprocentowanie zmienne: WIBOR/WIRON + marża), harmonogram liczy add-on przy stałej bieżącej
    stopie; raty z księgi przesuwają stan, rozjazd raty wywołuje dzwonek „zmieniła się stopa?”. Kalkulator
    porównuje nadpłatę (krótszy okres / niższa rata) z odsetkami netto z konta oszczędnościowego (stopa
    efektywna z M10 albo wpisana; checkbox „zawsze promocja”) i symuluje zmiany WIBOR i marży. Dane kredytu
    tylko w bazie, nigdy w repo. Majątek netto wydzielony do M26. Szczegóły: [`PLAN_M9.md`](PLAN_M9.md).

29. **(2026-10-14) Prognoza roczna (M18) = jeden ekran „Rok”:** do końca roku kalendarzowego (od 1.11 cały
    następny rok), start z wolnych środków M8; miesiąc = serie (M/Q/Y) + Flex (mediana 12 mies. + wiersz
    „nieregularne” zgodny z sumą historii); odpowiada na: ile odłożę, czy będzie deficyt, ile mogę wydać
    (cel na koniec horyzontu, domyślnie 0, bufor M8). Zdarzenia (zmiana kwoty serii, nowa seria, jednorazowe)
    w trybie plan/scenariusz; propozycje progu PIT (plan) i premii (scenariusz) z historii, zatwierdza
    użytkownik. Kredyt i oszczędności luźno (zwykłe serie/zdarzenia jednorazowe, bez przeliczania rat).
    Encja `sensor.budget_year_end` i źródło czatu `year`, bez dzwonka i push. Szczegóły: [`PLAN_M18.md`](PLAN_M18.md).

30. **(2026-10-19) Agent inwestycyjny (M22, scala M17 jako E5):** doradztwo bez operacji na kontach; trzy koszyki
    (poduszka = mnożnik × miesięczne wydatki, cele 1–5 lat = skarbonki M10, długi termin = reszta z EDO/IKE, ETF i nadpłatą),
    rekomendacja najpierw dopełnia poduszkę; nowe pieniądze = nadwyżka z M18 po skarbonkach i buforze (przy deficycie tylko
    optymalizacja tego, co leży). Zysk netto liczy add-on deterministycznie (Belka/IKE, ETF w 3 scenariuszach); LLM tylko
    streszcza wpisy blogów i pisze uzasadnienie, do LLM idą kwoty zbiorcze (decyzja 23). Źródła: obligacjeskarbowe.pl, ranking
    lokat i kont, RSS 2–3 blogów; oferta z LLM ma status „do sprawdzenia” do potwierdzenia. Promocje „tylko dla nowych”
    filtrowane po liście banków użytkownika. Szczegóły i etapy: [`PLAN_M22.md`](PLAN_M22.md).

31. **(2026-10-20) Majątek netto (M26):** tylko majątek finansowy (bez nieruchomości i aut; hipoteka po stronie pasywów).
    Aktywa: konta (EUR po kursie NBP), oszczędności M10, skarbonki, aktywa M22 bez powiązanych z oszczędnością M10;
    pasywa: kredyt M9 i dług karty. Historia: migawka dzienna + jednorazowe odtworzenie końców miesięcy (oznaczone
    „przybliżone”). Wskaźniki: płynność w miesiącach wydatków i LTV (do agenta M22 i czatu). Aktywa M22 z datą wartości
    i przypomnieniem po 90 dniach. Parking oszczędności: drugie konto M10 z flagą „parking dla Profit”, przelewy
    Profit ↔ parking to „przeniesienie”, nie wypłata. Alerty tylko w podsumowaniu miesięcznym. Szczegóły: [`PLAN_M26.md`](PLAN_M26.md).

## Zmiany względem SPEC (zweryfikowane na danych)

- **§4 klucz konta:** zastępczy `account.id` + aliasy (hashe EB, IBAN, numery kart z CSV) zamiast
  `identification_hash` jako PK — hash to funkcja (IBAN, waluta), więc koliduje.
- **§5.2 deduplikacja:** tabela referencji zewnętrznych + odcisk transakcji z indeksem wystąpienia
  (odporne na przenumerowanie licznika w `entry_reference`), granica CSV/API, parowanie przelewów
  karta↔konto, parowanie zwrotów — szczegóły w M2.
- **§5.3 kategoryzacja:** krok MCC usunięty (Millennium nie podaje MCC); w zamian słownik polskich
  sieci, typ transakcji, pamięć sprzedawców, klasyfikator, LLM.
- **§5.4 / §6 budżet i encje:** Flex zamiast samych limitów per kategoria; zdarzenia i alerty
  w czasie rzeczywistym → backlog (zostają operacyjne: zgoda, błędy synchronizacji).
- **§10 kolejność:** pakowanie add-onu wcześniej (M3), bo poprawianie kategorii wymaga panelu.

## Wnioski z danych, na których stoi plan (metryki metody, bez danych osobowych)

- **Spłaty karty:** po stronie rachunku w API — pusty opis, brak kontrahenta; po stronie karty
  „WCZESN.SPL.Z RACHUNKU”. Parowanie (ta sama kwota, przesunięcie 0–1 dnia) trafiło **7/7**.
  Bez parowania wydatki kartą liczą się podwójnie (karta przejmuje coraz większą część wydatków).
- **CSV↔API:** rachunek w oknie wspólnym **370/370** zgodnych po (data rozliczenia, kwota);
  karta: zdublowany blok pod dwoma numerami kart, a zakupy walutowe mają w CSV inną kwotę PLN
  niż w API (mediana różnicy ~2%) → CSV tylko przed granicą API.
- **Saldo w CSV ciągłe** (0 przerw w ~2800 parach wierszy) → kontrola kompletności importu.
- **Typ transakcji** jest tylko w CSV; heurystyka odtwarza go z pól API w **89%** przypadków.
- **Kategoryzacja z pudełka** (słownik ~200 słów kluczowych polskich sieci + typ transakcji):
  **67% transakcji / 53% kwoty**. Resztę kwot niosą głównie przelewy do osób (reguły per
  odbiorca) — top 10 odbiorców pokrywa większość takich przelewów; top 50 nieznanych sprzedawców
  podnosi pokrycie transakcji do ~81%; długi ogon to sprzedawcy jednorazowi (→ M7).
- **Zwroty:** 86% daje się sparować z wcześniejszym zakupem (ten sam sprzedawca, ≤ 90 dni).
- **Płatności cykliczne** są znaczącą częścią miesięcznych wydatków; zdarzają się pojedyncze
  bardzo duże przelewy jednorazowe → flaga „jednorazowe / wyłączone z budżetu”.

---

## M2 — Rdzeń danych: jedna księga bez duplikatów

**Wartość:** cała historia (CSV) + API w jednej, zdeduplikowanej księdze, spłaty karty jako
przelewy, saldo uzgodnione.

- `storage/`: SQLite, migracje `NNN_*.sql` + `PRAGMA user_version`. Tabele: `account`
  (+ `account_alias`), `txn` (kwota ze znakiem jako tekst/Decimal, `orig_amount`/`orig_currency`,
  `kind` + `kind_source`, `transfer_group`, `refund_of`, `budget_flag`, `fingerprint`,
  `raw_json`), `txn_ref` (source, konto, ref — UNIQUE), `import_batch`, `balance_snapshot`,
  `eb_session`, `sync_log`.
- `csv_import.py`: parser Millenetu (BOM, CRLF, QUOTE_ALL, kropka dziesiętna, waluta oryginalna
  z opisu karty), mapowanie numerów kart → konto karty (propozycja automatyczna po nakładaniu
  się z API).
- **Warstwy deduplikacji:**

  | Warstwa | Reguła |
  |---|---|
  | L0 w obrębie źródła | CSV: ten sam klucz pod różnymi numerami kart → max(liczności), nie suma (prawdziwe „bliźniaki” zostają). API: referencja, potem odcisk (konto, data, kwota, opis znormalizowany) + indeks wystąpienia. |
  | L1 CSV↔API | Wiersze CSV sprzed najstarszej transakcji API danego konta → wstawiane; w oknie wspólnym CSV tylko **wzbogaca** (typ, konto kontrahenta, oryginalna waluta): rachunek 1:1, karta dokładnie lub rozmyto (sprzedawca, ±5 dni, kwota ±5% przy walucie obcej). Niesparowane → raport, nie księga. |
  | L2 przelewy | DBIT konto A ↔ CRDT konto B (oba podlinkowane), ta sama kwota, 0–3 dni; sygnały: pusty opis / typ „WCZEŚN.SPŁ” / „WCZESN.SPL.Z RACHUNKU” / własny IBAN. Strona bez pary (poza oknem) też oznaczana jako przelew. |
  | L3 zwroty | CRDT-zwrot → zakup u tego samego sprzedawcy ≤ 90 dni, kwota ≤ zakupu (`refund_of`; kategorię dziedziczy w M4). |
  | L4 PDNG→BOOK | Ogólnie jak w SPEC (Millennium nie zwraca PDNG). |

- Typ transakcji dla API odtwarzany heurystycznie, z `kind_source`.
- **Uzgadnianie salda:** ciągłość salda CSV, saldo na granicy CSV/API, `balance_snapshot` (ITBD)
  vs saldo z księgi → rozbieżność = brak lub duplikat → raport.
- CLI `budget ingest` / `budget report` (same liczby). Na start: drugi zrzut API (stabilność
  `entry_reference`, informacyjnie — odcisk i tak obsługuje przenumerowanie).

**Akceptacja:** 0 duplikatów (suma kontrolna salda zgodna na każdym koncie); 7/7 spłat
sparowanych; zdublowany blok karty usunięty; ponowny import = brak zmian; testy na danych
syntetycznych i zanonimizowanej próbce.

## M3 — Add-on w HA: pierwsze uruchomienie

**Wartość:** add-on działa, synchronizuje 3×/dobę, dane w panelu lokalnie.

- Dockerfile wg pozostałych add-onów autora (`python:3.12-alpine`, wersja przypięta),
  `run.sh`, AppArmor, Ingress (`X-Ingress-Path`, allowlista `172.30.32.2`), zasady cache dla
  WebView (`no-store`, `?v=`, plakietka wersji).
- `sync_service`: harmonogram, licznik 4 zapytań/dobę, backfill, `sync_log`; **migracja sesji
  z CLI** (bez nowego SCA; zgoda ważna do 2027-03-30).
- Panel (htmx, mobile-first): Status, Połącz bank / Odnów zgodę, Import CSV (z raportem
  L0–L3), Konta, Transakcje (lista z filtrami).
- MQTT: salda (ITAV), `last_sync`, `consent_days_left`, `sync_now`;
  powiadomienia operacyjne (zgoda wygasa, 3 nieudane synchronizacje).
- Wydanie: GitHub release (skill `release`), aktualizacja przez Supervisor.

**Akceptacja:** instalacja i synchronizacja działają; panel zweryfikowany w Playwright
(zrzut + 0 błędów konsoli); encje widoczne w HA.

## M4a — Kategoryzacja v1: silnik reguł + ekran „Wydatki”

**Wartość:** „gdzie idą pieniądze” — wydatki miesiąca w kategoriach, w panelu. Szczegóły:
[`PLAN_M4a.md`](PLAN_M4a.md).

- Normalizacja sprzedawców (`LIDL UL. PRZYKLADOWA MIASTO POL` → „Lidl”, `AMZN*…` → „Amazon”).
- Wersjonowany **słownik polskich sieci** dostarczany z add-onem (tylko sieci ogólnopolskie).
- **Jeden deterministyczny silnik:** ręczna > zwrot dziedziczy kategorię zakupu > reguły
  użytkownika > słownik > domyślne kategorie typów; przeliczanie od zera (wzorzec
  `rebuild_links`), ręczne nietykalne.
- Reguły: warunki (pole/operator/wartość, kierunek, konto, typ, zakres kwot) → kategoria
  (+ nazwa sprzedawcy); priorytety, **podgląd „ile pasuje / ile zmieni”** przed zapisem (zamiast
  osobnego „zastosuj do historii”). Pamięć poprawek = reguła tworzona z ręcznej zmiany.
- Kategorie seed (2 poziomy) z grupami Flex; wyłączenie z budżetu = kategoria z grupy `excluded`.
- Ekran **„Wydatki”**: miesiąc, kategorie z udziałem i zmianą m/m, rozwinięcie podkategorii,
  przejście do transakcji, nieskategoryzowane.

**KPI:** pokrycie automatyczne ≥ 67% transakcji / ≥ 53% kwoty od startu; po ~1 h sesji reguł
(top sprzedawców i odbiorców) **≥ 85% transakcji i ≥ 85% kwoty**.

## M4b — Kolejka „do przejrzenia”

**Wartość:** nowe transakcje bez kategorii lub z niepewną podpowiedzią nie giną.

- Kolejka w panelu: nieskategoryzowane i nowe od ostatniego przeglądu, grupowane po sprzedawcy
  / odbiorcy; akceptacja grupowa, „utwórz regułę” jednym kliknięciem.
- Liczba do przejrzenia liczona w add-onie (dla podsumowań M6), bez encji i HA to-do.
- **(2026-10-02) Kolejka = tylko nieskategoryzowane** (bez „nowych od ostatniego przeglądu” —
  automatycznie skategoryzowanych nie trzeba potwierdzać); grupa = sprzedawca + kierunek,
  domyślnie reguła, opcja „tylko te”; zagraniczne transakcje kartą grupowane po kraju.
  Szczegóły: [`PLAN_M4b.md`](PLAN_M4b.md).

## M4c — Kolejka miesiąca + podpowiedzi AI (poza planem, 2026-10-02)

**Wartość:** z ekranu „Wydatki” przegląda się tylko nieskategoryzowane z danego miesiąca;
dla grup w kolejce i transakcji bez kategorii AI podpowiada kategorię, zatwierdzaną jednym
dotknięciem. Część LLM z M7 przeniesiona tutaj; lokalny klasyfikator i KPI zostają w M7.

1. **0.3.1** — kolejka „Do przejrzenia” z filtrem miesiąca (zapis jak dotąd: domyślnie reguła).
2. **0.4.0** — silnik podpowiedzi: klient freellmapi, redakcja danych, cache w bazie, przebieg
   po synchronizacji, backtest trafności (`suggest-eval`) jako punkt decyzji przed etapem 3.
3. **0.5.0** — chip „AI: kategoria ✓ ✕” w kolejce (✓ = reguła dla grupy) i na liście Transakcji
   (✓ = kategoria ręczna jednej transakcji), „podpowiedz teraz”, statystyka przyjęte/odrzucone.

Szczegóły: [`PLAN_M4c.md`](PLAN_M4c.md).

## M5 — Budżet Flex

**Wartość:** „ile zostało?” i „gdzie uciekają pieniądze?” — w panelu add-onu.

**(2026-10-02) Podział:** M5a — „ile mogę jeszcze wydać” (ręczna kwota, tempo, ekran „Budżet”,
edycja grupy podkategorii; etap 2 = 0.9.0: encje `flex_*`), szczegóły [`PLAN_M5a.md`](PLAN_M5a.md);
M5b — płatności cykliczne, `fixed_paid`/`fixed_planned`; M5c — skarbonki, wykresy trendu,
opcjonalne limity, `savings_rate`, `month_income`/`month_expenses`, `category_<slug>`.
Poniżej zakres całego M5 sprzed podziału. **(2026-10-06)** M5c scalony z M10: skarbonki i
`savings_rate` przechodzą do M10, trendy są już w M13 E2, limity odrzucone w M5a.

- Grupy kategorii: przychody, stałe, elastyczne, nieregularne („skarbonki”: cel roczny →
  miesięcznie, z przeniesieniem), oszczędności, przelewy, wyłączone/jednorazowe.
- **Wykrywanie płatności cyklicznych** (seria, kadencja, oczekiwana kwota i data) → plan kosztów
  stałych; budżet elastyczny z podpowiedzią (mediana 6 mies.) + opcjonalne limity per kategoria;
  prognoza końca miesiąca.
- Encje: `flex_remaining` / `flex_spent` / `flex_budget`, `fixed_paid` / `fixed_planned`,
  `month_income` / `month_expenses`, `savings_rate`, `category_<slug>` (wybrane), skarbonki.
- Encje bez dashboardu w HA (do automatyzacji i powiadomień).
- **Ekran „Budżet” w panelu:** Flex zostało/wydane, stałe zapłacone/planowane, skarbonki,
  wykresy trendu miesięcznego z własnej bazy (biblioteka wykresów serwowana lokalnie, nie z CDN).

**Akceptacja:** suma grup = wydatki z księgi (bez przelewów); historia widoczna w wykresach panelu.

## M6 — Podsumowania + kalendarz płatności

- Podsumowanie tygodniowe (poniedziałek) i miesięczne (1.) przez konfigurowalną usługę notify
  (alias osoby, nigdy `mobile_app_*`): wydatki vs plan, zostało (Flex), top kategorie, największe
  pozycje, zmiany cen subskrypcji, liczba do przejrzenia (liczona w add-onie) + link do panelu.
- **Kalendarz:** add-on serwuje ICS z nadchodzącymi płatnościami (serie cykliczne, raty) →
  integracja HA **Remote Calendar**; po synchronizacji `homeassistant.update_entity`.

**Akceptacja:** podsumowanie dociera na telefon; kalendarz pokazuje płatności na 60 dni.

## M7 — Kategoryzacja v2: mniej pracy z kolejką

**(2026-10-06, decyzja 20)** Cel zmieniony po wywiadzie: pokrycie z reguł to już ~97%, więc
liczy się praca z kolejką, nie odsetek automatycznych. Od 0.11.0 zapis w kolejce domyślnie nie
tworzy reguły, więc powracający sprzedawca wraca do kolejki — stąd pamięć sprzedawcy przed
klasyfikatorem. Szczegóły: [`PLAN_M7.md`](PLAN_M7.md).

- E1 — pomiar w add-onie (przycisk na Status): backtest pamięci sprzedawcy i naive Bayes na
  ręcznych decyzjach, udział powracających sprzedawców w kolejce. Punkt decyzji.
- E2 — pamięć sprzedawcy: źródło `learned` (zgodne ręczne decyzje dla sprzedawcy i kierunku),
  sekcja „przypisane automatycznie” w kolejce.
- E3 (warunkowo) — lokalny klasyfikator (czysty Python, naive Bayes na n-gramach sprzedawcy +
  typ + przedział kwoty) dla sprzedawców widzianych pierwszy raz.
- ~~Opcjonalny fallback `ai_task.generate_data`~~ → **przeniesione do M4c** (freellmapi,
  zakres danych wg decyzji 12).

**KPI:** pozycji trafiających do kolejki tygodniowo o ≥ 50% mniej, precyzja auto-przypisań
≥ 95% (< 5% poprawianych w sekcji „przypisane automatycznie”).

## M8 — Prognoza przepływów

- Saldo przewidywane dzień po dniu do końca miesiąca i do najbliższego wpływu (serie cykliczne,
  wykryte wpływy, tempo wydatków elastycznych).
- Wykres prognozowanego salda na ekranie panelu.
- `safe_to_spend` (encja) = saldo − płatności stałe do najbliższego wpływu − bufor; ostrzeżenie
  (podsumowanie + powiadomienie persistent), gdy prognozowane minimum < próg przed ratą.

**Akceptacja:** backtest — prognoza z 1. dnia vs rzeczywiste saldo końca miesiąca (6 mies.).

## M9 — Hipoteka: nadpłacać czy oszczędzać

Wywiad 2026-10-12, szczegóły i etapy: [`PLAN_M9.md`](PLAN_M9.md), decyzja 28.

- Kredyt hipoteczny: parametry ręcznie (kapitał na dzień, WIBOR/WIRON + marża, raty równe/malejące,
  data końca), harmonogram liczony w add-onie; raty z księgi (seria `loan`) przesuwają stan.
- Jeden kalkulator scenariuszy: nadpłata (jednorazowa/miesięczna, oba warianty), zmiana WIBOR i marży,
  stopa oszczędności (z konta M10 albo wpisana, opcja „zawsze promocja”), horyzont; wynik = korzyść
  nadpłaty vs odsetki netto z oszczędności + tabela wariantów WIBOR × nadpłata.
- Podstawa rekomendacji agenta (M22). Majątek netto (salda, oszczędności, karta, migawki) → M26.

**Akceptacja:** harmonogram zgodny z parametrami (rata wyliczona = rata z banku ±1 zł); wynik
kalkulatora zgodny z ręcznym przeliczeniem jednego scenariusza.

## Backlog (świadomie odłożone)

Alerty w czasie rzeczywistym (duży wydatek, 80/100% limitu, wpływ) · Assist (czat w panelu → M12) ·
integracje z innymi add-onami (np. tankowania, rachunki za energię; tracker akcji → M11) · rozliczenia z osobami ·
„kto wydał” z CSV · HA to-do „do przejrzenia” · statystyki długoterminowe HA (import/backfill) ·
dashboard Lovelace · słowniki sprzedawców zagranicznych (decyzja M4b: grupy po kraju) · kolejne konta i banki · eksport (CSV/XLSX, Firefly III, Actual) · podział
transakcji (split) i tagi · paragony.

## Zasady przekrojowe

- **(2026-10-06, decyzja 24) Etap z nowymi danymi kończy się źródłem dla czatu** (M12 E3): nazwa,
  opis dla modelu i funkcja zwracająca wynik zbiorczy tym samym kodem co ekran — inaczej czat
  odpowie „nie umiem”.
- Zero danych osobowych w logach, repo i fixture'ach; do repo tylko dane syntetyczne albo
  zanonimizowane i przejrzane. Analizy prawdziwych danych wyłącznie lokalnie (raporty = liczby).
- CI zielone przed każdym checkpointem; wydania przez GitHub release; UI weryfikowane
  w Playwright.
- **Wizualizacje wyłącznie w panelu add-onu;** HA dostaje encje i kalendarz, nie dashboardy.
- DOCS: kopia zapasowa HA zawiera dane finansowe.
- Odnowienie zgody bankowej przed 2027-03-30.

---

## Historia decyzji technicznych

- **2026-10-01 — add-on, nie integracja.** Encje przez MQTT Discovery. Integracja
  SurfHost/ha-enablebanking tylko jako punkt odniesienia.
- **2026-10-01 — klucz EB generowany lokalnie** (`python -m budget.cli keygen`: RSA +
  self-signed cert); do Control Panelu EB trafia tylko certyfikat. Rejestracja przez
  `POST /api/applications` wymaga JWT sesji Control Panelu, więc w pełni z CLI się nie da.
- **2026-10-01 — M1b przed M2:** deduplikacja zależy od zachowania Millennium, którego Sandbox
  nie pokaże.
- **Dane prywatne w dev** (PEM, `.env`, zrzuty z banku, surowy CSV) — poza repo, w katalogu
  deweloperskim kontenera.
- **2026-10-01 — CSV potrzebny:** Millennium przez PSD2 oddaje tylko 90 dni (także zaraz po SCA
  i ze `strategy=longest`).
- **2026-10-01 — roadmapa M2–M9** na podstawie benchmarku i analizy danych (ten dokument).
- **2026-10-02 — obraz `python:3.12-alpine` (przypięty), stos async wg SPEC §3** (FastAPI +
  uvicorn + htmx + APScheduler + aiomqtt w jednej pętli); Supervisor buduje lokalnie. Sesja
  przenoszona z CLI plikiem przez panel (bez nowego SCA), historia przez ponowny import CSV.
  Szczegóły i odstępstwa: `PLAN_M3.md`.
- **2026-10-02 — wizualizacje w panelu, nie w HA;** M4 dzielone na M4a (silnik reguł +
  „Wydatki”) i M4b (kolejka). Kategoria liczona deterministycznie od zera, bez przycisku
  „zastosuj do historii” (podgląd przed zapisem reguły). Szczegóły: `PLAN_M4a.md`.
- **2026-10-02 — M4b przed checkpointami M3/M4a;** kolejka przyspiesza sesję reguł. Słowniki
  zagraniczne odrzucone na rzecz grup po kraju (mały udział w luce). Szczegóły: `PLAN_M4b.md`.

## Wnioski z Sandboxa (M1, 2026-10-01)

- Klucz z `cli keygen` przyjęty przez Control Panel (opcja „Generate outside the browser and
  import public certificate”). Pola Privacy/Terms URL muszą być prawdziwymi URL-ami.
- `GET /aspsps?country=PL`: „Bank Millennium” (beta) i „Mock ASPSP”; `maximum_consent_validity`
  = 180 d, brak `required_psu_headers`.
- Sandbox Millennium: konta i salda, **zero transakcji** — do testów transakcji Mock ASPSP
  z `tools/make_mock_dataset.py`.
- Mock ASPSP: wszystkie transakcje w jednej stronie, gubi `transaction_id` (zostaje
  `entry_reference`).
- `identification_hash` = hash z (IBAN, waluta) — ten sam IBAN dwa razy w sesji = ten sam hash.
- Błąd po stronie banku przychodzi jako `?state=…&error=server_error`; link autoryzacji
  utworzony przed wgraniem danych do Mock ASPSP kończył się `server_error`.
