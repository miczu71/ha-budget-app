# M15 — Karta kredytowa

Wywiad 2026-10-06 (dopisany do roadmapy w trakcie wywiadu M8). Kolejność: **M15 E1 → M8 → M15 E2**
— licznik jest mały, niezależny od prognozy i daje wartość już na koniec bieżącego miesiąca.

## Co daje bank (`FINDINGS_millennium.md`)

- Zakupy kartą = transakcje API na koncie karty → licznik w całości z księgi.
- `ITBD` karty = bieżące zadłużenie (używa go też M8).
- Limitu nie ma wprost; `ITAV` (dostępne) jest opóźnione, więc ITAV + ITBD to tylko przybliżenie.
- Brak daty zamknięcia cyklu, terminu spłaty i kwoty minimalnej — to muszą być ustawienia.

## E1 — licznik zakupów (0.23.0)

### Cel i ograniczenia

1. **Cel:** karta jest bezpłatna przy co najmniej 5 zakupach w miesiącu; add-on pilnuje, żeby
   warunek był spełniony, zanim miesiąc się skończy.
2. **Okres:** miesiąc kalendarzowy.
3. **Co się liczy:** każde obciążenie karty będące zakupem bezgotówkowym. Nie liczą się: spłaty,
   wypłaty gotówki, opłaty, odsetki. Zwroty nie odejmują. Karta dodatkowa się liczy (i tak jej
   nie odróżniamy — decyzja 2).
4. **Automatycznie:** licznik w panelu i encja zawsze aktualne; jeśli 5 dni przed końcem miesiąca
   zakupów jest mniej niż 5 — jedno powiadomienie przez `summary_notify_service` (jak M6) + wpis
   w dzwonku; drugie przypomnienie dzień przed końcem, jeśli nadal brakuje. Każde wysyłane raz
   (znacznik w `kv`, nadrabianie po restarcie tego samego dnia).
5. **Sukces:** licznik zgadza się z listą zakupów karty w bankowości; przy braku zakupów
   powiadomienie dociera na telefony we właściwym dniu.

### Założenia do sprawdzenia

- API podaje tylko datę księgowania i datę waluty — licznik liczy po **dacie waluty** (bliższej
  dacie zakupu). Zakup z ostatnich dni może dotrzeć do API z opóźnieniem (ITBD wyprzedza API),
  więc panel pokazuje dopisek o zapasie w końcówce miesiąca.
- Rozpoznanie „zakupu”: `kind` transakcji na koncie karty (spłata = przelew z M2, opłaty/odsetki
  i gotówka po typie/opisie). Sprawdzić na kopii księgi przed kodem: lista miesięcy z liczbą
  zakupów vs historia w bankowości (użytkownik).

### Zakres

- Moduł licznika (miesiąc → liczba zakupów, lista, próg 5 jako stała).
- Panel: kafelek na Podsumowaniu („Karta: N/5 zakupów w tym miesiącu”).
- Encja `sensor.budget_card_purchases_month` (atrybuty: próg, brakuje, miesiąc).
- Terminy powiadomień w pętli obok podsumowań M6; wpis w dzwonku i `sensor.budget_inbox`.

Dokładne kroki (pliki, migracja, testy, wydanie) — do akceptacji przed startem E1.

## E2 — limit i okres bezodsetkowy (zarys, osobny wywiad)

- Limit wpisany ręcznie; ITAV + ITBD obok do porównania.
- Dzień zamknięcia cyklu i termin spłaty w ustawieniach.
- Kwota do spłaty z zamkniętego cyklu (żeby nie płacić odsetek) i dni do terminu; wykorzystanie
  limitu. Kanał przypomnienia o terminie — do wywiadu.
