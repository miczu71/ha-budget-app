-- M4c/3: do 3 kandydatów na podpowiedź (JSON [[category_id, pewność], …], od najpewniejszego);
-- `category_id`/`confidence` = pierwszy kandydat. Oczekujące z jednym kandydatem liczone od nowa.
ALTER TABLE suggestion ADD COLUMN candidates TEXT;
DELETE FROM suggestion WHERE status = 'pending';
