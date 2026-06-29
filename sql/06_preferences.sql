-- VinoSage 2.0: per-user durable taste profile (long-term memory).
-- One row per user. Arrays hold multi-valued taste dimensions so the sidebar
-- can render each as a multiselect and the recommend_for_me tool can build
-- catalog filters directly from them. Price stored as integer cents (project
-- convention — never float euros).
create table if not exists user_preferences (
  user_id                  uuid primary key references auth.users(id) on delete cascade,
  expertise_level          text not null default 'beginner'
                             check (expertise_level in ('beginner','enthusiast','connoisseur')),
  preferred_types          text[] not null default '{}',   -- subset of wines.type values
  preferred_grapes         text[] not null default '{}',
  preferred_countries      text[] not null default '{}',
  preferred_regions        text[] not null default '{}',
  preferred_styles         text[] not null default '{}',   -- subset of wines.style values
  preferred_characteristics text[] not null default '{}',  -- flavour descriptors (wines.characteristics)
  disliked_types           text[] not null default '{}',
  disliked_grapes          text[] not null default '{}',
  disliked_styles          text[] not null default '{}',
  min_price_eur_cents      integer check (min_price_eur_cents is null or min_price_eur_cents >= 0),
  max_price_eur_cents      integer check (max_price_eur_cents is null or max_price_eur_cents >= 0),
  -- Free-form memory the agent should keep but that isn't a structured filter,
  -- e.g. "mentioned liking Barolo (not stocked) — offer Nebbiolo alternatives".
  notes                    text,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

create trigger user_preferences_moddatetime before update on user_preferences
  for each row execute function moddatetime(updated_at);

alter table user_preferences enable row level security;

create policy prefs_own_read   on user_preferences
  for select using (auth.uid() = user_id);
create policy prefs_own_insert on user_preferences
  for insert with check (auth.uid() = user_id);
create policy prefs_own_update on user_preferences
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy prefs_own_delete on user_preferences
  for delete using (auth.uid() = user_id);
create policy prefs_service    on user_preferences
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
