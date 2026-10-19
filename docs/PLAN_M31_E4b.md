# Ściśnięcie kafelków sald (M31 E4 → 0.55.1)

## Context
Kafelki sald nad hero (0.55.0) zajmują za dużo miejsca. Pomiar na żywo:
- przy 390 px pasek ma **148 px** wysokości (przy 1280 px: 109 px);
- winny jest podpis „w tym skarbonki X zł” w kafelku Oszczędności, który łamie się na 3 linie (59 px);
- do tego dochodzi etykieta-link z `.tap` (min. 44 px), a grid rozciąga pozostałe kafelki do tej samej wysokości.

User chce małego paska, ściśniętego maksymalnie. Cel to **≤ 44 px** przy 390 i 1280 px.

## Zmiany (repo `/config/addons/ha-budget-app`, gałąź `main`)

1. **`budget/app/src/budget/web/templates/_balance_tiles.html`**
   - Każdy kafelek to jeden `<a class="bal-tile">`, bez `.tap`. Oszczędności też linkują w całości do `/piggy`.
   - Podpis „w tym skarbonki …” znika z kafelka i trafia jako nagłówek do popovera, nad listą skarbonek.
   - Kwoty w pasku bez groszy: `money("PLN", whole=True)` → „3 426 zł”. Grosze zostają w popoverze i na stronach szczegółów.
2. **`budget/app/src/budget/money.py` `pl()`**: dodać opcjonalny parametr `whole: bool = False`, który zaokrągla do pełnych złotych i pomija „,00”. Domyślne zachowanie zostaje bez zmian. Jinja przekaże go jako `money("PLN", whole=True)`.
3. **`budget/app/src/budget/web/static/app.css`** (tylko klasy `bal-*`):
   - `.bal-tiles`: `gap: 6px; margin-bottom: 8px`;
   - `.bal-tile`: `padding: 5px 10px; gap: 0; border-radius: 10px; min-height: 0`;
   - `.bal-label`: 11–12 px, `line-height: 1.2`;
   - `.bal-value`: 14 px, `line-height: 1.2`, `white-space: nowrap; overflow: hidden; text-overflow: ellipsis` zamiast `overflow-wrap: anywhere`, żeby kwota nie zawijała się do drugiej linii;
   - popover tylko na urządzeniach z kursorem: `@media (hover: hover)`. Na telefonie dotknięcie od razu przechodzi do `/piggy`, gdzie są skarbonki. Usunąć `tabindex` i `:focus-within` oraz regułę `.bal-sub`.
4. **Testy `tests/test_web_home.py`**:
   - dostosować 2–3 asercje kwot w kafelkach do formatu bez groszy;
   - „w tym skarbonki” teraz w popoverze, ale nadal w HTML, więc ta asercja zostaje;
   - dodać test `money.pl(..., whole=True)` w istniejących testach `money`.

## Weryfikacja
- `uv run pytest -q`, `ruff check`, `ruff format --check`, `mypy src`: wszystko zielone (poza dawnym E501).
- Dev server na kopii księgi (`devserve.py` w scratchpadzie) i Playwright przy 390 i 1280 px: wysokość `.bal-tiles` ≤ 44 px, `scrollWidth <= innerWidth`, kwoty niezawinięte (`scrollWidth <= clientWidth` dla `.bal-value`), konsola czysta; hover przy 1280 px pokazuje popover.
- Wydanie **0.55.1**: commit → skill `release` (bump `config.yaml`, `pyproject.toml`, `__init__.py`, `uv.lock`, CHANGELOG) → `ha_manage_updates install backup=true` → pomiar na żywo w Ingress tym samym skryptem co wyżej (wysokość paska). Bez commitów 02:45–03:15.
- Rollback: `git revert` i wydanie 0.55.2 albo przywrócenie backupu add-onu.
