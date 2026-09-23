-- ============================================================
--  Aetheris Core — Supabase (pgvector) setup
--  Run this in the Supabase SQL editor BEFORE setting
--  VECTOR_BACKEND=supabase (or leaving it on "auto" with creds).
--
--  IMPORTANT: the vector dimension MUST equal EMBEDDING_DIM from
--  the root .env (384 for the local hash embedder, 1024 for
--  snowflake-arctic-embed-l, 1024 for bge-m3, 1536 for text-embedding-3-small).
-- ============================================================

create extension if not exists vector;

create table if not exists public.aetheris_chunks (
    chunk_id    text primary key,
    doc_id      text,
    header_path text default '',
    text        text default '',
    embedding   vector(384)          -- <-- change to match EMBEDDING_DIM
);

create index if not exists idx_aetheris_chunks_doc
    on public.aetheris_chunks (doc_id);

-- Optional ANN index (build after you have >= 1000 rows):
-- create index on public.aetheris_chunks
--     using ivfflat (embedding vector_cosine_ops)
--     with (lists = 100);

-- Similarity RPC used by the orchestrator's SupabaseVectorStore.
create or replace function public.match_aetheris_chunks(
    query_embedding vector(384),     -- <-- must match the column dimension
    match_count int default 10
)
returns table (
    chunk_id    text,
    doc_id      text,
    header_path text,
    text        text,
    similarity  float
)
language sql stable
as $$
    select c.chunk_id,
           c.doc_id,
           c.header_path,
           c.text,
           1 - (c.embedding <=> query_embedding) as similarity
    from public.aetheris_chunks c
    order by c.embedding <=> query_embedding
    limit match_count;
$$;

-- Lock the table down: only the service-role key may touch it.
alter table public.aetheris_chunks enable row level security;

create policy "service role full access"
    on public.aetheris_chunks
    for all
    using (auth.role() = 'service_role')
    with check (auth.role() = 'service_role');
