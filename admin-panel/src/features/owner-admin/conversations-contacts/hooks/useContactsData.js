import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  assignContactPackage,
  assignContactTags,
  createContactNote,
  getContactProfile,
  listContactConsent,
  listContactPackages,
  listContactTags,
  listContacts,
  listTreatmentPackages,
  refundContactPackage,
  unassignContactTag,
  updateContactPhone,
} from '../../../../services/coreApi.js';

/**
 * Data layer for the Conversaciones · Contactos view. Owns the CRM state and
 * all the fetch / mutation handlers extracted verbatim from the legacy
 * `ContactsModule` — the split panels stay presentational and consume this.
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {string|undefined} options.tenantId — active tenant id
 */
export function useContactsData({ session, tenantId }) {
  const [contacts, setContacts] = useState([]);
  const [availableTags, setAvailableTags] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterTagId, setFilterTagId] = useState('');
  const [selectedContactId, setSelectedContactId] = useState(null);
  const [profile, setProfile] = useState(null);
  const [isBusy, setIsBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [contactPackages, setContactPackages] = useState([]);
  const [availablePackages, setAvailablePackages] = useState([]);
  const [consent, setConsent] = useState(null);

  const fail = useCallback((error) => {
    setNotice({ type: 'error', text: error?.message || 'Error inesperado.' });
  }, []);

  const refreshContacts = useCallback(() => {
    if (!tenantId) return Promise.resolve();
    return listContacts(session, tenantId, {
      q: searchTerm || undefined,
      tagId: filterTagId || undefined,
      limit: 100,
    })
      .then((items) => {
        const list = items || [];
        setContacts(list);
        setSelectedContactId((current) => {
          if (list.length === 0) return null;
          if (list.some((c) => c.id === current)) return current;
          return list[0].id;
        });
      })
      .catch(fail);
  }, [session, tenantId, searchTerm, filterTagId, fail]);

  const refreshTags = useCallback(() => {
    if (!tenantId) return Promise.resolve();
    return listContactTags(session, tenantId)
      .then((items) => setAvailableTags(items || []))
      .catch(fail);
  }, [session, tenantId, fail]);

  const refreshProfile = useCallback(
    (contactId) => {
      const id = contactId ?? selectedContactId;
      if (!tenantId || !id) {
        setProfile(null);
        return Promise.resolve();
      }
      return getContactProfile(session, tenantId, id).then(setProfile).catch(fail);
    },
    [session, tenantId, selectedContactId, fail],
  );

  const refreshContactPackages = useCallback(
    (contactId) => {
      const id = contactId ?? selectedContactId;
      if (!tenantId || !id) {
        setContactPackages([]);
        return Promise.resolve();
      }
      return listContactPackages(session, tenantId, id)
        .then((items) => setContactPackages(Array.isArray(items) ? items : []))
        .catch(fail);
    },
    [session, tenantId, selectedContactId, fail],
  );

  const refreshConsent = useCallback(
    (contactId) => {
      const id = contactId ?? selectedContactId;
      if (!tenantId || !id) {
        setConsent(null);
        return Promise.resolve();
      }
      return listContactConsent(session, tenantId, id, { limit: 100 })
        .then(setConsent)
        .catch(fail);
    },
    [session, tenantId, selectedContactId, fail],
  );

  const refreshAvailablePackages = useCallback(() => {
    if (!tenantId) return Promise.resolve();
    return listTreatmentPackages(session, tenantId, { is_active: true })
      .then((items) => setAvailablePackages(Array.isArray(items) ? items : []))
      .catch(fail);
  }, [session, tenantId, fail]);

  useEffect(() => {
    if (!tenantId) return;
    refreshTags();
    refreshContacts();
    refreshAvailablePackages();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId]);

  useEffect(() => {
    if (selectedContactId) {
      refreshProfile(selectedContactId);
      refreshContactPackages(selectedContactId);
      refreshConsent(selectedContactId);
    } else {
      // BUG-116: cuando `selectedContactId` cae a null (tenant switch con
      // contacts vacío, search sin resultados, etc.), antes solo limpiamos
      // `consent` — `profile` y `contactPackages` quedaban stale del contacto
      // anterior, así que el drawer mostraba el contacto del tenant anterior.
      setProfile(null);
      setContactPackages([]);
      setConsent(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedContactId]);

  async function runBusy(fn, successText) {
    setIsBusy(true);
    try {
      await fn();
      if (successText) setNotice({ type: 'success', text: successText });
    } catch (error) {
      fail(error);
    } finally {
      setIsBusy(false);
    }
  }

  const actions = {
    search: () => refreshContacts(),
    selectContact: setSelectedContactId,
    setSearchTerm,
    setFilterTagId,
    assignTag: (tagId) =>
      runBusy(async () => {
        await assignContactTags(session, tenantId, selectedContactId, [tagId]);
        await Promise.all([refreshProfile(), refreshContacts()]);
      }, 'Etiqueta asignada.'),
    removeTag: (tagId) =>
      runBusy(async () => {
        await unassignContactTag(session, tenantId, selectedContactId, tagId);
        await Promise.all([refreshProfile(), refreshContacts()]);
      }, 'Etiqueta retirada.'),
    assignPackage: (packageId) =>
      runBusy(async () => {
        await assignContactPackage(session, tenantId, selectedContactId, {
          package_id: packageId,
          payment_status: 'pending',
        });
        await refreshContactPackages();
      }, 'Paquete asignado.'),
    refundPackage: (contactPackageId) =>
      runBusy(async () => {
        await refundContactPackage(session, tenantId, selectedContactId, contactPackageId);
        await refreshContactPackages();
      }, 'Paquete reembolsado.'),
    updatePhone: (phoneE164, reason) =>
      runBusy(async () => {
        await updateContactPhone(session, tenantId, selectedContactId, {
          phone_e164: phoneE164,
          reason: reason || undefined,
        });
        await Promise.all([refreshProfile(), refreshContacts()]);
      }, 'Teléfono actualizado y registrado en audit_logs.'),
    createNote: (body) =>
      runBusy(async () => {
        await createContactNote(session, tenantId, selectedContactId, body);
        await refreshProfile();
      }, 'Nota interna agregada.'),
    dismissNotice: () => setNotice(null),
  };

  const unassignedTags = useMemo(() => {
    const assignedIds = new Set((profile?.tags || []).map((t) => t.id));
    return availableTags.filter((tag) => !assignedIds.has(tag.id));
  }, [availableTags, profile?.tags]);

  return {
    state: {
      contacts,
      availableTags,
      unassignedTags,
      searchTerm,
      filterTagId,
      selectedContactId,
      profile,
      isBusy,
      notice,
      contactPackages,
      availablePackages,
      consent,
    },
    actions,
  };
}
