# M8 — Prognoza: czy starczy do wypłaty

Wywiad 2026-10-06. Start po M15 E1 (`PLAN_M15.md`).

## Cel i ograniczenia

1. **Cel:** odpowiedź na pytanie „czy starczy do wypłaty” — wolne środki dzień po dniu do
   najbliższej wypłaty i najniższy punkt po drodze.
2. **Horyzont (decyzja 2026-10-06, dwukrotnie zmieniona):** do terminu **wypłaty wskazanej przez
   użytkownika** (przełącznik na serii przychodów; dzień resetu, ~24.); bez wskazania — seria
   przychodów o największej kwocie, bez serii — koniec miesiąca. Mniejsze wpływy przed wypłatą
   wchodzą do salda; spóźniony wpływ nie jest wypłatą i nie zwiększa salda.
3. **Wolne środki dziś** = saldo rachunku PLN − bieżące zadłużenie karty (`ITBD`). Rachunek EUR
   obok jako informacja, poza wynikiem (bez kursów walut).
4. **Przyszłość:** pozostałe wydatki serii w ich terminach; reszta puli Flex rozłożona równo na
   dni (pula przekroczona → dotychczasowe tempo na dzień); wpływy serii w ich terminach.
5. **Automatycznie:** wpis w dzwonku + encje, gdy najniższy punkt przed wypłatą < bufor (opcja
   add-onu `forecast_buffer`, domyślnie 0). Bez powiadomień z add-onu — ewentualnie automatyzacja
   w HA na encji.
6. **Sukces:** na Podsumowaniu kwota na dzień wypłaty i najniższy punkt z datą; na produkcji wynik
   zgadza się z rachunkiem ręcznym (saldo − karta − serie − reszta Flex + wpływy).

## Widok — rozbicie obowiązkowe

Zadłużenie karty ma być jawnie widoczne jako pomniejszenie wolnych środków:

```
Saldo rachunku PLN
− Zadłużenie karty            (stan z banku, godzina odczytu)
= Wolne środki dziś
− Serie do wypłaty (N)
− Reszta puli Flex
+ Wpływy przed wypłatą
= Na dzień wypłaty (data)     · najniższy punkt: kwota (data)
```

Każdy wiersz z kwotą; wiersz karty widoczny także przy zadłużeniu 0 zł. Odczyt sald starszy niż
doba → dopisek.

## Założenia do sprawdzenia

- Horyzont przechodzący na następny miesiąc: dni z nowego miesiąca liczone pulą na dzień
  z bieżącego.
- Wydatki już zrobione są w saldzie i zadłużeniu karty — nie liczą się drugi raz.
- Saldo i zadłużenie z ostatniej migawki (synchronizacja 3×/dobę).

## Etapy

- **E1:** moduł `forecast.py`, sekcja „Do wypłaty” na Podsumowaniu (rozbicie + prosty wykres
  dzienny), opcja `forecast_buffer`.
- **E2:** encje `sensor.budget_forecast_*` (w tym zadłużenie karty) i `binary_sensor` zagrożenia,
  wpis w dzwonku i `sensor.budget_inbox`.

Numery wersji ustalane przy planie kroków etapu (po M15 E1 = 0.23.0).
