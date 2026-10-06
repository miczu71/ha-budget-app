# Changelog

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
