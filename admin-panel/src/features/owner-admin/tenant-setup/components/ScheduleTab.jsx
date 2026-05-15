import { Button, Card } from '../../../../components/ui/index.js';
import { weekdays } from '../tenantSetupData.js';
import styles from '../TenantSetupWizard.module.css';

export function ScheduleTab({ state, actions }) {
  const { hoursForm, isBusy, currentTenantId } = state;
  const { handleSaveSettings, setHoursForm } = actions;

  return (
    <Card padding="md">
      <form onSubmit={handleSaveSettings}>
        <div className={styles.daysGrid}>
          {weekdays.map(([day, label]) => (
            <fieldset className={styles.dayCard} key={day}>
              <legend>{label}</legend>
              <label className={styles.inlineCheck}>
                <input
                  checked={hoursForm[day].enabled}
                  onChange={(event) =>
                    setHoursForm({
                      ...hoursForm,
                      [day]: { ...hoursForm[day], enabled: event.target.checked },
                    })
                  }
                  type="checkbox"
                />
                Activo
              </label>
              <label>
                Inicio
                <input
                  value={hoursForm[day].start}
                  onChange={(event) =>
                    setHoursForm({
                      ...hoursForm,
                      [day]: { ...hoursForm[day], start: event.target.value },
                    })
                  }
                  type="time"
                />
              </label>
              <label>
                Fin
                <input
                  value={hoursForm[day].end}
                  onChange={(event) =>
                    setHoursForm({
                      ...hoursForm,
                      [day]: { ...hoursForm[day], end: event.target.value },
                    })
                  }
                  type="time"
                />
              </label>
            </fieldset>
          ))}
        </div>
        <div className={styles.actions}>
          <Button variant="primary" disabled={isBusy || !currentTenantId} type="submit">
            Guardar horarios
          </Button>
        </div>
      </form>
    </Card>
  );
}
