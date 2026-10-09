"""Ledger snapshot (M14): wyniki liczone z całej księgi, zapamiętane do pierwszego zapisu.

Przynależność do serii (`series.candidates`) czyta i parsuje każdą transakcję, a potrzebują jej
dzwonek (na każdej stronie), Podsumowanie, Budżet, Cykliczne i publikator encji. Add-on ma jedno
połączenie SQLite i jest jedynym pisarzem księgi, więc sygnatura to `total_changes` połączenia
(każdy zapis: transakcja, reguła, seria, kategoria, kwota Flex) i `data_version` (zapis z innego
połączenia). Kosztowne sumy i drzewo kategorii nie są tu zapamiętywane — są tanie (zmierzone).
"""

from __future__ import annotations

import sqlite3

from budget.recurring import series


class Snapshot:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._key: tuple[int, int] | None = None
        self._candidates: tuple[series.Candidate, ...] = ()
        self._members_key: tuple[int, int] | None = None
        self._members: dict[int, list[series.Candidate]] = {}

    def signature(self) -> tuple[int, int]:
        return (self.conn.total_changes, self.conn.execute("PRAGMA data_version").fetchone()[0])

    def candidates(self) -> tuple[series.Candidate, ...]:
        """Jak `series.candidates(conn)`, ale liczone raz do pierwszego zapisu."""
        key = self.signature()
        if key == self._key:
            return self._candidates
        found = tuple(series.candidates(self.conn))
        # Wewnątrz transakcji `total_changes` nie maleje po ROLLBACK — wynik byłby nieaktualny.
        if not self.conn.in_transaction:
            self._key, self._candidates = key, found
        return found

    def members(self) -> dict[int, list[series.Candidate]]:
        """Transakcje aktywnych serii (`series.assign`), liczone raz do pierwszego zapisu.
        Transakcja trafia tylko do serii o swoim kierunku, więc wynik dla podzbioru serii
        (np. wydatkowych) jest taki sam jak tu."""
        key = self.signature()
        if key == self._members_key:
            return self._members
        live = series.all_series(self.conn, ("active",))
        found = series.assign(live, self.candidates()) if live else {}
        if not self.conn.in_transaction:
            self._members_key, self._members = key, found
        return found
