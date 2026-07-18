-- Run in Supabase SQL Editor. Change the email, run.
do $$
declare
  target_email text := 'someone@example.com';  -- <-- change this
  target_user_id uuid;
begin
  select id into target_user_id from auth.users where email = target_email;

  if target_user_id is null then
    raise exception 'no user found with email %', target_email;
  end if;

  insert into public.user_roles (user_id, role)
  values (target_user_id, 'admin')
  on conflict (user_id) do update set role = 'admin';
end $$;
