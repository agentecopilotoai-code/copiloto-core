-- ============================================================================
-- Copiloto Core — Seed mínimo del core
-- ============================================================================
-- Solo inserta el dataset MÍNIMO que el core necesita para funcionar:
-- un tenant demo + activación de módulos opt-in vacía.
--
-- Cada módulo opt-in seedea su propio dataset cuando se instala sobre el
-- core (típicamente en `infra/postgres/modules/<modulo>.sql`).
-- ============================================================================

-- Tenant demo para development local. En producción este insert NO se
-- ejecuta (no hay un script que lo cargue automáticamente — solo el
-- bootstrap del dev environment).
--
-- QUAL (audit#4): guard explícito contra ejecución accidental en prod.
-- Antes el archivo era ejecutable contra cualquier DB; un operador
-- que ejecutara `psql prod_db -f 20-seed.sql` insertaba el tenant
-- demo en producción. Ahora aborta si la DB no contiene 'dev', 'test'
-- o 'local' en su nombre. Para forzar override (caso staging que
-- legítimamente necesita el seed), setear `app.allow_seed = 'true'`
-- en la sesión antes de \i este archivo.
do $$
declare
  db_name text := current_database();
  override boolean := coalesce(
    nullif(current_setting('app.allow_seed', true), '')::boolean,
    false
  );
begin
  if not override and db_name !~* '(dev|test|local)' then
    raise exception
      'Refusing to run 20-seed.sql against DB %; '
      'name must match (dev|test|local) or set app.allow_seed=true.',
      db_name;
  end if;
end;
$$;

insert into app.tenants (id, slug, legal_name, display_name, vertical_code, status)
values
  ('11111111-1111-1111-1111-111111111111', 'demo', 'Demo Tenant SAS', 'Demo Tenant', 'generic', 'active')
on conflict (slug) do nothing;
