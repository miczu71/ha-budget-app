"""Ledger snapshot (M14): wyniki liczone z całej księgi, zapamiętane do pierwszego zapisu.

Przynależność do serii (`series.candidates`) czyta i parsuje każdą transakcję, a potrzebują jej
dzwonek (na każdej stronie), Podsumowanie, Budżet, Cykliczne i publikator encji. Add-on ma jedno
połączenie SQLite i jest jedynym pisarzem księgi, więc sygnatura to `total_changes` połączenia
(każdy zapis: transakcja, reguła, seria, kategoria, kwota Flex) i `data_version` (zapis z innego
połączenia). Kosztowne sumy i drzewo kategorii nie są tu zapamiętywane — są tanie (zmierzone).
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import TYPE_CHECKING

from budget.recurring import series

if TYPE_CHECKING:
    from budget.recurring.changes import Change


class Snapshot:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._key: tuple[int, int] | None = None
        self._candidates: tuple[series.Candidate, ...] = ()
        self._members_key: tuple[int, int] | None = None
        self._members: dict[int, list[series.Candidate]] = {}
        self._piggy_key: tuple[int, int] | None = None
        self._piggy_ids: set[int] = set()
        self._savings_key: tuple[int, int] | None = None
        self._savings_ids: frozenset[int] = frozenset()
        self._changes_key: tuple[tuple[int, int], date] | None = None
        self._changes: tuple[Change, ...] = ()

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

    def piggy_ids(self) -> set[int]:
        """Transakcje skarbonek i konta oszczędnościowego poza pulą Flex (`piggy.txn_ids`,
        `savings.txn_ids`; M10), do pierwszego zapisu."""
        from budget import piggy, savings  # piggy korzysta z harmonogramu serii, który zna Snapshot

        key = self.signature()
        if key == self._piggy_key:
            return self._piggy_ids
        found = piggy.txn_ids(self.conn) | savings.txn_ids(self.conn)
        if not self.conn.in_transaction:
            self._piggy_key, self._piggy_ids = key, found
        return found

    def savings_ids(self) -> frozenset[int]:
        """Przelewy na/z oszczędności (`ledger.savings_transfer_ids`), do pierwszego zapisu.
        Kosztowny `ledger._analyze` — wspólny dla dzwonka (karty Velobanku i promocji)."""
        from budget import ledger  # import leniwy jak w piggy_ids (unika cyklu)

        key = self.signature()
        if key == self._savings_key:
            return self._savings_ids
        found = frozenset(ledger.savings_transfer_ids(self.conn))
        if not self.conn.in_transaction:
            self._savings_key, self._savings_ids = key, found
        return found

    def series_changes(self, today: date) -> tuple[Change, ...]:
        """Zmiany serii (`changes.detect`) dla dnia `today`, do pierwszego zapisu. Wynik zależy
        tylko od bazy i dnia, więc kluczem jest sygnatura z datą (dzwonek liczył to na każdej
        stronie, ~75 ms)."""
        from budget.recurring import changes, schedule  # changes importuje Snapshot (cykl)

        key = (self.signature(), today)
        if key == self._changes_key:
            return self._changes
        active = series.all_series(self.conn, ("active",))
        found = tuple(
            changes.detect(
                active,
                self.members(),
                schedule.acks_from_db(self.conn),
                today,
                schedule.overrides_from_db(self.conn),
            )
            if active
            else ()
        )
        if not self.conn.in_transaction:
            self._changes_key, self._changes = key, found
        return found
