# M5a etap 4 — składniki puli i edycja kosztów stałych na ekranie „Budżet” (0.13.0)

Decyzja 15 w [`ROADMAP.md`](ROADMAP.md) (zmienia sposób liczenia stałych z decyzji 14).

## Dlaczego

Sekcja „Kwota budżetu” pokazuje tylko dwie sumy: wpływy i koszty stałe. Nie widać, z czego się
składają, więc trudno ocenić, czy pula automatyczna jest trafna. Grupę „stałe” ustawia się
osobno przy każdej podkategorii w Kategoriach, rozrzuconej po kategoriach głównych — nie ma
jednego miejsca, gdzie widać i poprawia się listę kosztów stałych.

## Zasady (wywiad 2026-10-04)

1. **Koszt stały = podkategoria z grupą `fixed`.** Bez ręcznie wpisanych pozycji (płatności
   cykliczne to M5b).
2. **Stałe w puli = suma median podkategorii** z `HISTORY_MONTHS` pełnych miesięcy (miesiąc bez
   wydatków w podkategorii = 0), zamiast mediany sumy miesięcznej. Składniki sumują się dokładnie
   do kwoty w puli, a zdjęcie podkategorii ze stałych zmienia pulę dokładnie o jej medianę.
   Pula automatyczna przesunie się względem 0.12.0 — to zmiana metody, nie błąd.
3. **Edycja w rozwinięciu na Budżecie** (sekcja „Kwota budżetu”):
   - „Wpływy” rozwija się na źródła z kwotami; przy premii — część poza pulą.
   - „Koszty stałe” rozwija się na podkategorie z medianami; przy każdej wybór innej grupy
     (domyślnie elastyczne) i „Przenieś”; na dole „dodaj do stałych” z listą pozostałych
     podkategorii wydatkowych z medianą > 0 (malejąco).
   - Zmiana grupy działa jak w Kategoriach: na całą historię i od razu na pulę (dopisek w UI).
   - Po zapisie rozwinięcie stałych zostaje otwarte (`?fixed=1#fixed`).
   - Blok widoczny także przy kwocie ręcznej (pula automatyczna jest wtedy informacyjna).

## Zmiany

- `flex.py`: `FixedLine(category, parent, median)`; `AutoBudget.fixed_lines`,
  `AutoBudget.candidates`; `fixed = sum(median)`.
- `routes_budget.py`: `POST /budget/fixed/{category_id}` (`flex_group`, `month`) →
  `taxonomy.set_flex_group`; `GET /budget?fixed=1` otwiera rozwinięcie.
- `budget.html`: rozwinięcia `<details>` wpływów i stałych z formularzami.
- Testy: `test_flex.py` (suma median ≠ mediana sumy, sortowanie, kandydaci), `test_web_budget.py`
  (render składników, POST zmienia grupę i pulę, błędna grupa).

## Weryfikacja

1. `pytest` lokalnie.
2. Panel dev na kopii księgi + Playwright (mobile, 0 błędów konsoli).
3. Na żywo przez Ingress: suma składników stałych = kwota w puli, wpływy = suma źródeł;
   porównanie nowej puli z 0.12.0 na checkpoincie.

## Wynik

—
