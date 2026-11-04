# M14 (dokończenie): szybki dzwonek i strony panelu Budżetu → wydanie 0.73.0

## Context
M14 jest jedynym otwartym etapem roadmapy Budżetu. Po 0.66.0 (E2c) `/status` trwa ~1250 ms (cel < 400),
`/` ~1640 ms, `/inbox` ~2400 ms. Na każdej stronie ~1100 ms zjada dzwonek (`inbox.ITEMS`). Główni podejrzani to
`rotation_card` (`rotation.recommend`) i `promo_track_due` (`promo_track.tracks`), ~500 ms każdy. Oba wołają
`ledger.savings_transfer_ids(conn)`, czyli pełne `_analyze(conn)`: skan wszystkich zaksięgowanych (BOOK) transakcji
i dopasowanie L2. Nic tego wyniku nie zapamiętuje, więc liczy się od nowa przy każdym renderowaniu, i to kilka razy.
Wzorzec memo już jest: `Snapshot` (`budget/app/src/budget/snapshot.py`) — sygnatura `(total_changes, data_version)`,
bez zapisu w trakcie transakcji (`candidates`, `members`, `piggy_ids`). Dzwonek dostaje `ctx.snap`.

Ustalenia z wywiadu (2026-11-04):
- **Kto korzysta:** user w panelu (telefon/komputer). Każda strona ładuje się szybciej, a wyniki (kwoty, liczniki,
  karty dzwonka) się nie zmieniają.
- **Sukces:** dzwonek < 150 ms, `/status` < 400 ms, `/` < 600 ms, `/inbox` < 600 ms. Liczy się mediana z 5 pomiarów
  `Server-Timing` na produkcji po wydaniu.
- **Zakres:** naprawiam każdego winnego z profilu, aż progi zostaną spełnione. Staję tylko wtedy, gdy poprawka
  zmieniłaby wynik (kwotę, licznik), a nie sam czas.
- **Dane:** na produkcji tylko GET-y przez playwright-ha (Server-Timing). Lokalnie cProfile na kopii z 02.10
  z dosianymi kontami Velo i aktywnymi `promo_track`.
- **Automatycznie:** etapy po kolei i jedno wydanie 0.73.0 na koniec (simplify → code-review → release → pomiar).
  **Za zgodą:** nic spoza planu. Restartu HA nie robię.

Repo: `/config/addons/ha-budget-app` (PUBLIC), gałąź `main`. Testy z `budget/app`:
`BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q`, `ruff check`, `mypy`.
Pierwszy krok implementacji: skopiować ten plan do `docs/ROADMAP_M14_dzwonek.md` i dopisać wiersz M14 + 0.72.1 w `docs/ROADMAP.md`.

## Etapy

### E3 — profil (fundament, bez zmian kodu w repo)
1. Na żywo (playwright-ha, Ingress `/a9413a25_budget`): po 5× GET `/status`, `/`, `/inbox`. Z `Server-Timing` odczytuję
   kroki `p_*` (źródła dzwonka) i `s_*`/`h_*`. Mediana trafia do tabeli „przed”.
2. Lokalnie, w scratchpadzie: kopia `~/budget_dev/prod/ledger.db` + dosiane konta Velo (#4/#5), aktywna `promo_track`
   z licznikiem bezgotówkowym i edycja rotacji. cProfile `inbox.collect` (albo odpowiednika z `inbox.py`) — ile razy
   i za ile liczy się `_analyze`, jakie inne gorące kroki.
3. Wynik: lista winnych z czasem i przyczyną w `ROADMAP_M14_dzwonek.md` § E3. Jeśli winny nie jest `_analyze`,
   E4 przestawiam na tego winnego (w tym samym wzorcu memo). Pytam tylko, gdy poprawka zmieniałaby wyniki.
- Rollback: nie dotyczy (sam odczyt; kopia w scratchpadzie).

### E4 — memo `savings_transfer_ids` na `Snapshot` (wartość: −~1000 ms na każdej stronie)
Plan wykonawcy w `docs/PLAN_M14_E4.md` (sekcja **Wykonawca**, `haiku-worker` w `wt new`, potem claimcheck + `verifier`):
- `snapshot.py`: `Snapshot.savings_ids() -> set[int]` = `ledger.savings_transfer_ids(conn)`, z pamięcią po sygnaturze
  i bez zapisu przy `conn.in_transaction` (jak `piggy_ids`). Zwraca kopię albo `frozenset`, żeby wywołujący nie zepsuł cache.
- `promo_track.tracks(..., savings: set[int] | None = None)` i `active_for_bank(..., savings=None)`: przy `None` jak dziś.
- `rotation.recommend(conn, today, savings=None)`: przekazuje dalej, jeśli woła `promo_track`.
- `inbox.rotation_card` / `promo_track_due` (i inne źródła z tym samym skanem, znalezione w E3) podają `ctx.snap.savings_ids()`.
- TDD: (a) drugie wywołanie przy tej samej sygnaturze nie liczy `_analyze` (monkeypatch licznika); (b) zapis do `txn`
  unieważnia; (c) w transakcji nie zapisuje cache; (d) `promo_track.tracks` z `savings` = bez niego (te same liczniki).
- `NIE RÓB:` zmian w `_analyze`/`rebuild_links`/`categorize/engine.py`, w kolejności źródeł dzwonka ani w treści kart.
- DONE: pytest/ruff/mypy zielone; lokalny profil: `_analyze` liczy się ≤ 1× na renderowanie dzwonka, a przy ciepłym cache 0×.
- Rollback: `git revert <commit>` (parametry opcjonalne, brak migracji).

### E5 — kolejni winni (warunkowo, gdy profil E3 lub pomiar po E4 nie mieści się w progach)
Każdy winny to podetap `E5a`, `E5b`… z własnym `docs/PLAN_M14_E5x.md` przed kodem. Wzorzec: memo na `Snapshot`/`ctx`
albo policzenie raz na żądanie. Wynik musi być bitowo ten sam (test równości). Najprawdopodobniej `/inbox` (pełna lista)
i `h_flex` na `/`. Rollback: `git revert`.

### Wydanie 0.73.0 (od razu po ostatnim etapie)
`simplify` → `code-review` (+ równolegle `silent-failure-hunter`, `pr-test-analyzer`, security review `general-purpose`
na `v0.72.1..HEAD`; zawiera też `fa5ff0a`) → skill `release` (bump, published) → aktualizacja przez `ha_manage_updates`
(`backup=true`) → pomiar na żywo.
Rollback wydania: `ha_manage_updates` nie cofa wersji, więc cofam przez `git revert` + 0.73.1.

## Weryfikacja
- Po każdym etapie kodu: pytest, ruff, mypy; lokalny pomiar `Server-Timing` na devserve (kopia z dosianymi danymi).
- Po wydaniu: playwright-ha, 5× GET `/status`, `/`, `/inbox`. Mediany vs progi (dzwonek < 150, `/status` < 400,
  `/` < 600, `/inbox` < 600 ms), konsola bez błędów. Karty dzwonka te same co przed wydaniem (porównanie listy tytułów
  z pomiaru E3). Logi add-onu bez błędów (`haiku-scout`).
- Wynik i tabela przed/po w `ROADMAP_M14_dzwonek.md` + wiersz M14 w `ROADMAP.md` ze statusem ✅, gdy progi są spełnione.

## Wynik E3+E4 (2026-11-04, produkcja 0.73.0, `Server-Timing`, mediana z 5 ciepłych żądań)

| Miara | Przed (0.72.1) | Po (0.73.0) | Próg | |
|---|---|---|---|---|
| dzwonek (`inbox`) | ~1170 ms | **~140 ms** | < 150 | ✓ |
| `/status` | ~1350 ms | **303 ms** | < 400 | ✓ |
| `/inbox` | ~2300 ms | **282 ms** | < 600 | ✓ |
| `/` | ~1640 ms | **615 ms** | < 600 | ✗ (o ~15 ms) |

- `p_rotation_card` 510 → 5 ms, `p_promo_track_due` 510 → 5 ms (na `/inbox` ~10 ms): przyczyna potwierdzona
  (wspólny `_analyze` przez `savings_transfer_ids`). Pierwsze żądanie po starcie add-onu jest zimne (`/status` 1561 ms), kolejne z pamięci.
- Zostało na dzwonku `p_series_changes` ~75 ms (150 ms na `/inbox`), na `/` `h_flex` ~124 ms, `h_networth` ~53 ms, `h_forecast` ~55 ms.
- Karty dzwonka bez zmian, panel renderuje się (zrzut), konsola 0 błędów, wersja 0.73.0 zgodna z tagiem.
- **Otwarte: E5a** — `/` o ~15 ms ponad próg; najtańsze kroki: `p_series_changes` (75 ms, liczone też w dzwonku) albo `h_flex`
  (124 ms). Zaczyna się od profilu tych dwóch na kopii z dosianymi danymi, potem plan etapu i wydanie 0.73.1 (osobny pomiar).
- Nieblokujące z przeglądów: `summary.py:294,350`, `routes_invest.py:57,77`, `routes_piggy.py:35,41` nadal liczą `_analyze` od zera
  (rozwiązanie ogólne: memo w `ledger.savings_transfer_ids`); `rotation_card` liczy `savings_ids()` także bez oferty Velo (bez regresu —
  `tracks()` robił to w 0.72.1 i tak); szablon memo w `Snapshot` powtórzony 4× (helper przy następnym memo).
