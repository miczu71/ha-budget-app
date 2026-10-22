-- M32 E1: wielobankowość PSD2. Konto pamięta bank (nazwa ASPSP z Enable Banking), z którego
-- pochodzi; NULL = konto bez API (CSV). Sesje `eb_session` bez zmian schematu: `is_current`
-- oznacza teraz bieżącą sesję danego banku (`aspsp`), a nie jedyną w bazie.
ALTER TABLE account ADD COLUMN bank TEXT;

-- Dotychczasowa baza ma jedną sesję (jeden bank): jej konta dostają ten bank
UPDATE account SET bank = (
    SELECT aspsp FROM eb_session WHERE is_current = 1 ORDER BY created_at DESC LIMIT 1
)
WHERE bank IS NULL AND id IN (SELECT account_id FROM account_alias WHERE source = 'eb_uid');
