create extension if not exists pgcrypto;

create table if not exists profiles (
  id uuid primary key,
  username text not null,
  email text,
  transfers_left integer not null default 17,
  total_points integer not null default 0,
  team_name text default '',
  team_confirmed boolean not null default false,
  created_at timestamptz default now(),
  confirmed_at timestamptz
);

create table if not exists teams (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  player_id integer not null,
  added_at timestamptz default now()
);
create unique index if not exists teams_user_player_idx on teams(user_id, player_id);

create table if not exists leagues (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  type text not null check (type in ('public','private')),
  max_members integer not null default 20,
  created_by uuid not null,
  join_code text,
  created_at timestamptz default now()
);

create table if not exists league_members (
  id bigint generated always as identity primary key,
  league_id uuid not null,
  user_id uuid not null,
  joined_at timestamptz default now()
);
create unique index if not exists league_members_unique_idx on league_members(league_id, user_id);

create table if not exists player_points (
  id bigint generated always as identity primary key,
  player_id integer not null,
  points integer not null,
  game_date date,
  created_at timestamptz default now()
);
