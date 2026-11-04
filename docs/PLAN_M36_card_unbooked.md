# Karta kredytowa: „do spłaty” liczy nieksięgowane zakupy z bieżącego cyklu

## Context
Panel Budżetu (0.73.1) i `sensor.budget_card_due` pokazują 1 969,65 zł do spłaty do 20.11, czyli całe
obecne zadłużenie (`debt` = `left`). W księdze nie ma żadnego obciążenia karty zaksięgowanego w listopadzie
(licznik płatności 0/5, ostatni zakup 27.10). Cykl październikowy jest praktycznie wyzerowany: obciążenia
2 301,14 − spłaty 2 202,81 − zwrot 100 = −1,67 zł. Te 1 969,65 zł to listopadowe autoryzacje, które są już
w ITBD, ale bank ich jeszcze nie zaksięgował (API Millennium nie zwraca PDNG, zob. `docs/FINDINGS_millennium.md:21`).

Regulamin kart kredytowych Millennium (umowy od 20.10.2021, akt. 1.04.2025) mówi:
- definicja 68: Wyciąg obejmuje kwoty **zaksięgowane** w danym cyklu,
- § 13 ust. 2: transakcja jest rozliczana najpóźniej następnego dnia roboczego po żądaniu od akceptanta, a do tego czasu tylko blokuje limit,
- § 20 (odsetki), pkt 2: odsetek od transakcji bezgotówkowych nie ma, jeśli saldo z Wyciągu spłacisz w całości przed Terminem spłaty.

Zakupy z listopada trafią więc na wyciąg listopadowy z terminem 20.12. Wynik powinien wynosić ~0 zł.

Przyczyna w kodzie: `card.due_status` (`budget/app/src/budget/card.py`) liczy `left = ITBD − obciążenia BOOK od 3. dnia cyklu`.
Autoryzacje w ITBD, których nie ma w księdze, liczy jako dług z zamkniętego cyklu. To ryzyko odnotowano w `PLAN_M15.md` (E4).

## Zmiana (repo `/config/addons/ha-budget-app`, `main`, wydanie 0.73.2)
1. `card.due_status`: odjąć część ITBD bez pokrycia w księdze.
   - `ledger_debt` = zadłużenie z księgi: bazowa migawka ITBD (ta sama, której używa kontrola karty:
     `ledger.py` ~l.1011, funkcja bazy kontroli) − suma podpisanych kwot BOOK konta karty po migawce bazowej.
   - `unbooked = max(0, ITBD − ledger_debt)` (autoryzacje).
   - `left = max(0, ITBD − unbooked + new)`, gdzie `new` jak dziś (obciążenia BOOK od dnia 3 cyklu).
   - Bez bazy kontroli zostaje obecne zachowanie.
   - `debt` (zadłużenie z banku) się nie zmienia. Nowy atrybut/wiersz: „nieksięgowane (bieżący cykl)”.
2. Tekst na ekranie Karta: „zadłużenie z banku minus nieksięgowane i zakupy zaksięgowane w tym cyklu”.
3. Testy (`tdd`): autoryzacja bez księgowania → `left` 0; zakup z 1.–2. dnia → nadal w wyciągu;
   spłata częściowa; brak bazy → stare zachowanie; dryf bazy (rozbieżność 1,67) nie daje fałszywego „do spłaty”.
4. `simplify` → `code-review` (+ `silent-failure-hunter`, `pr-test-analyzer`) → `release` 0.73.2 (backup add-onu).

Ryzyko: jeśli baza kontroli się rozjedzie (brak księgowania w API), wynik może wyjść zaniżony.
Zabezpieczenie: gdy kontrola karty (`check_balances`) pokazuje rozbieżność, wracamy do obecnego, ostrożnego wzoru.

## Weryfikacja
- pytest + ruff + mypy w repo.
- Na żywo po instalacji: `sensor.budget_card_due` ≈ 0, `/card` przez Ingress: „Spłacone”, konsola bez błędów.
- Kontrola 20.11 i 20.12: porównanie z „kwotą do spłaty” w aplikacji banku.

Rollback: revert commitu + 0.73.3 albo backup add-onu 0.73.1.
