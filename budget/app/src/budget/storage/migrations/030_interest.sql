-- Odsetki z banku (kapitalizacja i podatek od odsetek) mają własny typ i podkategorię
-- Przychody → Odsetki (netto), zamiast ręcznie kategoryzowanych przelewów.
INSERT OR IGNORE INTO category (id, parent_id, slug, name, flex_group, sort, is_seed) VALUES
    (103, 1, 'odsetki', 'Odsetki', 'income', 25, 1);

UPDATE txn SET kind = 'interest'
WHERE kind_source <> 'manual'
  AND (UPPER(description) LIKE '%KAPITALIZACJA ODSETEK%'
       OR UPPER(description) LIKE '%PODATEK OD ODSETEK%');

-- Ręczna kategoria przelewu nie ma sensu po zmianie typu: silnik przypisze „Odsetki” przy
-- starcie (`recategorize`)
UPDATE txn SET category_id = NULL, category_source = NULL, rule_id = NULL
WHERE kind = 'interest' AND category_source = 'manual';
