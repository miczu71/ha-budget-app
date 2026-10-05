# M13 — Refaktor UI panelu Budżet Domowy (styl Copilot Money)

## Context

M5b zamknięty 2026-10-05. W roadmapie M13 („całkowity refaktor UI”) było oznaczone „po M5b, zakres do wywiadu”,
a `PLAN_M5b.md` odłożył nowe ekrany M5b właśnie do M13. Robimy go teraz, przed M5c, M6 i M8, żeby kolejne ekrany
(wykresy, skarbonki, prognoza) powstawały od razu w docelowym stylu, a nie były przerabiane drugi raz.

Wywiad (2026-10-05):
- **Cel:** nowy wygląd. Strona główna (`/`) ma być **podsumowaniem budżetu**: Flex „ile zostało” + tempo,
  wykres wpływów i wydatków (~12 mies.), top kategorie, ostatnie wpływy i wydatki, co jeszcze zejdzie lub wpłynie
  z serii M5b, licznik „do przejrzenia”. **Status przenosimy na koniec.**
- **Nawigacja w grupach:** na wierzchu Podsumowanie · Budżet · Wydatki · Cykliczne · Transakcje, dzwonek z licznikiem;
  w menu ⚙: Reguły · Konta · Import CSV · Bank · Status (ostatni).
- **Styl:** [Copilot Money z Refero](https://styles.refero.design/style/91b110da-902b-4d09-8bf0-26bd1f25f8b2),
  **tylko ciemny** (bez trybu jasnego).
- **Etapy:** fundament → strona główna → ekrany robocze; każdy etap to osobne wydanie i checkpoint.

### Ograniczenia (do potwierdzenia)
1. Korzysta jedna osoba (Ty), głównie na telefonie w HA Companion (Ingress WebView), czasem na desktopie.
2. Automatycznie dzieje się tylko render z istniejących danych. Logika budżetu, encje MQTT i schemat bazy się
   nie zmieniają. Każde wydanie robię dopiero po Twojej zgodzie na etap.
3. Wszystko serwowane lokalnie z add-onu (fonty, wykresy), bez CDN. Cache WebView: `no-store` dla HTML,
   `?v=` z `immutable` dla statyk, wersja widoczna w UI (mechanizm już jest w `web/app.py:56`).
4. **Sukces:** po otwarciu panelu na telefonie od razu widzisz „ile zostało” i stan miesiąca bez przewijania
   do Statusu. Wszystkie dotychczasowe funkcje działają (testy zielone). Zrzuty 360 px i 1280 px bez defektów
   (detektor impeccable, konsola bez błędów).

## Kierunek wizualny (tłumaczenie Copilot Money na UI narzędzia)
- **Kolory:** tło `#000814`; powierzchnie `#010d1e` → `#001533` → `#00215e`; hairline `#11263b`; tekst `#ffffff`,
  `#ccced0`, `#999ca1`. Jedyny akcent akcji to `#1c6cff`. Kolory etykiet Copilot (coral, lime, tangerine,
  hot pink, violet, sunflower, sky, ember, olive, slate) stają się **kolorami kategorii głównych**
  w wykresach i chipach. Każda kategoria ma kolor stały, przypisany w kodzie.
- **Znaczenie kwot:** wpływ = lime `#00cc4b`; wydatek = neutralny biały (nie czerwony, bo większość pozycji to
  wydatki); przekroczenie tempa = coral.
- **Typografia:** firmowe kroje Jokker i Matter są płatne. Zamiast nich, zgodnie z podpowiedzią Refero:
  **Space Grotesk** (nagłówki, duże liczby) i **Inter** (UI), oba OFL, jako woff2 w `static/fonts/`.
  **Świadome odstępstwo:** Copilot używa grubości 100 dla treści; w gęstym UI na telefonie dam 300–400,
  a liczby w `tabular-nums`. Do odrzucenia na checkpoincie E1.
- **Kształt i głębia:** karty r24, przyciski r16, chipy r20. Głębia z wewnętrznych cieni (inset), bez drop shadow.
  Sekcje oddzielone tonem tła, nie ramkami.
- **Bez** „pływających przekrzywionych etykiet” z ich marketingowego hero: to dekoracja landing page,
  w panelu nie ma dla niej miejsca.
- **Wykresy:** SVG renderowane po stronie serwera (Jinja i Python), **bez biblioteki JS**. Dzięki temu
  nie ma CDN ani problemu z cache WebView, a htmx działa bez zmian.

## Etapy (zapis do `docs/ROADMAP.md` jako M13 E1–E3)

| Etap | Wydanie | Zakres |
|---|---|---|
| **E1 Fundament** | 0.18.0 | Tokeny Copilot w `app.css`, lokalne fonty, nowa nawigacja (5 + dzwonek + menu ⚙ na `<details>`, bez JS); Status przeniesiony na `/status`; `/` = Podsumowanie v0 (karta Flex + tempo + licznik do przejrzenia); wszystkie istniejące ekrany w nowej skórce, bez zmian funkcji |
| **E2 Strona główna** | 0.19.0 | Wykres wpływów i wydatków (12 mies., SVG), top kategorie bieżącego miesiąca (paski w kolorach kategorii), ostatnie wpływy i wydatki, „co jeszcze zejdzie / wpłynie” z `recurring.schedule.for_month`. Częściowo wchłania wykresy z M5c |
| **E3 Ekrany robocze** | 0.20.0 | Dopracowanie gęstych ekranów: Transakcje, Do przejrzenia, Reguły (wiersze księgi, chipy kategorii, formularze reguł) na 360 px |

Szczegółowy plan E2 i E3 (`docs/PLAN_M13_E2.md`, `docs/PLAN_M13_E3.md`) piszę i pokazuję dopiero po checkpoincie
poprzedniego etapu.

## E1 — dokładne kroki (to zatwierdzasz teraz)

Repo `/config/addons/ha-budget-app`, gałąź `main` (konwencja repo), `PATH=$HOME/.local/bin:$PATH`.

1. **Dokumenty, przed kodem:**
   - `docs/PLAN_M13.md`: ta treść (kontekst, kierunek, etapy, kroki E1).
   - `docs/ROADMAP.md`: wiersz M13 dostaje status „w toku, E1”, z odnośnikiem do planu.
   - `PRODUCT.md`: kontekst produktu dla impeccable (użytkownik, WebView, zasady prywatności; bez danych prywatnych).
   - `DESIGN.md`: tokeny i zasady powyżej.
   - Commit `docs(M13): plan refaktoru UI (styl Copilot Money)`.
2. **Fonty:** pobranie `InterVariable.woff2` i `SpaceGrotesk[wght].woff2` z oficjalnych wydań na GitHubie
   (rsms/inter, floriankarsten/space-grotesk) do `budget/app/src/budget/web/static/fonts/`, razem z `OFL.txt`.
   `@font-face` z `font-display: swap`, ścieżki z `?v={{ version }}`.
3. **`static/app.css`:** przepisanie na zmienne `:root` (kolory, kolory kategorii, promienie, odstępy, typografia).
   Te same klasy, z których korzystają szablony, więc ekrany działają bez zmian HTML. Wcześniej grep klas
   używanych w `templates/*.html`, żeby żadna nie wypadła.
4. **Nawigacja w `templates/base.html`:** 5 głównych linków, potem `_bell.html` (licznik), potem
   `<details class="more">⚙` z Regułami, Kontami, Importem CSV, Bankiem i Statusem. Aktywna strona podświetlona
   także wewnątrz menu. Na 360 px nawigacja przewija się poziomo, bez łamania na dwie linie.
5. **Status na `/status`:** w `web/routes_status.py` `@r.get("/")` zmieniam na `"/status"`.
   Sprawdzę wszystkie `RedirectResponse`/`HX-Redirect` i formularze, które dziś wracają na `/`, i przestawię je
   na `/status`.
6. **Podsumowanie v0:** nowy `web/routes_home.py` (`GET /`) i `templates/home.html`. Duża liczba „Zostało”,
   pasek tempa i dni do końca miesiąca z `flex.build(conn, month, today)` (te same pola co ekran Budżet), licznik
   z `inbox.items(...)`, link do Budżetu. Rejestracja w `web/app.py` jako pierwszy router.
7. **Testy:**
   - testy, które dziś czytają Status z `/` (`test_web_suggest.py`, `test_web_categorize.py:55`), przestawiam na `/status`;
   - `test_web_budget.py:38` zostaje (link do Budżetu w nawigacji);
   - nowe testy: `/` pokazuje kartę Flex; nawigacja zawiera menu ⚙ ze Statusem;
     `/static/fonts/*` dostaje nagłówek `immutable`.
   - Uruchomienie: `BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, `ruff`, `mypy`.
8. **Weryfikacja wizualna przed wydaniem:**
   - lokalnie panel na kopii `~/budget_dev/prod/ledger.db`;
   - Playwright: zrzuty wszystkich 11 ekranów w 360×800 i 1280×800 (jedna partia), konsola;
   - `impeccable detect --json` na zmienionych plikach;
   - poprawki w jednej partii, maksymalnie jedna runda potwierdzająca;
   - zrzuty tylko lokalnie (`/config/playwright/`, gitignored), bo zawierają dane prywatne.
9. **`simplify`** na diffie, potem hook pre-commit (skaner danych prywatnych). Commit
   `feat(M13 E1): styl Copilot Money, nowa nawigacja, Podsumowanie v0`.
10. **Wydanie przez skill `release`:**
    - bump `budget/config.yaml` 0.17.1 → 0.18.0, CHANGELOG, push, opublikowany GitHub release (nie draft);
    - sprawdzenie, że Supervisor widzi 0.18.0 (`ha_get_app`);
    - aktualizację add-onu robię za Twoją zgodą, z backupem przy update.
11. **Weryfikacja na żywo:** `playwright-ha` przez Ingress. Zrzut `/` i jednego ekranu roboczego na telefonowej
    szerokości, znacznik `v0.18.0` w nawigacji, konsola. Potem **checkpoint**: E2 dopiero po Twoim „go”.

### Ryzyka
- **Formularze i przekierowania Statusu** wracające na `/`: wyłapię je grepem i testami (krok 5).
- **Kontrast cienkiego, jasnego tekstu na granacie:** mierzę w kroku 8 (WCAG AA dla treści).
- **Rozmiar fontów** (~350 kB) przy pierwszym wczytaniu w WebView: jednorazowo, potem `immutable`.
- **Kolory kategorii** na kilku ekranach w E1 wymagają stałego przypisania kolor ↔ kategoria główna. Najprościej:
  według kolejności/slug w kodzie. Pełne użycie dopiero w E2.

### Cofnięcie
- E1 nie zmienia schematu bazy ani encji.
- Cofnięcie = `git revert` commitu E1 i wydanie 0.18.1 przez `release`. Alternatywnie przywrócenie backupu add-onu
  zrobionego przy aktualizacji.
- Docs zostają (wiersz ROADMAP wraca do „—”).

## Weryfikacja końcowa E1
- pytest, ruff i mypy zielone;
- CI na GitHubie zielone;
- zrzuty 360 i 1280 bez defektów, detektor bez znalezisk krytycznych;
- na żywo: `/` = Podsumowanie, Status w menu ⚙ działa (synchronizacja, AI), wersja 0.18.0 widoczna w UI.

## Wynik E1 (0.18.0, 2026-10-05)

Wydane (release `v0.18.0`, CI zielone) i zainstalowane w HA z backupem add-onu `f6938514` („Budżet Domowy 0.17.1”,
tuż przed update'em). 487 testów, ruff i mypy bez uwag.

**Dowody:** zrzuty lokalne (360 i 1280 px, 12 ekranów) bez przepełnienia poziomego, bez błędów w konsoli, kontrast
treści ≥ 7:1; na żywo przez Ingress (390 i 1280 px) stopka `v0.18.0`, fonty Inter i Space Grotesk załadowane,
`/status` działa, konsola bez błędów. Detektor impeccable: tylko ostrzeżenia „overused-font” (Inter, Space Grotesk;
świadomy wybór, bo Refero wskazuje je jako otwarte zamienniki fontów Copilota).

**Odstępstwa od planu E1 (do oceny na checkpoincie):**
1. **„Do przejrzenia” w menu ⚙** (pierwsza pozycja). Plan wymieniał tylko Reguły, Konta, Import, Bank, Status, ale kolejka
   przeglądu zostałaby bez bezpośredniego wejścia (poza dzwonkiem i linkiem z Podsumowania).
2. **Wersja add-onu w stopce strony**, nie w pasku nawigacji (miejsce zajęły dzwonek i ⚙); nadal widoczna na każdym ekranie.
3. **Fonty bez `?v=` w ścieżce** (CSS jest plikiem statycznym; fonty są stałymi wydaniami OFL, serwowane `immutable`).
4. **Treść w grubości 400**, nie 300–400 (cienki tekst na telefonie był za słaby); nagłówki Space Grotesk 500–600.
5. **Kwota wydatku w wierszu biała** (kolor tylko wpływ i przekroczenie), bo koralowe kwoty na setkach transakcji dawały
   wrażenie alarmu.
6. **Poprawka pakowania:** `package-data` nie obejmowało `static/fonts/`, więc obraz (`pip install .` i `rm -rf src`)
   zgubiłby fonty bez żadnego błędu. Dodane globy i test `test_package_data_covers_every_static_file`.
7. **Ikony i grafiki zawsze SVG** (Lucide, ISC, przez iconify.design): dzwonek, ⚙, a szewrony i ptaszek z CSS-owych
   ramek zamienione na maski SVG. Animacje, gdy będą potrzebne, jako Lottie.

**Znane, odłożone:** długie wartości w `.kv` (np. „Tempo”) zawijają się na telefonie w 3 linie (stare zachowanie, karta
„Zostało” zostanie przebudowana w E2); Inter ładowany w całości (352 kB, bez przycinania do łaciny); trzy starsze kopie makra
`pct` w szablonach; chipy i małe przyciski poniżej 44 px (E3, ekrany robocze).

