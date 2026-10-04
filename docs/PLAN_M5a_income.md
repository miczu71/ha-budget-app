# M5a etap 3 — pula elastyczna z dochodu (0.12.0)

Decyzja 14 w [`ROADMAP.md`](ROADMAP.md) (zmienia decyzję 13). W tym samym wydaniu: poprawka
kontroli salda karty (diagnoza 2026-10-04, niżej).

## Dlaczego

Pula ustawiana ręcznie (etap 1) nie widzi dochodu. Wynagrodzenie netto zmienia się w ciągu roku:
po przekroczeniu progu podatkowego przelewy pensji wyraźnie spadają do końca roku, a w styczniu
wracają. Miesiąc przekroczenia przesuwa się z roku na rok, więc stała data nie działa, a średnia
z dochodu zawyża pulę po progu i zaniża ją po styczniu.

## Zasady (wywiad 2026-10-04)

1. **Pula miesiąca M = wpływy z M−1 − stałe.**
   - Wpływy: transakcje z podkategorii grupy `income` (tylko skategoryzowane — wpływ bez
     kategorii nie zasila puli), te same filtry co „Wydatki” (zaksięgowane, bez przelewów
     wewnętrznych, konta „w budżecie”, PLN), miesiąc po dacie transakcji.
   - Pensja przychodzi pod koniec miesiąca za ten sam miesiąc, więc żyje się z wypłaty
     poprzedniego miesiąca: pula jest znana 1. dnia i nie zmienia się w trakcie.
   - Stałe: mediana grupy `fixed` z `HISTORY_MONTHS` pełnych miesięcy przed M (jak mediany
     etapu 1).
   - Oszczędności nie są odejmowane — oszczędza się to, co zostanie.
   - Wynik ujemny → pula 0 (ekran mówi dlaczego). Brak wpływów w M−1 → brak puli auto.
2. **Spadek po progu bez średniej:** pula idzie za faktyczną wypłatą z M−1 — niższa wypłata
   obniża pulę od następnego miesiąca, wyższa podnosi.
3. **Premia poza pulą.** Źródło wpływu = sprzedawca/kontrahent. Dla źródła z co najmniej
   `BONUS_MIN_MONTHS` (3) miesiącami wpływów w ostatnich 12 pełnych miesiącach przed M−1: jeśli
   wpływ w M−1 > `BONUS_RATIO` (1,5) × mediana miesięcznych wpływów tego źródła z tych 12
   miesięcy, do puli idzie mediana z ostatnich 3 miesięcy źródła sprzed M−1, a nadwyżka zostaje
   poza pulą („premia: X zł poza pulą”). Źródła z krótszą historią liczą się w całości.
   Mediana z 12 miesięcy obejmuje miesiące przed i po progu, więc styczniowy powrót do wyższej
   pensji nie jest brany za premię.
4. **Ręczna kwota nadpisuje.** Wpis w `flex_budget` od miesiąca (jak dotąd) ma pierwszeństwo;
   wpis z pustą kwotą (migracja 007: `amount` NULL) = „wróć do automatycznej” od miesiąca.
   Ekran pokazuje kwotę automatyczną także przy ręcznej.
5. **Dopisek o progu** (informacja, bez obliczeń podatkowych): gdy główne źródło wpływów
   (największa suma w 12 mies.) w M−1 jest niższe o ponad `DROP_RATIO` (15%) od mediany swoich
   wpływów z wcześniejszych miesięcy tego samego roku (bez miesięcy z premią) — „wpływ z <źródło>
   niższy o X% — prawdopodobnie próg podatkowy; zwykle wraca w styczniu”.

## Zmiany

| Plik | Zmiana |
|---|---|
| `storage/migrations/007_flex_budget_auto.sql` | `flex_budget.amount` NULL-owalne (przebudowa tabeli) |
| `flex.py` | `AutoBudget` + `auto_budget(conn, month)`; `budget_for` zwraca też wpis „auto”; `FlexMonth.budget` = ręczna albo auto, nowe `budget_source`, `auto`; `set_budget(..., None)` |
| `web/routes_budget.py`, `templates/budget.html` | rozbicie puli auto (wpływy M−1, premia poza pulą, stałe), dopisek o progu, „wróć do automatycznej” |
| `ha_publisher.py` | `budget_flex_budget` z wartością auto; atrybuty `source`, `income_base`, `bonus_excluded`, `fixed_median` |
| `ledger.py` (kontrola karty) | patrz niżej |

## Poprawka: kontrola salda karty

Diagnoza (2026-10-04): „ROZBIEŻNOŚĆ” na karcie to błąd kontroli, nie księgi. Konto bez salda
otwarcia porównywało zmiany ITBD ze zmianami sumy transakcji od pierwszej migawki.
1. ITBD karty to **zadłużenie (dodatnie)** — zakup podnosi je, a w księdze jest ujemny; kontrola
   porównywała zmiany z tym samym znakiem.
2. ITBD obejmuje autoryzację, zanim API pokaże transakcję (Millennium zwraca tylko
   zaksięgowane), a uznania (np. zwrot) potrafią trafić do ITBD później niż do API. Pierwsza
   migawka złapana „w drodze” psuła bazę na stałe.

Poprawka: dla kont bez salda otwarcia zmiana banku = −zmiana księgi; różnica utrzymująca się
krócej niż `IN_TRANSIT_DAYS` (3) od jej pojawienia się = „w drodze”, nie rozbieżność; baza
kontroli karty do ustawienia przyciskiem na Status („przyjmij tę migawkę jako bazę”,
tabela/ustawienie w bazie). Po wdrożeniu baza na migawkę, od której bank i księga się zgadzają.
Pozostaje znana stała różnica rzędu złotówek (niewidoczna ani w API, ani w historii karty w
bankowości) — obserwacja w `FINDINGS_millennium.md`.

## Testy (dane syntetyczne)

- spadek wypłaty w M−1 → niższa pula w M; wzrost w styczniu → nie premia;
- wpływ 3× mediany → nadwyżka poza pulą, do puli mediana z 3 mies.; źródło z krótką historią
  w całości;
- stałe = mediana; ujemny wynik → 0; brak wpływów w M−1 → brak puli auto;
- ręczna nadpisuje, „wróć do automatycznej” przywraca auto od miesiąca, wcześniejsze bez zmian;
- dopisek o progu: pojawia się przy spadku > 15% względem wcześniejszych miesięcy roku;
- karta: zakup widoczny w ITBD przed API → „w drodze”, po zaksięgowaniu OK; znak zadłużenia;
  różnica dłuższa niż 3 dni → rozbieżność; baza z przycisku.

## Akceptacja

Pula na bieżący miesiąc policzona ręcznie z księgi = ekran; `sensor.budget_flex_budget`
z wartością i atrybutami; kontrola karty OK (albo „w drodze”) zamiast rozbieżności; panel
w Playwright przez Ingress (zrzut + 0 błędów konsoli); skan pre-commit czysty.
