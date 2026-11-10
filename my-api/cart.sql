-- Supabase 대시보드 > SQL Editor 에 붙여넣고 Run 하세요. (한 번만 실행)
create table if not exists public.cart_items (
  cart_id    text        not null,
  product_id text        not null,
  qty        integer     not null check (qty between 1 and 99),
  updated_at timestamptz not null default now(),
  primary key (cart_id, product_id)
);

-- 화면(브라우저)이 DB에 직접 접근하지 못하게 잠근다.
-- FastAPI가 secret key로 접속할 때만 읽고 쓸 수 있다.
alter table public.cart_items enable row level security;
