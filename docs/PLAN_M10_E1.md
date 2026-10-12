# M10 E1 — Skarbonki

## Context
Koszty roczne i nieregularne (subskrypcje roczne, wakacje, przeglądy) zaskakują w miesiącu, w którym
schodzą. Serie roczne liczą się dziś w kosztach stałych puli jako 1/12 (`recurring/series.py`), ale nic
tych pieniędzy nie odkłada. Bank pozwala zakładać konta oszczędnościowe na cele; Enable Banking ich nie
widzi (`FINDINGS_millennium.md`: tylko rachunek bieżący, EUR, karta), ale widzi przelewy na nie
z rachunku bieżącego (`txn.counterparty_account`).

Decyzje z wywiadu (2026-10-12, decyzja 25):
- skarbonka = nazwa + numer konta-celu + kwota celu + termin, tworzona ręcznie (dla kosztów stałych
  i innych); opcjonalna seria cykliczna podpowiada cel (oczekiwana kwota) i termin (następna płatność);
- saldo = saldo początkowe + przelewy na numer konta-celu − przelewy z niego;
- zalecane odłożenie miesięczne = (cel − saldo) / miesiące do terminu (≥ 0);
- nieprzelane odłożenie w bieżącym okresie wypłaty wchodzi do prognozy M8 jako planowany przelew,
  dzwonek przypomina, gdy do wypłaty < 5 dni;
- wydatki przypisuje się do skarbonki ręcznie (jak osobę przy karcie, M15 E2); przelewy na konta-cele
  i wydatki ze skarbonki nie liczą się do puli Flex;
- widok: ekran „Skarbonki” + kafelek na Podsumowaniu; bez encji HA; źródło dla czatu w M12 E3b.

Ograniczenia:
- korzysta użytkownik w panelu (telefon);
- automatycznie: saldo, zalecana kwota, rezerwacja w prognozie, przypomnienie; ręcznie: tworzenie,
  edycja, przypisanie wydatków, sam przelew w banku;
- numery kont tylko w bazie, w UI maskowane; w testach fikcyjne numery;
- sukces: skarbonka z numerem konta-celu pokazuje saldo z historii przelewów; limit dzienny „Do wypłaty”
  spada o nieprzelane odłożenie i wraca po przelewie.

## Etapy (wydanie 0.39.0 razem z M21 E4–E5)

### E1a — model i ekran
- Migracja `013_piggy.sql` (addytywna): tabela `piggy` (nazwa, numer, cel, termin, seria, saldo
  początkowe, archiwizacja) i `txn.piggy_id` (ręczne przypisanie wydatku).
- Moduł `budget/piggy.py`: zapis z walidacją numeru, przelewy po numerze, stan (saldo, zalecane
  miesięcznie, odłożone w okresie, wydane ze skarbonki), podpowiedź z serii.
- Flex: przelewy na/z kont-celów i wydatki przypisane do skarbonki w `skip`.
- Panel: ekran `/piggy` (lista + formularz), pole „Skarbonka” przy wydatku w Transakcjach.
- Najpierw sprawdzić na produkcji, czy przelewy na konta-cele z API mają `counterparty_account`;
  jeśli nie — stop i decyzja (tytuł albo ręczne przypisanie).

### E1b — prognoza i Podsumowanie
- Prognoza: zdarzenie „Do skarbonek” na dziś = Σ max(zalecane − odłożone od początku okresu, 0);
  wydatek serii powiązanej ze skarbonką o wystarczającym saldzie nie obniża prognozy.
- Dzwonek: „Odłóż X zł do skarbonek”, gdy do wypłaty < 5 dni.
- Kafelek „Skarbonki” w siatce Podsumowania (M16).

## Weryfikacja
pytest, ruff, mypy; lokalny panel na kopii bazy + Playwright (360 px, konsola); po wydaniu stan add-onu,
screenshot przez Ingress i pierwsza skarbonka użytkownika.
