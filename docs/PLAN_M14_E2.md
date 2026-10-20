# Budżet: M14 E2 (wydajność, powrót do progów) + M12 E3d (pytania z dwóch źródeł)

## Context
- **M14:** pomiar na produkcji 0.61.0 (2026-10-20, Ingress, mediana z 5 prób) pokazał regres od 06.10:
  `/` 438→1053 ms, `/status` 130→1090, `/invest` 767, `/networth` 754, `/review` 462, `/recurring` 428,
  `/inbox` 407; pozostałe 230–380. Doszły M18/M22/M26/M11 (nowe ekrany, kafle, sensory).
- **M12:** stabilność pytań z dwóch źródeł zmierzona tylko dla pary „karta + do wypłaty” (8/8 w 0.56.2).

Decyzje z wywiadu (2026-10-20):
1. M14 cel = powrót do progów M14 E1: każdy ekran < 400 ms, `/` < 600 ms; poprawki tylko tam, gdzie profil wskaże czas.
2. M12 zakres = 8 realnych par × 3 próby = 24 pytania; sukces ≥ 90% odpowiedzi z obiema tabelami i liczbami zgodnymi z ekranami.
3. M12 poniżej 90% → poprawka promptu/planu w tym samym wydaniu i ponowny pomiar tych par.

Podsumowanie: korzysta tylko użytkownik (panel na telefonie i czat). Automatycznie: pomiary (GET-y i 24 pytania
czatu — trafią do logu czatu na Status), kod i testy lokalnie, commity etapów, na końcu jedno wydanie 0.62.0
(simplify → code-review → release → weryfikacja na żywo). Za zgodą: nic poza planem; stop, jeśli profil na kopii
nie odtwarza regresu (wtedy decyzja o wydaniu z samym pomiarem czasu). Sukces: progi spełnione na wszystkich ekranach
na żywo + M12 ≥ 90%.

Repo: `/config/addons/ha-budget-app` (`main`), kod w `budget/app/src/budget/`. Dokumenty: wiersze M12 i M14 w
`docs/ROADMAP.md` + `docs/PLAN_M14_E2.md` i `docs/PLAN_M12_E3d.md` (kopia tego planu jako pierwszy krok).

## Etapy

**E0 — pomiar M12 na 0.61.0 (bez kodu).** Pary: karta+budżet, budżet+cykliczne, rok+cykliczne, kredyt+inwestycje,
majątek+skarbonki, majątek+kredyt, skarbonki+do wypłaty, karta+do wypłaty (kontrola regresu). Po 3 próby przez
iframe Ingress (fetch POST na endpoint czatu, ten sam origin co przy pomiarze czasów). Liczę: obie tabele / jedna /
„nie umiem” / błąd; liczby porównuję z ekranami. Wyniki bez kwot do `PLAN_M12_E3d.md` § Pomiar.
Rollback: brak (tylko odczyt + wpisy w logu czatu).

**E1 — profil M14.** Kopia księgi z 02.10 w scratchpadzie (`devserve` wg notatki `budget_app_dev_environment`),
cProfile na `/`, `/status`, `/invest`, `/networth`, `/review`; czytanie handlerów pod kątem I/O na ścieżce żądania
(HA API/WS, NBP, RSS, freellmapi, odczyt `/share`) i obliczeń spoza `Snapshot` (M14 E1, sygnatura `total_changes` +
`data_version` + dzień). Hipotezy z liczbami do `PLAN_M14_E2.md`. Jeśli kopia nie odtwarza czasu → stop i pytanie.
Rollback: usunięcie kopii księgi.

**E2 — poprawki M14 (TDD).** Wzorzec z M14 E1: test „≤ 1 przeliczenie na dwa renderowania” / „render nie woła I/O”
(czerwony przed, zielony po), potem memo po sygnaturze `Snapshot` albo przeniesienie I/O do zadań w tle z wynikiem
w `kv`. Bez zmian logiki, schematu i encji. Pełne testy + ruff/mypy, commit. Etap ≥ 5 edycji → sekcja **Wykonawca**
w planie etapu dla `sonnet-worker` (worktree `wt new ha-budget-app m14-e2`) + `verifier`.
Rollback: `git revert` commitu etapu.

**E3 — poprawka M12 (warunkowo, gdy E0 < 90%).** Diagnoza na logu czatu (para, `unsupported` vs złe źródło),
zmiana `ask/query.py` `plan_prompt` / `SCHEMA` z testem w `tests/test_ask_engine.py`. Rollback: `git revert`.

**E4 — wydanie 0.62.0.** simplify → code-review (repo + `246f163..HEAD`) → release (bump, published, backup add-onu)
→ na żywo.

## Weryfikacja
- Lokalnie: `uv run pytest`, `ruff`, `mypy` na zielono; profil przed/po na kopii.
- Na żywo po 0.62.0: ten sam skrypt pomiaru w iframe Ingress (19 ścieżek, 5 prób, mediana) — każdy ekran < 400 ms,
  `/` < 600 ms; `/healthz` w trakcie `/` < 100 ms; konsola bez błędów panelu. M12: ponowny pomiar par < 100%
  (wszystkich, jeśli był E3). Wynik do ROADMAP (M12, M14) i obu planów.
