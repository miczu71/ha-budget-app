# M6 — Podsumowania na telefon + kalendarz płatności

Wywiad 2026-10-06. Wydane razem jako 0.22.0 (E1 + E2) na prośbę użytkownika — bez checkpointu
między etapami.

## Cel i ograniczenia

1. **Cel:** korekta wydatków w trakcie miesiąca — wiadomość mówi, czy Flex idzie zgodnie z tempem,
   zanim na reakcję będzie za późno. Kalendarz jest dodatkiem.
2. **Rytm:** poniedziałek 7:00 (po porannej synchronizacji) — tydzień; 1. dnia 7:00 — krótkie
   zamknięcie poprzedniego miesiąca. „Tydzień” = poniedziałek–niedziela przed wysyłką.
3. **Treść tygodnia:** zostało z puli + na dzień, tempo do wczoraj (o 7:00 dzień dopiero się
   zaczyna), top 3 kategorie główne tygodnia (wydatki elastyczne netto + bez kategorii, jak
   „wydane” w puli), płatności cykliczne w 7 dni (suma + 3 największe), do przejrzenia, link.
4. **Odbiorca:** osobna opcja `summary_notify_service` (na produkcji grupa wszystkich domowników); alerty
   techniczne zostają na `notify_service`. Puste = podsumowania wyłączone.
5. **Kalendarz:** `/calendar.ics` → integracja HA Remote Calendar; 60 dni naprzód (od początku
   miesiąca — także zapłacone, ze statusem); encja `calendar_entity` odświeżana po synchronizacji.
6. **Automatycznie:** wysyłka o 7:00, nadrabianie po restarcie tego samego dnia, odświeżenie
   kalendarza. **Ręcznie:** „Wyślij teraz” na Status (test).
7. **Sukces:** wiadomość dociera na oba telefony i zgadza się z ekranem Budżet; kalendarz w HA
   pokazuje te same terminy co ekran Cykliczne.

## Odrzucone

- Encja z gotowym tekstem + automatyzacja w HA (limit 255 znaków stanu, logika w dwóch repo).
- Alarm tempa w tygodniu, codzienna linia — użytkownik wybrał tydzień + zamknięcie miesiąca.
- ICS dostępny z telefonu (wymagałby wystawienia na zewnątrz z tokenem w URL).
- Zmiany cen subskrypcji w wiadomości — są w dzwonku (M5b E3).

## E1 — podsumowania

- `budget/summary.py`: `weekly`, `monthly`, `due` (termin, po 7:00, nie wysłane — `kv`
  `summary_sent`), `mark_sent`, `next_send`; kwoty w pełnych złotych.
- `Service.summaries()` — pętla obok `daily_tick`; `send_due_summaries` czeka na blokadę
  synchronizacji; `send_summary` → `ha.notify(..., data={clickAction, url})` (panel Ingress).
- Status: karta „Podsumowania na telefon” z podglądem obu wiadomości i „Wyślij teraz”.
- Opcja `summary_notify_service` (schemat, tłumaczenia, walidacja jak `notify_service`).

## E2 — kalendarz

- `budget/calendar_ics.py`: wydarzenia całodniowe z `schedule.for_month` (te same terminy i
  statusy co Cykliczne), UID `budget-<seria>-<data>`, zawijanie linii RFC 5545.
- `/calendar.ics` — jedyna trasa dostępna spoza proxy Ingress, tylko z HA Core (sieć hosta →
  brama sieci hassio `172.30.32.1`); odrzucone żądania do kalendarza logowane z adresem.
- Opcja `calendar_entity` → `homeassistant.update_entity` po każdej synchronizacji.

## Weryfikacja

- Testy: `tests/test_summary.py` (treść, tempo, okna, terminy wysyłki, brak dubli, Status,
  allowlista kalendarza, zawijanie i escape ICS, walidacja opcji).
- Kopia księgi (lokalnie): oba podsumowania i ICS w ~0,03 s.
- Na żywo: konfiguracja Remote Calendar przez HA; pierwsza wiadomość w poniedziałek o 7:00
  (bez testowej wysyłki w nocy).

## Wynik

- 2026-10-06: 0.22.0 wydane (v0.22.0, CI zielone) i zainstalowane z backupem add-onu; 539 testów.
- Remote Calendar dodany przez ha-mcp (URL `http://<host add-onu>:8099/calendar.ics`) — walidacja
  przeszła, więc wyjątek allowlisty dla HA Core (`172.30.32.1`) działa; encja `calendar.platnosci`
  pokazuje terminy serii (także kwartalne, ze statusami) zgodne z Cykliczne. Nazwa hosta zamiast
  IP — IP add-onu zmienia się przy restarcie (zmieniło się przy tym wdrożeniu).
- Opcje ustawione: `summary_notify_service` (grupa domowników), `calendar_entity`; po restarcie
  start czysty, nic nie wysłane (wtorek). Status na żywo: podgląd obu wiadomości z danymi
  produkcji, 0 błędów konsoli, przyciski 44 px.
- 2026-10-06 rano: użytkownik wysłał obie wiadomości „Wyślij teraz” — dotarły, ale dotknięcie nie
  otwierało panelu: HA 2026.9 nie ma już trasy `/hassio/ingress/<slug>` (404). 0.22.1: link
  `/app/<slug>` (działa też bez panelu w pasku bocznym); po wydaniu testowa wysyłka — dotknięcie
  otwiera panel (potwierdzone przez użytkownika). ✅ M6 zamknięty.
