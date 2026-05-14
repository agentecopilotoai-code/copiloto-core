import { BranchesManager } from '../../branches/index.js';

export function BranchesTab({ state, session }) {
  const { currentTenantId } = state;

  return (
    <section className="wizard-panel" data-wizard-tab="branches">
      <p className="hint">
        Configura una sede para empezar. Si tu negocio opera en varias ubicaciones, agrega más
        desde el módulo <strong>Sedes</strong> en el menú principal. El bot ofrecerá la
        selección de sede al cliente cuando exista más de una activa.
      </p>
      {currentTenantId ? (
        <BranchesManager
          module={{ label: 'Sedes', summary: 'Configura las ubicaciones físicas del tenant.' }}
          session={session}
          tenant={{ id: currentTenantId }}
        />
      ) : (
        <p>Primero guarda los datos del negocio para configurar sedes.</p>
      )}
    </section>
  );
}
