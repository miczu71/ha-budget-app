# Changelog

## 0.70.1

**Kafelek „Karta” na górze Podsumowania** — zadłużenie jako minus (czerwone), nadwyżka na karcie (nadpłata)
jako plus (zielone); wcześniej odwrotnie.

## 0.70.0

**Wykres wydatków: poziom 3 wg sprzedawców** — `docs/PLAN_podsumowanie_merchants.md`.
- Po zejściu do podkategorii wycinki to sprzedawcy, a nie pojedyncze transakcje: zakupy w tym samym sklepie
  (np. kilka razy w tym samym markecie) są zsumowane, z dopiskiem „×N”, gdy było ich więcej niż jeden.
- Klik w sprzedawcę otwiera listę transakcji z filtrem nazwy i okresem widoku. Transakcje bez nazwy sprzedawcy
  trafiają do jednej pozycji „—” (link do całej podkategorii).
- Podzielona transakcja liczy się jako jedna; zwroty i waluty inne niż PLN są pominięte jak dotąd.

## 0.69.0

**Podsumowanie: zwijana prognoza i wykres wydatków z drill-down** — `docs/ROADMAP_podsumowanie.md` (E2–E4).
- Prognoza jest zwinięta: widać nagłówek i wynik, reszta (oraz „Tygodnie okresu”) po rozwinięciu. Przełącznik
  zadłużenia karty nie zwija jej ponownie.
- Wykres „Gdzie poszły pieniądze” ma miesiąc w tytule („w październiku”) i w bieżącym miesiącu przełącznik
  „Miesiąc / Od ostatniej wypłaty” (porównanie z tyloma samymi dniami wcześniej).
- Wykres schodzi w głąb bez opuszczania strony: kategoria → podkategorie → pojedyncze transakcje (top 6 +
  „Pozostałe”), z okruszkami, „← wstecz” i linkiem „Zobacz transakcje” z filtrem okresu widoku.

## 0.68.1

**Nadpłata karty kredytowej** — `docs/ROADMAP_podsumowanie.md` (E1).
- Zwrot ponad zadłużenie: bank trzyma saldo ITBD karty na zerze, a nadpłatę pokazuje tylko dostępne środki (ITAV)
  powyżej limitu. Uzgodnienie salda karty i prognoza czytają teraz nadpłatę jako ujemne zadłużenie, więc kontrola
  nie zgłasza fałszywej rozbieżności, a „Wolne środki” rosną o kwotę zwrotu.
- Bez ustawionego limitu karty nadpłaty nie da się odczytać — zachowanie jak dotąd (zadłużenie nie spada poniżej zera).

## 0.68.0

**M34: hero „Do wypłaty” z kwotą ponad zaplanowane i kafelek „Akcje” bez dopisków** — `docs/PLAN_M34_akcje_hero.md`.
- Hero „Do wypłaty” pokazuje pod limitem dziennym linię „Ponad zaplanowane do wypłaty”: stan konta + wpływy do wypłaty
  − płatności cykliczne − skarbonki (to samo „=” co w kafelku prognozy, bez bufora).
- Kafelek „Akcje” pokazuje samą kwotę wolnych akcji, bez daty zawiązania i dopisku „nieaktualne”.

## 0.67.0

**M33: okres od wypłaty i nieregularne w puli** — `docs/ROADMAP_M33.md`.
- Dzień wypłaty należy do nowego okresu: „Od wypłaty” (hero, tygodnie, sensory) liczy wydatki od dnia wpływu pensji
  do dnia przed następną, a porównanie z rokiem temu mierzy ten sam przedział, więc różnica r/r przestaje być zawyżona.
- Nieregularne (prezenty, ogród, serwis, ubezpieczenia…) zmniejszają „Zostało” faktycznie wydaną kwotą w miesiącu;
  zwrot netto nie powiększa puli. Hero pokazuje „elastyczne + nieregularne”, a przy braku w bieżącym miesiącu dopisek
  „Do uzupełnienia z oszczędności”. Tempo, pasek, podsumowania tygodnia i miesiąca oraz fakty czatu liczą z tego samego
  obciążenia puli; `sensor.budget_flex_remaining` ma atrybut `non_monthly`.
- Kafelek „Akcje” w Podsumowaniu pokazuje tylko wartość zawiązanych (bez kwoty niezawiązanych).

## 0.66.0

**M32: alerty bankowe per bank + M14 E2c** — `docs/PLAN_M32_M14_E2c.md`.
- Alerty „Zgoda nieaktywna”, „Zgoda wygasa” i „Nieudane synchronizacje” są osobne dla każdego banku i podają jego nazwę
  (dzwonek, powiadomienia HA); licznik porażek liczy się per bank (błąd, limit, wygasła sesja), ręczna synchronizacja
  jednego banku nie zeruje liczników pozostałych. Po aktualizacji stare alerty bez banku zamkną się, a aktywne przyjdą ponownie.
- Encje: `sensor.budget_consent_days_left` ma atrybut `banks` (dni, status, termin każdej zgody), `binary_sensor.budget_sync_problem`
  — `bank_failures`; problem świeci także przy nieaktywnej zgodzie dowolnego banku.
- Zapis konta (nazwa, „w budżecie”, rodzaj) jednym zapytaniem.
- Status: podglądy podsumowań (tydzień, miesiąc) liczone raz do pierwszego zapisu w bazie; kroki `s_weekly`/`s_monthly` w `Server-Timing`.

## 0.65.0

**M32 cd. 2: Velobank jako zwykłe konto promocyjne** — `docs/PLAN_M32_E10.md`.
- Przelewy własne: wewnętrzne (budżet↔budżet) i na oszczędności (po numerach kont) dostają kategorię „Przelewy na oszczędności”
  zamiast wpadać do wydatków; wpływ z własnych oszczędności nie liczy się do warunku promocji.
- Przeniesienia między wszystkimi kontami oszczędnościowymi są parowane bez „parkingu”; stopa oszczędności ich nie liczy.
- Rotacja liczy koniec promocji z edycji wpisanej przez użytkownika (z fallbackiem do terminu z oferty).
- Karta konta Velo w Oszczędnościach: promocja i licznik BLIK/karta zamiast formularza Profit (ten zostaje tylko dla Millennium).
- Sekcja „Promocja Nowe środki w VeloBanku”: stawki, termin, próg i sposoby z regulaminu, „Sprawdź teraz”, „Widziałem”;
  push i karta w dzwonku o nowej edycji (raz na edycję; pierwszy odczyt ustawia edycję bazową bez pusha).
- Saldo „Konto” w budżecie to suma wszystkich rachunków PLN w budżecie (etykieta „Rachunki”); rachunek bez migawki jest
  pomijany, a rachunek oznaczony jako poza budżetem nie daje już salda.

## 0.64.0

**M32 cd.: VeloBank w Budżecie** — `docs/PLAN_M32_E6.md`.
- BLIK Velobanku (`BLIK: /OPT/…`) liczy się jako zakup BLIK; licznik promocji i warunek karty Millennium liczą transakcje
  tylko kont właściwego banku.
- Oszczędności powiązane z kontem z księgi po numerze: saldo z banku (stan z dnia migawki), odsetki „do dopisania” osobno,
  poza sumą; Majątek liczy takie konto raz (historia Majątku nadal z szacunku ręcznego); rekomendacja rotacji bierze saldo
  Velo z powiązanych kont.
- Hero „Do wypłaty”: zamiast „Starczy · zapas” porównanie wydatków elastycznych od wypłaty z tym samym dniem okresu rok temu.
- Kafelek „Akcje” (wolne akcje pracownicze) obok Konto/Karta/Oszczędności; na telefonie układ 2×2.

## 0.63.0

**M32: rotacja środków między kontami promocyjnymi (Velobank + Millennium)** — `docs/PLAN_M32.md`.
- Wielobankowość: drugie połączenie PSD2 (Velobank) obok Millennium, osobna zgoda i stan synchronizacji per bank.
- Licznik transakcji bezgotówkowych (karta, BLIK) w miesiącu dla edycji promocji wpisanej ręcznie: „zrób jeszcze N”,
  dzwonek i powiadomienia 14/7/2 dni przed końcem oraz w ostatnim tygodniu miesiąca; bez przypomnień przed startem edycji.
- Monitor regulaminu Velobanku: codzienny odczyt, nowa edycja jako karta do wglądu, wstrzymanie przy nieczytelnym
  regulaminie lub błędzie odczytu (karta błędu po kilku dniach).
- Rekomendacja „dokąd przelać” po końcu promocji (kwota, konto, zysk netto, „najpóźniej do”); Budżet niczego nie przelewa.
  Saldo starsze niż 7 dni nie jest podstawą rekomendacji.
- Prognoza „do wypłaty” liczona bez Flexu — tylko znane i zaplanowane pozycje; usunięte kolumna Flex i atrybut `flex_rest`
  encji prognozy.
- Walidacja banku przy wpisywaniu edycji promocji (literówka nie daje już fałszywych przypomnień).

## 0.62.3

**Monitor promocji Profit czyta regulamin ed. 78** — bank zmienił zdanie „Okres promocyjny trwa przez 91 dni” na „trwa 91 dni”,
przez co parser nie znajdował długości okresu i panel pokazywał błąd odczytu regulaminu. Parser przyjmuje oba sformułowania.
Bez zmian w danych, ekranach i encjach.

## 0.62.2

**Czat: pytania o nadwyżkę i kredyt** (M12 E3d, `docs/PLAN_M12_E3d.md`) — pytanie „ile odłożyć z nadwyżki zamiast nadpłacać kredyt”
w jednej próbie z trzech trafiało w Skarbonki zamiast w Inwestycje. Prompt planu rozróżnia teraz stan (Skarbonki: ile jest na kontach
i w skarbonkach) od decyzji (Inwestycje: ile i gdzie odłożyć, nadpłata kredytu) i podaje przykład pary Kredyt + Inwestycje.
Bez zmian w danych, ekranach i encjach.

## 0.62.1

**Trafniejszy dobór źródeł w czacie** (M12 E3d, `docs/PLAN_M12_E3d.md`) — pytanie łączące kredyt i inwestycje („odłożyć z nadwyżki
zamiast nadpłacać”) trafiało w Skarbonki zamiast w Inwestycje, bo opisy obu źródeł zachodziły na „odłożyć”. Skarbonki opisują teraz
stan oszczędności, Inwestycje — decyzje (ile i gdzie odłożyć, nadpłata kredytu). Bez zmian w danych, ekranach i encjach.

## 0.62.0

**Przepływ pieniędzy** (M19, `docs/PLAN_M19.md`) — na ekranie Wydatki nowa sekcja z wykresem Sankey: wpływy → grupy budżetu
(stałe, elastyczne, nieregularne, oszczędności) → kategorie główne, z węzłami „Bez kategorii”, „Nadwyżka” i „Z oszczędności /
deficyt”. Przełącznik Miesiąc / Rok (rok kalendarzowy wybranego miesiąca, strzałki miesięcy zachowują wybór). Dotknięcie
kategorii otwiera jej transakcje, „Bez kategorii” — kolejkę przeglądu. Sumy z tego samego źródła co reszta ekranu.

## 0.61.4

**Szybszy dzwonek i Inwestycje** (M14, `docs/PLAN_M14_E2.md`) — dzwonek na każdej stronie liczył przypisanie transakcji do serii
od nowa (zmiany serii, rata kredytu); teraz korzysta z pamięci `Snapshot`. Uzasadnienie rekomendacji na `/invest` liczy majątek
netto na `Snapshot` serwisu (wcześniej ~390 ms na świeżym). Bez zmian wyglądu i danych.

## 0.61.3

**Szybsza strona główna, Majątek i Status** (M14, `docs/PLAN_M14_E2.md`) — pomiar na produkcji wskazał obliczenie majątku netto
(~430 ms) jako główny koszt: skarbonki liczyły się na świeżym `Snapshot`, więc pamięć serii nie działała. Teraz używają
`Snapshot` serwisu. `Server-Timing` ma też kroki wewnątrz majątku (`n_*`). Bez zmian wyglądu i danych.

## 0.61.2

**Szybsze Inwestycje i Majątek** (M14, `docs/PLAN_M14_E2.md`) — rekomendacja agenta inwestycyjnego liczy się raz na stan bazy
(wcześniej przy każdym wejściu na `/invest` i `/networth`). Nagłówek `Server-Timing` ma teraz kroki strony głównej (`h_*`),
Statusu (`s_*`) i dzwonka (`p_*`), żeby wskazać resztę wolnych miejsc. Bez zmian wyglądu i danych.

## 0.61.1

**Pomiar wolnych ekranów** (M14, `docs/PLAN_M14_E2.md`) — każda odpowiedź panelu niesie nagłówek `Server-Timing`
(`total`, `inbox`, `template`, w ms), żeby na produkcji wskazać, co spowalnia Podsumowanie i Status. Bez zmian logiki i danych.

## 0.61.0

**Akcje Nokia w majątku netto** (M11, `docs/PLAN_M11.md`) — dwa nowe składniki grupy Inwestycje: „Akcje Nokia”
(wartość rynkowa) i „Akcje Nokia — niezawiązane” (niezawiązane akcje po bieżącej cenie, z podpisem „vesting DD.MM.RRRR: N akcji”).
Dane czyta add-on z encji integracji trackera akcji (opcja `stocks_entity_prefix`, puste = wyłączone).

- Historia: przybliżone migawki z końców 07–09.2026 dostają akcje ze statystyk HA (jednorazowo, idempotentnie);
  wcześniej statystyk nie ma — wykres informuje „brak danych o akcjach”.
- Zmiana m/m i r/r nie liczy akcji jako skoku, gdy migawka odniesienia powstała przed M11.
- Dzwonek „Vesting akcji DD.MM” 14 dni przed najbliższym vestingiem (ile akcji i ≈ wartość).
- Wartość akcji starsza niż 3 dni jest oznaczana jako nieaktualna; wyłączenie opcji usuwa składniki z majątku.
- Nowa zależność: `websockets` (klient statystyk HA).

## 0.60.1

Poprawka M26: kredyt liczył się w historii majątku dopiero od daty wpisanego kapitału, więc zmiana m/m i r/r
pokazywała fałszywy skok o wartość kredytu. Teraz przed tą datą zostaje kapitał z dnia wpisu (punkt przybliżony).
Migracja 028 kasuje tylko odtworzone punkty historii; add-on odtworzy je od nowa przy najbliższym odświeżeniu.

## 0.60.0

**Majątek netto** (M26, `docs/PLAN_M26.md`) — jeden obraz finansów: konta (EUR po kursie średnim NBP), oszczędności,
skarbonki i inwestycje minus kredyty i zadłużenie karty. Tylko majątek finansowy, bez nieruchomości i aut.

- Nowa zakładka „Majątek”: bilans aktywa/pasywa, wykres miesięczny (odtworzona historia oznaczona jako przybliżona),
  zmiana m/m i r/r, płynność (miesiące wydatków), LTV i lista wartości do aktualizacji (starszych niż 90 dni).
  Kafel „Majątek netto” na Podsumowaniu.
- Historia: migawka dzienna i jednorazowe odtworzenie końców miesięcy od najstarszej transakcji.
- Aktywa z Inwestycji: pole „Wartość z dnia” i „To samo co oszczędność” (bez liczenia podwójnie).
- Parking oszczędności: konto M10 oznaczone „parking dla …”; przelewy Profit ↔ parking to „przeniesienie”,
  nie wypłata ani wpłata.
- `sensor.budget_net_worth` (atrybuty: assets, liabilities, liquidity_months, ltv, change_mom, change_yoy, stale).
- Podsumowanie miesięczne: linijka majątku z m/m i przypomnienie „Zaktualizuj wartość: …”.
- Czat: źródło „majatek”; do modelu idą tylko sumy i wskaźniki, bez nazw pozycji.
- Agent inwestycyjny: płynność i LTV w uzasadnieniu rekomendacji (jednorazowe odświeżenie tekstu po aktualizacji).
- Migracje bazy 026 i 027 (addytywne): `parking_for`, `savings_id`, `valued_at`, `networth_snapshot`, kursy NBP.

## 0.59.0

**Śledzenie promocji bankowych** (M22 E5, dawne M17, `docs/PLAN_M22.md`) — razem z 0.58.1 (nagłówek `User-Agent`
w zapytaniach do routera LLM, bez zmian w działaniu).

- „Inwestycje” → „Promocje w toku”: przy potwierdzonej ofercie przycisk „Skorzystaj” zapisuje okres promocji
  (długość z oferty, domyślnie 3 mies.). Model wstępnie podpowiada premię i warunki z opisu oferty — to tylko
  propozycje do zatwierdzenia lub poprawienia; gdy AI jest wyłączone albo zawiedzie, dodajesz warunki ręcznie.
- Warunki: liczba płatności kartą, suma wpływów, saldo na dzień i inny krok. Płatności i wpływy liczą się
  same z księgi tylko dla konta Millennium (wpływy bez przelewów własnych); reszta warunków i inne banki — ręczne
  „Zrobione”. Warunki liczone w okresie całej promocji.
- Przypomnienia: dzwonek (7 dni przed końcem, po spełnieniu warunków „odbierz premię”, po terminie „oznacz wynik”)
  i push 5 oraz 1 dzień przed końcem, gdy warunki niespełnione.
- Rejestr premii: należne i odebrane; odebraną premię dopisujesz do aktywów albo tylko do wpływów. Odebranej
  promocji nie da się już cofnąć.
- Migracja bazy 025 (addytywna): tabele `promo_track` i `promo_condition`.

## 0.58.1

- Zapytania do routera LLM niosą nagłówek `User-Agent: ha-budget/<wersja>`, dzięki czemu panel LLM (:3004) pokazuje, który add-on używa którego modelu. Bez zmian w działaniu.

## 0.58.0

**Agent inwestycyjny: oferty z blogów, dzwonek, push po wypłacie, czat** (M22 E3 + E4, `docs/PLAN_M22.md`).

- Blogi: raz na dobę add-on czyta kanały RSS pięciu blogów o oszczędzaniu, a model wyciąga z nowych wpisów
  oferty lokat i kont (bank, stawka, limit, okres, warunki). Oferta czeka w „Do sprawdzenia” — możesz ją poprawić
  i potwierdzić albo odrzucić; do porównania wchodzi dopiero po potwierdzeniu. Status → „Oferty z blogów —
  trafność” liczy, ile potwierdzono bez poprawek. Opcja add-onu `invest_daily_calls` (domyślnie 10) ogranicza
  liczbę wywołań modelu na dobę; do modelu idzie tylko tytuł i streszczenie wpisu.
- Dzwonek: „Lepsza oferta” (potwierdzona lokata albo konto daje rocznie co najmniej tyle więcej niż Twoje konto —
  próg w ustawieniach agenta, domyślnie 200 zł) i „termin” (lokata kończy się albo obligacje do wykupu w ciągu
  14 dni).
- Push po wypłacie (przez `summary_notify_service`): ile odłożyć i gdzie, albo „nadwyżki brak”.
- Czat: nowe źródło „Inwestycje” (koszyki, rekomendacja, najlepsze opcje); do modelu idą kwoty i rodzaje opcji,
  bez nazw banków, kont i kredytów.
- Ekran „Inwestycje”: 2–3 zdania uzasadnienia rekomendacji od modelu (liczy add-on, model tylko opisuje wynik).
- Migracja bazy 024 (addytywna): pola `extracted` i `verdict` w ofertach.

## 0.57.0

**Agent inwestycyjny: oferty z sieci** (M22 E2, `docs/PLAN_M22.md`).

- „Inwestycje”: raz na dobę add-on pobiera oprocentowanie obligacji skarbowych (EDO, COI, TOS, DOR, ROR — stawka
  pierwszego roku i marża ze strony serii) oraz najlepsze oferty z rankingu lokat i kont oszczędnościowych.
  Wszystko wchodzi do porównania netto obok nadpłaty kredytu i konta oszczędnościowego.
- Ranking nie podaje banku jako osobnego pola — add-on rozpoznaje go po nazwie i adresie oferty. Oferty, których
  banku nie rozpoznał, czekają w sekcji „Do sprawdzenia” (popraw nazwę i potwierdź albo odrzuć) i nie liczą się
  w porównaniu. Każda oferta z rankingu ma link do opisu.
- „Moje banki”: oferty „tylko dla nowych klientów” z banków z tej listy są pomijane w porównaniu.
- Błąd odczytu któregokolwiek źródła nie blokuje pozostałych; po 3 dniach pojawia się karta w dzwonku.
- Migracji bazy nie ma (tabele z 0.56.x dodane w E1).

## 0.56.2

- Czat: pytania łączące dwa ekrany stanu (np. płatności kartą i kwota do wypłaty) nie kończą się już tak często
  odpowiedzią „nie umiem” — model dostał wprost zasadę i przykład użycia drugiego źródła.

## 0.56.1

- Prognoza roczna: do mediany Flex i średniej nie wchodzi już pierwszy miesiąc księgi, jeśli księga zaczęła się po
  7. dniu (to tylko końcówka miesiąca i zaniżała bazę o kilka procent). Księga krótsza niż miesiąc nadal używa
  tego, co ma.
- Status → „Prognoza roczna — pomiar”: pokazuje bazę Flex, początek historii oraz składniki prognozy i faktu
  (Flex, sezon) w każdym miesiącu; wcześniejsze pomiary pozostają czytelne.
- Czat: gdy fakty mówią, że czegoś nie starczy („Starczy do wypłaty: nie”), zdanie odpowiedzi ma to powiedzieć wprost.

## 0.56.0

**Czat: pytania z dwóch źródeł naraz** (M12 E3c, `docs/PLAN_M12_E3c.md`).

- „Zapytaj”: pytanie może łączyć dwa ekrany stanu (np. płatności kartą i kwota do spłaty, albo limit do wypłaty
  i skarbonki). Add-on liczy oba źródła lokalnie jak na ekranach, model opisuje je jednym zdaniem; w odpowiedzi tabela
  i link do ekranu dla każdego źródła. Źródło bez danych pokazuje notatkę zamiast pustej tabeli.
- Bez zmian w bazie i w encjach.

## 0.55.1

- Strona główna: kafelki sald nad głównym kafelkiem to teraz mały pasek (ok. 42 px zamiast 110–150 px): kwoty w pełnych
  złotych, lista skarbonek w podpowiedzi po najechaniu (na telefonie kafelek Oszczędności przechodzi do skarbonek).

## 0.55.0

**Poprawki panelu** (M31, `docs/PLAN_M31.md`).

- „Do decyzji”: przy kartach (poza błędami zgody i synchronizacji, które można tylko ukryć) przycisk „Usuń” kasuje kartę
  na stałe; zmiana tytułu to nowa karta.
- Strona główna: kafelki sald nad głównym kafelkiem — „Konto”, „Karta” (zadłużenie) i „Oszczędności” (konta
  oszczędnościowe razem ze skarbonkami; po najechaniu lub dotknięciu lista skarbonek).
- Prognoza: tydzień okresu kończy się w dniu wypłaty (dzień wypłaty należy do starego okresu).
- Skarbonki: zalecane odłożenie w pełnych złotych (zaokrąglane w górę, nigdy więcej niż brakuje).

## 0.54.0

**Prognoza roczna bez wydatków jednorazowych** (M30, `docs/PLAN_M30.md`).

- Kategorie: przy każdej podkategorii przełącznik „Pomiń w prognozie rocznej (wydatki jednorazowe)”. Oflagowana
  kategoria wypada z mediany Flex, korekty „nieregularne” i wierszy „roczne bez serii” na ekranie „Rok” oraz z pomiaru
  na Statusie; nie zmienia grupy budżetu, więc „Budżet” i „Wydatki” liczą jak dotąd.
- Ekran „Rok”: linijka „Pominięte w prognozie” z nazwami kategorii i średnią miesięczną z ostatnich 12 miesięcy oraz
  link do Kategorii. Pominięte kategorie nie trafiają też na listę „Płatności roczne bez serii”.
- Duży planowany wydatek (remont, wyjazd) dodaje się teraz jako zdarzenie roku, zamiast kopiować go z poprzedniego roku.

## 0.53.0

**Prognoza roczna** (M18, `docs/PLAN_M18.md`).

- Nowy ekran „Rok” (zakładka po „Kredyt”): saldo miesiąc po miesiącu do końca roku (od 1.11 do końca następnego),
  pierwszy deficyt, „ile mogę wydać miesięcznie”, wykres z linią scenariusza, ustawienia Flex i celu salda oraz lista
  rocznych płatności bez serii.
- Zdarzenia roku: zmiana kwoty serii, nowa seria i kwota jednorazowa — w trybie „Plan” (zmienia prognozę bazową,
  np. niższa wypłata po progu podatkowym) albo „Scenariusz” (druga linia „co jeśli”). Propozycje z historii (próg
  podatkowy, premia) czekają na zatwierdzenie i nie wracają po odrzuceniu.
- Strona główna: kafelek „Rok” (koniec horyzontu, pierwszy deficyt). Encja `sensor.budget_year_end` z atrybutami
  `horizon_end`, `first_deficit`, `max_flex`, `scenario_end`, `buffer`.
- Czat: nowe źródło „Rok” (te same liczby co ekran; nazwy zdarzeń nie trafiają do modelu).
- Status: karta „Prognoza roczna — pomiar” (błąd prognozy wydatków spoza serii wobec faktu).

## 0.52.3

- Transakcje: odznaka serii z dłuższą nazwą zawija się w kolumnie Szczegóły — koniec przewijania poziomego tabeli.

## 0.52.1

- Transakcje: kolumna „Szczegóły” zawija odznaki i wybór skarbonki zamiast wychodzić poza kartę na desktopie.
- Status: krótki opis pod nagłówkiem „Uzgodnienie salda” (co jest sprawdzane i co znaczą OK / W DRODZE / ROZBIEŻNOŚĆ).

## 0.52.0

- Wycofany ekran „Koszty banku” z 0.51.0 (razem z kursami NBP i źródłem czatu). Kwoty płatności w walutach
  znów pochodzą z API banku — import CSV karty nie zmienia już kwot ani nie kasuje podziału transakcji.
  Po najbliższej synchronizacji kwoty wrócą do wartości z API.

## 0.51.0

**Koszty banku** (M23, `docs/PLAN_M23.md`).

- Nowy ekran „Koszty banku” (menu ⚙, link w Wydatkach): ile bank wziął w roku poza ceną zakupów —
  przewalutowanie płatności kartą względem kursu średniego NBP (tabela A, dzień roboczy przed zakupem)
  i opłaty/prowizje; podział na miesiące, lista płatności w walutach (koszt, %, kurs NBP) i opłat.
- Kursy NBP pobierane z api.nbp.pl raz dziennie i po imporcie CSV, tylko dla dni płatności w walutach.
- **Kwota płatności w walucie obcej pochodzi z CSV karty:** API pokazuje ją bez 2% prowizji banku za
  przewalutowanie, więc wydatki kartą były zaniżone. Po imporcie CSV karty kwota w księdze jest
  faktycznym obciążeniem (podział takiej transakcji zrobiony przed importem trzeba powtórzyć).
- Kwoty w walucie są tylko w eksporcie CSV karty — importuj go raz w miesiącu.
- Czat: nowe źródło „Koszty banku” (rok, miesiące).

## 0.50.2

- Głęboki link `/app/<slug>/inbox` (np. chip „do decyzji” na dashboardzie HA) otwiera ekran „Do decyzji”
  zamiast samej strony głównej panelu.

## 0.50.1

- Transakcje: link „paragon Lidl” w aplikacji HA na telefonie otwierał przeglądarkę zamiast panelu
  Lidla. Teraz przełącza panel routerem HA (bez przeładowania okna); poza HA zostaje zwykły link.

## 0.50.0

**Paragony Lidl Plus** (M29 E4–E5, `docs/PLAN_M29.md`; wymaga add-onu Lidl Plus ≥ 0.19.1).

- Po każdej synchronizacji Budżet czyta `/share/lidl/receipts.json` (paragony z podziałem na kategorie
  produktów) i łączy paragon z płatnością w Lidlu: ta sama kwota co do grosza, data ±3 dni, jeden
  kandydat po obu stronach. Paragony gotówkowe pomija.
- Połączony zakup dzieli się według paragonu (np. Spożywcze + Drogeria) — raz, przy połączeniu; ręcznej
  kategorii i ręcznego podziału nie rusza, a późniejsza zmiana użytkownika wygrywa.
- Transakcje: link „paragon Lidl” otwiera paragon w panelu Lidla; „to nie ten paragon” odłącza go
  (i nie łączy ponownie); gdy paragon pasuje do kilku płatności — wybór w edytorze kategorii.
- Kategorie: karta „Paragony Lidl” — do której podkategorii trafia każda kategoria produktów.
- Migracja `019_lidl.sql` (nowe tabele `txn_lidl`, `txn_lidl_reject`, addytywna); add-on dostaje dostęp
  do `/share` tylko do odczytu.

## 0.49.0

**Podział transakcji na podkategorie** (M29 E1–E3, `docs/PLAN_M29.md`).

- Transakcje: w karcie kategorii „Podziel na kategorie” — wiersze podkategoria + kwota, „Dodaj wiersz”,
  licznik „Zostało do przydzielenia”; „Zapisz podział” dopiero przy reszcie 0,00 zł. Pierwszy wiersz sam
  bierze resztę. Podzieloną transakcję otwiera się od razu w podziale („Usuń podział”); na liście znacznik
  „N kategorie” i części w podpisie.
- Wyliczenia (Wydatki, Budżet, Podsumowanie, oszczędności, czat) liczą każdą część w jej podkategorii;
  liczba transakcji liczy podzieloną raz. Filtr kategorii w Transakcjach trafia też w części.
- Ręczna kategoria zwykłym wyborem zastępuje podział; podział nie uczy pamięci sprzedawcy ani podpowiedzi AI.
  Zmiana kwoty przez bank zdejmuje podział; CSV zastąpiony przez API przenosi podział na następcę.
- Migracja `018_split.sql` (nowa tabela `txn_split`, addytywna).

## 0.48.0

**Kredyt bez zbędnego pola i edytowalne zakładki** (M28, `docs/PLAN_M28.md`).

- Kredyt: „Seria rat w księdze” przeniesiona do formularza „Zmień”; na karcie, gdy serii brak, jedna
  linia z odnośnikiem. Pole kalkulatora nazwane „Oprocentowanie oszczędności (% rocznie)” z podpisem,
  z czym porównujemy nadpłatę i co znaczy puste pole.
- Zakładki u góry: menu ⚙ → „Zakładki” — kolejność strzałkami i ukrywanie; „Podsumowanie” zawsze
  pierwsze. Układ wspólny dla urządzeń; ukryta zakładka nadal działa pod swoim adresem.
- Podsumowanie: „ponad plan” w osobnej linii — nie poszerza karty prognozy na 390 px.
  Bez migracji schematu.

## 0.47.0

**Kalkulator kredytu i tygodnie okresu czytelniejsze** (M27, `docs/PLAN_M9_M21_poprawki.md`).

- Kredyt: tabela „zmiana WIBOR przy tej nadpłacie” jest zwinięta i liczy się dopiero po rozwinięciu
  (nie przy każdym ruchu suwaka); pięć wierszy (−2…+2 kroki), krok do wyboru: 1, 0,5 lub 0,25 p.p.
- Podsumowanie, „Tygodnie okresu”: zdanie wyjaśnia, czym mierzone są minione tygodnie (plan z dnia
  wypłaty) i kolejne (dzisiejszy limit dzienny, więc przekroczenie obniża następne tygodnie). Przyszłe
  tygodnie mają pusty pasek planu, minione przekroczone „+X zł ponad plan”, a skrócony pierwszy
  i ostatni tydzień okresu etykietę „N dni od/do wypłaty”. Bez migracji schematu.

## 0.46.0

**Czat „Zapytaj” zna stan panelu, nie tylko transakcje** (M12 E3b, `docs/PLAN_M12_E3b.md`).

- Nowy rejestr źródeł danych: Do wypłaty, Karta, Budżet, Cykliczne, Skarbonki (konta oszczędnościowe
  i skarbonki) oraz Kredyt. Pytania typu „czy starczy do wypłaty?”, „ile zostało w budżecie we
  wrześniu?”, „ile spłacić na karcie i do kiedy?”, „jaką mam ratę kredytu?” liczy ten sam kod co ekran;
  pod odpowiedzią tabela faktów, „Jak policzono” i link do ekranu.
- Karta, Budżet i Cykliczne przyjmują miesiąc z pytania; reszta pokazuje stan na dziś.
- Do modelu idą kwoty, ale nie nazwy: osoby, serie, konta, skarbonki i kredyty widzi jako `[Osoba 1]`,
  `[Seria 1]`, `[Konto 1]`, `[Skarbonka 1]`, `[Kredyt 1]`; nazwy wracają lokalnie. Brak danych źródła
  (np. brak salda) daje odpowiedź bez drugiego wywołania modelu. Bez migracji schematu.

## 0.45.0

**Kredyt: śledzenie WIBOR 3M i rata po zmianie oprocentowania** (M9 E4, `docs/PLAN_M9_wibor.md`).

- Add-on raz dziennie czyta notowania WIBOR 3M (bankier.pl). Przy kredycie z wpisaną „Ostatnią zmianą
  oprocentowania” (bank zmienia je co 3 miesiące, np. 9.03/9.06/9.09/9.12) ekran Kredyt pokazuje:
  „od 9.12 rata ≈ X zł (wyższa o Y)”. Do dnia ustalenia stawki to prognoza przy ostatnim WIBOR, potem
  stawka ostateczna. Dzień ustalenia = 3 dni robocze przed zmianą (skalibrowane na zmianie z 9.09).
- Dzień po zmianie (o 7:00, przez usługę podsumowań) przychodzi powiadomienie z nową stopą i ratą; karta
  w dzwonku „nowe oprocentowanie” zostaje, dopóki nie zaktualizujesz kredytu. Gdy WIBOR się nie zmienił,
  nic nie przychodzi.
- Atrybuty `sensor.budget_loan_principal`: `wibor`, `wibor_date`, `next_reset`, `forecast_installment`.
- Karta w dzwonku, gdy odczyt WIBOR nie działa od 3 dni. Migracja 017 (addytywna).

## 0.44.1

**Kredyt: harmonogram zgodny z bankiem** (`docs/PLAN_M9_kalibracja.md`).

- Odsetki liczone jak w banku, metodą 30/360: pełny miesiąc to saldo × stopa / 12 (wcześniej dni/365, przez co
  odsetki skakały z miesiąca na miesiąc, a suma do końca wychodziła o ok. 1 100 zł za duża).
- Ostatnia rata wypada w dniu końca kredytu (odsetki za niepełny okres), nie w dniu raty.
- Nowe, opcjonalne pole „Rata wg banku” (raty równe): bank przelicza ratę po zmianie WIBOR po swojemu,
  więc wzór annuitetowy bywa o kilkanaście groszy inny. Puste = rata ze wzoru. Migracja 016 (addytywna).

## 0.44.0

**„Do decyzji”: ręczne ukrywanie kart** (`docs/PLAN_inbox_dismiss.md`).

- Przy każdej karcie (strona dzwonka i kafelek na stronie głównej) jest przycisk ✕. Ukryta karta znika
  też z licznika dzwonka i z encji `sensor.budget_inbox`.
- Ukrywana jest para „rodzaj + tytuł”: karta wraca, gdy zmieni się jej tytuł (np. nowa edycja promocji
  albo inna kwota spłaty karty).
- Na stronie dzwonka przycisk „Przywróć ukryte (N)” cofa wszystkie ukrycia.

## 0.43.0

**Kredyt hipoteczny: ekran „Kredyt” i kalkulator „nadpłacić czy oszczędzać”** (M9, `docs/PLAN_M9.md`, decyzja 28).

- Nowa zakładka „Kredyt”: kredyt wpisany ręcznie (kapitał na dzień, WIBOR/WIRON + marża, raty równe albo
  malejące, dzień raty, data ostatniej raty). Panel liczy harmonogram, kapitał na dziś, najbliższą ratę,
  datę spłaty i odsetki do końca. Nowy kapitał albo nowa stopa to korekta względem banku.
- Powiązanie z serią rat w księdze (Cykliczne). Gdy ostatnia rata w księdze różni się od harmonogramu
  o więcej niż 1%, dzwonek podpowiada „zmienił się WIBOR lub marża? wpisz nowy kapitał i stopę”.
- Encja `sensor.budget_loan_principal` (kapitał wg harmonogramu; atrybuty: stopa, rata, raty do spłaty,
  data spłaty, odsetki do końca). Kolejne kredyty dostają encje z numerem.
- Kalkulator scenariuszy: nadpłata dziś i co miesiąc (krótszy okres albo niższa rata), zmiana WIBOR
  suwakiem i nowa marża od wybranej daty, stopa oszczędności z konta (promocja Profit do jej końca) albo
  wpisana, opcja „zawsze załapię promocję”, horyzont 12 miesięcy / 5 lat / do końca kredytu. Wynik:
  która opcja wychodzi lepiej i o ile, plus tabela „zmiana WIBOR × bez nadpłaty / krótszy okres / niższa
  rata”. Odsetki z oszczędności liczone netto (Belka 19%).
- Migracja 015 (tabela `loan`) jest addytywna; starsza wersja add-onu ją ignoruje.
- Konto Profit: komunikaty mówią, że zerować trzeba tylko KOP, a saldo rachunków PLN to próg łączny.

## 0.42.0

**Konto Profit: monitor edycji promocji, szczegóły miesięcy, aktywacja promocji** (M10 E5–E7, `docs/PLAN_M10_E7.md`, decyzja 27).

- Monitor promocji „Nowe środki na Koncie Oszczędnościowym Profit” (Bank Millennium): raz dziennie
  (i po kliknięciu „Sprawdź teraz”) add-on czyta regulamin (publiczny PDF) i zapisuje ostatnią
  edycję: dzień badania sald, termin przystępowania, długość okresu promocyjnego. Działa tylko, gdy
  jest konto oszczędnościowe. Sekcja „Promocja Profit w Millennium” na ekranie Oszczędności.
- Prognoza okna badania sald następnej edycji: od końca przystępowania obecnej minus 6 dni do tego
  końca (bank podaje datę badania dopiero po fakcie). Dzwonek i push „wyzeruj Millennium”: 3, 1
  i 0 dni przed początkiem okna; push o nowej edycji z potwierdzoną datą (z uwagą, gdy badanie
  wypadło wcześniej niż zakładała prognoza); karta, gdy regulaminu nie da się odczytać przez 3 dni.
- „Stopa oszczędności”: każdy miesiąc rozwija się do przelewów (data, wpłata/wypłata, kwota)
  pogrupowanych per konto oszczędnościowe.
- Karta konta: „Aktywuj promocję „Nowe środki” (Profit)” — nowe środki (do 200 000 zł), data
  przystąpienia, stawka łączna i bazowa; odsetki liczą się przez 91 dni od przystąpienia (z
  regulaminu), potem po stawce bazowej. Zakłada spełniony warunek 5 płatności miesięcznie.
- Nowa zależność: `pypdf` (czysty Python). Bez migracji bazy.

## 0.40.0

**Konto oszczędnościowe, odsetki i stopa oszczędności** (M10 E2–E4, `docs/PLAN_M10_E2.md`, decyzja 26).

- Ekran „Skarbonki” zmienia nazwę na „Oszczędności i skarbonki”. Nowa sekcja „Konto oszczędnościowe”
  (konto spoza Enable Banking): saldo = wpisane saldo na dzień + przelewy na konto i z konta
  (po numerze, jak skarbonki; numer tylko w bazie, w panelu maskowany). Przelewy na konto nie liczą się
  do puli Flex. Gdy saldo różni się od banku, wpisz nowe na nowy dzień.
- Odsetki (szacunek): stopa bazowa i opcjonalna promocja (stopa, limit kwoty, data końca),
  kapitalizacja miesięczna, podatek 19%. W dzwonku i jako powiadomienie push przypomnienie
  14 i 3 dni przed końcem promocji.
- Stopa oszczędności = wpłaty netto na konto oszczędnościowe / wpływy miesiąca (skarbonki się nie
  liczą; wpływy bez przelewów z kont oszczędnościowych i skarbonek). Wykres 12 miesięcy na ekranie
  i nowy kafelek „Oszczędności” na Podsumowaniu (można go ukryć w układzie).
- Cykliczne: na liście aktywnych serii widać, która seria ma skarbonkę, z linkiem do niej.
- Migracja 014 jest addytywna (starsza wersja ją ignoruje).

## 0.39.1

- Skarbonki: formularz nie rozpycha ekranu na telefonie przy długich nazwach serii w liście
  „Seria (opcjonalnie)”.

## 0.39.0

**Skarbonki i tygodnie w „Do wypłaty”** (M10 E1, M21 E4–E5, `docs/PLAN_M10_E1.md`, `docs/PLAN_M21.md`).

- Nowy ekran „Skarbonki”: skarbonka = nazwa, numer konta-celu w banku, cel i termin (albo seria
  cykliczna, np. roczna subskrypcja — wtedy cel i termin z serii). Saldo liczy się z przelewów na
  konto-cel i z niego; panel podpowiada, ile przelać w bieżącym okresie wypłaty. Numer konta jest
  zapisany tylko w bazie, w panelu widać go zamaskowany.
- Prognoza „Do wypłaty”: nieprzelane odłożenie do skarbonek schodzi dziś („Do skarbonek”), więc
  limit dzienny je uwzględnia; wydatek serii pokryty saldem skarbonki liczy się jako 0. Dzwonek
  przypomina o przelewie na mniej niż 5 dni przed wypłatą.
- Przelewy na konta-cele i wydatki przypisane do skarbonki (pole „Skarbonka” przy wydatku
  w Transakcjach) nie liczą się do puli Flex.
- „Do wypłaty”: bieżący tydzień (pon–nd) w hero — wydane z limitu i ile zostało; w kafelku prognozy
  paski wszystkich tygodni okresu (minione wobec limitu z początku okresu, bieżący i przyszłe
  z dzisiejszego limitu dziennego).
- Nowy kafelek „Skarbonki” na Podsumowaniu (do ukrycia w układzie).
- Migracja bazy 013 (addytywna).

## 0.38.1

**Poprawka prognozy: wpływy w dniu wypłaty.**

- Inne wpływy serii, które przychodzą tego samego dnia co wypłata (np. świadczenie), liczą się do
  prognozy, tak jak wydatki tego dnia; sama wypłata dalej jest po najniższym punkcie. Wcześniej
  przesunięcie daty wypłaty na dzień takiego wpływu gubiło go i pogarszało wynik zamiast poprawiać.

## 0.38.0

**Okres od wypłaty** (M21 E3, `docs/PLAN_M21.md`).

- Karta „Do wypłaty”: pasek, ile minęło okresu od ostatniej wypłaty do następnej, i „Od wypłaty dd.mm
  wydane na elastyczne …” (ta sama definicja co „wydane” w budżecie miesiąca).
- `sensor.budget_forecast_at_payday`: nowe atrybuty `period_start`, `spent_since_payday`, `safe_per_day`,
  `payday_manual`.
- Przynależność transakcji do serii liczy się raz na stan bazy (wspólna dla prognozy, puli i terminów).

## 0.37.0

**Podsumowanie liczy do wypłaty** (M21 E2, `docs/PLAN_M21.md`).

- Na górze Podsumowania (bieżący miesiąc, gdy są salda) karta „Do wypłaty”: ile dziennie możesz wydawać
  do dnia wypłaty, żeby saldo nie spadło poniżej bufora, i czy przy obecnym tempie starczy (zapas albo
  brak, najniższy dzień). Link prowadzi do prognozy dzień po dniu i pola daty wypłaty.
- „Zostało na elastyczne” (miesiąc kalendarzowy) jest teraz kafelkiem „Zostało w miesiącu” zaraz za
  prognozą; można go przesunąć albo ukryć w „Edytuj układ”. Bez sald i w minionych miesiącach na górze
  zostaje karta miesięczna jak dotąd.
- Kafelek prognozy nazywa się „Prognoza do wypłaty” i zawiera rozbicie, wykres, listę zdarzeń i datę.
- Nowe kafelki w kolejnych wersjach trafiają za swojego domyślnego poprzednika, nie na koniec układu.

## 0.36.0

**Ręczna data wypłaty** (M21 E1, `docs/PLAN_M21.md`).

- Na karcie „Do wypłaty” jest pole „Data wypłaty w tym miesiącu”: gdy znasz faktyczną datę (np. dzień
  wcześniej niż zwykle), wpisz ją, a prognoza, „Co jeszcze zejdzie”, kalendarz ICS i encje HA liczą do
  niej. Nagłówek pokazuje „(data ręczna)”, a „wróć do dnia z serii” przywraca stały dzień.
- Data obowiązuje tylko w miesiącu terminu; kolejne miesiące wracają do dnia z serii.

## 0.35.2

**Poprawka wyglądu: plakietka w wierszu listy.**

- Plakietka stanu (np. „spóźniona”) w tytule wiersza listy, m.in. w „Do wypłaty”, nie rozciąga się już
  na całą szerokość wiersza, tylko ma szerokość treści (reguła `.row-title > .badge` w `app.css`).

## 0.35.1

**Status: log pytań czatu** (M12 E3a, `docs/PLAN_M12.md` § E3).

- Nowa karta „Czat — ostatnie pytania”: 30 ostatnich pytań z zakładki „Zapytaj” z numerem tury
  i wynikiem w skrócie — jak policzono, „nie umiem: …” albo błąd; na górze podsumowanie. Bez kwot.
  Podstawa do wyboru, czego czat ma się nauczyć w kolejnych wersjach (źródła danych, decyzja 24).

## 0.35.0

**Zapytaj — rozmowa z dopytywaniem** (M12 E2, `docs/PLAN_M12_E2.md`).

- Kolejne pytania dopisują się pod poprzednimi i mogą się do nich odnosić: „a w 2025?”, „bez paliwa”,
  „rozbij na miesiące”. Model pamięta 4 ostatnie pytania rozmowy (ich plany zapytań, bez wyników).
- „Nowa rozmowa”, a przykłady i „Ostatnie rozmowy” zawsze zaczynają od nowa (dopytania nie trafiają
  na tę listę).
- Język zapytań: wykluczanie kategorii („Bez kategorii: …” w „Jak policzono”).
- Kontekst rozmowy jest tylko w otwartej stronie (bez zapisu w bazie); odświeżenie zaczyna od nowa.

## 0.34.1

**Zrozumiałe komunikaty błędów AI** (czat, podpowiedzi, Status).

- Zamiast surowej odpowiedzi routera (np. „HTTP 429 — {json}”) panel pokazuje zdanie: wyczerpany limit
  modelu z czasem odnowienia, chwilowy limit, zły klucz, nieznany model, model bez obsługi schematu
  JSON, awaria dostawcy, brak połączenia z routerem, nieczytelna odpowiedź modelu. Każdy komunikat
  podpowiada, co zrobić (np. inny model w opcji `ai_model`). Surowa odpowiedź trafia do logu add-onu.

## 0.34.0

**Zapytaj — czat z danymi** (M12 E1, decyzja 23, `docs/PLAN_M12.md`).

- Nowa zakładka „Zapytaj”: pytanie po polsku (np. „ile wydaliśmy na jedzenie w tym roku?”,
  „który miesiąc był najdroższy?”, porównanie dwóch okresów) → zdanie odpowiedzi, tabela z liczbami,
  „Jak policzono” i link do pasujących transakcji. Przykłady i ostatnie pytania do dotknięcia.
- Liczby liczy add-on tym samym zbiorem co „Wydatki” (bez przelewów własnych, zwroty netto); model
  tylko tłumaczy pytanie na zapytanie i opisuje wynik.
- Do modelu wychodzą pytanie, lista kategorii i wynik zbiorczy — bez pojedynczych transakcji;
  odbiorcy przelewów jako [O1], [O2]…, prawdziwe nazwy wstawiane lokalnie.
- Nowa opcja `chat_daily_calls` (domyślnie 40; pytanie = 2 wywołania), osobno od podpowiedzi
  kategorii. Pytania spoza zakresu dostają „nie umiem” zamiast zgadywanej liczby.

## 0.33.0

**Pula budżetu tylko z wynagrodzenia i świadczeń** (decyzja 22, `docs/ROADMAP.md`).

- Automatyczna pula Flex liczy wpływy poprzedniego miesiąca tylko z podkategorii „Wynagrodzenie”
  i „Świadczenia”. Jednorazowe wpływy w „Inne wpływy” (zwroty, przelewy od znajomych) nie podnoszą
  już puli; w „Wydatkach” nadal są liczone jako przychód.
- Budżet: opis źródeł puli w sekcji „Kwota budżetu” zaktualizowany.

## 0.32.0

**Pamięć sprzedawcy: mniej pracy z kolejką** (M7 E2, `docs/PLAN_M7.md`).

- Transakcja bez reguły i bez wpisu słownika dostaje kategorię z Twoich wcześniejszych ręcznych decyzji
  u tego samego sprzedawcy (ten sam kierunek), jeśli wszystkie były zgodne. Nigdy nie nadpisuje kategorii
  ręcznej, reguły, słownika ani typu; od razu liczy się w budżecie i wydatkach.
- Do przejrzenia: nowa zwinięta sekcja „Przypisane automatycznie (N)” — ptaszek przy grupie albo
  „Potwierdź wszystkie” zatwierdza kategorię; inna kategoria (rozwiń grupę) wyłącza pamięć dla tego
  sprzedawcy, a jego pozostałe pozycje wracają do kolejki. Pozycje odznaczone przy zapisie grupy przejmuje
  pamięć — potwierdzenie zapisu mówi ile.
- Transakcje: etykieta źródła „pamięć”. Status: „Pamięć sprzedawcy na żywo: potwierdzone / poprawione”.
- Migracja bazy 012 (źródło `learned`). **Powrót do 0.31.x tylko przez przywrócenie backupu add-onu.**

## 0.31.1

**Pomiar kategoryzacji: trafność pamięci według typu transakcji** (M7 E1b, `docs/PLAN_M7.md`).

- Status → „Kategoryzacja — pomiar”: nowa tabela „Pamięć według typu transakcji” — karta i BLIK w kraju,
  karta za granicą, przelewy, inne; dla każdego typu: ile pozycji pamięć by przypisała, jak trafnie i ile
  z dzisiejszej kolejki. Na tej podstawie automatyczne przypisywanie (następny etap) obejmie tylko typy,
  w których pamięć jest pewna. Nic nie zmienia w kategoriach.

## 0.31.0

**Kategoryzacja: pomiar przed automatycznym przypisywaniem** (M7 E1, `docs/PLAN_M7.md`).

- Status: karta „Kategoryzacja — pomiar” z przyciskiem „Zmierz”. Na Twojej historii, miesiąc po miesiącu,
  sprawdza, ile pozycji z kolejki dałoby się przypisać z wcześniejszych ręcznych decyzji u tego samego
  sprzedawcy (1, 2 albo 3 zgodne decyzje) i jak trafnie, oraz jak radziłby sobie lokalny klasyfikator dla
  sprzedawców widzianych pierwszy raz. Pokazuje też, jaka część dzisiejszej kolejki to sprzedawcy, o których
  już decydowano. Nic nie zmienia w kategoriach; dane nie opuszczają add-onu.
- `sensor.budget_card_due`: atrybut `available` → `available_bank` (Home Assistant pomija atrybut
  o nazwie `available` w encjach MQTT).

## 0.30.0

**Karta kredytowa: ile spłacić i do kiedy** (M15 E4, `docs/PLAN_M15.md` § E4).

- Ekran Karta: sekcja „Spłata” — kwota z zamkniętego cyklu (miesiąc kalendarzowy) do spłaty do 20. dnia
  następnego miesiąca, liczba dni i stan (do spłaty / spłacone / po terminie). Kwota = zadłużenie z banku
  minus zakupy zaksięgowane w bieżącym cyklu; liczona ostrożnie, może wyjść nieco wyższa niż w banku.
- Sekcja „Limit”: limit wpisany ręcznie (bank go nie podaje), pasek wykorzystania, zadłużenie i „dostępne”
  według banku do porównania.
- Przypomnienie na telefon 15. i 19. o 7:00 (tylko gdy coś zostało do spłaty), pozycja w dzwonku od 1. dnia
  (ostrzeżenie od 15. i po terminie), linia „Do spłaty” na kafelku karty.
- Nowa encja `sensor.budget_card_due` (stan = zostało do spłaty; atrybuty: termin, dni, po terminie,
  zadłużenie, limit, wykorzystanie).
- Kwoty w powiadomieniach i w panelu formatuje jedna funkcja. Bez zmian w schemacie bazy.

## 0.29.0

**„Do wypłaty”: wykres osi czasu i jedna lista zdarzeń** (M8 E3b, `docs/PLAN_M8_E3.md`).

- Wykres prognozy jest większy, ma strefę poniżej zera, znaczniki wpływów i trzech największych wydatków
  (dotknięcie pokazuje nazwę i kwotę), etykietę „najniżej dd.mm” i oś „dziś” – „wypłata dd.mm”.
- Dwie rozwijane listy (serie, wpływy) zastąpiła jedna lista chronologiczna z saldem po każdym dniu;
  wiersz najniższego punktu jest wyróżniony, a wiersze prowadzą do serii. Powyżej 8 pozycji reszta jest zwinięta
  (rozwinięta od razu, gdy kryje dno).
- Bez zmian w schemacie bazy, encjach i dzwonku.

## 0.28.0

**Układ strony głównej** (M16, `docs/PLAN_M16.md`).

- „Edytuj układ” na dole Podsumowania: lista ośmiu kafelków z przyciskami wyżej/niżej i pokaż/ukryj;
  każda zmiana zapisuje się od razu, a „Przywróć domyślny” cofa układ.
- Układ jest wspólny dla wszystkich urządzeń (zapis w bazie add-onu). Nawigacja miesiąca i kafelek
  „Ile możesz jeszcze wydać” zostają zawsze na górze.
- Kafelki bez danych (np. „Do wypłaty”, karta) nadal pojawiają się tylko wtedy, gdy mają co pokazać.
- Bez zmian w schemacie bazy, encjach i dzwonku.

## 0.27.0

**„Do wypłaty”: werdykt i dzienny limit** (M8 E3a, `docs/PLAN_M8_E3.md`).

- Na górze jedna odpowiedź: „Starczy · zapas …” albo „Zabraknie …” (przy buforze: „Poniżej bufora o …”)
  z dniem najniższego punktu.
- Dzienny limit wydatków z puli Flex, przy którym saldo nie spadnie poniżej zera (bufora), obok obecnego
  tempa; gdy same płatności cykliczne przekraczają wolne środki, widać to wprost.
- Rozbicie jako pasek czterech liczb (wolne dziś, serie, Flex, wpływy) i wynik na dzień wypłaty; listy serii
  i wpływów nadal rozwijane.
- Salda, data migawki i przełącznik „Odejmij zadłużenie karty” w stopce karty; przełącznik zapisuje się sam,
  bez przycisku „Zastosuj”.
- Bez zmian w schemacie bazy, encjach i dzwonku.

## 0.26.0

**Prognoza „Do wypłaty”: encje i ostrzeżenie w dzwonku** (M8 E2, `docs/PLAN_M8_E2.md`).

- Dzwonek: karta „Prognoza: zabraknie do wypłaty” (albo „…poniżej bufora”), gdy najniższe wolne
  środki przed wypłatą są poniżej `forecast_buffer` (domyślnie 0); wlicza się też w `sensor.budget_inbox`.
- Encje w HA: `sensor.budget_forecast_free_now`, `_card_debt`, `_lowest`, `_at_payday` oraz
  `binary_sensor.budget_forecast_shortfall` (problem). Powiadomienie zrób automatyzacją na tej encji.
- Prognoza jest liczona raz na zmianę bazy (dzwonek liczy się na każdej stronie).
- Bez zmian w schemacie bazy.

## 0.25.1

**Prognoza „Do wypłaty”: wypłata wskazana przez Ciebie** (M8 E1b, `docs/PLAN_M8_E1b.md`).

- Na ekranie aktywnej serii przychodów przełącznik „To moja wypłata (dzień resetu prognozy)”.
  Prognoza liczy do terminu tej serii, a po jej dniu — do terminu w następnym miesiącu. Bez
  wskazania działa dotychczasowa reguła (seria o największej kwocie).
- W sekcji „Do wypłaty” checkbox „Odejmij zadłużenie karty” (domyślnie włączony, pamiętany).
  Wyłączony: wiersz karty zostaje widoczny z dopiskiem „nie odjęte”, a wolne środki nie są pomniejszone.
- Bez zmian w schemacie bazy (ustawienia w tabeli `kv`).

## 0.25.0

**Prognoza „czy starczy do wypłaty”** (M8 E1, `docs/PLAN_M8.md`, `docs/PLAN_M8_E1.md`).

- Podsumowanie (bieżący miesiąc): sekcja „Do wypłaty” — najniższe wolne środki przed wypłatą z datą,
  rozbicie (saldo rachunku PLN − zadłużenie karty = wolne środki dziś − serie do wypłaty − reszta
  puli Flex + wpływy przed wypłatą = kwota na dzień wypłaty) i wykres dzień po dniu.
- Wypłata = najbliższy termin serii przychodów o największej kwocie; bez takiej serii — koniec miesiąca.
  Zadłużenie karty jest zawsze osobnym wierszem, także przy 0 zł. Saldo starsze niż doba ma dopisek.
- Nowa opcja `forecast_buffer` (zł): najniższy punkt poniżej bufora jest zaznaczony na czerwono.
- Bez zmian w schemacie bazy i encjach (encje i dzwonek — E2).

## 0.24.3

- „Karta” jest główną zakładką, zaraz po „Wydatkach” (wcześniej w menu ⚙).
- Na telefonie pasek zakładek przewija się do aktywnej zakładki po każdym przejściu.
- Poprawka: zakładka „Transakcje” jest podświetlona, gdy jesteś na tym ekranie.

## 0.24.2

- Poprawka: zapis numeru karty z CSV kończył się błędem („unable to open database file”). Pliki
  tymczasowe bazy SQLite są teraz w pamięci — profil AppArmor add-onu nie pozwala pisać do
  `/var/tmp`, gdzie SQLite domyślnie je zakłada.

## 0.24.1

**Historia płatności kartą przypisana z eksportu CSV** (M15 E3, `docs/PLAN_M15.md`).

- Karta → Osoby z kartą: przy każdej osobie wybór numeru karty z eksportu Millenetu. Gdy każdy numer
  karty ma osobę, płatności z historii dostają osobę same — także po kolejnych importach CSV
  i synchronizacjach. Ręczne przypisania zostają.
- Eksport zawiera blok całego konta karty pod jednym numerem i blok płatności jednej karty pod drugim —
  płatność dostaje osobę z najwęższego bloku, w którym występuje.
- Bez zmian w schemacie bazy i encjach.

## 0.24.0

**Płatności kartą przypisane do osób** (M15 E2, `docs/PLAN_M15.md`).

- Bank liczy warunek bezpłatnej karty (5 płatności w miesiącu) osobno dla karty głównej i dodatkowej,
  a API nie podaje numeru karty. Nowy ekran **Karta** (menu ⚙): dodajesz osoby, a każdą płatność kartą
  przypisujesz osobie jednym dotknięciem. Licznik liczy 5 płatności dla każdej osoby; nieprzypisana
  płatność nie liczy się nikomu.
- Dzwonek: „płatności do przypisania” przez cały miesiąc (w ostatnich 5 dniach jako ostrzeżenie) i braki
  każdej osoby w ostatnich 5 dniach. Przypomnienie na telefon podaje stan każdej osoby i liczbę
  nieprzypisanych.
- Kafelek „Karta kredytowa” na Podsumowaniu z wierszem na osobę; plakietka osoby w Transakcjach.
- `sensor.budget_card_purchases_month`: nowe atrybuty `holders` (imię, liczba, brakuje) i `unassigned`.
- Bez osób wszystko działa jak w 0.23.0 (licznik wspólny).
- Migracja bazy `011_card_holder` (addytywna).

## 0.23.0

**Licznik płatności kartą kredytową** (M15 E1, `docs/PLAN_M15.md`).

- Karta jest bezpłatna przy co najmniej 5 płatnościach kartą w miesiącu (BLIK się nie liczy, bank
  liczy kartę główną i dodatkową osobno). API nie podaje numeru karty ani daty zakupu, więc licznik
  jest wspólny dla konta karty i ostrożny: mniejsza z liczb po dacie księgowania i po dacie
  księgowania − 2 dni.
- Kafelek „Karta kredytowa” na Podsumowaniu, encja `sensor.budget_card_purchases_month`
  (atrybuty `threshold`, `missing`, `month`).
- 5 dni i dzień przed końcem miesiąca, gdy brakuje płatności: powiadomienie przez
  `summary_notify_service` (o 7:00, raz) i karta w dzwonku przez ostatnie 5 dni.
- Poprawka: strona panelu otwarta w aplikacji HA przed aktualizacją przeładowuje się w całości przy
  pierwszym kliknięciu (wcześniej mogła zostać ze starym wyglądem do czasu resetu pamięci podręcznej).
- Bez zmian w schemacie bazy.

## 0.22.1

- Poprawka: dotknięcie podsumowania na telefonie i link w powiadomieniu w HA otwierają panel Budżetu.
  Od HA 2026.9 adres `/hassio/ingress/<slug>` zwraca 404 — teraz `/app/<slug>`.

## 0.22.0

**Podsumowania na telefon i kalendarz płatności** (M6, `docs/PLAN_M6.md`).

- Nowa opcja `summary_notify_service`: w poniedziałek o 7:00 podsumowanie tygodnia (zostało z puli,
  na dzień, tempo, top 3 kategorie tygodnia, płatności cykliczne w 7 dni, do przejrzenia), 1. dnia
  miesiąca zamknięcie poprzedniego miesiąca. Wiadomość nie wysłana o 7:00 (add-on nie działał)
  wychodzi po starcie tego samego dnia. Podgląd i „Wyślij teraz” na ekranie Status.
- Kalendarz płatności `/calendar.ics` dla integracji Remote Calendar (terminy serii na 60 dni,
  z kwotą i statusem); dostępny tylko dla Home Assistant Core. Opcja `calendar_entity` — odświeżenie
  encji kalendarza po każdej synchronizacji. Instrukcja w dokumentacji add-onu.
- Bez zmian w schemacie bazy i istniejących encjach.

## 0.21.1

**Szybsze Konta i Import** (M14 etap 1b, `docs/PLAN_M14_E1.md`).

- Konta: ekran budował pełny raport księgi (m.in. uzgodnienie sald), a pokazuje tylko listę kont — teraz liczy tylko ją.
- Import: uzgodnienie sald pochodzi z tej samej pamięci co dzwonek i Status, zamiast liczyć się od nowa przy każdym otwarciu.
- Wygląd i wyniki bez zmian (strony przed i po identyczne co do bajtu); bez zmian w encjach i schemacie bazy.

## 0.21.0

**Szybszy panel** (M14 etap 1, `docs/PLAN_M14_E1.md`).

- Przynależność transakcji do serii cyklicznych (czytanie i parsowanie całej księgi) liczyła się trzy razy na jedno
  wyświetlenie strony: dzwonek na każdym ekranie, Podsumowanie, Budżet, Cykliczne i encje MQTT. Teraz liczy się raz i jest
  ważna do pierwszego zapisu w księdze (transakcja, reguła, seria, kategoria, kwota Flex).
- Wygląd i wyniki bez zmian (strony zrenderowane przed i po są identyczne co do bajtu); bez zmian w encjach i schemacie bazy.

## 0.20.3

**Domknięcie refaktoru UI** (M13 etap 3e, `docs/PLAN_M13_E3e.md`).

- Budżet → Koszty stałe: wiersz podkategorii stałej pokazuje nazwę i medianę; kategoria główna, link do transakcji
  i „Przenieś” rozwijają się po dotknięciu wiersza (jak w Kategoriach) — lista jest krótsza na telefonie.
- Budżet: wiersz „Wpływy (…)” ma co najmniej 44 px (był o 1,5 px niższy).
- Reguły: pusty stan nie radzi już przycisku „Zawsze dla …” (usuniętego w 0.11.0), tylko pole „utwórz regułę”.
- Wewnętrznie: jedna klasa `tap` dla linków samodzielnych zamiast list selektorów per ekran; wygląd pozostałych ekranów
  bez zmian (zrzuty przed i po identyczne). Bez zmian w logice budżetu, encjach i schemacie bazy.

## 0.20.2

**Cele dotyku na pozostałych ekranach** (M13 etap 3d, `docs/PLAN_M13_E3d.md`). Po tym wydaniu wszystkie ekrany panelu mają
cele dotyku co najmniej 44 px.

- Kategorie: wiersz podkategorii pokazuje nazwę, grupę budżetu i liczbę transakcji; zmiana nazwy, grupy i przeniesienie
  rozwijają się po dotknięciu wiersza (wcześniej dwa małe formularze w każdym wierszu).
- Konta, Bank, Import, Status, Płatności cykliczne i strona serii: pola, przyciski, pola wyboru, nazwy serii, „Edytuj
  i potwierdź” i link powrotu mają co najmniej 44 px; wiersze nadchodzących serii na Podsumowaniu również.
- Linki w środku zdania (np. „Status” w linii „Dane z …”, „Kategoriach”, „Bank”) mają powiększony niewidoczny obszar dotyku,
  bez rozsuwania wierszy tekstu.
- Wewnętrznie: jedna reguła dla wszystkich pól i przycisków zamiast reguł per ekran. Bez zmian w logice budżetu, encjach
  i schemacie bazy.

## 0.20.1

**Cele dotyku na Podsumowaniu, w Wydatkach i Budżecie** (M13 etapy 3b i 3c, `docs/PLAN_M13_E3b.md`, `docs/PLAN_M13_E3c.md`).

- Podsumowanie: strzałki miesięcy (także w Do przejrzenia i Wydatkach), link „Status”, linki pod kartami, pozycje „Do decyzji”
  i „Ustaw budżet” mają cele dotyku co najmniej 44 px.
- Wykres 12 miesięcy: etykiety osi pionowej leżą w obszarze wykresu (po prawej, pod linią siatki, bez zera), dzięki czemu
  słupki mają ok. 24 px szerokości na telefonie (było 22 px).
- Wydatki i Budżet: linki podkategorii i linii bilansu, formularze kwoty i formularze kosztów stałych mają co najmniej 44 px.
- Wewnętrznie: reguły CSS ograniczone do klas tych ekranów. Bez zmian w logice budżetu, encjach i schemacie bazy.

## 0.20.0

**Ekrany robocze na telefonie** (M13 etap 3, `docs/PLAN_M13_E3.md`).

- Do przejrzenia, Transakcje i Reguły mają cele dotyku co najmniej 44 px: chipy kategorii i podpowiedzi AI, przyciski, pola
  formularzy, przełączniki rozwijania, linki oraz wiersze pozycji (cały wiersz zaznacza pozycję).
- Lista reguł na telefonie to karty (warunki, kategoria, trafienia i rząd przycisków) zamiast tabeli przewijanej w poziomie;
  na komputerze tabela bez zmian.
- Wewnętrznie: token `--tap` w stylach, reguły ograniczone do klas tych ekranów. Bez zmian w logice budżetu, encjach i schemacie bazy.

## 0.19.1

**Jeden wygląd: Monarch** (M13 etap 1c, `docs/PLAN_M13_E1b.md`).

- Panel ma już tylko wygląd Monarch (jasny, jeden pomarańczowy akcent, szeryfowe nagłówki). Wygląd Copilot Money i przełącznik
  „Wygląd” z menu ⚙ zniknęły; wygląd ekranów jest taki sam jak w 0.19.0 w Monarch.
- Poprawka: podpis porównania w środku wykresu kołowego (np. „vs 1–5 września”) mieści się w otworze, bez zachodzenia na pierścień.
- Wewnętrznie: reguły CSS bez warstwy nadpisań motywu, usunięta trasa `POST /theme`, krój Space Grotesk i ustawienie wyglądu
  (stary wpis w ustawieniach add-onu jest nieszkodliwy i ignorowany). Bez zmian w logice budżetu, encjach i schemacie bazy.

## 0.19.0

**Rozszerzone Podsumowanie** (M13 etap 2, `docs/PLAN_M13_E2.md`), w obu wyglądach (Copilot i Monarch).

- **Wykres kołowy wydatków** miesiąca: sześć największych kategorii, „Inne” i „Bez kategorii”; w środku suma i zmiana
  względem poprzedniego okresu. Wycinek i wiersz legendy prowadzą do transakcji tej kategorii (albo do kolejki
  „Do przejrzenia”). Kolor kategorii jest stały, a lime, czerwień i żółć zostają zarezerwowane dla znaczeń.
- **Przełączanie miesięcy** na całym ekranie (« wrzesień), także karta „Zostało” dla miesięcy minionych.
- **Bilans miesiąca:** wydatki, wpływy i bilans ze zmianą względem poprzedniego okresu. Bieżący, niepełny miesiąc jest
  porównywany z tym samym zakresem dni poprzedniego miesiąca (podpis mówi to wprost, np. „vs 1–5 września”).
- **Co jeszcze zejdzie:** najbliższe płatności z serii cyklicznych i sumy „jeszcze zejdzie / jeszcze wpłynie” (bieżący miesiąc).
- **Ostatnie transakcje** (5, bez przelewów własnych) i **wykres 12 miesięcy** (wpływy i wydatki; słupek otwiera ten miesiąc).
- **Linia „Dane z …”:** czas ostatniej udanej synchronizacji (ostrzeżenie, gdy dane są starsze niż 30 godzin) i dni do końca zgody.
- Karta „Zostało” jest wspólna dla Budżetu i Podsumowania; na telefonie pary etykieta i wartość są jedna pod drugą.
- Poprawka separatora tysięcy w kwotach wyglądu Monarch (znak U+202F z Inter zamiast zbyt wąskiego z szeryfa).
- Bez zmian w logice budżetu, encjach i schemacie bazy.

## 0.18.1

**Drugi wygląd panelu: Monarch, z przełącznikiem „Wygląd”** (M13 etap 1b, `docs/PLAN_M13_E1b.md`).

- **Menu ⚙ → Wygląd:** przełączasz Copilot Money (ciemny, jak w 0.18.0, nadal domyślny) i Monarch (jasny, lniane tło,
  białe karty, jeden pomarańczowy akcent, szeryfowe nagłówki). Wybór jest zapamiętany w add-onie i dotyczy wszystkich
  ekranów; po przełączeniu wracasz na tę samą stronę.
- Przełącznik jest tymczasowy: po wyborze jednego wyglądu drugi i przełącznik znikną w kolejnym wydaniu.
- Bez zmian w logice budżetu, encjach i schemacie bazy.

## 0.18.0

**Nowy wygląd panelu i strona główna „Podsumowanie”** (M13 etap 1, `docs/PLAN_M13.md`).

- **Styl Copilot Money, tylko ciemny:** granatowe tło, karty z wewnętrznym cieniem, jeden niebieski
  kolor akcji. Kroje Inter i Space Grotesk oraz ikony Lucide (SVG) są w add-onie — bez zewnętrznych
  zasobów. Kwota wydatku w wierszu jest biała; kolor mają wpływy (zielony) i przekroczenia (czerwony).
- **Strona główna `/` = Podsumowanie:** „Zostało na elastyczne” z paskiem tempa i kwotą na dzień oraz
  karta „Do decyzji”. Wykresy, top kategorii i ostatnie transakcje dojdą w 0.19.0.
- **Nowa nawigacja:** Podsumowanie · Budżet · Wydatki · Cykliczne · Transakcje, dzwonek i menu ⚙ z pozostałymi
  ekranami (Do przejrzenia, Reguły, Konta, Import CSV, Bank, Status na końcu). Wersja add-onu jest w stopce.
- **Status przeniesiony na `/status`** (menu ⚙ → Status); karty „Nieudane synchronizacje” i „Synchronizacja
  niepełna” w dzwonku prowadzą tam. Zakładki i skróty do starego adresu `/` otworzą Podsumowanie.
- Bez zmian w logice budżetu, encjach i bazie danych.

## 0.17.1

**Wypłata w seriach wpływowych: ostatnia kwota zamiast mediany** (poprawka M5b).

- Nowa propozycja serii **wpływowej** ma oczekiwaną kwotę równą ostatniemu wpływowi niebędącemu
  premią (powyżej 1,5 × mediany ostatnich 6 pomijany) i tolerancję 10%. Dotąd mediana z 6 miesięcy
  zawyżała kwotę po spadku wypłaty, a szeroka tolerancja chowała tę zmianę przed kartą „inna kwota”.
- Serie wydatkowe bez zmian. Istniejące serie nie przeliczają się same — kwotę i tolerancję
  poprawiasz w Cykliczne → seria → Edytuj; kolejne zmiany wypłaty zgłasza karta „inna kwota”.
- Pula Flex bez zmian (serie wpływów jej nie ruszają).

## 0.17.0

**Pula Flex ze stałymi z serii** (M5b etap 4, `docs/PLAN_M5b_E4.md`).

- **Stałe w puli = serie + mediany spoza serii.** Aktywna seria wydatkowa wchodzi do kosztów
  stałych oczekiwaną kwotą w przeliczeniu na miesiąc (kwartalna ⅓, roczna 1/12); mediany
  podkategorii „stałe” liczą się bez transakcji serii, więc nic nie jest liczone dwa razy.
- **Transakcje serii wypadają z „wydane”** elastycznych (miesiąc, historia, podpowiedź kwoty,
  linie kategorii) i z „Poza pulą”; w „Poza pulą” pojawia się wiersz „Cykliczne”.
- **Seria oszczędnościowa nie zmienia puli**: gdy ostatnia transakcja serii ma kategorię
  z grupy oszczędności, przychodów albo „poza budżetem”, seria zostaje poza pulą.
- **Budżet → Koszty stałe**: sekcja „Płatności cykliczne” (nazwa z linkiem do serii, kadencja,
  kwota na miesiąc) i „Podkategorie stałe spoza serii”.
- Encja `sensor.budget_flex_budget` dostaje atrybut `fixed_series`; `fixed_median` to nadal
  całość stałych. Kwota ręczna bez zmian, serie wpływów nie wpływają na pulę. Bez migracji.

## 0.16.0

**Zmiany serii w dzwonku** (M5b etap 3, `docs/PLAN_M5b_E3.md`).

- **Trzy rodzaje zmian** aktywnych serii: *inna kwota* (ostatni zapłacony termin poza
  kwotą ± tolerancja), *spóźniona* (termin z bieżącego lub poprzedniego miesiąca bez płatności)
  i *ustała* (dwa ostatnie terminy bez płatności; zastępuje kartę „spóźniona”).
- **Cykliczne → „Zmiany”**: przyciski „Przyjmij nową” / „Jednorazowo”, „Pomiń ten okres”,
  „Zakończ” / „Zostaw”. Decyzje zapisuje nowa tabela `series_ack` (migracja 010, addytywna).
- **Dzwonek** i `sensor.budget_inbox` dostają po jednej karcie na rodzaj zmiany.
- Pominięty termin ma status „pominięte” i nie liczy się do „jeszcze zejdzie / wpłynie”.
- Pula Flex bez zmian (stałe z serii — etap 4).

## 0.15.0

**„Ten miesiąc”: co jeszcze zejdzie i wpłynie** (M5b etap 2, `docs/PLAN_M5b_E2.md`).

- **Cykliczne → „Ten miesiąc”**: aktywne serie z terminem i statusem (zapłacone / oczekiwane /
  spóźnione, w minionych miesiącach „brak płatności”), sumy „zapłacone”, „jeszcze zejdzie”,
  „wpłynęło”, „jeszcze wpłynie”; przełączanie miesięcy. Transakcja należy do najbliższego
  terminu w promieniu 15 dni, więc płatność 30. na termin 1. liczy się do miesiąca terminu.
- **Budżet**: linia „Cykliczne: zapłacone … · jeszcze zejdzie … · jeszcze wpłynie …”
  z linkiem do szczegółów.
- **„To się powtarza”** na Transakcjach: formularz serii wypełniony z transakcji, z podglądem
  objętych transakcji; zapis tworzy od razu aktywną serię ręczną (detektor nie zaproponuje
  jej ponownie). Transakcje serii mają plakietkę „cykliczna: nazwa”.
- Pula Flex bez zmian (stałe z serii — etap 4).

| Encja | Zmiana |
|---|---|
| `sensor.budget_fixed_paid` | **nowa** — wydatki z serii zapłacone w tym miesiącu; atrybuty `items`, `paid_count`, `expected_count`, `late_count` |
| `sensor.budget_fixed_planned` | **nowa** — wydatki z serii, które jeszcze zejdą (oczekiwane + spóźnione) |
| `sensor.budget_income_planned` | **nowa** — wpływy z serii, które jeszcze wpłyną; atrybuty `received`, `items`, liczniki |

Bez migracji bazy. Nowe trasy panelu: `GET /recurring/new?txn=ID`, `POST /recurring/new`,
`POST /recurring/new/preview`; `GET /recurring?month=RRRR-MM`. Bez nowych usług.

## 0.14.0

**Dzwonek i płatności cykliczne** (M5b etap 1, `docs/PLAN_M5b_E1.md`).

- **Dzwonek w pasku panelu** z liczbą kart „do decyzji” i ekranem `/inbox`: bez kategorii
  w bieżącym i poprzednim miesiącu, nowe propozycje serii, zgoda bankowa (< 30 dni /
  nieaktywna), nieudane synchronizacje, rozbieżność uzgodnienia salda. Licznik przy
  „Do przejrzenia” przeszedł do dzwonka.
- **Zakładka „Cykliczne”**: wykrywanie serii po każdej synchronizacji i na żądanie
  (co miesiąc / kwartał / rok, wydatki i wpływy, raty kredytu po typie), propozycje do
  potwierdzenia, edycji albo odrzucenia, lista aktywnych i zakończonych serii, strona serii
  z warunkami jak w regułach i dopasowanymi transakcjami.
- Pula Flex bez zmian — serie wejdą do budżetu w kolejnych etapach.
- Uzgodnienie salda na ekranie Status liczone raz na zmianę danych (szybsze odświeżanie).

| Encja | Zmiana |
|---|---|
| `sensor.budget_inbox` | **nowa** — liczba kart w dzwonku; atrybut `items` (`kind`, `title`, `count`, `severity`) |

Migracja bazy `009_series` (tabela `series`). Nowe trasy panelu: `GET /inbox`, `GET /recurring`,
`GET /recurring/{id}`, `POST /recurring/detect`, `POST /recurring/{id}/save`,
`POST /recurring/{id}/status`. Bez nowych usług.

## 0.13.0

**Budżet: z czego składa się pula i jedno miejsce na koszty stałe** (M5a etap 4,
`docs/PLAN_M5a_fixed.md`).

- **Wpływy rozwijają się na źródła** z kwotami (przy premii — część poza pulą).
- **Koszty stałe rozwijają się na podkategorie** z medianą miesięczną. Przy każdej: „Przenieś”
  do innej grupy (domyślnie elastyczne); na dole „Dodaj do stałych” z listą pozostałych
  podkategorii wydatkowych (z medianą i obecną grupą). Zmiana grupy działa jak w Kategoriach —
  na całą historię i od razu na pulę; po zapisie rozwinięcie zostaje otwarte.
- **Zmiana liczenia stałych:** suma median podkategorii z 6 miesięcy zamiast mediany
  miesięcznej sumy — składniki zawsze sumują się do kwoty odejmowanej od puli. Pula
  automatyczna może się przesunąć względem 0.12.0.

| Encja | Zmiana |
|---|---|
| `sensor.budget_flex_budget` | atrybut `fixed_median` = suma median podkategorii stałych (wcześniej mediana sumy) |
| `sensor.budget_flex_remaining`, `sensor.budget_flex_per_day` | liczone od nowej puli automatycznej |

Bez nowych encji ani usług. Nowe trasy panelu: `POST /budget/fixed/{id}`, `POST /budget/fixed`.

## 0.12.0

**Budżet Flex: pula liczona z dochodu** (M5a etap 3, `docs/PLAN_M5a_income.md`).

- **Pula automatyczna:** bez ręcznej kwoty pula elastyczna miesiąca = wpływy z poprzedniego
  miesiąca (podkategorie z grupy „przychody”, tylko skategoryzowane) − koszty stałe (mediana
  z 6 miesięcy). Pula idzie za faktyczną wypłatą: niższa pensja po przekroczeniu progu
  podatkowego obniża pulę od następnego miesiąca, bez uśredniania dochodu.
- **Premia poza pulą:** nietypowo wysoki wpływ ze stałego źródła (powyżej 1,5 × górnego kwartyla
  z 12 miesięcy) zasila pulę tylko zwykłą kwotą; nadwyżka jest pokazana jako „premia poza pulą”.
- **Dopisek o progu podatkowym**, gdy główne źródło wpływów jest niższe o ponad 15% niż zwykle
  w tym roku.
- **Kwota ręczna nadal działa** i ma pierwszeństwo; nowy przycisk „Wróć do automatycznej od
  tego miesiąca”. Ekran Budżet pokazuje rozbicie puli (wpływy, premia, stałe).
- **Kontrola salda karty:** liczy w znaku zadłużenia (ITBD karty jest dodatnie), różnica krótsza
  niż 3 dni to „w drodze” (autoryzacja przed pojawieniem się w API), a na Status jest przycisk
  „Przyjmij ostatnią migawkę jako bazę”. Wcześniej karta pokazywała fałszywą „ROZBIEŻNOŚĆ”.
- Migracje bazy: 007 (pusta kwota = pula automatyczna), 008 (baza kontroli salda).

| Encja | Zmiana |
|---|---|
| `sensor.budget_flex_budget` | ma wartość także bez ręcznej kwoty (pula z dochodu); nowe atrybuty `source`, `auto_amount`, `income_base`, `bonus_excluded`, `fixed_median`, `income_drop_pct` |
| `sensor.budget_flex_remaining`, `sensor.budget_flex_per_day` | liczone od puli automatycznej, gdy brak ręcznej |

Bez nowych encji ani usług.

## 0.11.1

- **Poprawka:** sprawdzanie zgody bankowej (co 6 h) i okresowe odświeżanie encji nie zatrzymują się
  już po błędzie sieci. Wcześniej chwilowy brak DNS albo zerwane połączenie z Enable Banking
  (`httpx.ConnectError`) kończyły tę pętlę po cichu aż do restartu add-onu. Teraz błąd trafia do
  logu jako ostrzeżenie, a kolejne sprawdzenie odbywa się normalnie.
- Dokumentacja: limit 4 zapytań/dobę w Millennium jest liczony osobno dla każdego endpointu
  (salda, transakcje), nie łącznie na konto.
- Bez nowych encji ani usług.

## 0.11.0

**Zmiana domyślnego zachowania:** zapis kategorii nie tworzy już reguły (M4h etap 2,
`docs/PLAN_review_rule_conditions.md`).

- **Kolejka „Do przejrzenia”:** pole „tylko te transakcje (bez reguły)” zastąpione przez
  **„utwórz regułę”** (domyślnie odznaczone). Bez zaznaczenia zapis nadaje kategorię **ręczną**
  zaznaczonym pozycjom — przyszłe transakcje tego sprzedawcy pojawią się w kolejce jako nowe
  pozycje. Z zaznaczeniem pokazują się pola reguły (jak w 0.10.0), a pozycje grupy wybierają
  warunki (pola wyboru pozycji są wtedy nieaktywne).
- **Ptaszek w filtrze „Propozycja AI”** nadaje kategorię ręcznie całej grupie (bez reguły).
- **Reguła w każdej grupie:** także w grupach krajów (przycisk „reguła dla tego sprzedawcy”
  zamiast linku do edytora) i w grupach bez nazwy (warunek do wpisania, np. konto kontrahenta).
- **Transakcje:** w formularzu kategorii „utwórz regułę” rozwija w miejscu pola reguły
  (sprzedawca równa się … + kierunek, dodatkowe warunki, kwota, nazwa) z podglądem na żywo; reguła
  musi pasować do tej transakcji i zastępuje jej ręczną kategorię. Link „Zawsze dla …” usunięty.
- Bez nowych encji ani usług.

## 0.10.0

Pełne warunki reguły w kolejce „Do przejrzenia” (M4h etap 1, `docs/PLAN_review_rule_conditions.md`).

- **Wiersz reguły** w grupie sprzedawcy: oprócz operatora i tekstu można wybrać pole (sprzedawca,
  opis/tytuł, kontrahent, konto kontrahenta).
- **„+ więcej warunków”** rozwija w miejscu te same pola co edytor w zakładce Reguły: drugi
  i trzeci warunek tekstowy, konto, typ, kierunek (domyślnie kierunek grupy, także „oba”), kwota
  od–do, nazwa sprzedawcy. Warunki łączone przez „i” — bez przechodzenia do zakładki Reguły.
- **Część grupy:** reguła może złapać tylko część pozycji (np. tytuł zawiera „składka”) — musi
  złapać co najmniej jedną; podgląd mówi „k z n pozycji tej grupy” i wymienia pozycje, które
  zostaną w kolejce; po zapisie grupa zostaje otwarta z resztą.
- Podpowiedź AI sprzedawcy jest zamykana (przyjęta/odrzucona) tylko wtedy, gdy reguła obejmie
  wszystkie jego pozycje w kolejce.
- Podgląd i ostrzeżenie o innych grupach liczone po wszystkich polach reguły (nie tylko nazwie
  sprzedawcy); opis reguły w podglądzie jak na liście reguł.
- Bez nowych encji ani usług; edytor w zakładce Reguły wygląda jak dotąd (wspólny fragment pól).

## 0.9.1

Szybszy zapis reguł i podgląd w kolejce „Do przejrzenia” (`docs/PLAN_rule_index.md`).

- **Przyczyna:** przeliczenie kategorii sprawdzało dla każdej transakcji wszystkie reguły po kolei,
  więc każda nowa reguła z kolejki spowalniała kolejny zapis i podgląd (przy ~150 regułach ~5 s
  podglądu i ~10 s zapisu na słabym CPU; baza danych to ułamek sekundy).
- **Poprawka:** reguły „sprzedawca równa się X” (domyślne z kolejki) są w indeksie po nazwie
  sprzedawcy; pozostałe reguły sprawdzane po kolei jak dotąd. Wynik kategoryzacji bez zmian
  (ta sama kolejność reguł), czas zapisu ~1 s i prawie niezależny od liczby reguł. Przyspiesza też
  przeliczenie po każdej synchronizacji i imporcie.
- Bez nowych encji, usług ani zmian w panelu.

## 0.9.0

„Ile zostało” w Home Assistant — encje budżetu elastycznego (M5a etap 2, `docs/PLAN_M5a.md`).

- **Nowe encje** (bieżący miesiąc, PLN, bez statystyk długoterminowych):

  | Encja | Stan | Atrybuty |
  |---|---|---|
  | `sensor.budget_flex_budget` | kwota budżetu elastycznego | `budget_from`, `suggested` (podpowiedź), `month` |
  | `sensor.budget_flex_spent` | wydane elastyczne (z wydatkami bez kategorii) | `uncategorized_amount`, `uncategorized_count`, `other_currency`, `month` |
  | `sensor.budget_flex_remaining` | zostało | `per_day`, `expected_today`, `over_pace`, `used_pct`, `days_left`, `month` |
  | `sensor.budget_flex_per_day` | zostało na dzień do końca miesiąca | `days_left` |

  Dopóki kwota nie jest ustawiona na ekranie Budżet, kwota/zostało/na dzień mają stan „nieznany”.
- **Odświeżanie encji:** kilka sekund po każdym zapisie w panelu (kwota, grupa podkategorii,
  kolejka, reguły, kategoria transakcji) i tuż po północy (nowy „na dzień”, nowy miesiąc) — poza
  dotychczasowym odświeżeniem po synchronizacji.

## 0.8.2

- Filtr „Propozycja AI”: od razu widać 8 najliczniejszych podkategorii, reszta jest pod
  „więcej (N)”. Przy kilkudziesięciu podkategoriach pasek zasłaniał na telefonie całą listę.
  Gdy wybrana podkategoria jest w „więcej”, ta część jest rozwinięta.

## 0.8.1

Kolejka „Do przejrzenia”: przegląd po jednej kategorii naraz (M4f etap 2,
`docs/PLAN_review_rule_text.md`).

- **Filtr „Propozycja AI”** pod zakładkami Wydatki/Wpływy: podkategorie z propozycji AI z liczbą
  grup (np. „Restauracje i kawiarnie (14)”), od najliczniejszej, i „wszystkie”. Grupa jest pod
  podkategorią, gdy ta jest wśród jej propozycji (dowolna z 3). W filtrze bez sekcji Zagranica.
- **Przycisk zatwierdzenia przy każdej grupie w filtrze** (ptaszek + nazwa podkategorii): jedno
  dotknięcie zapisuje regułę „sprzedawca równa się …” dla całej grupy (podpowiedź AI —
  przyjęta) i chowa wiersz; licznik kolejki i pokrycie odświeżają się od razu. Rozwinięcie grupy
  nadal pozwala wybrać inną kategorię, skrócić tekst reguły albo odznaczyć pozycje.
- Filtr zostaje przy przełączaniu Wydatki/Wpływy, sortowania, miesięcy, „pokaż więcej”
  i „Podpowiedz teraz”.

## 0.8.0

Kolejka „Do przejrzenia”: jedna reguła dla całej sieci sklepów (poza planem, M4f etap 1,
`docs/PLAN_review_rule_text.md`).

- **Edytowalny tekst reguły** w każdej grupie sprzedawcy: warunek „równa się” (jak dotąd,
  domyślnie), „zawiera” albo „zaczyna się od” i tekst do skrócenia, np. z „Qwerty 12” do
  „Qwerty”. Podgląd odświeża się w trakcie pisania.
- **Podgląd pokazuje, co jeszcze reguła złapie z kolejki:** liczba transakcji i grup oraz do
  5 nazw sprzedawców; po zapisie ta sama informacja i link „odśwież listę”.
- Fragment, który nie obejmuje sprzedawcy grupy, albo krótszy niż 3 znaki — komunikat, nic nie
  jest zapisane. Przy błędzie formularz zachowuje wybraną kategorię i wpisany tekst.
- Podpowiedzi AI: zapis reguły zamyka (przyjęta/odrzucona) podpowiedzi wszystkich sprzedawców,
  których reguła objęła, nie tylko tej grupy.

## 0.7.0

Budżet Flex, pierwszy kawałek (M5a, `docs/PLAN_M5a.md`): „ile mogę jeszcze wydać w tym miesiącu”.

- **Nowy ekran „Budżet”** (zakładka po Statusie): zostało z miesięcznej kwoty na wydatki
  elastyczne, pasek z kreską tempa, „na dzień do końca miesiąca”, „przy równym tempie do dziś”,
  podkategorie elastyczne z wydanym i medianą 6 miesięcy; stałe i nieregularne obok,
  informacyjnie. Nawigacja po miesiącach jak w „Wydatkach”.
- **Kwota budżetu** ustawiana w panelu od wybranego miesiąca (wcześniejsze miesiące bez zmian),
  z podpowiedzią = mediana wydatków elastycznych z 6 pełnych miesięcy.
- Wydatki bez kategorii liczą się do „wydane” (ostrożnie) — z liczbą i linkiem do kolejki.
- **Kategorie:** grupa budżetu (przychody, stałe, elastyczne, nieregularne, oszczędności, poza
  budżetem) do zmiany przy każdej podkategorii.
- Migracja bazy 006 (`flex_budget`).

## 0.6.1

Wyszukiwanie na żywo w całym panelu (poza planem, `docs/PLAN_live_search.md`).

- **Reguły:** nowe pole „Szukaj” — po wartościach warunków, podkategorii, kategorii głównej,
  nazwie sprzedawcy z reguły i stanie „wyłączona”. Przy aktywnym filtrze nie ma „wyżej/niżej”
  (kolejność zmieniasz bez filtra); „Wyłącz”/„Usuń” wracają do tej samej przefiltrowanej listy.
- **Słownik** i **Transakcje:** lista zawęża się w trakcie pisania, bez przycisku. Na
  Transakcjach na żywo działają też konto, daty, kategoria, kierunek i typ; licznik wyników
  i „wyczyść filtry” nad listą.
- Jedno dopasowanie wszędzie, takie samo jak w regułach: bez polskich znaków i wielkości liter
  („zolw” = „ŻÓŁW”), wszystkie słowa w dowolnej kolejności. Na Transakcjach wcześniej „żółw”
  nie znajdowało „ŻÓŁW”, a dwa słowa szukały ciągu dokładnie w tej kolejności.
- Filtr zostaje w adresie strony — odświeżenie i powrót z edycji go nie gubią.
- Poprawka: filtrowanie Transakcji z kontem „wszystkie” (i przejście na kolejną stronę)
  kończyło się błędem 422.

## 0.6.0

Przegrupowanie kategorii (poza planem, `docs/PLAN_categories_move.md`).

- **Kategorie:** nowa kategoria główna (karta „Nowa kategoria główna” na końcu listy).
- Przy każdej podkategorii lista **przenieś do…** — podkategoria trafia na koniec wybranej
  kategorii głównej razem z transakcjami, regułami, słownikiem i grupą budżetu; „Wydatki”
  liczą ją pod nową kategorią także za poprzednie miesiące (bez przeliczania księgi).
- Pustą kategorię główną można usunąć; kategorii z podkategoriami — nie.
- Nazwa kategorii głównej musi być unikalna (także przy zmianie nazwy).

## 0.5.0

Podpowiedzi kategorii per sprzedawca (etap M4c/3, `docs/PLAN_M4c.md`). Po pierwszym pomiarze
trafność pojedynczej odpowiedzi była za niska na zatwierdzanie jednym dotknięciem — zamiast tego
do 3 propozycji, wybór zawsze ręczny.

- Model zwraca do 3 kandydatów (podkategoria + pewność), każdy sprawdzany; migracja `005`
  (kolumna `candidates`, oczekujące podpowiedzi z jednym kandydatem liczone od nowa).
- **Do przejrzenia:** przyciski „AI: …” pod nazwą sprzedawcy — dotknięcie rozwija grupę
  z wybraną kategorią i podglądem reguły; zapis jak dotąd. Grupy krajów: propozycje per
  sprzedawca jako tekst. Przycisk **Podpowiedz teraz (AI)** (zachowuje kierunek, sortowanie
  i miesiąc).
- **Transakcje:** propozycje w formularzu kategorii (ustawiają wybór).
- Zapis kategorii sprzedawcy w kolejce oznacza podpowiedź jako przyjętą albo odrzuconą.
- **Zmierz trafność:** nowa kolumna „wśród 3”.

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
