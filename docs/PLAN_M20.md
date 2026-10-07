# M20 — System designu „Budżet Domowy — Monarch” (artefakt Claude Design)

## Kontekst
Styl Monarch (M13, zamknięty 2026-10-06) żyje w `budget/app/src/budget/web/static/app.css` (`:root`, 896 linii)
i `DESIGN.md`. Chcemy przeglądalny **artefakt typu Design System** w Claude Design jako bazę dla przyszłych makiet
(M18 prognoza roczna, M19 Sankey) i refaktorów. Decyzje z wywiadu (2026-10-07):
- **Kod jest źródłem prawdy, artefakt lustrem.** Po każdej zmianie stylu w kodzie: re-sync artefaktu (procedura
  `from-code` typu). Zmian stylu nie projektujemy w artefakcie.
- **Pełny inwentarz komponentów** (wszystkie grupy klas z `app.css`), ale wgrywany etapami.

Ograniczenia: artefakt prywatny (domyślnie), w podglądach **tylko neutralne dane** (Sklep X, Osoba 1, Miasto A) —
żadnych danych z `~/budget_dev/prod`; fonty Inter/Source Serif 4 (OFL) i ikony Lucide (ISC) można wgrać;
bez commitów 02:45–03:15. Sukces = makieta w Claude Design zbudowana na tym systemie wygląda jak panel na żywo
(te same tokeny, fonty, komponenty), a re-sync po zmianie w `app.css` to jedna procedura z dokumentu.

## Gdzie leżą pliki
- Źródła artefaktu w repo: `/home/claude/ha-config/addons/ha-budget-app/design-system/project/…` (= `/config/addons/…`;
  ścieżka przez `/home/claude`, bo `root` publikacji musi być pod katalogiem roboczym). Poza kontekstem builda add-onu
  (build idzie z `budget/`), więc nie trafia do obrazu. Commit przechodzi przez hook prywatności (`scan_staged.py`).
- Plan: `docs/PLAN_M20.md` (kopia tego pliku) + wiersz M20 w `docs/ROADMAP.md`.

## Etapy (każdy z checkpointem; przed etapem pokazuję dokładne kroki i czekam na „go”)

### E0 — Dokumenty
- `docs/PLAN_M20.md`, wiersz M20 w `docs/ROADMAP.md`. Commit + push na `main`.
- Cofnięcie: `git revert`.

### E1 — Fundament: tokeny, fonty, ikony, README, okładka
1. Utworzenie artefaktu: `Artifact publish` z `type_url` Design System
   (`https://claude.ai/artifact/5M7UeXXcx16TP3vzVFNDzd`), tytuł „Budżet Domowy — Monarch”, `auto_open: after_first_write`.
2. `project/tokens.json` z `:root` w `app.css` (dokładne wartości, jeden motyw `light`):
   kolory (`canvas`, `surface-1..3`, `border`, `control-border`, `text`, `text-2`, `text-3`, `accent`, `on-accent`, `link`,
   `pos`, `neg`, `warn`, `ok-bg`/`warn-bg`/`error-bg`, `chart-1..8`, `chart-other`, `chart-unc` = alias `{warn}`,
   `bar-income`/`bar-expense` = aliasy), typografia (Serif Display 350–400 + tracking, Inter 350/400, tabular-nums),
   promienie (`r-card` 12/20 mobile, `r-input` 8, `r-btn`/`r-chip` pigułka), odstępy (siatka 4, karta 20/16, gap 16, `tap` 44),
   cień `elev`. Każdy token z `usage` z tabeli w `DESIGN.md`. Stare aliasy (`--bg`, `--card`, `--muted`…) tylko jako uwaga
   w README („nie używać w nowym kodzie”).
3. `project/fonts/InterVariable.woff2`, `project/fonts/SourceSerif4-latin.woff2` (kopie ze `static/fonts/`) + licencje w README.
4. Ikony Lucide jako uploady do grupy `assets/Ikony/` (te, które panel faktycznie używa: inline SVG z szablonów + chevron/check
   z masek CSS), `README.md` grupy z licencją ISC i zasadą „tylko SVG”.
5. `project/README.md` = księga stylu z `DESIGN.md` + `PRODUCT.md` (po polsku): kolory i role, typografia (w tym trik U+202F),
   kształt i głębia, zasady (jeden akcent, cele dotyku, nawigacja, ikony, wykresy, kontrast), kontekst WebView HA i cache-busting.
6. Okładka `components/Cover/preview.html` wg `artifact-type/reference/cover.md`.
7. Index `project/design-system.json` (`createdOnFiles`, `namespace: "Budzet"`, `libraries: []`) — wysłany ostatni.
- Weryfikacja: lokalny render okładki w Playwright (zrzut + konsola), kontrast tokenów tekstu ≥ 4,5:1 na `canvas`
  i `surface-1`, potem `Artifact open` dla Ciebie.
- Cofnięcie: usunięcie artefaktu (`Artifact delete`, tylko na Twoje polecenie) + revert katalogu.

### E2 — Komponenty rdzenia (wspólne dla wszystkich ekranów)
- `components/bundle.css` = `app.css` 1:1 (tylko ścieżki `@font-face` → `../fonts/…`), żeby podglądy renderowały się
  dokładnie jak panel; `bundle.js` pusty namespace (panel nie ma komponentów JS — htmx poza systemem).
- Znaczniki **przechwycone z prawdziwych szablonów**: dev server (`devserve.py` ze scratchpadu, notatka
  `budget_app_dev_environment`) na **świeżej księdze z `tests/fixtures/millenet_sample.csv`** (zanonimizowany fixture
  z publicznego repo), `outerHTML` elementów przez Playwright, potem ręczne skrócenie i podmiana nazw na neutralne.
- Grupy i komponenty: **Nawigacja** (`.top`, zakładki, `.more`/menu ⚙, `.bell`/`.badge`), **Układ** (`.card`, `.grid`,
  `.home-grid`, `.layout-*`, `.foot`), **Akcje i formularze** (przyciski, pola, `select`, `.tabs`, chipy `.cat-chip`, `a.tap`,
  wyszukiwanie `.search-form`/`.search-count`, `.pager`), **Listy** (`.rows`/`.row-*`, tabela transakcji + wariant kart na
  telefonie, `.kv`, `.stats`/`.stat-*`), **Kwoty** (`.num`, `.pos`/`.neg`, `.delta`/`.chg`/`.arrow`, `.hero-amount`),
  **Komunikaty** (`.msg`, `.warn-note`, `.fresh`, pusty stan).
- Każdy komponent: `README.md` (pierwsze zdanie = streszczenie, kiedy używać, wymagane klasy, cele dotyku) + `preview.html`.
- Weryfikacja: każdy podgląd renderowany lokalnie (390 i 1280 px) i porównany wzrokowo z tym samym elementem w panelu dev;
  konsola bez błędów; skan prywatności przy commicie.

### E3 — Wykresy i komponenty ekranów
- **Wykresy** (SVG z `_charts.html`, przechwycone z dev servera): koło kategorii + legenda (`.donut*`, `.legend*`),
  słupki 12 miesięcy (`.bars*`), karta „Zostało” (`.flex-hero`, `.flex-bar`, `.limit-*`), prognoza „Do wypłaty”
  (`.fc-*`), werdykt karty (`.card-limit`, `.due-verdict`).
- **Ekrany robocze**: Do przejrzenia (`.rv-*`, `.inbox*`), Reguły (`.rule-*`, `.pool`, `.steps`), Kategorie (`.cats`,
  `.subcats`, `.leaf*`), Cykliczne (`.series-*`), Zapytaj (`.ask-*`, `.chat-log`, `.ai-*`), Budżet (`.month-nav`, `.summary*`).
- Weryfikacja jak w E2. Na koniec raport: lista klas z `app.css` bez podglądu (jeśli zostaną) — świadomie pominięte albo do E4.

### E4 — Procedura re-sync i pamięć
- Sekcja „Re-sync systemu designu” w `DESIGN.md`: kiedy (każda zmiana `:root`, nowej grupy klas, fontów, ikon),
  kroki (read indexu → edycja plików w `design-system/project/` → jedna publikacja zmienionych plików → index ostatni),
  link do artefaktu. W `tokens.json` `meta.source` = `app.css @ <sha>`.
- Wpis o artefakcie (link, rola lustra, gdzie procedura) w notatce pamięci `-config/memory/project_budget_app.md`.

## Pliki krytyczne (odczyt źródeł)
- `budget/app/src/budget/web/static/app.css`, `DESIGN.md`, `PRODUCT.md`
- `budget/app/src/budget/web/templates/{base,_charts,_flex_hero,_forecast,_macros,…}.html`, `web/charts.py`
- `budget/app/src/budget/web/static/fonts/*`

## Ryzyka
- **Rozjazd z kodem** — łagodzi go E4 i `meta.source` z sha; artefakt jawnie oznaczony jako lustro.
- **Wyciek danych** — tylko fixture + neutralne nazwy; hook pre-commit na plikach `design-system/`; artefakt prywatny.
- **Rozmiar** — fonty ~510 KB, `bundle.css` ~30 KB; daleko od limitów (≤15 MiB/plik).
- **Publikacja do usługi zewnętrznej** — utworzenie artefaktu i każda publikacja dopiero po „go” danego etapu.

## Weryfikacja końcowa
Po E3: w Claude Design nowa makieta (np. szkic M19) z tym systemem — porównanie zrzutu z panelem dev
(fonty, kolory, karty, wiersze). Zamknięcie M20 Twoim checkpointem.

## Wynik (2026-10-07)
Artefakt: https://claude.ai/artifact/GgbLCb6vkcwtvKAEQ3wwzr (prywatny). Źródła w `design-system/project/`.
- E0 `b1efd84`: plan i wiersz roadmapy.
- E1 `9b118bc`: tokeny (29 kolorów, 9 stylów, odstępy, promienie, cień), fonty, 11 ikon SVG, README, okładka.
- E2 `0329eb8`: `bundle.css` z `app.css` i 16 komponentów rdzenia.
- E3 `0084711`: 13 komponentów (wykresy i ekrany robocze), SVG z prawdziwych makr `_charts.html`.
- E3b `22f6ee5` (dodatek poza pierwotnym planem, na życzenie): 7 komponentów domykających inwentarz;
  223 z 227 klas `app.css` ma podgląd (bez: `buffer`, `c1`, `c2`, `htmx-request`).
- E4: procedura re-sync w `DESIGN.md`, `meta.ref` w `tokens.json`; skrypt `check.py` (rozbieżności tokenów) pominięty.
Odchylenia: podglądy AI (AiCard, część ReviewExtras) to statyczne odwzorowania szablonów (w dev AI wyłączone);
`bundle.css` bez dwóch głównych `@font-face` (te kroje dają tokeny), zostaje blok U+202F.
Znaleziska poza M20: plakietka w `.row-title` prognozy rozciąga się na cały wiersz (rodzic `flex-direction: column`);
w publicznym fixture `millenet_sample.csv` jest ciąg z „gmail” do zbadania.
