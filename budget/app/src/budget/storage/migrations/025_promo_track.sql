-- M22 E5 (dawne M17): śledzenie promocji bankowych. `promo_track` = jedna skorzystana oferta w okresie
-- start..koniec, `promo_condition` = jej warunki (payments/income liczone z księgi tylko dla banku
-- z `ledger` = 1, balance/manual odhaczane ręcznie; `proposed` = propozycja LLM do sprawdzenia). Addytywna.
CREATE TABLE promo_track (
    id         INTEGER PRIMARY KEY,
    offer_id   INTEGER REFERENCES invest_offer (id) ON DELETE SET NULL,
    bank       TEXT NOT NULL,
    title      TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date   TEXT NOT NULL,
    bonus      TEXT,                          -- premia, PLN
    ledger     INTEGER NOT NULL DEFAULT 0,    -- postęp z księgi (konta Millennium)
    status     TEXT NOT NULL DEFAULT 'active', -- active | paid | failed | cancelled
    paid_at    TEXT,
    paid_to    TEXT,                          -- asset | income
    created_at TEXT NOT NULL
);

CREATE TABLE promo_condition (
    id       INTEGER PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES promo_track (id) ON DELETE CASCADE,
    kind     TEXT NOT NULL,                   -- payments | income | balance | manual
    label    TEXT NOT NULL,
    target   TEXT,                            -- liczba płatności albo kwota wpływów
    done     INTEGER NOT NULL DEFAULT 0,
    proposed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX promo_condition_track ON promo_condition (track_id);
