import { Card } from '../../../../components/ui/index.js';
import { BranchesManager } from '../../branches/index.js';
import styles from '../TenantSetupWizard.module.css';

export function BranchesTab({ state, session }) {
  const { currentTenantId } = state;

  return (
    <Card padding="md" data-wizard-tab="branches">
      <p className={styles.hint}>
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
        <p className={styles.hint}>Primero guarda los datos del negocio para configurar sedes.</p>
      )}
    </Card>
  );
}
