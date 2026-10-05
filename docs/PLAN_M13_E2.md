# M13 E2 — Rozszerzone Podsumowanie (wykres kołowy, bilans, nadchodzące, ostatnie, 12 miesięcy)

## Kontekst

E1 (0.18.0) dał nowy styl, nawigację i Podsumowanie v0 (karta „Zostało” + „Do decyzji”). E1b (0.18.1) dołożył drugi wygląd
(Monarch) za przełącznikiem „Wygląd”; użytkownik chce wybrać motyw **po rozszerzeniu Podsumowania**, więc E2 musi wyglądać
dobrze w obu motywach. Cel: jedno spojrzenie odpowiada na „ile mogę wydać” (jest), „gdzie poszły pieniądze” (wykres kołowy),
„czy jest gorzej niż miesiąc temu” (bilans), „co jeszcze zejdzie” (serie), „co się działo” (ostatnie transakcje) i „jak wygląda
rok” (12 miesięcy). Nic z tego nie wymaga nowych danych: wszystko liczy się z istniejących tabel.

Decyzje użytkownika (2026-10-05): wykres kołowy kategorii wydatków miesiąca **nad „Do decyzji”**, atrakcyjny i użyteczny;
dodać wszystkie cztery: bilans z porównaniem, „co jeszcze zejdzie/wpłynie”, ostatnie transakcje, wykres 12 miesięcy;
**przełączanie miesięcy na całym ekranie**; **jedno duże wydanie 0.19.0** (odstępstwo od mojej rekomendacji dwóch wydań, więc
budowa idzie blokami z commitem i weryfikacją po każdym). Lokalnie najpierw, wydanie i update HA dopiero na „go”.

## Oba motywy (Copilot i Monarch), bez wyjątków
Każdy nowy element (wykres kołowy, bilans, nadchodzące, ostatnie transakcje, 12 miesięcy, linia „Dane z …”, strzałki miesięcy)
powstaje i jest weryfikowany **w obu motywach**; przełącznik „Wygląd” zostaje, żebyś mógł je porównać na telefonie na swoich
danych przed wyborem. Struktura HTML i kod wykresów są wspólne, różnią się tylko tokeny CSS (kolory, promienie, cienie, krój
nagłówków, paleta wykresów) i drobne nadpisania w bloku `[data-theme="monarch"]`. W planie weryfikacji każdy zrzut, pomiar
kontrastu i test renderu dotyczy obu motywów (zestawienia Copilot | Monarch dla każdego ekranu, 360 i 1280 px).

## Kolejność kart (mobile, od góry)
nagłówek z miesiącem i strzałkami + linia „Dane z …” → **Zostało** (wspólna karta) → **Wykres kołowy** → **Do decyzji**
(zgodnie z prośbą zaraz pod wykresem) → **Bilans miesiąca** → **Co jeszcze zejdzie** (tylko bieżący miesiąc) →
**Ostatnie transakcje** → **12 miesięcy**. Na desktopie karty w dwóch kolumnach (wykres + bilans obok siebie).

## Projekt elementów
**Wykres kołowy (donut, SVG po stronie serwera, bez JS i bez bibliotek).** Top 6 kategorii głównych z wydatkami + „Inne”
(reszta) + „Bez kategorii” (osobny wycinek, link do kolejki), tylko kwoty > 0 (zwroty nie tworzą wycinków; udziały liczone od
sumy dodatnich, żeby suma = 100%). Wycinek to `<circle pathLength="100">` z `stroke-dasharray`, małe odstępy między wycinkami.
Środek: suma wydatków miesiąca i zmiana względem poprzedniego (HTML nałożony na SVG, żeby kontrolować kroje). Pod spodem
legenda: kropka koloru, nazwa (link do `/transactions?category=<id głównej>&date_from&date_to`, filtr już obejmuje
podkategorie), kwota, udział, zmiana %. Wycinki też są linkami z `<title>`. Jedna animacja: wjazd wycinków (`stroke-dasharray`
z `from`, kolejno co 60 ms), wyłączona przy `prefers-reduced-motion`. Podświetlenie legendy ↔ wycinka przez CSS `:has()`
(bez JS; gdy WebView nie wspiera, nic się nie psuje). Stany: brak wydatków (pusty pierścień + tekst), jeden wycinek (pełny
okrąg bez odstępu), miesiąc z samymi zwrotami.
**Kolory kategorii:** stały kolor per kategoria (`id % 8`, żeby kategoria wyglądała tak samo co miesiąc), kolizje w obrębie
jednego wykresu rozwiązywane zachłannie „następny wolny”. Tokeny `--chart-1…8`, `--chart-other`, `--chart-unc` osobno w obu
motywach, kod nic nie wie o kolorach.
- Copilot: tangerine, hot pink, fiolet (rozjaśniony dla kontrastu), sky, ember, olive + dwa pochodne (teal, jasny
  indygo). **Lime, coral i sunflower zarezerwowane dla znaczeń** (wpływ, przekroczenie, ostrzeżenie), więc nie są kolorami
  kategorii. „Inne” = slate, „Bez kategorii” = obrys sunflower.
- Monarch (styl nie ma kolorów kategorii, więc to **pochodna paleta ciepłych ziem**, odstępstwo od specyfikacji do Twojej
  oceny): ember, ink, terakota, przygaszony niebieski, szałwia, ochra, śliwka, ciepły szary; „Inne” ciemniejszy kamień.
**Bilans miesiąca:** trzy kafle Wydatki / Wpływy / Bilans, każdy z różnicą względem poprzedniego miesiąca. **Porównanie
rzetelne:** dla bieżącego miesiąca poprzedni liczony **za ten sam okres** (np. do 5. dnia), inaczej „−94%” byłoby fałszem.
Etykieta mówi to wprost („vs 1–5 września”). Strzałki jako SVG (Lucide), kolor wg znaczenia (mniej wydatków = dobrze).
**Co jeszcze zejdzie/wpłynie:** do 5 najbliższych pozycji z `recurring.schedule.for_month` (statusy oczekiwana/spóźniona,
spóźniona z plakietką), sumy „jeszcze zejdzie / jeszcze wpłynie”, link do Cyklicznych. Ukryta dla miesięcy minionych.
**Ostatnie transakcje:** 5 ostatnich zaksięgowanych bez przelewów własnych (jak w budżecie), data, sprzedawca, kategoria,
kwota (wydatek biały, wpływ lime), link „Wszystkie”. Dla miesiąca minionego: ostatnie z tego miesiąca.
**12 miesięcy:** SVG, pary słupków wpływy (lime/ink) i wydatki (kolor akcentu), skala „ładna” (3 linie pomocnicze), etykiety
miesięcy, wybrany miesiąc podświetlony, bieżący (niepełny) lżejszy; każdy słupek to link do `/?month=RRRR-MM`. Opis dla
czytników ekranu (aria-label + `<title>` per słupek).
**Linia „Dane z …”:** czas ostatniej udanej synchronizacji (`sync_log`) i dni do końca zgody; Status jest teraz schowany w
menu, a nieświeże dane to największe ryzyko dla zaufania do liczb na ekranie startowym.
**Poza zakresem (świadomie):** skarbonki/limity (M5c), prognoza salda (M8), majątek netto (M9), alert o wygasającej zgodzie
na górze (dzwonek i „Do decyzji” już to niosą).

## Pliki i ponowne użycie
- `budget/spending.py`: dopisać do `Month` pola `prev_income`, `prev_expenses`, `prev_label` (okno porównawcze) przez nową
  funkcję `totals(tree, sums)` używającą istniejących `sums()` i `taxonomy.tree()`; nowa `monthly_totals(conn, end, n=12)`.
  Istniejące `build()` bez zmiany zachowania (Wydatki dalej jak dziś).
- NOWY `web/charts.py`: czyste funkcje `donut_slices()` (top-N, „Inne”, kolor stały + kolizje, długości i przesunięcia
  wycinków, linki) i `month_bars()` (skala, geometria). Testowalne bez HTTP.
- NOWY `web/templates/_charts.html`: makra `donut` i `bars` (inline SVG), strzałki Lucide pobrane z iconify.design.
- NOWY `web/templates/_flex_hero.html`: wspólny fragment karty „Zostało” (z `budget.html`, gałąź „kwota ustawiona”), używany przez
  Budżet i Podsumowanie, także dla miesięcy minionych; naprawia przy okazji zawijanie „Tempo” na telefonie.
- `web/routes_home.py`: parametr `month` (`spending.parse_month`), jeden `flex.build`, jeden `spending.build`,
  `schedule.for_month`, zapytanie o ostatnie transakcje (`TXN_DATE` z `routes_transactions`), ostatnia synchronizacja.
- `web/templates/home.html`, `static/app.css` (donut, legenda, bilans, listy, słupki, tokeny wykresów w obu motywach,
  `animation: none` w bloku reduced-motion), `web/templates/budget.html` (include wspólnej karty).
- Dokumenty: `docs/PLAN_M13_E2.md` (kopia tego planu jako pierwszy krok), `ROADMAP.md`, `DESIGN.md` (paleta wykresów, zasady),
  `CHANGELOG.md`, bump 0.19.0 w `config.yaml`, `__init__.py`, `pyproject.toml`.

## Kroki (repo `/config/addons/ha-budget-app`, gałąź `main`, `PATH=$HOME/.local/bin:$PATH`)
1. Dokumenty przed kodem: `PLAN_M13_E2.md`, wiersz w `ROADMAP.md`; commit.
2. **Dane:** `spending.totals()`, pola poprzedniego okresu, `monthly_totals()`; testy `tests/test_spending.py` (okno „ten sam
   okres”, miesiąc minięty vs bieżący, przełom miesięcy o różnej długości). Commit.
3. **`web/charts.py` + testy** (`tests/test_web_charts.py`): top-N i „Inne”, zwroty, zero/jedna kategoria, stabilność i kolizje
   kolorów, długości wycinków sumują się do 100 (z odstępami), skala słupków. Commit.
4. **Wspólna karta „Zostało”** (`_flex_hero.html`) w Budżecie i Podsumowaniu; istniejące testy Budżetu muszą przejść bez zmian.
5. **Szablony i CSS:** donut + legenda, bilans, nadchodzące, ostatnie, 12 miesięcy, strzałki SVG, tokeny w obu motywach,
   przełączanie miesięcy, linia „Dane z …”. Testy `tests/test_web_home.py` (sekcje, `?month=`, miesiąc minięty bez karty
   „Co jeszcze zejdzie”, miesiąc pusty, link wycinka, `<title>`). Commit.
6. **Weryfikacja lokalna** na kopii księgi (`~/budget_dev/prod/ledger.db` do scratchpadu, serwer uvicorn, po teście kill po PID
   i usunięcie kopii): Podsumowanie w obu motywach, 360 i 1280 px, bieżący miesiąc (rzadki), wrzesień (bogaty), miesiąc pusty;
   kontrast liczony w przeglądarce (tekst ≥ 4,5:1, wycinki i słupki ≥ 3:1 względem karty), brak przepełnienia poziomego,
   konsola czysta, `prefers-reduced-motion` bez animacji; `impeccable detect` raz; `simplify` na diffie; jedna runda poprawek.
   Zestawienia obok siebie wysyłam użytkownikowi (`SendUserFile`; zawierają prawdziwe dane, nigdzie nie publikuję).
7. **Na „go”:** bump 0.19.0 + CHANGELOG, `pytest` + `ruff` + `mypy`, push (razem z lokalną poprawką separatora `af7a25d`), czekam
   na CI dla tego commita, opublikowany release `v0.19.0`, `check_updates` i `ha_manage_updates` (tylko Budżet Domowy, z
   backupem add-onu), weryfikacja na żywo przez `playwright-ha` (390 i 1280 px, obie motywy, powrót do Copilot), checkpoint.
8. Po decyzji o motywie osobny krok **E1c**: usunięcie przegranego motywu i przełącznika, wydanie sprzątające.

## Ryzyka i cofnięcie
- **Wydajność strony głównej:** dochodzi 1 `spending.build` (2 przebiegi `sums`), `monthly_totals` (12 zapytań z filtrem dat),
  `for_month`, 2 małe zapytania; na ~3 tys. transakcji to milisekundy, ale mierzę czas odpowiedzi `/` lokalnie.
- **Fałszywe porównanie niepełnego miesiąca:** rozwiązane oknem „ten sam okres”; test jednostkowy pilnuje.
- **Różne waluty / zwroty:** `sums()` już pomija inne waluty; wycinki tylko z kwot dodatnich.
- **Kolory kategorii vs znaczenia:** zarezerwowane lime/coral/sunflower; paleta Monarch jest pochodna (do oceny).
- **WebView:** `:has()` opcjonalne; brak JS; HTML `no-store`, statyki z `?v=`.
- **Cofnięcie:** `git revert` commitów E2 i wydanie poprawkowe, albo backup add-onu z kroku 7. Brak zmian schematu, encji i
  logiki budżetu (dopisane tylko pola wynikowe w `spending.Month`).

## Weryfikacja końcowa
`BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, `ruff check`, `ruff format --check`, `mypy`; zrzuty obu motywów;
na żywo: stopka `v0.19.0`, wykres kołowy z prawdziwymi danymi, kliknięcie wycinka otwiera przefiltrowane transakcje, strzałka
miesiąca zmienia cały ekran, słupek 12 miesięcy przenosi na ten miesiąc, konsola czysta.
