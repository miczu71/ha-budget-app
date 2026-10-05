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
| M2 | **Rdzeń danych** — jedna księga bez duplikatów (CSV + API, karta↔konto, uzgadnianie salda) | ✅ 2026-10-02 (`PLAN_M2.md` § Wynik) |
| M3 | **Add-on w HA** — instalacja, synchronizacja 3×/dobę, panel (status, bank, import, transakcje), podstawowe encje | ✅ 2026-10-03 (`PLAN_M3.md` § Wynik; limit PSD2 liczony per endpoint) |
| M4a | **Kategoryzacja v1** — słownik polskich sieci, silnik reguł z podglądem, ekran „Wydatki” | ✅ 2026-10-04 — pokrycie wydatków 97% transakcji / 98% kwoty (KPI 85/85) (`PLAN_M4a.md`) |
| M4b | **Kolejka „do przejrzenia”** w panelu (grupy sprzedawców i krajów) | ✅ 2026-10-04 — kolejka w użyciu, zapis rozwinięty w M4f/M4h (`PLAN_M4b.md`) |
| M4c | **Poza planem (2026-10-02):** kolejka dla wybranego miesiąca + podpowiedzi kategorii z AI (freellmapi), zatwierdzane jednym dotknięciem | ✅ 2026-10-04 — 0.5.0; 84% decyzji to przyjęte podpowiedzi (`PLAN_M4c.md`) |
| M4d | **Poza planem (2026-10-02):** nowe kategorie główne, przenoszenie podkategorii, usuwanie pustej głównej | 0.6.0 (`PLAN_categories_move.md`) |
| M4e | **Poza planem (2026-10-02):** wyszukiwanie na żywo (Reguły — nowe, Słownik, Transakcje), jednolite dopasowanie bez ogonków i wielkości liter, wiele słów | 0.6.1 (`PLAN_live_search.md`) |
| M4f | **Poza planem (2026-10-03):** kolejka „Do przejrzenia” — edytowalny tekst reguły (zawiera / zaczyna się od) z podglądem innych grup; filtr po propozycji AI + „✓” | etap 1 = 0.8.0 (tekst reguły), etap 2 = 0.8.1/0.8.2 (filtr AI + zatwierdzenie) — ✅ 2026-10-04, zapis zastąpiony w M4h etap 2 (`PLAN_review_rule_text.md`) |
| M4g | **Poza planem (2026-10-04):** wydajność — zapis reguły z kolejki i podgląd zwalniały z każdą regułą (dopasowanie po kolei: transakcje × reguły); indeks reguł „sprzedawca równa się” | 0.9.1 wydane i zainstalowane 2026-10-04 — podgląd na żywo ~10 s → ~0,8 s; ✅ 2026-10-04 (`PLAN_rule_index.md`) |
| M4h | **Poza planem (2026-10-04):** pełne warunki reguły w miejscu — kolejka „Do przejrzenia” (dowolne pola, kilka warunków I, kwota, kierunek; reguła może złapać część grupy, reszta zostaje w kolejce), potem Transakcje i grupy krajów | ✅ 2026-10-04 (checkpoint zamknięty przez użytkownika) — etap 1 = 0.10.0 (kolejka); etap 2 = 0.11.0 (zapis domyślnie bez reguły — „utwórz regułę” na żądanie we wszystkich miejscach; Transakcje, grupy krajów) (`PLAN_review_rule_conditions.md`) |
| M5a | **Budżet Flex: „ile mogę jeszcze wydać”** — ręczna kwota elastyczna, tempo, ekran „Budżet”, grupy edytowalne; potem encje | etap 1 = 0.7.0 wydane i zainstalowane 2026-10-02; etap 2 = 0.9.0 (encje `budget_flex_*`) wydane i zainstalowane 2026-10-04; etap 3 = 0.12.0 pula z dochodu (decyzja 14, `PLAN_M5a_income.md`) wydane i zainstalowane 2026-10-04 (z poprawką kontroli salda karty); etap 4 = 0.13.0 składniki puli + edycja kosztów stałych na ekranie Budżet (decyzja 15, `PLAN_M5a_fixed.md`) wydane i zainstalowane 2026-10-04; ✅ 2026-10-04 — checkpoint zamknięty przez użytkownika (`PLAN_M5a.md`) |
| M5b | **Płatności cykliczne + centrum powiadomień** — wykrywane serie (wydatki i wpływy, M/Q/Y) potwierdzane przez użytkownika, „co jeszcze zejdzie / wpłynie”, zmiany serii, dzwonek w panelu, stałe w puli z serii | plan zaakceptowany 2026-10-04 (`PLAN_M5b.md`, decyzja 16): E1 0.14.0 dzwonek + detektor, E2 0.15.0 ten miesiąc, E3 0.16.0 zmiany, E4 0.17.0 pula; E1 = 0.14.0 wydane i zainstalowane 2026-10-04 (`PLAN_M5b_E1.md`), ✅ checkpoint E1 zamknięty przez użytkownika 2026-10-05; E2 = 0.15.0 wydane i zainstalowane 2026-10-05 (`PLAN_M5b_E2.md`), ✅ checkpoint E2 zamknięty przez użytkownika 2026-10-05; plan E3 zaakceptowany (`PLAN_M5b_E3.md`), E3 = 0.16.0 wydane i zainstalowane 2026-10-05, czeka checkpoint E3; E4 po „go” |
| M5c | **Skarbonki, trendy, limity** — nieregularne z celem rocznym, wykresy miesięczne, opcjonalne limity, `savings_rate` | — |
| M6 | **Podsumowania + kalendarz płatności** — tydzień/miesiąc na telefon, kalendarz ICS | — |
| M7 | **Kategoryzacja v2** — lokalny klasyfikator (LLM przeniesiony do M4c) | — |
| M8 | **Prognoza przepływów** — saldo do końca miesiąca, „bezpiecznie do wydania” | — |
| M9 | **Majątek netto + kredyt** | — |
| M10 | **Moduł oszczędności** — cele i postęp oszczędzania, stopa oszczędności w czasie (zakres do wywiadu) | — |
| M11 | **Integracja z trackerem akcji** (osobny add-on autora) — wartość pakietu akcji w majątku netto, wpływy ze sprzedaży/dywidend powiązane z księgą (zakres do wywiadu) | — |
| M12 | **Czat AI z danymi** — pytania o własne finanse w języku naturalnym w panelu (zakres danych wysyłanych do LLM do ustalenia, jak decyzja 12) | — |
| M13 | **Całkowity refaktor UI** panelu (zakres i moment do wywiadu — może wejść wcześniej) | — |

Mapowanie starego planu (SPEC §10) na nowy: storage+dedup → M2; sync_service, panel, pakowanie,
HA publisher (podstawy) → M3; kategoryzacja → M4/M7; `budget_engine` → M5; import CSV → M2;
test end-to-end na produkcji → kryteria akceptacji M3; HA publisher (statystyki, dashboard) →
backlog (decyzja 10).

## Decyzje użytkownika (wywiad 2026-10-01)

1. **Zakres: tylko 3 podlinkowane konta** (rachunek PLN, rachunek EUR, karta kredytowa).
   Przelewy na inne konta (także własne, niepodlinkowane) są wydatkami/wpływami kategoryzowanymi
   według odbiorcy — np. „Rodzina”, „Oszczędności” (grupa oszczędności, nie wydatek elastyczny).
2. Karta kredytowa ma kartę dodatkową — **bez funkcji „kto wydał”** (API nie podaje numeru karty);
   druga karta istotna tylko dla deduplikacji importu CSV.
3. Metoda budżetu: **Flex + opcjonalne limity** (stałe / elastyczne / nieregularne).
4. Okres: **miesiąc kalendarzowy**.
5. Kategoryzacja: **lokalnie, LLM opcjonalnie** (`ai_task.generate_data`, minimalizacja danych).
   **Zmienione 2026-10-02 (M4c):** LLM przez lokalny router OpenAI-compatible (freellmapi) zamiast
   `ai_task`; zakres danych w decyzji 12.
6. Priorytety HA: **podsumowania** oraz **kalendarz płatności** (to-do „do przejrzenia” → backlog,
   decyzja 10).
7. Dalsze etapy: **prognoza przepływów**, **majątek netto + kredyt**.
8. CSV z Millenetu = historia; ponowny import dozwolony (idempotentny).
9. Fixture CSV w repo dopiero po usunięciu lokalizacji sklepów/bankomatów.
10. **(2026-10-02) Wszystkie wizualizacje w panelu add-onu, bez dashboardów w HA.** Po stronie HA
    zostają encje budżetu (automatyzacje, powiadomienia) i kalendarz płatności; HA to-do,
    statystyki długoterminowe HA i dashboard Lovelace → backlog.
11. **(2026-10-02) Kategoryzacja:** cel pierwszy „gdzie idą pieniądze” (ekran w panelu),
    kategorie dwupoziomowe, lukę po słowniku zamyka pełny silnik reguł; M4 dzielone na M4a/M4b.
12. **(2026-10-02) Dane wysyłane do LLM (M4c):** płatności kartą/BLIK — nazwa sprzedawcy i opis
    (po wycięciu IBAN-ów, numerów kart, e-maili, telefonów); przelewy — wyłącznie tytuł, bez nazwy
    odbiorcy i jej tokenów; kwota tylko jako przedział. Router przekazuje zapytania do darmowych
    chmur — zaakceptowane świadomie.
13. **(2026-10-02) Budżet Flex — pierwszy kawałek (M5a) odpowiada na „ile mogę jeszcze wydać”:**
    pula = kwota ustawiona ręcznie (podpowiedź: mediana 6 pełnych miesięcy), „wydane” = tylko grupa
    elastyczne + wydatki bez kategorii (ostrożnie, z dopiskiem); stałe i nieregularne obok jako
    informacja; odpowiedź = kwota + tempo (na dzień, kreska „gdzie powinieneś być dziś”), bez
    limitów per kategoria.
14. **(2026-10-04) Pula Flex z dochodu (M5a etap 3, zmienia decyzję 13):** pula miesiąca =
    wpływy z grupy przychody z poprzedniego miesiąca − mediana stałych (6 mies.); oszczędności
    nie są odejmowane. Pula idzie za faktyczną wypłatą (spadek po progu podatkowym obniża ją od
    następnego miesiąca) — bez średniej dochodu. Nadwyżka nietypowo wysokiego wpływu (premia)
    zostaje poza pulą. Ręcznie wpisana kwota nadpisuje automatyczną. Szczegóły:
    [`PLAN_M5a_income.md`](PLAN_M5a_income.md).
15. **(2026-10-04) Koszty stałe w puli = suma median podkategorii (M5a etap 4, zmienia sposób
    liczenia stałych z decyzji 14):** zamiast mediany miesięcznej sumy — składniki sumują się do
    kwoty w puli. Koszt stały = podkategoria z grupą „stałe” (bez ręcznych pozycji — M5b); jedno
    miejsce do przeglądu i edycji = rozwinięcie „Koszty stałe” w sekcji „Kwota budżetu”.
    Szczegóły: [`PLAN_M5a_fixed.md`](PLAN_M5a_fixed.md).

16. **(2026-10-04) Płatności cykliczne + centrum powiadomień (M5b, uzupełnia decyzję 15):**
    serie wykrywane automatycznie i potwierdzane przez użytkownika (także wpływy; kadencje
    miesięczna, kwartalna, roczna; roczne głównie ręcznie z transakcji). Stałe w puli = oczekiwane
    kwoty serii wydatkowych w przeliczeniu na miesiąc + mediany podkategorii „stałe” spoza serii;
    transakcje serii nie wchodzą do „wydane”. Serie wpływów nie zmieniają puli. Dzwonek w panelu
    zbiera wszystko, co czeka na decyzję (nowe serie, zmiany serii, nieskategoryzowane miesiąca,
    sprawy operacyjne) + encja `sensor.budget_inbox`. Szczegóły: [`PLAN_M5b.md`](PLAN_M5b.md).

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

- Dockerfile wg pozostałych add-onów autora (`python:3.12-alpine`, wersja przypięta),
  `run.sh`, AppArmor, Ingress (`X-Ingress-Path`, allowlista `172.30.32.2`), zasady cache dla
  WebView (`no-store`, `?v=`, plakietka wersji).
- `sync_service`: harmonogram, licznik 4 zapytań/dobę, backfill, `sync_log`; **migracja sesji
  z CLI** (bez nowego SCA; zgoda ważna do 2027-03-30).
- Panel (htmx, mobile-first): Status, Połącz bank / Odnów zgodę, Import CSV (z raportem
  L0–L3), Konta, Transakcje (lista z filtrami).
- MQTT: salda (ITAV), `last_sync`, `consent_days_left`, `sync_now`;
  powiadomienia operacyjne (zgoda wygasa, 3 nieudane synchronizacje).
- Wydanie: GitHub release (skill `release`), aktualizacja przez Supervisor.

**Akceptacja:** instalacja i synchronizacja działają; panel zweryfikowany w Playwright
(zrzut + 0 błędów konsoli); encje widoczne w HA.

## M4a — Kategoryzacja v1: silnik reguł + ekran „Wydatki”

**Wartość:** „gdzie idą pieniądze” — wydatki miesiąca w kategoriach, w panelu. Szczegóły:
[`PLAN_M4a.md`](PLAN_M4a.md).

- Normalizacja sprzedawców (`LIDL UL. PRZYKLADOWA MIASTO POL` → „Lidl”, `AMZN*…` → „Amazon”).
- Wersjonowany **słownik polskich sieci** dostarczany z add-onem (tylko sieci ogólnopolskie).
- **Jeden deterministyczny silnik:** ręczna > zwrot dziedziczy kategorię zakupu > reguły
  użytkownika > słownik > domyślne kategorie typów; przeliczanie od zera (wzorzec
  `rebuild_links`), ręczne nietykalne.
- Reguły: warunki (pole/operator/wartość, kierunek, konto, typ, zakres kwot) → kategoria
  (+ nazwa sprzedawcy); priorytety, **podgląd „ile pasuje / ile zmieni”** przed zapisem (zamiast
  osobnego „zastosuj do historii”). Pamięć poprawek = reguła tworzona z ręcznej zmiany.
- Kategorie seed (2 poziomy) z grupami Flex; wyłączenie z budżetu = kategoria z grupy `excluded`.
- Ekran **„Wydatki”**: miesiąc, kategorie z udziałem i zmianą m/m, rozwinięcie podkategorii,
  przejście do transakcji, nieskategoryzowane.

**KPI:** pokrycie automatyczne ≥ 67% transakcji / ≥ 53% kwoty od startu; po ~1 h sesji reguł
(top sprzedawców i odbiorców) **≥ 85% transakcji i ≥ 85% kwoty**.

## M4b — Kolejka „do przejrzenia”

**Wartość:** nowe transakcje bez kategorii lub z niepewną podpowiedzią nie giną.

- Kolejka w panelu: nieskategoryzowane i nowe od ostatniego przeglądu, grupowane po sprzedawcy
  / odbiorcy; akceptacja grupowa, „utwórz regułę” jednym kliknięciem.
- Liczba do przejrzenia liczona w add-onie (dla podsumowań M6), bez encji i HA to-do.
- **(2026-10-02) Kolejka = tylko nieskategoryzowane** (bez „nowych od ostatniego przeglądu” —
  automatycznie skategoryzowanych nie trzeba potwierdzać); grupa = sprzedawca + kierunek,
  domyślnie reguła, opcja „tylko te”; zagraniczne transakcje kartą grupowane po kraju.
  Szczegóły: [`PLAN_M4b.md`](PLAN_M4b.md).

## M4c — Kolejka miesiąca + podpowiedzi AI (poza planem, 2026-10-02)

**Wartość:** z ekranu „Wydatki” przegląda się tylko nieskategoryzowane z danego miesiąca;
dla grup w kolejce i transakcji bez kategorii AI podpowiada kategorię, zatwierdzaną jednym
dotknięciem. Część LLM z M7 przeniesiona tutaj; lokalny klasyfikator i KPI zostają w M7.

1. **0.3.1** — kolejka „Do przejrzenia” z filtrem miesiąca (zapis jak dotąd: domyślnie reguła).
2. **0.4.0** — silnik podpowiedzi: klient freellmapi, redakcja danych, cache w bazie, przebieg
   po synchronizacji, backtest trafności (`suggest-eval`) jako punkt decyzji przed etapem 3.
3. **0.5.0** — chip „AI: kategoria ✓ ✕” w kolejce (✓ = reguła dla grupy) i na liście Transakcji
   (✓ = kategoria ręczna jednej transakcji), „podpowiedz teraz”, statystyka przyjęte/odrzucone.

Szczegóły: [`PLAN_M4c.md`](PLAN_M4c.md).

## M5 — Budżet Flex

**Wartość:** „ile zostało?” i „gdzie uciekają pieniądze?” — w panelu add-onu.

**(2026-10-02) Podział:** M5a — „ile mogę jeszcze wydać” (ręczna kwota, tempo, ekran „Budżet”,
edycja grupy podkategorii; etap 2 = 0.9.0: encje `flex_*`), szczegóły [`PLAN_M5a.md`](PLAN_M5a.md);
M5b — płatności cykliczne, `fixed_paid`/`fixed_planned`; M5c — skarbonki, wykresy trendu,
opcjonalne limity, `savings_rate`, `month_income`/`month_expenses`, `category_<slug>`.
Poniżej zakres całego M5 sprzed podziału.

- Grupy kategorii: przychody, stałe, elastyczne, nieregularne („skarbonki”: cel roczny →
  miesięcznie, z przeniesieniem), oszczędności, przelewy, wyłączone/jednorazowe.
- **Wykrywanie płatności cyklicznych** (seria, kadencja, oczekiwana kwota i data) → plan kosztów
  stałych; budżet elastyczny z podpowiedzią (mediana 6 mies.) + opcjonalne limity per kategoria;
  prognoza końca miesiąca.
- Encje: `flex_remaining` / `flex_spent` / `flex_budget`, `fixed_paid` / `fixed_planned`,
  `month_income` / `month_expenses`, `savings_rate`, `category_<slug>` (wybrane), skarbonki.
- Encje bez dashboardu w HA (do automatyzacji i powiadomień).
- **Ekran „Budżet” w panelu:** Flex zostało/wydane, stałe zapłacone/planowane, skarbonki,
  wykresy trendu miesięcznego z własnej bazy (biblioteka wykresów serwowana lokalnie, nie z CDN).

**Akceptacja:** suma grup = wydatki z księgi (bez przelewów); historia widoczna w wykresach panelu.

## M6 — Podsumowania + kalendarz płatności

- Podsumowanie tygodniowe (poniedziałek) i miesięczne (1.) przez konfigurowalną usługę notify
  (alias osoby, nigdy `mobile_app_*`): wydatki vs plan, zostało (Flex), top kategorie, największe
  pozycje, zmiany cen subskrypcji, liczba do przejrzenia (liczona w add-onie) + link do panelu.
- **Kalendarz:** add-on serwuje ICS z nadchodzącymi płatnościami (serie cykliczne, raty) →
  integracja HA **Remote Calendar**; po synchronizacji `homeassistant.update_entity`.

**Akceptacja:** podsumowanie dociera na telefon; kalendarz pokazuje płatności na 60 dni.

## M7 — Kategoryzacja v2 (uczenie + opcjonalnie LLM)

- Lokalny klasyfikator (czysty Python, naive Bayes na n-gramach sprzedawcy + typ + przedział
  kwoty) uczony na poprawkach, z progiem pewności.
- ~~Opcjonalny fallback `ai_task.generate_data`~~ → **przeniesione do M4c** (freellmapi,
  zakres danych wg decyzji 12).
- Panel jakości: pokrycie, precyzja.

**KPI:** **≥ 92% transakcji automatycznie**, precyzja ≥ 95% (< 5% poprawianych w 30 dni),
kolejka do przejrzenia ≤ 15/tydzień.

## M8 — Prognoza przepływów

- Saldo przewidywane dzień po dniu do końca miesiąca i do najbliższego wpływu (serie cykliczne,
  wykryte wpływy, tempo wydatków elastycznych).
- Wykres prognozowanego salda na ekranie panelu.
- `safe_to_spend` (encja) = saldo − płatności stałe do najbliższego wpływu − bufor; ostrzeżenie
  (podsumowanie + powiadomienie persistent), gdy prognozowane minimum < próg przed ratą.

**Akceptacja:** backtest — prognoza z 1. dnia vs rzeczywiste saldo końca miesiąca (6 mies.).

## M9 — Majątek netto + kredyt

- Salda kont (EUR po kursie NBP), zadłużenie karty, inwestycje z konfigurowalnych encji HA.
- Kredyt: parametry wpisane ręcznie lub okresowe saldo kapitału + wykryte raty → harmonogram,
  pozostały kapitał, data spłaty; historia majątku w panelu (migawki we własnej bazie).

**Akceptacja:** majątek netto zgodny z przeliczeniem ręcznym; harmonogram zgodny z parametrami.

## Backlog (świadomie odłożone)

Alerty w czasie rzeczywistym (duży wydatek, 80/100% limitu, wpływ) · Assist (czat w panelu → M12) ·
integracje z innymi add-onami (np. tankowania, rachunki za energię; tracker akcji → M11) · rozliczenia z osobami ·
„kto wydał” z CSV · HA to-do „do przejrzenia” · statystyki długoterminowe HA (import/backfill) ·
dashboard Lovelace · słowniki sprzedawców zagranicznych (decyzja M4b: grupy po kraju) · kolejne konta i banki · eksport (CSV/XLSX, Firefly III, Actual) · podział
transakcji (split) i tagi · paragony.

## Zasady przekrojowe

- Zero danych osobowych w logach, repo i fixture'ach; do repo tylko dane syntetyczne albo
  zanonimizowane i przejrzane. Analizy prawdziwych danych wyłącznie lokalnie (raporty = liczby).
- CI zielone przed każdym checkpointem; wydania przez GitHub release; UI weryfikowane
  w Playwright.
- **Wizualizacje wyłącznie w panelu add-onu;** HA dostaje encje i kalendarz, nie dashboardy.
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
- **2026-10-02 — obraz `python:3.12-alpine` (przypięty), stos async wg SPEC §3** (FastAPI +
  uvicorn + htmx + APScheduler + aiomqtt w jednej pętli); Supervisor buduje lokalnie. Sesja
  przenoszona z CLI plikiem przez panel (bez nowego SCA), historia przez ponowny import CSV.
  Szczegóły i odstępstwa: `PLAN_M3.md`.
- **2026-10-02 — wizualizacje w panelu, nie w HA;** M4 dzielone na M4a (silnik reguł +
  „Wydatki”) i M4b (kolejka). Kategoria liczona deterministycznie od zera, bez przycisku
  „zastosuj do historii” (podgląd przed zapisem reguły). Szczegóły: `PLAN_M4a.md`.
- **2026-10-02 — M4b przed checkpointami M3/M4a;** kolejka przyspiesza sesję reguł. Słowniki
  zagraniczne odrzucone na rzecz grup po kraju (mały udział w luce). Szczegóły: `PLAN_M4b.md`.

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
