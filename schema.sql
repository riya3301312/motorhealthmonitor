-- Run this once in Supabase: left sidebar -> SQL Editor -> New query -> Run.

create table if not exists public.readings (
  id          bigserial primary key,
  device_id   text not null default 'motor-01',
  ts          timestamptz not null default now(),
  vibration   double precision,
  temperature double precision,
  voltage     double precision,
  status      text,
  health      integer,
  note        text
);

create index if not exists readings_device_ts_idx
  on public.readings (device_id, ts desc);

-- Row level security is on by default. These two policies let the public
-- anon key write readings and read them back, which is what the forwarder
-- and the dashboard need. Fine for a college project on a dedicated
-- Supabase project; do not reuse this key anywhere sensitive.
alter table public.readings enable row level security;

drop policy if exists "anon can insert readings" on public.readings;
create policy "anon can insert readings"
  on public.readings for insert to anon with check (true);

drop policy if exists "anon can read readings" on public.readings;
create policy "anon can read readings"
  on public.readings for select to anon using (true);
