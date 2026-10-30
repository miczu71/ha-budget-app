# PLAN E4 — drill-down donuta „Gdzie poszły pieniądze”

Źródło prawdy: `docs/ROADMAP_podsumowanie.md`. Bez migracji, bez wydania (0.69.0 po E4).
Rollback: `git revert` commitu E4.

## Zachowanie
- Poziom 1 (jak dziś): kategorie główne + „Inne” + „Bez kategorii”. Wycinek/legenda kategorii głównej (`cat-<id>`)
  przechodzi w poziom 2 fragmentem htmx; „Inne” i „Bez kategorii” linkują jak dotąd.
- Poziom 2 (`cat=<id>`): podkategorie tej kategorii (top 6 + „Pozostałe”), środek = kwota kategorii i „N% wydatków”.
  Wycinek podkategorii → poziom 3.
- Poziom 3 (`cat=<id>&sub=<leaf>`): pojedyncze transakcje podkategorii (top 6 + „Pozostałe”), bez dalszego drill;
  wycinki linkują do `/transactions?category=<leaf>&<okres>`.
- Okruszki + „← wstecz” (poziom wyżej) nad wykresem na poziomach 2–3; pod wykresem „Zobacz transakcje »”
  (`/transactions?category=<sub lub cat>&<okres>`) zamiast „Wszystkie kategorie…” (to zostaje na poziomie 1).
- Okres = ten sam co widok (miesiąc albo „od ostatniej wypłaty”); przełącznik Miesiąc/Od wypłaty zeruje drill.
- Nieznane/nieprawidłowe `cat`/`sub` → poziom 1 (bez błędu 422). Bez JS działa link `/?month=…&cat=…&sub=…`.

## Wykonawca

WORKTREE: z `wt new /config/addons/ha-budget-app podsumowanie-E4`. Katalog aplikacji: `budget/app`.
Skill `addon-conventions`; TDD — najpierw testy (czerwone), potem kod.

### Pliki i zmiany (ścieżki względem `budget/app/`)

1. `src/budget/web/charts.py`
   - `Slice` dostaje pole `drill: str = ""` (na końcu, z wartością domyślną): sufiks zapytania, np. `cat=5`; pusty = brak drill.
   - Wydziel z `donut_slices` geometrię (liczenie `shares`, `_percentages`, `start/length`) do `_layout(parts, gap)`,
     gdzie `parts` to lista krotek `(key, label, amount, count, color, href, drill)`; `donut_slices` buduje `parts`
     jak dziś (drill = `f"cat={g.category.id}"` dla `cat-<id>`, `""` dla `other`/`unc`) i woła `_layout`. Zachowanie
     dotychczasowych wycinków bez zmian (istniejące testy zielone).
   - Nowa `@dataclass(frozen=True) class Item`: `key: str, label: str, amount: Decimal, count: int, href: str, drill: str = ""`.
   - Nowa `drill_slices(items: Sequence[Item], *, other_href: str, top: int = 6, gap: float = 0.8) -> list[Slice]`:
     tylko `amount > 0`, malejąco; top `top` dostaje kolory `c1…c6` kolejno (indeks), reszta zbita w jeden wycinek
     `key="other"`, `label="Pozostałe"`, kolor `"other"`, `href=other_href`, `drill=""`; suma 0 → `[]`.
2. `src/budget/spending.py`
   - `@dataclass(frozen=True) class Purchase: id: int; label: str; day: str; amount: Decimal` (amount dodatnia = wydano).
   - `purchases(conn, leaf_id: int, start: date, end: date) -> list[Purchase]`: `_rows(conn, start, end, details=True)`,
     tylko `category_id == leaf_id`, `currency == BASE_CURRENCY`, `amount < 0`; `label = merchant or counterparty_name or description or "—"`
     (przycięte do 40 znaków z „…”); malejąco po kwocie. `end` wyłączny.
3. `src/budget/web/routes_home.py`
   - `spending_card(panel, start, today, since_payday, since_date, cat: int | None = None, sub: int | None = None)`:
     dodaje do kontekstu `spend_q` (`month=<ym>` + `&since_payday=1` gdy `since_on`), `crumbs` (lista `(label, query)`),
     `back_q` (query poziomu wyżej albo `None`), `drill_level` (1–3), `drill_total` (Decimal), `drill_share` (int %), `see_href`
     (`/transactions?category=<id>&<period>` albo `None` na poziomie 1) i `slices` właściwe dla poziomu:
     poz. 2 = `charts.drill_slices` z `g.children` (`Item(key=f"cat-{leaf.id}", label=leaf.category.name, amount=leaf.amount, count=leaf.count,
     href=f"/transactions?category={leaf.id}&{period}", drill=f"cat={cat}&sub={leaf.id}")`), `other_href=f"/transactions?category={cat}&{period}"`;
     poz. 3 = `charts.drill_slices` z `spending.purchases(...)` (okno: `[since_date, today+1d)` gdy `since_on`, inaczej `[start, add_months(start,1))`;
     `Item(key=f"txn-{p.id}", label=p.label, amount=p.amount, count=1, href=f"/transactions?category={sub}&{period}")`).
     `g` = element `m.expense_groups` o `g.category.id == cat`; `sub` musi być w `g.children`; inaczej poziom niżej/1.
   - `/home/spending` i `/` przyjmują `cat: str = ""`, `sub: str = ""` → `int` przez helper `_id(value) -> int | None`
     (nie-cyfry → `None`) i przekazują do `spending_card`.
4. `src/budget/web/templates/_charts.html` (makro `donut`)
   - Dla `s.drill`: oba linki (wycinek i legenda) mają `href="{{ base }}/?{{ spend_q }}&{{ s.drill }}"` oraz
     `hx-get="{{ base }}/home/spending?{{ spend_q }}&{{ s.drill }}" hx-target="#spending-card" hx-select="#spending-card" hx-swap="outerHTML" hx-push-url="false"`;
     bez `s.drill` — jak dziś (`href="{{ base }}{{ s.href }}"`).
5. `src/budget/web/templates/_spending.html`
   - Gdy `crumbs`: `<nav class="crumbs" aria-label="Poziom wykresu">` z linkiem „← wstecz” (`back_q`, ten sam wzorzec hx/href
     co w drill) i okruszkami „Wszystkie › Kategoria › Podkategoria” (ostatni bez linku, `aria-current="page"`).
   - Środek donuta na poz. 2–3: `drill_total` i podpis („w kategorii”, na poz. 3 „w podkategorii”) + `{{ drill_share }}% wydatków` na poz. 2;
     poz. 1 bez zmian.
   - Dół karty: na poz. 2–3 link `see_href` „Zobacz transakcje »”, na poz. 1 dotychczasowy „Wszystkie kategorie i podkategorie »”.
   - Przełącznik zakresu (`.tabs`) bez `cat`/`sub` (zeruje drill).
6. `src/budget/web/static/app.css` (plik ze stylem `.tabs`/`.donut`; sprawdź nazwę `grep -ln "\.donut-wrap" src/budget/web/static/*.css`)
   - `.crumbs`: flex, wrap, gap 6px, `font-size: 13px`, kolor `var(--muted)`, linki `.tap` (cel dotyku ≥ 44 px wysokości jak `.tabs a`), bez nowych kolorów.
7. Testy (każdy najpierw czerwony):
   - `tests/test_web_charts.py`: `drill_slices` (top 6 + „Pozostałe”, kolory c1…c6, suma 0 → `[]`, kwoty ≤ 0 pominięte), `donut_slices` ustawia `drill="cat-…"` tylko dla kategorii.
   - `tests/test_spending.py`: `purchases` (tylko wydatki leafa w oknie, `end` wyłączny, etykieta z fallbackiem, sortowanie, część podziału M29 jako osobna pozycja).
   - `tests/test_web_home.py`: `GET /home/spending?month=…&cat=<id>` → podkategorie + okruszki + „Zobacz transakcje”; `&sub=<leaf>` → transakcje;
     `cat=abc`/nieistniejące → poziom 1 (status 200); `since_payday=1&cat=…` zachowuje okres w linkach (`date_from` = dzień wypłaty);
     poz. 1 ma `hx-get` tylko na wycinkach kategorii, nie na „Inne”/„Bez kategorii”. Dane: neutralne nazwy („Sklep X”, „Kategoria A”).

### Komenda testu
```
cd budget/app && BUDGET_OPTIONS_PATH=/nonexistent .venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests && .venv/bin/mypy src
```

### DONE
- Powyższa komenda zielona (≥ 1329 testów + nowe), nowe testy istniały i były czerwone przed kodem.
- `GET /home/spending?month=<bieżący>&cat=<id z danych>` zwraca 200 z `class="crumbs"` i linkami `hx-get` z `sub=`.
- Poziom 1 renderuje się bez zmian wizualnych względem E3 (te same wycinki, te same linki dla „Inne”/„Bez kategorii”).

### NIE RÓB
- Nie ruszaj `spending.build`, `forecast*`, `_forecast.html`, migracji, `config.yaml`/wersji, CHANGELOG, docs/.
- Nie zmieniaj istniejących asercji testów (tylko dodawaj); nie obchodź hooka prywatności; nie commituj (robi rodzic przez `wt land`).
- Żadnych nowych zależności, JS ani emoji/PNG (tylko SVG/CSS).
