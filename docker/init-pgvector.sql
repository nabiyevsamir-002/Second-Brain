-- Postgres init: pgvector genişlənməsini aktivləşdir.
-- Bu fayl konteyner ilk dəfə qalxanda avtomatik icra olunur
-- (docker-entrypoint-initdb.d). pgvector image-i extension-u daşıyır.
CREATE EXTENSION IF NOT EXISTS vector;
