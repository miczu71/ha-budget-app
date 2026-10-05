# Budżet Domowy

Transakcje i salda pobierane automatycznie z banku przez PSD2
([Enable Banking](https://enablebanking.com), tylko odczyt — AIS), zapisywane lokalnie
w Home Assistant w jednej księdze bez duplikatów: CSV z historią + API, spłaty karty jako
przelewy między kontami, uzgadnianie salda.

> **Prywatność:** baza (`/data/budget.db`) i klucz Enable Banking są częścią **kopii zapasowych
> Home Assistant** — kopia zawiera Twoje dane finansowe. Chroń ją hasłem i nie udostępniaj.

## Wymagania

- Aplikacja w Enable Banking Control Panel (tryb **Restricted Production** wystarcza dla
  własnych kont): identyfikator aplikacji i klucz prywatny `.pem`. Konta muszą być wcześniej
  podlinkowane w Control Panelu.
- Broker MQTT (add-on Mosquitto) — encje trafiają do HA przez MQTT Discovery.

## Pierwsze uruchomienie

1. W opcjach add-onu wpisz `eb_application_id` (i ewentualnie `eb_redirect_url`), uruchom add-on.
2. Otwórz panel **Budżet** → **Bank**:
   - wgraj klucz prywatny `.pem` (zapisany z prawami 600 w katalogu konfiguracji add-onu),
   - **przenieś sesję** z CLI (plik `sessions/<id>.json`) — bez ponownego logowania w banku,
     albo **Połącz bank**: otwórz link, potwierdź w aplikacji banku, wklej adres zwrotny.
     Po nowym połączeniu add-on pobiera 90 dni historii.
3. **Import CSV** (opcjonalnie): eksport historii z bankowości internetowej. Starsze transakcje
   uzupełniają historię sprzed 90 dni dostępnych w API. Import można powtarzać — nic się nie
   zdubluje.
4. **⚙ → Status** → **Synchronizuj teraz** — pierwsze pobranie.

## Synchronizacja i limit banku

Bank może odmówić więcej niż **4 zapytań na konto na dobę** wykonanych bez Twojej obecności.
Add-on liczy każde zapytanie (salda, każdą stronę transakcji) per konto i endpoint i nie wyśle
zapytania ponad limit. Domyślne 3 synchronizacje dziennie (`sync_times`) pobierają salda
i transakcje od ostatniego księgowania − 5 dni; bank oddaje strony od najnowszych, więc
stronicowanie kończy się po pokryciu okna (zwykle jedna strona).

- **„Synchronizuj teraz” w panelu** wysyła dane przeglądarki (nagłówki PSU) — jesteś obecny,
  więc te zapytania nie liczą się do limitu.
- **Przycisk `button.budget_sync_now` w HA** nie ma tych danych — liczy się do limitu.
- Jeśli okno transakcji nie zmieści się w limicie, nie trafia do księgi (żeby nie powstała
  luka) i pojawia się prośba o synchronizację z panelu.

Jeśli wcześniej używałeś CLI (`python -m budget.cli ingest-eb --live`) na tej samej sesji, po
przeniesieniu sesji do add-onu przestań — sesja i limit są wspólne.

## Kategorie i ekran „Wydatki”

Każda transakcja dostaje podkategorię automatycznie, w tej kolejności:

1. **ręcznie ustawiona** w panelu (Transakcje → kategoria w wierszu) — nic jej nie nadpisuje,
2. **zwrot** dostaje kategorię zakupu, do którego należy,
3. **Twoje reguły** (Reguły) — wygrywa pierwsza pasująca z góry listy,
4. **słownik sieci** wbudowany w add-on (ogólnopolskie sieci i marki, np. Biedronka, Orlen,
   Rossmann) i słowa ogólne („APTEKA”, „PARKING”),
5. **typ transakcji**: wypłata z bankomatu, opłata banku, rata kredytu.

Przelewy między Twoimi podlinkowanymi kontami (np. spłata karty) nie mają kategorii i nie liczą
się do wydatków. Przelew do osoby kategoryzuje odbiorca, nie tytuł — dodaj regułę na odbiorcę
(albo przy zmianie kategorii transakcji zaznacz **utwórz regułę**).

**Kategoria w wierszu Transakcji** — zapis domyślnie ustawia kategorię ręczną tylko tej
transakcji. Zaznaczenie **utwórz regułę** rozwija w miejscu pola reguły (te same co w zakładce
Reguły) z warunkiem „sprzedawca równa się …” i kierunkiem transakcji; podgląd pokazuje, ile
transakcji reguła obejmie. Reguła musi pasować do tej transakcji, a jej ręczna kategoria jest
zastępowana regułą.

**Reguły** mają warunki (sprzedawca/odbiorca, opis, kontrahent, konto kontrahenta; „zawiera”,
„równa się”, „zaczyna się od”; konto, typ, kierunek, zakres kwot) i podgląd na żywo: ile
transakcji pasuje, ile zmieni kategorię i ile ma kategorię ręczną. Zapis przelicza kategorie
całej historii (ręczne zostają).

**Wydatki** pokazują miesiąc kalendarzowy (po dacie transakcji): wydatki w kategoriach z udziałem
i zmianą względem poprzedniego miesiąca, wpływy, oszczędności, transakcje poza budżetem
(kategoria „Jednorazowe / poza budżetem”) i pozycje bez kategorii. Kwoty w PLN; transakcje
w innej walucie są na razie pomijane.

**Kategorie** (zakładka obok Reguł i Słownika): dodasz podkategorię albo nową kategorię główną
i zmienisz nazwę. Każdą podkategorię możesz **przenieść** do innej kategorii głównej (lista
„przenieś do…” pod nazwą). Razem z nią idą jej transakcje, reguły i słownik, a „Wydatki”
pokażą nowy podział od razu, także za poprzednie miesiące. Grupa budżetu (stałe, elastyczne…)
zostaje przy podkategorii; zmienisz ją listą przy podkategorii i **Ustaw** (przypisania
transakcji się nie zmieniają). Pustą kategorię główną (np. po przeniesieniu wszystkich jej
podkategorii) można usunąć.

## Budżet — „ile mogę jeszcze wydać”

Ekran **Budżet** odpowiada na jedno pytanie: ile zostało w tym miesiącu na **wydatki
elastyczne** (codzienne: jedzenie, paliwo, zakupy, wyjścia).

- **Pula automatyczna (z dochodu):** wpływy z poprzedniego miesiąca z podkategorii grupy
  „przychody” (tylko skategoryzowane) minus koszty stałe (suma median podkategorii stałych
  z 6 pełnych miesięcy). Pensja
  przychodzi pod koniec miesiąca, więc żyjesz z wypłaty poprzedniego miesiąca — pula jest znana
  od 1. dnia. Niższa wypłata (np. po przekroczeniu progu podatkowego) obniża pulę od następnego
  miesiąca, wyższa podnosi; nie ma tu średniej z dochodu. Oszczędności nie są odejmowane.
- **Z czego składa się pula:** w sekcji „Kwota budżetu” wpływy rozwijają się na źródła,
  a koszty stałe na podkategorie z medianą. To jedno miejsce na koszty stałe: „Przenieś”
  zdejmuje podkategorię ze stałych (do wybranej grupy), „Dodaj do stałych” dopisuje inną.
  Zmiana działa jak grupa w Kategoriach — na całą historię i od razu na pulę.
- **Premia poza pulą:** jeśli wpływ ze źródła (np. pracodawcy), które wpłacało co najmniej
  w 3 z ostatnich 12 miesięcy, przekracza 1,5 × górny kwartyl jego miesięcznych wpływów, do puli
  idzie mediana z ostatnich 3 miesięcy tego źródła, a nadwyżka zostaje poza pulą.
- Gdy główne źródło wpływów jest niższe o ponad 15% niż zwykle w tym roku, ekran dopisuje, że
  to prawdopodobnie przekroczony próg podatkowy (bez żadnych obliczeń podatku).
- **Kwota ręczna** nadpisuje automatyczną — od wybranego miesiąca do następnej zmiany (zmiana
  „od tego miesiąca” nie zmienia wcześniejszych); „Wróć do automatycznej” przywraca pulę
  z dochodu od danego miesiąca. Mediana wydatków elastycznych z 6 miesięcy jest pokazana obok.
- **Wydane** = podkategorie z grupy „elastyczne” (netto, zwroty zmniejszają) **plus wydatki bez
  kategorii** — ostrożnie, żeby „zostało” nie było zawyżone. Jeśli taki wydatek okaże się stały
  albo nieregularny, po skategoryzowaniu wraca do puli. Link prowadzi do kolejki „Do przejrzenia”
  dla tego miesiąca.
- **Stałe** (rachunki, subskrypcje, kredyt) i **nieregularne** (remont, podróże, prezenty) są
  pokazane obok i nie zmniejszają „zostało”; oszczędności, „poza budżetem” i przelewy między
  własnymi kontami nie są liczone wcale. Które podkategorie są elastyczne, ustawisz w Kategoriach.
- **Tempo:** kreska na pasku pokazuje, jaka część miesiąca minęła; „przy równym tempie do dziś”
  to kwota × dzień / dni miesiąca. „Na dzień” = zostało / dni do końca miesiąca (z dzisiejszym).
- Lista podkategorii elastycznych pokazuje wydane w miesiącu i „zwykle” (mediana z 6 miesięcy).

Jak „Wydatki”: miesiąc kalendarzowy po dacie transakcji, tylko PLN.

## Płatności cykliczne

Zakładka „Cykliczne”. Po każdej synchronizacji (i przyciskiem „Wykryj teraz”) add-on szuka w
historii serii: ten sam sprzedawca/odbiorca i kierunek, regularny odstęp (co miesiąc, co
kwartał, co rok) i podobna kwota; raty kredytu — po typie transakcji i koncie. Wykrywanie
działa lokalnie, bez AI.

- Wykryte serie to **propozycje**: „Potwierdź”, „Edytuj i potwierdź” (nazwa, kadencja,
  oczekiwana kwota, tolerancja, warunki — te same pola co w regułach) albo „Odrzuć”
  (odrzucona nie wróci).
- Strona serii pokazuje transakcje spełniające warunki; zmiana warunków działa od razu
  wstecz. Gdy transakcja pasuje do kilku serii, należy do tej o najbliższej kwocie.
- **Ten miesiąc** (początek zakładki, przełączany miesiąc): aktywne serie z terminem i statusem
  — zapłacone, oczekiwane (do 5 dni po terminie), spóźnione — oraz sumy „jeszcze zejdzie /
  wpłynie”. Ta sama linia jest na ekranie Budżet. Pula Flex się od tego nie zmienia.
- **Seria ręczna**: na Transakcjach „to się powtarza” otwiera formularz serii wypełniony
  z transakcji; seria jest od razu aktywna (to główna droga dla płatności rocznych).
- Seria roczna z dwoma wystąpieniami ma dopisek „mało historii”.
- „Zakończ serię” (np. wypowiedziana umowa) / „Przywróć”.

Na razie serie nie zmieniają budżetu — statusy „zapłacone / oczekiwane”, zmiany kwot i pula
z serii przyjdą w kolejnych wersjach.

## Dzwonek — do decyzji

Ikona dzwonka w pasku panelu z liczbą kart: transakcje bez kategorii z bieżącego miesiąca (i
poprzedniego, dopóki je ma), nowe propozycje serii, zgoda bankowa wygasająca w ciągu 30 dni
lub nieaktywna, nieudane synchronizacje, rozbieżność uzgodnienia salda. Karta prowadzi do
miejsca, gdzie sprawę się załatwia, i znika sama, gdy zostanie załatwiona.

## Kolejka „Do przejrzenia”

Zakładka zbiera wszystkie transakcje **bez kategorii** (to, co
skategoryzowała reguła albo słownik, nie wymaga potwierdzania). Nagłówek pokazuje pokrycie
wydatków kategoriami (% transakcji i % kwoty).

- **Sprzedawcy i odbiorcy** — grupa = sprzedawca/odbiorca + kierunek (wydatek i wpływ od tej
  samej osoby to osobne grupy), sortowanie po kwocie albo liczbie.
- **Zapis domyślnie bez reguły** — wybrana kategoria trafia jako **ręczna** do zaznaczonych
  pozycji (odznaczone zostają w kolejce). Ręczna kategoria jest trwała, ale obejmuje tylko te
  transakcje: przyszłe transakcje tego sprzedawcy pojawią się w kolejce jako nowe pozycje (chyba
  że skategoryzuje je słownik sieci albo typ).
- **Utwórz regułę** — zaznaczenie pokazuje pola reguły; zapis tworzy regułę (domyślnie
  „sprzedawca równa się … + kierunek”), więc także przyszłe transakcje skategoryzują się same.
  W tym trybie pozycje grupy wybierają warunki reguły (pola wyboru pozycji są nieaktywne);
  podgląd ostrzega, gdy reguła zmieni też już skategoryzowane pozycje.
- **Warunek reguły** — wiersz „reguła: [sprzedawca] [równa się] [nazwa]”. Nazwę
  można skrócić do fragmentu i wybrać „zawiera” albo „zaczyna się od” (np. „Qwerty” dla
  wszystkich sklepów sieci o nazwach „Qwerty 12”, „Qwerty-Sklep”…), a pole zmienić na opis/tytuł,
  kontrahenta albo konto kontrahenta. Fragment musi mieć co najmniej 3 znaki; podgląd na bieżąco
  podaje, ile pozycji z **innych grup** kolejki reguła złapie (z nazwami), a po zapisie link
  „odśwież listę” chowa te grupy.
- **Więcej warunków** — rozwijany blok pod wierszem reguły z tymi samymi polami co edytor
  w zakładce Reguły: drugi i trzeci warunek tekstowy, konto, typ, kierunek (domyślnie kierunek
  grupy, można wybrać „oba”), kwota od–do i nazwa sprzedawcy. Wszystkie warunki muszą być
  spełnione naraz (np. odbiorca „Jan Kowalski” **i** tytuł zawiera „składka” **i** kwota
  50–150 zł). Reguła musi złapać co najmniej jedną pozycję grupy; pozostałe zostają w kolejce —
  podgląd wymienia je przed zapisem, a po zapisie grupa zostaje otwarta z resztą. Tak rozbija się
  odbiorcę o mieszanym przeznaczeniu na kilka reguł. Podpowiedź AI sprzedawcy zamyka się dopiero,
  gdy reguła obejmie wszystkie jego pozycje w kolejce.
- **Filtr „Propozycja AI”** (gdy podpowiedzi AI są włączone) — pod zakładkami lista podkategorii
  z propozycji AI z liczbą grup, np. „Restauracje i kawiarnie (14)” (8 najliczniejszych, reszta
  pod „więcej”). Wybór zostawia grupy, które
  mają tę podkategorię wśród swoich (do 3) propozycji; grupy kraju są wtedy ukryte. Przy każdej
  grupie jest przycisk z ptaszkiem i nazwą podkategorii — dotknięcie nadaje tę kategorię
  **ręcznie** wszystkim pozycjom grupy (bez reguły) i chowa wiersz. Reguła, inna kategoria albo
  część pozycji — po rozwinięciu grupy, jak zwykle.
- **Zagranica** — sporadyczne płatności kartą za granicą, grupowane po kraju (z opisu
  transakcji) albo walucie, zwykle wyjazd: jedna decyzja, np. „Podróże”, dla całej grupy.
  Przycisk „reguła dla tego sprzedawcy” przy sprzedawcy zaznacza „utwórz regułę” i wpisuje go do
  warunku — reguła obejmie tylko jego pozycje, reszta grupy zostaje w kolejce.
  Zagraniczny sprzedawca obecny w co najmniej 3 różnych miesiącach (subskrypcja, doładowania)
  jest wśród zwykłych sprzedawców.
- **Widok miesiąca** — „Nieskategoryzowane” na ekranie Wydatki otwiera kolejkę zawężoną do
  oglądanego miesiąca (`/review?month=RRRR-MM`, przejście « » między miesiącami, link „wszystkie
  miesiące”). Reguła zapisana z tego widoku działa we wszystkich miesiącach — podgląd podaje,
  ile pozycji spoza miesiąca obejmie; żeby skategoryzować tylko ten miesiąc, zapisz bez „utwórz
  regułę”.

## Podpowiedzi kategorii z AI (opcjonalnie)

Add-on może pytać model językowy o kategorię dla sprzedawców z kolejki „Do przejrzenia”,
przez router zgodny z API OpenAI (np. lokalny router freellmapi w sieci domowej).
Włączenie: opcje `ai_base_url` (np. `http://<host>:3003/v1`), `ai_api_key`, `ai_model`
(nazwany model — `auto` nie obsługuje odpowiedzi według schematu) i `ai_daily_calls`.

**Co trafia do modelu** — i nic poza tym:
- płatności kartą i BLIK: nazwa sprzedawcy i opis transakcji;
- przelewy, zlecenia, polecenia zapłaty itp.: tylko tytuł, **bez nazwy odbiorcy** (także
  odmienionej w tytule);
- zawsze: rodzaj operacji, kierunek, kwota jako przedział (np. „20–100 zł”), liczba transakcji;
- lista Twoich kategorii i przykłady „sprzedawca kartowy → kategoria” z Twoich decyzji.

Z tekstów wycinane są IBAN-y, numery kont i kart, e-maile, telefony, kody pocztowe, daty i inne
ciągi cyfr. Router może przekazywać zapytania do zewnętrznych dostawców (darmowe plany bywają
używane do trenowania modeli) — włącz tylko, jeśli to akceptujesz.

Działanie: po każdej synchronizacji, w tle, do 3 wywołań po 40 sprzedawców (w limicie
`ai_daily_calls`); o tego samego sprzedawcę nie pyta drugi raz. Karta **Podpowiedzi AI** na
ekranie Status pokazuje wywołania, ostatni błąd i liczbę podpowiedzi; **Podpowiedz teraz**
uruchamia przebieg od razu, **Zmierz trafność** pyta o do 80 sprzedawców, którzy już mają
kategorię (najpierw Twoje ręczne i reguły, potem słownik), i pokazuje trafność pierwszej
propozycji, trafność „wśród 3” i zgodność kategorii głównej według progu pewności.

**Gdzie widać podpowiedzi:** model podaje do 3 propozycji kategorii na sprzedawcę, od
najpewniejszej. Decyzja jest zawsze Twoja:
- **Do przejrzenia** — pod nazwą sprzedawcy przyciski „AI: …”; dotknięcie rozwija grupę
  z wybraną kategorią i podglądem reguły, zapisujesz jak zwykle („Zapisz”). W grupach krajów
  propozycje są przy każdym sprzedawcy jako tekst. Przycisk **Podpowiedz teraz (AI)** liczy
  propozycje bez czekania na synchronizację.
- **Transakcje** — w formularzu kategorii transakcji bez kategorii; dotknięcie ustawia wybór.

Zapis kategorii sprzedawcy w kolejce oznacza podpowiedź jako przyjętą (wybrano jedną
z propozycji) albo odrzuconą (inna kategoria) — liczniki na karcie AI na ekranie Status.

## Encje

| Encja | Opis |
|---|---|
| `sensor.budget_saldo_<rodzaj>_<waluta>` | Dostępne środki (ITAV) na koncie; ITBD i zamaskowany numer w atrybutach. Dla karty kredytowej ITAV to dostępny limit |
| `sensor.budget_consent_days_left` | Dni do wygaśnięcia zgody bankowej |
| `sensor.budget_last_sync` | Ostatnia udana synchronizacja (wynik ostatniej próby w atrybutach) |
| `binary_sensor.budget_sync_problem` | Brak zgody albo nieudane synchronizacje |
| `sensor.budget_requests_today` | Diagnostyka: najwięcej zapytań dziś na (konto, endpoint) bez PSU |
| `button.budget_sync_now` | Synchronizacja na żądanie (w ramach limitu) |
| `sensor.budget_flex_budget` | Pula elastyczna w bieżącym miesiącu (ręczna albo z dochodu); w atrybutach `source` (`manual`/`auto`), `auto_amount`, `income_base`, `bonus_excluded`, `fixed_median`, `income_drop_pct`, mediana wydatków `suggested` |
| `sensor.budget_flex_spent` | Wydane elastyczne (z wydatkami bez kategorii — liczba i kwota w atrybutach) |
| `sensor.budget_flex_remaining` | Zostało; w atrybutach `per_day`, `expected_today` (przy równym tempie), `over_pace`, `used_pct`, `days_left` |
| `sensor.budget_flex_per_day` | Zostało na dzień do końca miesiąca (z dzisiejszym) |
| `sensor.budget_inbox` | Liczba kart w dzwonku panelu; atrybut `items` — lista (`kind`, `title`, `count`, `severity`) |
| `sensor.budget_fixed_paid` | Wydatki z aktywnych serii zapłacone w bieżącym miesiącu; atrybut `items` (nazwa, termin, kwota, status) i liczniki |
| `sensor.budget_fixed_planned` | Wydatki z serii, które jeszcze zejdą w tym miesiącu (oczekiwane + spóźnione) |
| `sensor.budget_income_planned` | Wpływy z serii, które jeszcze wpłyną; atrybut `received` — już wpłynęło |

Encje budżetu liczone są jak ekran Budżet dla bieżącego miesiąca. Bez kwoty ręcznej i bez
wpływów w poprzednim miesiącu `flex_budget`, `flex_remaining` i `flex_per_day` mają stan
„nieznany”. Odświeżają się po
synchronizacji, kilka sekund po każdym zapisie w panelu i tuż po północy. Nie mają statystyk
długoterminowych (historia stanów — tak).

## Powiadomienia

Powiadomienie w HA (i opcjonalnie przez `notify_service`) gdy: zgoda wygasa w ciągu
`consent_warning_days` dni, zgoda wygasła lub została cofnięta, 3 synchronizacje z rzędu się
nie udały, okno transakcji nie zmieściło się w limicie. Aktywne powiadomienie jest
przypominane raz na dobę i znika samo, gdy problem ustąpi.

## Podsumowania na telefon

Opcja `summary_notify_service` (np. `notify.<grupa>`; puste = wyłączone) włącza dwie wiadomości
o 7:00:

- **w poniedziałek** — ile zostało z puli i ile na dzień, tempo względem planu (do wczoraj),
  top 3 kategorie minionego tygodnia (wydatki elastyczne i bez kategorii), płatności cykliczne
  do zapłaty w 7 dni, liczba do przejrzenia;
- **1. dnia miesiąca** — zamknięcie poprzedniego miesiąca: wydane z puli, top 3 kategorie,
  liczba do przejrzenia.

Dotknięcie wiadomości otwiera panel. Jeśli add-on nie działał o 7:00, wiadomość wychodzi po
starcie tego samego dnia (bez dubli). Podgląd obu wiadomości i „Wyślij teraz” — ekran Status.

## Kalendarz płatności

Add-on wystawia `http://<nazwa hosta add-onu>:8099/calendar.ics` (nazwa hosta to slug z `-`
zamiast `_`, np. `abcd1234-budget`): terminy aktywnych serii cyklicznych od początku miesiąca do
60 dni naprzód, z kwotą i statusem (zapłacone, spóźnione…). Adres odpowiada tylko Home Assistant
Core — panel nadal tylko przez Ingress.

1. Ustawienia → Urządzenia i usługi → Dodaj integrację → **Remote Calendar**, URL jak wyżej.
2. Wpisz utworzoną encję (np. `calendar.platnosci`) w opcji `calendar_entity` — add-on odświeży
   ją po każdej synchronizacji (sama integracja pobiera kalendarz rzadko).

## Odnowienie zgody

Zgoda PSD2 jest ważna maksymalnie 180 dni. Przed wygaśnięciem: **Bank → Odnów zgodę** —
ten sam przepływ co „Połącz bank”; nowa zgoda zastępuje starą, historia zostaje.
