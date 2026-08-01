-- Full Mock Test phase 2: adds the 2 frozen Speaking role-play picks. Everything
-- else (per-roleplay results, combined band, status transition to 'complete')
-- reuses the existing `results` jsonb column -- no other schema change needed.

alter table mock_test_sessions
  add column if not exists speaking_scenario_id_1 bigint references scenarios(id) on delete set null,
  add column if not exists speaking_scenario_id_2 bigint references scenarios(id) on delete set null;
