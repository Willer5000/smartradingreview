-- RC9.7 OPTIONAL SECURITY HARDENING
-- NO ejecutar hasta verificar que Main + Research usan service_role/service secret.
-- El service_role bypassa RLS; anon/authenticated quedan sin acceso directo.
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT schemaname, tablename
    FROM pg_tables
    WHERE schemaname='public'
  LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',r.schemaname,r.tablename);
  END LOOP;
END $$;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
