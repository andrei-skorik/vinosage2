-- VinoSage 2.0: 👍/👎 on individual recommended wines, folded back into the
-- taste profile (§5.4). user_id nullable so anonymous sessions can rate too
-- (those rows are service-role-only, like anonymous query_logs).
create table if not exists recommendation_feedback (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  session_id  text not null,
  user_id     uuid references auth.users(id) on delete cascade,
  query_id    uuid references query_logs(id) on delete cascade,
  wine_id     uuid references wines(wine_id) on delete set null,
  wine_title  text,                      -- denormalised so feedback survives wine deletion
  rating      text not null check (rating in ('up','down')),
  reason      text,
  unique (user_id, query_id, wine_id)    -- one rating per (user, turn, wine); upsert toggles it
);
create index if not exists idx_feedback_user on recommendation_feedback(user_id);
create index if not exists idx_feedback_wine on recommendation_feedback(wine_id);

alter table recommendation_feedback enable row level security;
create policy fb_own_read   on recommendation_feedback
  for select using (auth.uid() = user_id);
create policy fb_own_insert on recommendation_feedback
  for insert with check (auth.uid() = user_id);
create policy fb_own_update on recommendation_feedback
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy fb_service    on recommendation_feedback
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
