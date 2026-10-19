-- M22 E3: oferty z blogów (LLM). `extracted` = JSON z tym, co wyciągnął model (do porównania z tym, co
-- user potwierdził), `verdict` = clean | fixed | rejected (pomiar trafności na Status). Addytywna.
ALTER TABLE invest_offer ADD COLUMN extracted TEXT;
ALTER TABLE invest_offer ADD COLUMN verdict TEXT;
