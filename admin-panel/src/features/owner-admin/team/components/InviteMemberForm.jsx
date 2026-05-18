import { FormField, Modal } from '../../../../components/ui/index.js';
import { ROLE_OPTIONS } from '../teamData.js';
import styles from '../TeamModule.module.css';

/**
 * Invite-member drawer. Reuses the `Modal` primitive; presentational — all
 * state and the invite action come from the `useTeamData` hook via props. The
 * `owner` role option stays disabled unless the caller is an owner (the backend
 * re-enforces this).
 *
 * @param {{
 *   open: boolean,
 *   inviteForm: { email: string, display_name: string, role: string },
 *   isBusy: boolean,
 *   isOwner: boolean,
 *   tenantId: string | undefined,
 *   onChange: (form: object) => void,
 *   onSubmit: () => void,
 *   onClose: () => void,
 * }} props
 */
export function InviteMemberForm({
  open,
  inviteForm,
  isBusy,
  isOwner,
  tenantId,
  onChange,
  onSubmit,
  onClose,
}) {
  if (!open) return null;

  const set = (key) => (event) => onChange({ ...inviteForm, [key]: event.target.value });

  return (
    <Modal
      open
      onClose={onClose}
      size="md"
      title="Invitar miembro"
      description="El nuevo miembro recibirá un email para configurar su contraseña y acceder al panel con el rol que le asignes."
      footer={
        <div className={styles.modalActions}>
          <button type="button" className={styles.secondaryButton} onClick={onClose}>
            Cancelar
          </button>
          <button
            type="submit"
            form="team-invite-form"
            className={styles.primaryButton}
            disabled={isBusy || !tenantId || !inviteForm.email.trim()}
          >
            {isBusy ? 'Enviando…' : 'Invitar'}
          </button>
        </div>
      }
    >
      <form
        id="team-invite-form"
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <FormField label="Email" required>
          <input
            type="email"
            required
            value={inviteForm.email}
            onChange={set('email')}
            placeholder="usuario@dominio.com"
          />
        </FormField>
        <FormField label="Nombre (opcional)">
          <input
            type="text"
            value={inviteForm.display_name}
            onChange={set('display_name')}
            placeholder="María Pérez"
          />
        </FormField>
        <FormField label="Rol">
          <select value={inviteForm.role} onChange={set('role')}>
            {ROLE_OPTIONS.map((option) => {
              const disabled = option.value === 'owner' && !isOwner;
              return (
                <option key={option.value} value={option.value} disabled={disabled}>
                  {option.label}
                  {disabled ? ' (solo owners)' : ''}
                </option>
              );
            })}
          </select>
        </FormField>
      </form>
    </Modal>
  );
}
