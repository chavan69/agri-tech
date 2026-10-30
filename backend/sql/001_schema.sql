-- ===========================================================================
-- 02build AgriTech - Supabase schema
-- Run this in the Supabase SQL editor, or with: python scripts/init_db.py
-- Safe to re-run: tables, indexes, triggers and policies are created IF NOT
-- EXISTS / dropped and recreated.
-- ===========================================================================

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- Users (application accounts - not Supabase Auth)
-- ---------------------------------------------------------------------------
create table if not exists public.users (
    id            uuid primary key default gen_random_uuid(),
    name          text not null,
    phone         text not null unique,
    password_hash text not null,
    location      text,
    role          text default 'Farmer & Seller',
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

comment on table public.users is 'AgriTech app accounts (phone + password, hashed).';

-- ---------------------------------------------------------------------------
-- E-market listings
-- ---------------------------------------------------------------------------
create table if not exists public.market_listings (
    id           uuid primary key default gen_random_uuid(),
    name         text not null,
    category     text not null default 'Vegetables',
    mode         text not null default 'direct' check (mode in ('direct', 'auction')),
    price        numeric(12, 2) not null check (price > 0),
    current_bid  numeric(12, 2),
    quantity     text default '100 kg',
    seller       text,
    phone        text,
    location     text,
    image        text,
    owner_id     uuid references public.users (id) on delete set null,
    status       text not null default 'active' check (status in ('active', 'sold', 'closed')),
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

comment on table public.market_listings is 'Crop/produce listings: direct sales and live auctions.';

-- ---------------------------------------------------------------------------
-- Auction bids
-- ---------------------------------------------------------------------------
create table if not exists public.bids (
    id          uuid primary key default gen_random_uuid(),
    listing_id  uuid not null references public.market_listings (id) on delete cascade,
    bidder_id   uuid references public.users (id) on delete set null,
    bidder_name text,
    amount      numeric(12, 2) not null check (amount > 0),
    created_at  timestamptz not null default now()
);

comment on table public.bids is 'Bid history for auction market listings.';

-- ---------------------------------------------------------------------------
-- Machinery / labour listings
-- ---------------------------------------------------------------------------
create table if not exists public.machinery_listings (
    id         uuid primary key default gen_random_uuid(),
    title      text not null,
    type       text not null default 'available' check (type in ('available', 'requirement')),
    category   text default 'Heavy Machinery',
    rate       text,
    owner      text,
    phone      text,
    location   text,
    specs      text,
    owner_id   uuid references public.users (id) on delete set null,
    status     text not null default 'active' check (status in ('active', 'closed')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

comment on table public.machinery_listings is 'Machinery and labour rental listings.';

-- ---------------------------------------------------------------------------
-- AI Plant Doctor scans
-- ---------------------------------------------------------------------------
create table if not exists public.scans (
    id            uuid primary key default gen_random_uuid(),
    user_id       uuid not null references public.users (id) on delete cascade,
    crop          text,
    status        text,
    badge_color   text check (badge_color in ('green', 'amber', 'red')),
    diagnosis     text,
    confidence    integer check (confidence between 0 and 100),
    prevention    jsonb not null default '[]'::jsonb,
    organic_cure  text,
    chemical_cure text,
    image_mime    text,
    created_at    timestamptz not null default now()
);

comment on table public.scans is 'Saved AI Plant Doctor diagnostic reports.';

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
create index if not exists idx_market_created_at on public.market_listings (created_at desc);
create index if not exists idx_market_mode on public.market_listings (mode);
create index if not exists idx_market_owner on public.market_listings (owner_id);
create index if not exists idx_bids_listing on public.bids (listing_id, created_at desc);
create index if not exists idx_machinery_created_at on public.machinery_listings (created_at desc);
create index if not exists idx_machinery_owner on public.machinery_listings (owner_id);
create index if not exists idx_scans_user_created on public.scans (user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- updated_at trigger
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_users_updated_at on public.users;
create trigger trg_users_updated_at
    before update on public.users
    for each row execute function public.set_updated_at();

drop trigger if exists trg_market_updated_at on public.market_listings;
create trigger trg_market_updated_at
    before update on public.market_listings
    for each row execute function public.set_updated_at();

drop trigger if exists trg_machinery_updated_at on public.machinery_listings;
create trigger trg_machinery_updated_at
    before update on public.machinery_listings
    for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Row Level Security
--
-- The API uses the service_role key, which bypasses RLS. These policies only
-- constrain direct access with the anon key: listings are publicly readable,
-- everything else (users, bids, scans) is private.
-- ---------------------------------------------------------------------------
alter table public.users enable row level security;
alter table public.market_listings enable row level security;
alter table public.bids enable row level security;
alter table public.machinery_listings enable row level security;
alter table public.scans enable row level security;

drop policy if exists "Public read market listings" on public.market_listings;
create policy "Public read market listings"
    on public.market_listings for select
    using (true);

drop policy if exists "Public read machinery listings" on public.machinery_listings;
create policy "Public read machinery listings"
    on public.machinery_listings for select
    using (true);
