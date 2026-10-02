# Roadmap — Budżet Domowy

Specyfikacja wyjściowa: [`SPEC.md`](SPEC.md) — **§10 (plan pracy) oraz §4, §5.2–5.4 i §6 zastępuje
ten dokument** (sekcja „Zmiany względem SPEC”). Przegląd rynku: [`BENCHMARK.md`](BENCHMARK.md).
Fakty o źródłach danych: [`FINDINGS_millennium.md`](FINDINGS_millennium.md),
[`FINDINGS_millenet_csv.md`](FINDINGS_millenet_csv.md).

Zasada pracy: etapy od fundamentu do wartości, każdy samodzielnie użyteczny. Szczegółowy plan
etapu (`docs/PLAN_<etap>.md`) jest akceptowany przed startem; po etapie checkpoint (przegląd +
jawne „go” przed następnym).

| Etap | Cel / wartość | Status |
|---|---|---|
| M0 | Szkielet repo, CI, `settings.py`, maskowanie w logach | ✅ |
| M1 | Klient Enable Banking + CLI, flow na Sandboxie | ✅ |
| M1b | Sonda Production Restricted na Millennium → `FINDINGS_millennium.md` | ✅ (drugi zrzut 2026-10-02: `entry_reference` stabilny) |
| M2 | **Rdzeń danych** — jedna księga bez duplikatów (CSV + API, karta↔konto, uzgadnianie salda) | zrealizowany 2026-10-02 (`PLAN_M2.md` § Wynik) — czeka checkpoint |
| M3 | **Add-on w HA** — instalacja, synchronizacja 3×/dobę, panel (status, bank, import, transakcje), podstawowe encje | — |
| M4 | **Kategoryzacja v1** — słownik polskich sieci, reguły, pamięć poprawek, kolejka + HA to-do | — |
| M5 | **Budżet Flex w HA** — stałe/elastyczne/nieregularne, cykliczne płatności, encje, statystyki, dashboard | — |
| M6 | **Podsumowania + kalendarz płatności** — tydzień/miesiąc na telefon, kalendarz ICS | — |
| M7 | **Kategoryzacja v2** — lokalny klasyfikator + opcjonalnie LLM przez `ai_task` | — |
| M8 | **Prognoza przepływów** — saldo do końca miesiąca, „bezpiecznie do wydania” | — |
| M9 | **Majątek netto + kredyt** | — |

Mapowanie starego planu (SPEC §10) na nowy: storage+dedup → M2; sync_service, panel, pakowanie,
HA publisher (podstawy) → M3; kategoryzacja → M4/M7; `budget_engine` → M5; import CSV → M2;
test end-to-end na produkcji → kryteria akceptacji M3.

## Decyzje użytkownika (wywiad 2026-10-01)

1. **Zakres: tylko 3 podlinkowane konta** (rachunek PLN, rachunek EUR, karta kredytowa).
   Przelewy na inne konta (także własne, niepodlinkowane) są wydatkami/wpływami kategoryzowanymi
   według odbiorcy — np. „Rodzina”, „Oszczędności” (grupa oszczędności, nie wydatek elastyczny).
2. Karta kredytowa ma kartę dodatkową — **bez funkcji „kto wydał”** (API nie podaje numeru karty);
   druga karta istotna tylko dla deduplikacji importu CSV.
3. Metoda budżetu: **Flex + opcjonalne limity** (stałe / elastyczne / nieregularne).
4. Okres: **miesiąc kalendarzowy**.
5. Kategoryzacja: **lokalnie, LLM opcjonalnie** (`ai_task.generate_data`, minimalizacja danych).
6. Priorytety HA: **podsumowania** oraz **kalendarz płatności + to-do „do przejrzenia”**.
7. Dalsze etapy: **prognoza przepływów**, **majątek netto + kredyt**.
8. CSV z Millenetu = historia; ponowny import dozwolony (idempotentny).
9. Fixture CSV w repo dopiero po usunięciu lokalizacji sklepów/bankomatów.

## Zmiany względem SPEC (zweryfikowane na danych)

- **§4 klucz konta:** zastępczy `account.id` + aliasy (hashe EB, IBAN, numery kart z CSV) zamiast
  `identification_hash` jako PK — hash to funkcja (IBAN, waluta), więc koliduje.
- **§5.2 deduplikacja:** tabela referencji zewnętrznych + odcisk transakcji z indeksem wystąpienia
  (odporne na przenumerowanie licznika w `entry_reference`), granica CSV/API, parowanie przelewów
  karta↔konto, parowanie zwrotów — szczegóły w M2.
- **§5.3 kategoryzacja:** krok MCC usunięty (Millennium nie podaje MCC); w zamian słownik polskich
  sieci, typ transakcji, pamięć sprzedawców, klasyfikator, LLM.
- **§5.4 / §6 budżet i encje:** Flex zamiast samych limitów per kategoria; zdarzenia i alerty
  w czasie rzeczywistym → backlog (zostają operacyjne: zgoda, błędy synchronizacji).
- **§10 kolejność:** pakowanie add-onu wcześniej (M3), bo poprawianie kategorii wymaga panelu.

## Wnioski z danych, na których stoi plan (metryki metody, bez danych osobowych)

- **Spłaty karty:** po stronie rachunku w API — pusty opis, brak kontrahenta; po stronie karty
  „WCZESN.SPL.Z RACHUNKU”. Parowanie (ta sama kwota, przesunięcie 0–1 dnia) trafiło **7/7**.
  Bez parowania wydatki kartą liczą się podwójnie (karta przejmuje coraz większą część wydatków).
- **CSV↔API:** rachunek w oknie wspólnym **370/370** zgodnych po (data rozliczenia, kwota);
  karta: zdublowany blok pod dwoma numerami kart, a zakupy walutowe mają w CSV inną kwotę PLN
  niż w API (mediana różnicy ~2%) → CSV tylko przed granicą API.
- **Saldo w CSV ciągłe** (0 przerw w ~2800 parach wierszy) → kontrola kompletności importu.
- **Typ transakcji** jest tylko w CSV; heurystyka odtwarza go z pól API w **89%** przypadków.
- **Kategoryzacja z pudełka** (słownik ~200 słów kluczowych polskich sieci + typ transakcji):
  **67% transakcji / 53% kwoty**. Resztę kwot niosą głównie przelewy do osób (reguły per
  odbiorca) — top 10 odbiorców pokrywa większość takich przelewów; top 50 nieznanych sprzedawców
  podnosi pokrycie transakcji do ~81%; długi ogon to sprzedawcy jednorazowi (→ M7).
- **Zwroty:** 86% daje się sparować z wcześniejszym zakupem (ten sam sprzedawca, ≤ 90 dni).
- **Płatności cykliczne** są znaczącą częścią miesięcznych wydatków; zdarzają się pojedyncze
  bardzo duże przelewy jednorazowe → flaga „jednorazowe / wyłączone z budżetu”.

---

## M2 — Rdzeń danych: jedna księga bez duplikatów

**Wartość:** cała historia (CSV) + API w jednej, zdeduplikowanej księdze, spłaty karty jako
przelewy, saldo uzgodnione.

- `storage/`: SQLite, migracje `NNN_*.sql` + `PRAGMA user_version`. Tabele: `account`
  (+ `account_alias`), `txn` (kwota ze znakiem jako tekst/Decimal, `orig_amount`/`orig_currency`,
  `kind` + `kind_source`, `transfer_group`, `refund_of`, `budget_flag`, `fingerprint`,
  `raw_json`), `txn_ref` (source, konto, ref — UNIQUE), `import_batch`, `balance_snapshot`,
  `eb_session`, `sync_log`.
- `csv_import.py`: parser Millenetu (BOM, CRLF, QUOTE_ALL, kropka dziesiętna, waluta oryginalna
  z opisu karty), mapowanie numerów kart → konto karty (propozycja automatyczna po nakładaniu
  się z API).
- **Warstwy deduplikacji:**

  | Warstwa | Reguła |
  |---|---|
  | L0 w obrębie źródła | CSV: ten sam klucz pod różnymi numerami kart → max(liczności), nie suma (prawdziwe „bliźniaki” zostają). API: referencja, potem odcisk (konto, data, kwota, opis znormalizowany) + indeks wystąpienia. |
  | L1 CSV↔API | Wiersze CSV sprzed najstarszej transakcji API danego konta → wstawiane; w oknie wspólnym CSV tylko **wzbogaca** (typ, konto kontrahenta, oryginalna waluta): rachunek 1:1, karta dokładnie lub rozmyto (sprzedawca, ±5 dni, kwota ±5% przy walucie obcej). Niesparowane → raport, nie księga. |
  | L2 przelewy | DBIT konto A ↔ CRDT konto B (oba podlinkowane), ta sama kwota, 0–3 dni; sygnały: pusty opis / typ „WCZEŚN.SPŁ” / „WCZESN.SPL.Z RACHUNKU” / własny IBAN. Strona bez pary (poza oknem) też oznaczana jako przelew. |
  | L3 zwroty | CRDT-zwrot → zakup u tego samego sprzedawcy ≤ 90 dni, kwota ≤ zakupu (`refund_of`; kategorię dziedziczy w M4). |
  | L4 PDNG→BOOK | Ogólnie jak w SPEC (Millennium nie zwraca PDNG). |

- Typ transakcji dla API odtwarzany heurystycznie, z `kind_source`.
- **Uzgadnianie salda:** ciągłość salda CSV, saldo na granicy CSV/API, `balance_snapshot` (ITBD)
  vs saldo z księgi → rozbieżność = brak lub duplikat → raport.
- CLI `budget ingest` / `budget report` (same liczby). Na start: drugi zrzut API (stabilność
  `entry_reference`, informacyjnie — odcisk i tak obsługuje przenumerowanie).

**Akceptacja:** 0 duplikatów (suma kontrolna salda zgodna na każdym koncie); 7/7 spłat
sparowanych; zdublowany blok karty usunięty; ponowny import = brak zmian; testy na danych
syntetycznych i zanonimizowanej próbce.

## M3 — Add-on w HA: pierwsze uruchomienie

**Wartość:** add-on działa, synchronizuje 3×/dobę, dane w panelu lokalnie.

- Dockerfile wg pozostałych add-onów autora (`python:3.12-alpine`; decyzja o obrazie `base` tu),
  `run.sh`, AppArmor, Ingress (`X-Ingress-Path`, allowlista `172.30.32.2`), zasady cache dla
  WebView (`no-store`, `?v=`, plakietka wersji).
- `sync_service`: harmonogram, licznik 4 zapytań/dobę, backfill, `sync_log`; **migracja sesji
  z CLI** (bez nowego SCA; zgoda ważna do 2027-03-30).
- Panel (htmx, mobile-first): Status, Połącz bank / Odnów zgodę, Import CSV (z raportem
  L0–L3), Konta, Transakcje (lista z filtrami).
- MQTT: salda (ITAV), `last_sync`, `consent_days_left`, liczba do przejrzenia, `sync_now`;
  powiadomienia operacyjne (zgoda wygasa, 3 nieudane synchronizacje).
- Wydanie: GitHub release (skill `release`), aktualizacja przez Supervisor.

**Akceptacja:** instalacja i synchronizacja działają; panel zweryfikowany w Playwright
(zrzut + 0 błędów konsoli); encje widoczne w HA.

## M4 — Kategoryzacja v1 (lokalna)

**Wartość:** wydatki w kategoriach przy minimum ręcznej pracy.

- Normalizacja sprzedawców (`LIDL UL. PRZYKLADOWA MIASTO POL` → „Lidl”, `AMZN*…` → „Amazon”).
- Wersjonowany **słownik polskich sieci** dostarczany z add-onem.
- Silnik reguł: warunki (pole/operator/wartość, kierunek, konto, typ, zakres kwot) → akcje
  (kategoria, nazwa sprzedawcy, przelew, wyłączenie z budżetu); priorytety, podgląd „ile pasuje”,
  „zastosuj do historii” (bez nadpisywania ręcznych).
- **Pamięć sprzedawców** z poprawek + podpowiedź „utwórz regułę”; reguły per odbiorca przelewów;
  domyślne kategorie typów (gotówka, opłaty, kredyt); zwrot dziedziczy kategorię zakupu.
- Kolejka „do przejrzenia” w panelu + **HA to-do „Budżet — do przejrzenia”** (Local To-do;
  odhaczenie = akceptacja podpowiedzi, zmiana kategorii przez link do panelu).
- Kategorie seed z grupami Flex.

**KPI:** pokrycie automatyczne ≥ 67% transakcji / ≥ 53% kwoty od startu; po ~1 h przeglądu
(top sprzedawców i odbiorców) **≥ 85% transakcji i ≥ 85% kwoty**.

## M5 — Budżet Flex w HA

**Wartość:** „ile zostało?” i „gdzie uciekają pieniądze?” w HA.

- Grupy kategorii: przychody, stałe, elastyczne, nieregularne („skarbonki”: cel roczny →
  miesięcznie, z przeniesieniem), oszczędności, przelewy, wyłączone/jednorazowe.
- **Wykrywanie płatności cyklicznych** (seria, kadencja, oczekiwana kwota i data) → plan kosztów
  stałych; budżet elastyczny z podpowiedzią (mediana 6 mies.) + opcjonalne limity per kategoria;
  prognoza końca miesiąca.
- Encje: `flex_remaining` / `flex_spent` / `flex_budget`, `fixed_paid` / `fixed_planned`,
  `month_income` / `month_expenses`, `savings_rate`, `category_<slug>` (wybrane), skarbonki.
- **Statystyki zewnętrzne** (`recorder/import_statistics`) z backfillem całej historii CSV.
- Dashboard „Budżet” (zapis przez WebSocket, weryfikacja Playwright).

**Akceptacja:** suma grup = wydatki z księgi (bez przelewów); historia widoczna w wykresach HA.

## M6 — Podsumowania + kalendarz płatności

- Podsumowanie tygodniowe (poniedziałek) i miesięczne (1.) przez konfigurowalną usługę notify
  (alias osoby, nigdy `mobile_app_*`): wydatki vs plan, zostało (Flex), top kategorie, największe
  pozycje, zmiany cen subskrypcji, liczba do przejrzenia + link do panelu.
- **Kalendarz:** add-on serwuje ICS z nadchodzącymi płatnościami (serie cykliczne, raty) →
  integracja HA **Remote Calendar**; po synchronizacji `homeassistant.update_entity`.

**Akceptacja:** podsumowanie dociera na telefon; kalendarz pokazuje płatności na 60 dni.

## M7 — Kategoryzacja v2 (uczenie + opcjonalnie LLM)

- Lokalny klasyfikator (czysty Python, naive Bayes na n-gramach sprzedawcy + typ + przedział
  kwoty) uczony na poprawkach, z progiem pewności.
- Opcjonalny fallback **`ai_task.generate_data`** (odpowiedź strukturalna `{category,
  confidence}`), encja konfigurowalna. Wysyłane wyłącznie: oczyszczona nazwa sprzedawcy, typ,
  przedział kwoty — **nigdy** nazwiska, IBAN-y, tytuły przelewów. Paczki ≤ 50 sprzedawców, cache
  per sprzedawca, dzienny limit.
- Panel jakości: pokrycie, precyzja.

**KPI:** **≥ 92% transakcji automatycznie**, precyzja ≥ 95% (< 5% poprawianych w 30 dni),
kolejka do przejrzenia ≤ 15/tydzień.

## M8 — Prognoza przepływów

- Saldo przewidywane dzień po dniu do końca miesiąca i do najbliższego wpływu (serie cykliczne,
  wykryte wpływy, tempo wydatków elastycznych).
- `safe_to_spend` = saldo − płatności stałe do najbliższego wpływu − bufor; ostrzeżenie
  (podsumowanie + powiadomienie persistent), gdy prognozowane minimum < próg przed ratą.

**Akceptacja:** backtest — prognoza z 1. dnia vs rzeczywiste saldo końca miesiąca (6 mies.).

## M9 — Majątek netto + kredyt

- Salda kont (EUR po kursie NBP), zadłużenie karty, inwestycje z konfigurowalnych encji HA.
- Kredyt: parametry wpisane ręcznie lub okresowe saldo kapitału + wykryte raty → harmonogram,
  pozostały kapitał, data spłaty; statystyki majątku w czasie.

**Akceptacja:** majątek netto zgodny z przeliczeniem ręcznym; harmonogram zgodny z parametrami.

## Backlog (świadomie odłożone)

Alerty w czasie rzeczywistym (duży wydatek, 80/100% limitu, wpływ) · Assist / czat ·
integracje z innymi add-onami (np. tankowania, rachunki za energię) · rozliczenia z osobami ·
„kto wydał” z CSV · kolejne konta i banki · eksport (CSV/XLSX, Firefly III, Actual) · podział
transakcji (split) i tagi · paragony.

## Zasady przekrojowe

- Zero danych osobowych w logach, repo i fixture'ach; do repo tylko dane syntetyczne albo
  zanonimizowane i przejrzane. Analizy prawdziwych danych wyłącznie lokalnie (raporty = liczby).
- CI zielone przed każdym checkpointem; wydania przez GitHub release; UI weryfikowane
  w Playwright.
- DOCS: kopia zapasowa HA zawiera dane finansowe.
- Odnowienie zgody bankowej przed 2027-03-30.

---

## Historia decyzji technicznych

- **2026-10-01 — add-on, nie integracja.** Encje przez MQTT Discovery. Integracja
  SurfHost/ha-enablebanking tylko jako punkt odniesienia.
- **2026-10-01 — klucz EB generowany lokalnie** (`python -m budget.cli keygen`: RSA +
  self-signed cert); do Control Panelu EB trafia tylko certyfikat. Rejestracja przez
  `POST /api/applications` wymaga JWT sesji Control Panelu, więc w pełni z CLI się nie da.
- **2026-10-01 — M1b przed M2:** deduplikacja zależy od zachowania Millennium, którego Sandbox
  nie pokaże.
- **Dane prywatne w dev** (PEM, `.env`, zrzuty z banku, surowy CSV) — poza repo, w katalogu
  deweloperskim kontenera.
- **2026-10-01 — CSV potrzebny:** Millennium przez PSD2 oddaje tylko 90 dni (także zaraz po SCA
  i ze `strategy=longest`).
- **2026-10-01 — roadmapa M2–M9** na podstawie benchmarku i analizy danych (ten dokument).
- **Do rozstrzygnięcia w M3:** obraz bazowy (`ghcr.io/home-assistant/base` wg SPEC vs
  `python:3.12-alpine` jak w innych add-onach autora).

## Wnioski z Sandboxa (M1, 2026-10-01)

- Klucz z `cli keygen` przyjęty przez Control Panel (opcja „Generate outside the browser and
  import public certificate”). Pola Privacy/Terms URL muszą być prawdziwymi URL-ami.
- `GET /aspsps?country=PL`: „Bank Millennium” (beta) i „Mock ASPSP”; `maximum_consent_validity`
  = 180 d, brak `required_psu_headers`.
- Sandbox Millennium: konta i salda, **zero transakcji** — do testów transakcji Mock ASPSP
  z `tools/make_mock_dataset.py`.
- Mock ASPSP: wszystkie transakcje w jednej stronie, gubi `transaction_id` (zostaje
  `entry_reference`).
- `identification_hash` = hash z (IBAN, waluta) — ten sam IBAN dwa razy w sesji = ten sam hash.
- Błąd po stronie banku przychodzi jako `?state=…&error=server_error`; link autoryzacji
  utworzony przed wgraniem danych do Mock ASPSP kończył się `server_error`.
