# Benchmark — aplikacje do budżetu domowego (PL i świat), stan 2026-10

Cel: wybrać do roadmapy (`ROADMAP.md`) funkcje, które najlepsi robią dobrze, i świadomie odrzucić
resztę. Źródła na końcu.

## Polska

| Aplikacja | Wyróżniki | Uwagi dla nas |
|---|---|---|
| **Martia** | darmowa, PSD2 (2500+ banków, w tym Millennium), automatyczna kategoryzacja polskich sieci, **czat AI po polsku** („ile wydaliśmy na jedzenie w marcu?”), widok dla par z kontami w różnych bankach | czat → backlog (Assist); słownik polskich sieci → M4 |
| **Kontomierz** | najstarsza polska PFM, sync z bankami, tagi, eksport; freemium | — |
| **Wallet (BudgetBakers)** | sync z polskimi bankami, budżety, płatności planowane, wspólne konta, inwestycje | płatności planowane → M5/M6 |
| **EasyBudget** | sync, kategoryzacja **ucząca się**, metoda kopertowa/zero-based, budżet współdzielony | uczenie na poprawkach → M4/M7 |
| **Freenance** | majątek netto, „runway”, IKE/IKZE/ETF/obligacje (FIRE) | majątek netto → M9 |
| Szybki Budżet, Spendee, 4grosze, Monefy, Goodbudget | od ręcznych kopert po sync; wielowalutowość, wspólne portfele | — |
| Aplikacje banków (IKO, mBank, ING, Millennium) | analizy wydatków w obrębie jednego banku | — |

Wspólna luka polskich aplikacji (wg porównań): **nie opisują obsługi przelewów między własnymi
kontami, kart kredytowych ani deduplikacji** — dokładnie to, co robi M2.

## Świat

| Aplikacja | Co robi najlepiej | Co bierzemy |
|---|---|---|
| **Monarch Money** | budżet **Flex** (stałe / elastyczne / nieregularne), reguły (sprzedawca, kwota, konto → kategoria, nazwa, ukrycie), płatności cykliczne + kalendarz, **weekly recap**, AI assistant, majątek netto, cash flow | Flex (M5), reguły (M4), cykliczne (M5), podsumowania (M6), majątek (M9) |
| **Copilot Money** | kategoryzacja **ucząca się na poprawkach**, kolejka „to review”, cykliczne, przeniesienia budżetu | pamięć poprawek + kolejka (M4), klasyfikator (M7) |
| **YNAB** | zero-based („każda złotówka ma zadanie”), cele, **uzgadnianie salda (reconcile)**, dopasowanie importu do ręcznych wpisów | reconcile (M2) |
| **Actual Budget** (open source) | silnik reguł warunki→akcje, **deduplikacja importu**: najpierw ID, potem okno dat (do 5 dni wstecz) + kwota + podobny sprzedawca; różne ID importu blokują dopasowanie rozmyte | algorytm L0/L1 (M2) |
| **Firefly III** (open source, add-on HA) | reguły i grupy reguł, budżety, rachunki (bills), skarbonki, importer **Enable Banking** z detekcją duplikatów, webhooki; integracja HA core od 2025.11 | skarbonki → nieregularne (M5); lekcja: uid EB zmienia się z sesją → dedup musi go ignorować (M2) |
| **Lunch Money** | reguły, płatności cykliczne, grupowanie i podział transakcji, API, wielowalutowość | split/grupowanie → backlog |
| **Finanzguru** (DE) | wykrywanie umów i subskrypcji, prognoza do końca miesiąca | cykliczne (M5), prognoza (M8) |
| **Emma** (UK) | budżet od wypłaty, subskrypcje, podsumowania | podsumowania (M6) |
| **PocketGuard** | „In My Pocket” — ile bezpiecznie wydać | `safe_to_spend` (M8) |
| Plaid Enrich, Salt Edge | komercyjne API wzbogacania transakcji (sprzedawca, kategoria) | odrzucone: chmura + koszt; zamiast tego słownik + lokalne uczenie + opcjonalny LLM w HA |

## Alternatywy architektoniczne (rozważone)

- **(A) Własny add-on** — **wybrane.** Lekki (SQLite), natywny dla HA (statystyki, kalendarz,
  to-do, `notify`, `ai_task`), polskie specyfiki, automatyczna deduplikacja karta↔konto.
- **(B) Firefly III + importer EB + integracja HA:** dojrzały, ale ciężki (PHP + MariaDB), bez
  uczenia kategorii i parowania karta↔konto, polski CSV do ręcznego mapowania, integracja HA
  tworzy encję na każde konto; importer EB miał do 04.2026 błąd deduplikacji po odnowieniu zgody.
- **(C) Hybryda (nasz silnik + UI Actual/Firefly):** dwa systemy do utrzymania. Eksport do
  Firefly/Actual zostaje w backlogu.

## Źródła

- [Martia — aplikacja do budżetu domowego 2026](https://martia.pl/aplikacja-do-budzetu-domowego-2026)
- [EasyBudget — 9 aplikacji do kontroli wydatków (2026)](https://www.easybudget.pl/9-aplikacji-do-spisywania-wydatkow)
- [financer.pl — ranking aplikacji do budżetu 2026](https://financer.pl/finanse-osobiste/aplikacja-do-budzetu-domowego/)
- [Actual Budget — Importing Transactions](https://actualbudget.org/docs/transactions/importing/)
- [Firefly III — Import from Enable Banking](https://docs.firefly-iii.org/tutorials/data-importer/eb/)
- [Firefly III — duplicate detection](https://docs.firefly-iii.org/references/data-importer/duplicate-detection/)
- [Firefly III issue #12093 — EB accountUid a duplikaty](https://github.com/firefly-iii/firefly-iii/issues/12093)
- [Home Assistant — Firefly III integration](https://www.home-assistant.io/integrations/firefly_iii/)
- [Home Assistant Community Add-on: Firefly III](https://github.com/hassio-addons/addon-firefly-iii)
- [Copilot Money vs Monarch Money (2026)](https://getfinny.app/blog/copilot-money-vs-monarch-money-2026)
- [Home Assistant — AI Task](https://www.home-assistant.io/integrations/ai_task/)
- [Home Assistant — Remote Calendar](https://www.home-assistant.io/integrations/remote_calendar/)
- [Plaid Enrich](https://plaid.com/products/enrich/), [Salt Edge data enrichment](https://www.saltedge.com/products/data_enrichment)
