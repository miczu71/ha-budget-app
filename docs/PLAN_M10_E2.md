# M10 (reszta) — konto oszczędnościowe, odsetki, stopa oszczędności

## Context
Następny etap roadmapy budżetu (`/config/addons/ha-budget-app/docs/ROADMAP.md`) nie był ustalony.
Otwarte checkpointy: M10 E1 (skarbonki, 0.39.x) i M21 E4/E5. Wybrałeś resztę M10. Cel z wywiadu:
„wszystkiego po trochu”, czyli widzieć saldo oszczędności, ile odkładam co miesiąc i czy odsetki
i promocja są wykorzystane (dane potem dla M9/M22/M25).

## Ograniczenia z wywiadu (2026-10-12)
- **Saldo:** saldo startowe na dzień X (wpisane ręcznie) + przelewy na konto i z konta rozpoznane po
  numerze w księdze + szacowane odsetki; ręczna korekta, gdy saldo różni się od banku (nowe saldo na
  nowy dzień). Numer konta tylko w bazie, nigdy w repo.
- **savings_rate** = (przelewy na konto oszczędnościowe − wypłaty z niego) / wpływy w miesiącu.
  Skarbonki (konta-cele) się NIE liczą.
- **Odsetki:** stopa bazowa + opcjonalna promocja (stopa, limit kwoty, data końca), kapitalizacja
  miesięczna, podatek Belki 19%; przypomnienie przed końcem promocji.
- **Widok:** sekcja na ekranie „Skarbonki” (zmiana nazwy na „Oszczędności”) + kafelek na Podsumowaniu
  (saldo, stopa w tym miesiącu) + wykres stopy z 12 miesięcy. Bez encji HA. Źródło dla czatu → M12 E3b.
- **Działa samo:** rozpoznawanie przelewów, odsetki, przypomnienie. **Za Twoją zgodą:** wydanie i
  instalacja. **Sukces:** saldo w panelu zgadza się z bankiem (±odsetki), a stopa za poprzednie
  miesiące jest wiarygodna.

## Etapy (commity; jedno wydanie 0.40.0 na koniec)
1. **E2 Konto oszczędnościowe:** migracja `014_savings.sql` (tabela jak `piggy`: nazwa, numer, saldo
   startowe + data, parametry odsetek), moduł `savings.py` reużywa `piggy.normalize_number`
   i `piggy.transfers`; przelewy na konto / z konta wyłączone z wydatków i wpływów tak jak przelewy na
   konta-cele (sprawdzę, gdzie robią to `flex.py`/`snapshot.py`); formularz + sekcja na ekranie
   `piggy.html`, przez `routes_piggy.py`.
2. **E3 Odsetki i promocja:** szacunek odsetek dzień po dniu z kapitalizacją miesięczną, stawka
   promocyjna do limitu i daty, Belka 19%, doliczone do salda; wpis w dzwonku (`inbox.py`)
   i powiadomienie N dni przed końcem promocji (wzorzec z M15 E1).
3. **E4 Stopa oszczędności:** `savings_rate` per miesiąc (wpływy wg istniejącej definicji z puli/Flex),
   kafelek na Podsumowaniu (`home_layout.py`, 9. kafelek, można go ukryć jak resztę) i wykres
   12 miesięcy na ekranie Oszczędności.
4. **Wydanie:** `simplify`, testy, skill `release` (0.40.0, cache-busting), weryfikacja na żywo
   (Playwright przez Ingress) i re-sync systemu designu, jeśli dojdą komponenty (procedura z DESIGN.md).

Pierwszy krok implementacji: `docs/PLAN_M10_E2.md` (ten plan) i aktualizacja wiersza M10 w ROADMAP.md,
nowa decyzja 26.

## Pliki
`budget/app/src/budget/{savings.py (nowy), piggy.py, flex.py, snapshot.py, inbox.py, home_layout.py}`,
`storage/migrations/014_savings.sql`, `web/routes_piggy.py`, `web/templates/piggy.html` + kafelek,
testy w `budget/app/tests/`, `docs/ROADMAP.md`, `docs/PLAN_M10_E2.md`. Gałąź `main`.

## Ryzyka
- Przelew na konto oszczędnościowe może nie mieć numeru odbiorcy w danych z API. To samo pytanie jest
  otwarte w checkpoincie M10 E1. Sprawdzę to na kopii księgi przed E2, a jeśli brak numeru, staję i pytam.
- Migracja 014 addytywna (starsza wersja ją ignoruje); backup add-onu przed wydaniem.
- Szacunek odsetek ≠ bank co do grosza: dlatego jest korekta salda.

## Weryfikacja
`uv run pytest` (obecnie 722 testy zielone + nowe), lokalny serwer na danych `~/budget_dev`
i Playwright (ekran Oszczędności, kafelek, konsola bez błędów), po wydaniu wersja w UI przez Ingress
i saldo porównane z aplikacją banku.
