# M10 E5–E7 — konto Profit: monitor edycji promocji, szczegóły miesięcy, preset warunków

## Cel
Konto oszczędnościowe Profit (Bank Millennium) ma promocję „Nowe środki na Koncie Oszczędnościowym Profit”
(edycje co ~6 tygodni, okres promocyjny 91 dni od przystąpienia). Oprocentowanie promocyjne dostają tylko nowe
środki: nadwyżka nad saldem z dnia badania sald (osobno na KOP i łącznie na rachunkach w banku). Plan
użytkownika: zerować Millennium przed dniem badania, potem wpłacić środki i aktywować promocję. Decyzja do
napędzenia: **kiedy wyprowadzić środki poza Millennium**.

## Fakty (regulamin ed. 77, wyciągnięty z PDF 2026-10-12; źródło: stały adres regulaminu na bankmillennium.pl)
- Dzień badania sald 4.09.2026, przystąpienie 11.09–21.10.2026, okres promocyjny 91 dni, nowe środki do 200 000 zł.
- Stawki: promocyjna 1,5% + premiowa 2,75% (konto otwarte do 4.09) lub 3,75% (od 5.09), razem do 4,25% / 5,25%;
  standardowa 0,5% (stare środki, powyżej 200 tys., po okresie promocyjnym); premia wymaga 5 płatności kartą/BLIK
  w każdym miesiącu. Odsetki wypłacane w nocy na przełomie miesięcy.
- Dzień badania bank publikuje 3–10 dni po fakcie (ed. 65: badanie 17.01.2025, wpis 27.01; ed. 66: 7.03.2025, wpis
  10.03). Odstęp badania od końca przystępowania poprzedniej edycji: 0 d (65→66), −5 d (75→76), −6 d (76→77).
  Okno następnej edycji (78): 15–21.10.2026 (do potwierdzenia).

## Ograniczenia z wywiadu
- Wynik: tylko użytkownik (dzwonek + push). Automatycznie: odczyt regulaminu, prognoza okna, przypomnienia.
  Za zgodą: wydanie i instalacja. Bank widzi tylko użytkownik — add-on niczego nie przelewa.
- Nowe środki wpisuje ręcznie przy aktywacji (próg = 0, bo konto zerowane). Warunek premii zakładany jako spełniony.
- Sukces: ostrzeżenie z oknem przed dniem badania; po publikacji — potwierdzona data; odsetki zgodne z bankiem.

## Etapy (E7 → E5 → E6)
1. **E7 Monitor edycji (0.41.0, pilne):** moduł `promo_watch` — codzienny odczyt regulaminu (`pypdf` w
   `requirements.txt` add-onu, bez AI), parsowanie numeru edycji, dnia badania, końca przystępowania, stawek;
   zapis w `kv`; wykrycie nowej edycji → karta/push „bank potwierdził dzień badania sald …”; prognoza okna
   następnej edycji i karta/push „wyzeruj Millennium od … do …”; alarm w dzwonku, gdy regulaminu nie da się
   odczytać; ręczna korekta daty.
2. **E5 Szczegóły miesięcy:** wiersze „Stopy oszczędności” rozwijane (`<details>`), w środku wpłaty i wypłaty
   per konto (data, kwota, konto).
3. **E6 Preset Profit:** przycisk w formularzu konta wypełnia warunki z ostatnio odczytanego regulaminu
   (stawka standardowa, promocyjna wg daty otwarcia, limit, koniec = aktywacja + 91 dni).
   E5 + E6 = jedno wydanie 0.42.0.

## Ryzyka
- Zmiana układu regulaminu → alarm i ręczna data. Nowe połączenie wychodzące (1 plik dziennie).
- Premia zakładana — odsetki mogą być zawyżone, gdy warunek nie jest spełniony.
- Prognoza okna z 3 odstępów; potwierdzenie przychodzi po fakcie.

## Wynik (2026-10-12)

E7, E5, E6 wydane razem jako 0.42.0 (użytkownik wybrał „najpierw E5 i E6”, bez osobnego 0.41.0).
Odchylenia od planu: (1) zamiast ręcznej korekty daty badania jest przycisk „Sprawdź teraz”;
(2) preset E6 to formularz aktywacji bez parsowania stawek z regulaminu — stawka łączna wpisywana ręcznie
(5,25% lub 4,25% zależnie od daty otwarcia konta), 91 dni bierze się z odczytanego regulaminu;
(3) okno prognozy sprawdza się po fakcie (luka badania względem końca poprzedniej edycji → log i uwaga
w push). Znane ograniczenie: warunek 5 płatności miesięcznie zakładany jako spełniony.
