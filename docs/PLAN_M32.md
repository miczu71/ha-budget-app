# M32 — Rotacja środków między kontami promocyjnymi (Velobank + Millennium)

## Kontekst
Wywiad 2026-10-22. Cel: Budżet pilnuje terminów i warunków promocji oprocentowania kont (Velobank ROR + Elastyczne
Konto Oszczędnościowe, Millennium Profit/KOP), żeby w porę przelać środki tam, gdzie stopa jest lepsza.
Edycja 12/2026 „Nowe środki na Elastycznym Koncie Oszczędnościowym”: 4,5% zamiast 1%, warunek 5 transakcji
bezgotówkowych w miesiącu na ROR (dziś 0/5). Scala M17 (tracker warunków) i rozszerza M10 E7 (`promo_watch`).

## Decyzje z wywiadu
1. **Źródło danych Velobanku: drugi bank przez PSD2 (Enable Banking)** — zmienia decyzję 1 (zakres: 3 konta Millennium).
   Wymaga wielobankowości w `sessions.py`/`settings.py` (dziś jeden `aspsp_name`, jedna bieżąca sesja).
   Limit 4 zapytań/konto/dobę liczy bank per konto.
2. **Zakres rotacji: przypomnienia + rekomendacja „dokąd przelać”** (porównanie stóp Velo vs Profit/KOP). Budżet **nigdy
   nie przelewa** — przelew robi user.
3. **Terminy i warunki: pełny automat z regulaminu** (stawki, daty, progi). Zabezpieczenie: nowa edycja = karta w dzwonku
   do wglądu; regulamin nieczytelny albo wartości poza normą → rekomendacja wstrzymana + alarm (bez cichego fallbacku).
4. **Licznik: karta i BLIK, bez przelewów własnych** (definicja z regulaminu edycji; uogólnienie licznika z M15 o regułę
   per promocja). Millennium bez pilnowania warunków (wyjątek: karta kredytowa, M15).
5. **Powiadomienia: dzwonek + `notify.family`**, progi 14/7/2 dni przed końcem promocji; „brakuje N transakcji” w ostatnich
   7 dniach miesiąca; alarm przy nowej edycji i nieczytelnym regulaminie.
6. **Kolejność:** E0 → E1 → E2 → E3 → E4. E3 jest niezależny od E1/E2 (może iść równolegle). Jedno wydanie po E2
   (pierwsza realna wartość), potem reszta zgrupowana (ostatni etap zamyka wydanie).

Kto korzysta: user i rodzina (panel w HA, telefon). Automatycznie: synchronizacja Velobanku, licznik, odczyt regulaminu,
przypomnienia. Za zgodą: każdy przelew (poza Budżetem). Sukces: dla edycji 12/2026 licznik pokazuje N/5 z księgi, przed
końcem okna przychodzi powiadomienie z rekomendacją, nowa edycja pojawia się jako karta w dzwonku.

Repo: `miczu71/ha-budget-app`, gałąź `main`, testy
`cd budget/app && BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, ruff, mypy. Hook pre-commit prywatności
musi istnieć (`test -x .git/hooks/pre-commit`); fixtures z neutralnymi nazwami. TDD w każdym etapie, skill
`addon-conventions` przy edycji kodu. Etapy = commity; wydanie robi skill `release` (lokalnie).

**Podział lokalnie/chmura:** E0, wydania, instalacja i weryfikacja na żywo, testy na kopii księgi (`~/budget_dev`) —
lokalnie (sekrety Enable Banking, HA, dane prywatne). Kod E1–E4 + review — kontrakty **Wykonawca** niżej mogą iść do
sesji `claude --remote` (chmura nie ma sekretów ani sieci domowej; testy na mockach/fixtures). Wynik = gałąź/PR,
weryfikuję lokalnie przed mergem.

## E0 — Czy Enable Banking obsługuje Velobank (lokalnie)
- `secret-run <usługa EB> --` mały skrypt w scratchpadzie: `get_aspsps("PL")`, `find_aspsp(..., "Velo...")`; wypisać tylko
  nazwę i dostępne scope/limity, nie klucze ani nagłówki. Sprawdzić też limit kont aplikacji EB (tryb ograniczony).
- Wynik zapisać w tym pliku. Velobank jest na liście → E1 jak niżej. Brak → zatrzymuję się i wracam do usera
  (konto ręczne + CSV jak Profit w M10 zmienia E1/E2).
- **Wynik (2026-10-22):** VeloBank jest na liście PL (24 banki), `beta=True`, maksymalna zgoda 15552000 s (180 dni) jak Bank Millennium; aplikacja EB ma 1 redirect URL. → E1 jak niżej (sesja per bank; uwaga: konektor w becie).
- Rollback: brak zmian w kodzie.

## E1 — Wielobankowość PSD2
Wykonawca:
- Pliki: `budget/sessions.py`, `budget/settings.py`, `budget/sync_service.py`, `budget/web/routes_bank.py`
  (+ szablon „Połącz bank”), `budget/eb_ingest.py`, `budget/storage` (migracja, jeśli sesja/konto potrzebuje kolumny banku),
  testy `test_sessions.py`, `test_sync_service.py`, nowe w stylu istniejących.
- Zmiana: sesja per bank (`aspsp_name` w rekordzie sesji; `current(conn, aspsp)`), opcja `aspsp_name` → lista banków
  (domyślnie Millennium bez zmiany zachowania), `start_auth`/`finish_auth` per bank, sync iteruje po sesjach i zapisuje
  bank na koncie w księdze; limit zapytań liczony per konto. Millennium działa jak dotąd (test regresji).
- Test: `cd budget/app && BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q && .venv/bin/ruff check . && .venv/bin/mypy .`
- DONE: dwie sesje różnych banków współistnieją w testach na mockach EB; sync obu; stare dane Millennium bez migracji
  psującej; konta Velobanku widoczne w księdze (typ „ROR”/„oszczędnościowe” do oznaczenia ręcznie w UI jeśli API nie podaje).
- NIE RÓB: zmian w `promo_watch.py`/`promo_track.py`/`card.py`; prawdziwych kluczy EB; realnych nazw/numerów kont w fixtures;
  wydania ani bumpu wersji.
- Rollback: `git revert`; migracja dodająca kolumnę nieszkodliwa.

## E2 — Licznik transakcji i terminy promocji + powiadomienia
Wykonawca:
- Pliki: `budget/promo_track.py` (uogólnienie liczenia licznika poza `millen`: warunek `cashless` — karta i BLIK, bez
  przelewów własnych), `budget/inbox.py` (`promo_cards`), `budget/summary.py`, `budget/notifications.py` (progi 14/7/2,
  „brakuje N” w ostatnich 7 dniach miesiąca, alias `notify.family`), `budget/web/*` (karta konta promocyjnego, kafelek),
  testy odpowiadające.
- Zmiana: warunek `cashless` liczony z księgi dla konta Velobanku z kluczem banku z E1; termin końca promocji ze stanu
  edycji (ręcznie wpisane parametry do czasu E3); dzwonek + powiadomienia; encja MQTT bez zmiany nazewnictwa.
- Test jak w E1.
- DONE: dla edycji 12/2026 na fixturze księgi licznik N/5, karta „zrób jeszcze N” w dzwonku, powiadomienia w progach
  14/7/2 (testy z zamrożoną datą), przelewy własne nie liczą się.
- NIE RÓB: parsera regulaminu (E3); rekomendacji (E4); zmian logiki karty kredytowej M15 poza wspólną funkcją licznika.
- Rollback: `git revert`.
- **Po E2: wydanie** (lokalnie: `simplify` → `code-review` → `release` → weryfikacja na żywo).

## E3 — Monitor i parser regulaminu (niezależny od E1/E2)
Wykonawca:
- Pliki: nowy `budget/promo_watch_velo.py` (albo uogólnienie `promo_watch.py` o źródła), `budget/inbox.py` (karta „nowa
  edycja”, alarm nieczytelnego regulaminu), testy z publicznym tekstem regulaminu jako fixture w `tests/fixtures/`.
- Zmiana: codzienny odczyt strony/regulaminu Velobanku (jak `promo_watch.py`: stały adres, stan w kv, `ERROR_ALERT_DAYS`),
  parser wyciąga stawkę, daty okna, próg transakcji i definicję liczonych operacji; walidacja zakresów (stawka 0–10%, daty
  w przyszłości/niedaleko); poza normą albo parse error → stan „wstrzymana”, nie wartości domyślne.
- Test jak w E1.
- DONE: fixture edycji 12/2026 → 4,5%, 1%, termin, próg 5; zmiana formatu → `WatchError`, alarm, rekomendacja wstrzymana;
  nowa edycja tworzy kartę do wglądu.
- NIE RÓB: żywych zapytań HTTP w testach; zapisu parametrów konta bez karty do wglądu; ruszania `promo_watch.py` w zakresie
  Profit poza niezbędnym uogólnieniem (testy Profit zielone bez zmian).
- Rollback: `git revert`; klucz kv nieszkodliwy.

## E4 — Rekomendacja „dokąd przelać”
Wykonawca:
- Pliki: nowy `budget/rotation.py`, `budget/inbox.py`, `budget/notifications.py`, `budget/web/*` (sekcja w karcie
  promocji), testy.
- Zmiana: z aktualnych stóp (E3) i sald kont porównanie „zostań vs przelej X zł na konto Y” z zyskiem w zł do końca okna;
  wstrzymana, gdy E3 w stanie „wstrzymana”; tekst „przelej sam” (Budżet nie przelewa).
- Test jak w E1.
- DONE: scenariusz Velo kończy promocję za 7 dni → rekomendacja przelewu na Profit z kwotą i zyskiem; edycja wstrzymana →
  brak rekomendacji + alarm.
- NIE RÓB: wywołań przelewów/PIS; zmiany prognozy odsetek (M10 E3).
- Rollback: `git revert`.
- **Po E4: wydanie końcowe** (`simplify` → `code-review` + `silent-failure-hunter` + security → `release` → weryfikacja).

## Chmura (claude --remote)
- Przed startem: push planu na `main` (chmura czyta tylko GitHub).
- Równolegle: sesja E3 + sesja E1 (rozłączne pliki); potem E2 (po merge E1), potem E4 (po E2+E3).
- Każdy prompt = sekcja **Wykonawca** dosłownie + repo `miczu71/ha-budget-app`. Wynik: gałąź/PR, lokalnie
  `verifier` + pytest przed merge. Koszt sesji nieznany — E3 jako pomiar.
- Przepływ nie rusza sekretów ani produkcji.

## Wyniki wykonania (stan 2026-10-26)

| Etap | Stan | Gdzie |
|---|---|---|
| E0 | zrobione 2026-10-22 | Velobank na liście Enable Banking (beta) |
| E1 | zmergowane 2026-10-26 (squash `53805ba`) | PR #1; review: brak blokujących |
| E2 | gotowe, **czeka na CI i merge** | PR #3 (`m32-e2-licznik`): +557/−21, 8 plików, pytest 1201 ok / 2 faile jak na `main`, ruff czysty, mypy bez nowych błędów, +26 testów |
| E3 | gotowe, **czeka na review i merge** | PR #2 (`m32-e3-parser`) |
| E4 | czeka na merge E2 i E3 | — |

**Dwa faile na czystym `main`** (nie z E1/E2): `test_web_recurring::test_recurring_flow`, `::test_reject_proposal`.
mypy: 75 błędów w testach, stan sprzed prac M32.

### Poprawki z review E1 (zrobione w E2, PR #3)
- Nieaktywna zgoda przy innym aktywnym banku → sync `partial` (nie `ok`); prefiks banku w `detail` zależy od `len(records) > 1`.
- `_sync_session` izoluje dowolny wyjątek (status `error`), reszta banków się synchronizuje.

### Otwarte uwagi (do decyzji, nie blokują)
- `partial` nie podbija `consecutive_failures` (wygasła zgoda widoczna w statusie, `detail` i alercie `session_inactive`). Zmiana wymaga ruszenia `consecutive_failures` — osobna decyzja.
- `finish_auth` nie sprawdza zgodności banku z wybranym w `pending` (UX); wspólny `pending_auth` dla wielu banków; `store_session` rozróżnia wielkość liter, `current()` nie; backfill migracji 029 zakłada jeden bank; brak testów: `finish_auth` z innym bankiem, backfill z kontami starszego banku.
- Alias `notify.family` nie jest w kodzie — idzie przez opcję `summary_notify_service` (ustawia user).

### Pomiar chmury i kredytu (ważne dla dalszej pracy)
- Kredyt „Cloud session credits” 100 USD (wygasa 2026-11-05) **nie zszedł**: 100/100 po review E1 (~85 tys. tokenów) i po E2 (~146 tys. tokenów).
- Przyczyna (potwierdzona): agent z `isolation: "remote"` wywołany z Claude Code **działał lokalnie** w kontenerze (worktree `~/dev/ha-budget-app-e2`, klon `/config/addons/ha-budget-app`), czyli poszedł z limitów planu, nie z kredytu cloud. Dotyczy też uruchomień E1/E3 z 2026-10-22.
- `/code-review ultra` nie działa przez Remote Control.
- Jedyna niesprawdzona droga do kredytu: sesja ręcznie na claude.ai/code (repo `miczu71/ha-budget-app`). Test: mała sesja (np. streszczenie sekcji E4), potem sprawdzić Settings → Usage. Jeśli kredyt nie spadnie → wsparcie Anthropic.
- Do 5.11 nie uruchamiać kolejnych agentów „remote” dla kredytu, dopóki test z claude.ai/code nie rozstrzygnie sprawy.

### Następne kroki
1. User: test sesji na claude.ai/code → wynik do tego pliku.
2. Merge PR #3 po CI i zgodzie; review i merge PR #2.
3. E4 (po E2+E3): w chmurze tylko jeśli test z p.1 pokaże zużycie kredytu, inaczej lokalnie wg kontraktu Wykonawca.
4. Po E4: wydanie końcowe (`simplify` → `code-review` + `silent-failure-hunter` + security → `release` → weryfikacja na żywo); wydanie po E2 łączone z końcowym, chyba że user zdecyduje inaczej.
