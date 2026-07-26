-- Stop the same scenario/test being added twice -- by the same admin re-submitting,
-- or two admins racing each other. The unique index is the only race-safe guard;
-- the app-level "duplicate key" checks in admin.py, scenario_generator.py, reading.py
-- and listening.py just turn the DB rejection into a clean 409 message.
--
-- NOTE: if any duplicate titles already exist in these tables, the CREATE UNIQUE INDEX
-- below will fail. Find them first with e.g.:
--   select module, lower(trim(title)), count(*) from scenarios group by 1,2 having count(*) > 1;
--   select lower(trim(title)), count(*) from reading_tests group by 1 having count(*) > 1;
--   select lower(trim(title)), count(*) from listening_tests group by 1 having count(*) > 1;
-- and rename/deactivate the extras before running this.

create unique index if not exists scenarios_module_title_uidx
  on scenarios (module, lower(trim(title)));

create unique index if not exists reading_tests_title_uidx
  on reading_tests (lower(trim(title)));

create unique index if not exists listening_tests_title_uidx
  on listening_tests (lower(trim(title)));
