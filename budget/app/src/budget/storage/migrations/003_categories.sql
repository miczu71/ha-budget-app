-- M4a: kategorie (2 poziomy), reguły użytkownika, kategoria i sprzedawca transakcji.

-- Kategorie główne (parent_id NULL) grupują podkategorie; transakcja dostaje tylko podkategorię.
-- `flex_group` (tylko podkategorie) — przygotowane pod budżet Flex (M5).
CREATE TABLE category (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES category (id),
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    flex_group TEXT CHECK (
        flex_group IN ('income', 'fixed', 'flexible', 'non_monthly', 'savings', 'excluded')
    ),
    sort INTEGER NOT NULL DEFAULT 0,
    is_seed INTEGER NOT NULL DEFAULT 0,
    CHECK ((parent_id IS NULL) = (flex_group IS NULL))
);
CREATE INDEX category_parent ON category (parent_id);

-- Reguły użytkownika: warunki jako JSON (`categorize.rules.Conditions`), wygrywa pierwsza
-- pasująca wg `priority` rosnąco
CREATE TABLE rule (
    id INTEGER PRIMARY KEY,
    priority INTEGER NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    conditions TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES category (id),
    rename TEXT,
    hits INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX rule_priority ON rule (priority);

-- Kategoria przeliczana od zera (`categorize.engine.recategorize`) poza `manual`
ALTER TABLE txn ADD COLUMN category_id INTEGER REFERENCES category (id);
ALTER TABLE txn ADD COLUMN category_source TEXT CHECK (
    category_source IN ('manual', 'refund', 'rule', 'dictionary', 'kind')
);
ALTER TABLE txn ADD COLUMN rule_id INTEGER REFERENCES rule (id) ON DELETE SET NULL;
ALTER TABLE txn ADD COLUMN merchant TEXT;
CREATE INDEX txn_category ON txn (category_id);

-- Seed: kategorie główne
INSERT INTO category (id, parent_id, slug, name, sort, is_seed) VALUES
    (1, NULL, 'przychody', 'Przychody', 10, 1),
    (2, NULL, 'jedzenie', 'Jedzenie', 20, 1),
    (3, NULL, 'dom', 'Dom', 30, 1),
    (4, NULL, 'transport', 'Transport', 40, 1),
    (5, NULL, 'zdrowie', 'Zdrowie i uroda', 50, 1),
    (6, NULL, 'dzieci', 'Dzieci', 60, 1),
    (7, NULL, 'zakupy', 'Zakupy', 70, 1),
    (8, NULL, 'rozrywka', 'Rozrywka i hobby', 80, 1),
    (9, NULL, 'podroze', 'Podróże', 90, 1),
    (10, NULL, 'finanse', 'Finanse', 100, 1),
    (11, NULL, 'rodzina', 'Rodzina i prezenty', 110, 1),
    (12, NULL, 'gotowka', 'Gotówka', 120, 1),
    (13, NULL, 'oszczednosci', 'Oszczędności', 130, 1),
    (14, NULL, 'wylaczone', 'Poza budżetem', 140, 1);

-- Seed: podkategorie (id od 100, żeby kategorie główne mogły kiedyś dojść bez kolizji)
INSERT INTO category (id, parent_id, slug, name, flex_group, sort, is_seed) VALUES
    (100, 1, 'wynagrodzenie', 'Wynagrodzenie', 'income', 10, 1),
    (101, 1, 'swiadczenia', 'Świadczenia', 'income', 20, 1),
    (102, 1, 'inne-wplywy', 'Inne wpływy', 'income', 30, 1),
    (110, 2, 'spozywcze', 'Spożywcze', 'flexible', 10, 1),
    (111, 2, 'restauracje', 'Restauracje i kawiarnie', 'flexible', 20, 1),
    (112, 2, 'dostawy-jedzenia', 'Dostawy jedzenia', 'flexible', 30, 1),
    (120, 3, 'media', 'Media i energia', 'fixed', 10, 1),
    (121, 3, 'internet-telefon', 'Internet i telefon', 'fixed', 20, 1),
    (122, 3, 'wyposazenie-remont', 'Wyposażenie i remont', 'non_monthly', 30, 1),
    (123, 3, 'ogrod', 'Ogród', 'non_monthly', 40, 1),
    (130, 4, 'paliwo', 'Paliwo', 'flexible', 10, 1),
    (131, 4, 'komunikacja', 'Komunikacja publiczna', 'flexible', 20, 1),
    (132, 4, 'parking-oplaty', 'Parking i opłaty drogowe', 'flexible', 30, 1),
    (133, 4, 'auto-serwis', 'Auto: serwis i ubezpieczenie', 'non_monthly', 40, 1),
    (140, 5, 'apteka', 'Apteka', 'flexible', 10, 1),
    (141, 5, 'lekarze', 'Lekarze i badania', 'flexible', 20, 1),
    (142, 5, 'drogeria', 'Drogeria', 'flexible', 30, 1),
    (143, 5, 'fryzjer-kosmetyka', 'Fryzjer i kosmetyka', 'flexible', 40, 1),
    (150, 6, 'szkola-zajecia', 'Szkoła i zajęcia', 'flexible', 10, 1),
    (151, 6, 'dzieci-zakupy', 'Zakupy dla dzieci', 'flexible', 20, 1),
    (160, 7, 'ubrania', 'Ubrania i obuwie', 'flexible', 10, 1),
    (161, 7, 'elektronika', 'Elektronika', 'non_monthly', 20, 1),
    (162, 7, 'zakupy-online', 'Zakupy online', 'flexible', 30, 1),
    (163, 7, 'zakupy-inne', 'Inne zakupy', 'flexible', 40, 1),
    (170, 8, 'subskrypcje', 'Subskrypcje', 'fixed', 10, 1),
    (171, 8, 'kultura', 'Kultura i wyjścia', 'flexible', 20, 1),
    (172, 8, 'sport-hobby', 'Sport i hobby', 'flexible', 30, 1),
    (180, 9, 'noclegi', 'Noclegi', 'non_monthly', 10, 1),
    (181, 9, 'podroze-transport', 'Bilety i transport', 'non_monthly', 20, 1),
    (182, 9, 'podroze-inne', 'Inne w podróży', 'non_monthly', 30, 1),
    (190, 10, 'kredyt', 'Kredyt', 'fixed', 10, 1),
    (191, 10, 'oplaty-bankowe', 'Opłaty bankowe', 'fixed', 20, 1),
    (192, 10, 'ubezpieczenia', 'Ubezpieczenia', 'fixed', 30, 1),
    (193, 10, 'podatki-urzedy', 'Podatki i urzędy', 'non_monthly', 40, 1),
    (200, 11, 'przelewy-rodzina', 'Przelewy rodzinne', 'flexible', 10, 1),
    (201, 11, 'prezenty', 'Prezenty', 'non_monthly', 20, 1),
    (202, 11, 'darowizny', 'Darowizny', 'non_monthly', 30, 1),
    (210, 12, 'wyplaty-gotowki', 'Wypłaty gotówki', 'flexible', 10, 1),
    (220, 13, 'oszczednosci-przelewy', 'Przelewy na oszczędności', 'savings', 10, 1),
    (221, 13, 'inwestycje', 'Inwestycje', 'savings', 20, 1),
    (230, 14, 'jednorazowe', 'Jednorazowe / poza budżetem', 'excluded', 10, 1);
