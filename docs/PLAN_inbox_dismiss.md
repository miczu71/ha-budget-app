# Ręczne usuwanie kart „Do decyzji” (ha-budget-app)

## Context
Karty dzwonka (`budget/inbox.py`) liczą się na żywo i znikają dopiero, gdy sprawa zostanie załatwiona.
Niektóre są tylko informacyjne i nie da się ich „załatwić”, np. `promo_wait`
(„Profit: czekam na regulamin edycji 77”). Użytkownik chce móc ukryć taką kartę ręcznie.

Ustalenia:
- Ukrywam parę **(kind, tytuł)**. Karta wraca, gdy zmieni się tytuł, np. edycja 78 albo nowa kwota spłaty karty.
- Przycisk ✕ jest **na /inbox i w kafelku „Do decyzji”** na stronie głównej. Na /inbox jest też „Przywróć ukryte (N)”.
- Ukryte karty znikają również z licznika dzwonka i z encji `sensor.budget_inbox`, bo wszystkie te miejsca czytają `service.inbox()`.

## Zmiany (repo `/config/addons/ha-budget-app`, gałąź `main`)
1. `budget/app/src/budget/inbox.py`
   - `DISMISSED_KEY = "inbox_dismissed"` w tabeli `kv` (`storage/db.py: kv_get/kv_set`) jako lista stringów.
   - `Item.key` (property) zwraca `f"{kind}|{title}"`.
   - `items()` pomija karty, których `key` jest w ukrytych. Dodaję też `hidden_count()` dla linku „Przywróć”.
   - `dismiss(conn, key, current_keys)` zapisuje ukryte klucze, które nadal występują wśród bieżących kart, i dokłada nowy. Sprzątanie dzieje się tylko przy zapisie, odczyt niczego nie zapisuje.
   - `restore(conn)` robi `kv_set(..., None)`.
2. `budget/app/src/budget/web/routes_inbox.py`: dwie trasy.
   - `POST /inbox/dismiss`: pola `key` i `back` (`/` albo `/inbox`). Wywołuje `panel.service.refresh_soon()`, potem `panel.redirect(request, back)`.
   - `POST /inbox/restore`: przekierowuje na `/inbox`.
   - Do `dismiss` potrzebna jest lista bieżących kluczy bez filtra. Biorę ją z wariantu `items(..., include_hidden=True)` albo z małej metody w `service.py` obok `inbox()`.
3. Szablony `inbox.html` i `home.html` (kafelek `inbox`): przy każdej karcie mała forma POST z przyciskiem ✕.
   - Forma stoi obok `<a>`, nie w nim. Przycisk ma `aria-label="Ukryj"`, ikona SVG inline (bez emoji).
   - Na /inbox, gdy coś jest ukryte, pojawia się forma „Przywróć ukryte (N)”.
   - Stopkę zmieniam na: „…albo gdy ją ukryjesz”.
4. `web/static/app.css`: `.inbox-item` z flexem, żeby link i ✕ stały w jednym wierszu. Zachowuję tap target `var(--tap)`. Styl dobieram skillem `impeccable`, zgodnie z istniejącymi przyciskami `.secondary`.
5. Testy w `tests/test_web_home.py` albo `test_web_recurring.py`:
   - dismiss ukrywa kartę w `service.inbox()` i na `/inbox`;
   - karta o innym tytule pojawia się mimo dismiss;
   - restore przywraca kartę;
   - klucze nieaktualnych kart są sprzątane przy kolejnym dismiss.

## Wydanie
Na koniec skill `release` (0.43.0 → 0.44.0). Skill obejmuje bump, testy, cache-busting statyk, opublikowany release, aktualizację w Supervisorze i weryfikację w Playwright. Przed commitem uruchamiam `simplify`. Commit i push są poza oknem 02:45–03:15.

## Ryzyka
- Ukryta karta typu `error` (np. nieaktywna zgoda bankowa) zniknie też z encji HA. Wraca dopiero przy zmianie tytułu albo po „Przywróć”. Akceptuję to, bo to świadoma decyzja użytkownika.
- Cofnięcie: „Przywróć ukryte” albo `kv_set(inbox_dismissed, None)`. Revert commitu nie wymaga migracji, klucz `kv` jest po prostu ignorowany.

## Weryfikacja
- `uv run pytest` w `budget/app`, w tym nowe testy.
- Na żywo, po aktualizacji add-onu, przez Playwright (`playwright-ha`):
  - ukrywam „Profit: czekam na regulamin edycji 77”;
  - sprawdzam licznik dzwonka, kafelek i `/inbox` z linkiem „Przywróć ukryte (1)”;
  - sprawdzam `ha_get_state(sensor.budget_inbox)`;
  - robię screenshot i sprawdzam konsolę.
