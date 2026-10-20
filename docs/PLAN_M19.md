# M19 — Wykres przepływów (Sankey) w Budżecie

## Context
Pozycja M19 w `docs/ROADMAP.md` (pomysł 2026-10-07 z raportów Monarch, „zakres do wywiadu”). Wywiad 2026-10-20:
cel nie jest jeszcze przesądzony („zbadajmy”), więc **najpierw makieta na prawdziwych danych**, decyzja o układzie
po zrzutach. Ustalone:
- **Kto/co:** użytkownik na telefonie, ekran **Wydatki** — nowa sekcja pod donutem, ten sam wybór miesiąca (‹ ›).
- **Okres:** miesiąc kalendarzowy + przełącznik **Rok** (rok kalendarzowy wybranego miesiąca); sumy = te same co Wydatki.
- **Warianty makiety:** B — 3 kolumny poziomo (Wpływy → grupy → kategorie główne), D — ten sam przepływ pionowo (telefon).
- **Automatycznie:** wykres liczony z księgi przy każdym wejściu; **za zgodą:** wybór wariantu po makiecie (jedyny przystanek).
- **Sukces:** na 390 px czytelne etykiety i kwoty, sumy węzłów zgodne z Wydatkami/Budżetem (test), klik w kategorię → transakcje.

## Model danych (decyzje domyślne, do korekty po makiecie)
- Grupy z `categorize/taxonomy.py:FLEX_GROUPS`: lewy węzeł **Wpływy** (`income` + wpływy bez kategorii);
  środek: **Stałe** (`fixed`), **Elastyczne** (`flexible`), **Nieregularne** (`non_monthly`), **Oszczędności** (`savings`),
  **Nadwyżka** (wpływy − wszystko, gdy > 0); `excluded` pomijane; wydatki bez kategorii → węzeł „Bez kategorii”.
- **Deficyt** (wydatki > wpływy): dodatkowy lewy węzeł „Z oszczędności / deficyt”, żeby przepływ się bilansował.
- Prawa kolumna: kategorie główne w grupie, top 8 łącznie (paleta `--chart-1…8`) + „Inne” per grupa.
- Źródło liczb: `spending.sums()` / `Sums.by_leaf` + `taxonomy.leaves()` (jak `flex.py:268`), podział M29 już uwzględniony.
- Render: **SVG po stronie serwera**, czysta geometria w `web/charts.py` (wzorzec `donut_slices`/`month_bars`), makro
  w `_charts.html`, kolory przez klasy `c1…c8/other/unc` — bez biblioteki JS. Unikalne klasy SVG (`.sk-*`), bo `.bar` koliduje.
- Link kategorii: `/transactions?category=<id>&<period>` jak w donucie.

## Etapy (jedno wydanie na koniec)
**E0 — makieta (bez commita do main).** `wt new ha-budget-app m19-proto`; tymczasowa trasa `/flow?variant=b|d&month=`
na danych dev (`~/budget_dev/prod/ledger.db` → kopia w scratchpadzie, `devserve.py` wg notatki `budget_app_dev_environment`;
kopia z 02.10 nie ma wpływów `income` → oznaczyć w kopii uznania > 1000 zł jako przychód). Zrzuty 390 px i 1280 px
(wycinki 800 px, `reducedMotion`, bez transition), wysłane SendUserFile. **STOP: user wybiera B/D + poprawki**
(jedyny planowany przystanek). Rollback: `wt drop`, usunąć kopię księgi.
**E1 — geometria + dane (TDD).** `budget/flow.py`: `build(conn, start, end) -> Flow` (węzły, krawędzie, kwoty, deficyt/nadwyżka);
`web/charts.py`: `sankey(flow, orientation) -> SankeyChart` (pozycje węzłów, ścieżki Béziera, etykiety, min. wysokość węzła).
Testy: bilans wejść = wyjść każdego węzła, zgodność z `spending.build` dla miesiąca, deficyt, pusty miesiąc, podział M29.
**E2 — sekcja w Wydatkach (miesiąc).** `routes_spending.py` + `spending.html` + makro w `_charts.html` + CSS w `app.css`
(tokeny, oba motywy, 390 px), linki do transakcji, pusty stan. Usunięcie trasy makiety.
**E3 — przełącznik Rok.** parametr `flow=year` (rok kalendarzowy wybranego miesiąca), ten sam widok.
**Domknięcie:** `simplify` → `code-review` (repo + `<baza>..HEAD`) → `release` (bump, CHANGELOG, published) →
weryfikacja na żywo przez Ingress (pomiary DOM, bez oglądania danych) → ROADMAP M19 ✅, `PLAN_M19.md` § Wynik.
Komponent do Claude Design (M20) — tylko zgłosić jako follow-up.

Po każdym etapie E1–E3: testy (`BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`), ruff, mypy, commit, `stage-end`.
Etapy E1/E2 (≥5 edycji) w `PLAN_M19.md` dostają sekcję **Wykonawca** dla `sonnet-worker` (worktree `wt new`) + `verifier`.

## Pierwszy krok implementacji
Skopiować ten plan do `/config/addons/ha-budget-app/docs/PLAN_M19.md`, wpis M19 w `docs/ROADMAP.md` → „wywiad 2026-10-20
(`PLAN_M19.md`)”, commit docs. Sprawdzić hook pre-commit (`test -x .git/hooks/pre-commit`).

## Ryzyka
- Dane prywatne: zrzuty makiety tylko do usera, nic z danymi do repo/artefaktów; fixtures testów z neutralnymi nazwami.
- Czytelność na 390 px przy wielu kategoriach — stąd top 8 + „Inne” i wariant D.
- Okno 02:45–03:15 bez commitów.

## Weryfikacja
pytest/ruff/mypy zielone; test zgodności sum Sankey = Wydatki; zrzuty dev przed wydaniem; na żywo: sekcja renderuje się
w miesiącu i roku, liczba węzłów > 0, brak błędów konsoli, klik kategorii prowadzi do `/transactions?category=`.

## Wynik E0 (2026-10-20)
Makieta B (poziomo) i D (pionowo) na kopii księgi dev (skrypt w scratchpadzie sesji; worktree niepotrzebny, `wt drop`).
**Decyzja usera: B poziomo + poprawki.** Wnioski do E1/E2:
- drobne węzły nachodzą na etykiety → minimalna wysokość węzła, ukrywanie etykiet małych węzłów (kwota w `<title>`/dotyku), „Inne” per grupa;
- D pionowy: etykiety nieczytelne na 390 px — odrzucony; na telefonie B w węższym viewBox z krótszymi etykietami albo przewijany poziomo;
- kategoria z ujemnym saldem netto (zwrot > wydatki) nie może rysować węzła — pomijać i dopisać do „Inne”/nadwyżki (test);
- „Bez kategorii” bywa największym węzłem (kopia 02.10) — węzeł z linkiem do kolejki przeglądu, osobny kolor `unc`;
- kopia z 02.10 nie ma kategoryzacji — w makiecie potrzebne `engine.recategorize`.
