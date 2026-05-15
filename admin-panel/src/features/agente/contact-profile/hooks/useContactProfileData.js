import { useCallback, useEffect, useState } from 'react';

import { getContactProfile, listContactConsent } from '../../../../services/coreApi.js';

/**
 * Data layer for the focused contact-profile deep-link view (UI-009.3).
 *
 * Owns the single read of `GET /contacts/:id/profile` plus the consent ledger
 * (`GET /contacts/:id/consent`), fetched in parallel. The consent call is
 * tolerated when it fails — like the existing Contactos drawer it degrades to
 * `null` rather than blocking the whole view. This view is read-only, so there
 * are no mutation handlers; `actions.refresh` simply re-runs the fetch.
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {string|undefined} options.tenantId — active tenant id
 * @param {string|undefined} options.contactId — contact id from the URL param
 */
export function useContactProfileData({ session, tenantId, contactId }) {
  const [profile, setProfile] = useState(null);
  const [consent, setConsent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [notFound, setNotFound] = useState(false);

  const load = useCallback(() => {
    if (!tenantId || !contactId) {
      setProfile(null);
      setConsent(null);
      setNotFound(false);
      setError(null);
      return Promise.resolve();
    }
    setLoading(true);
    setError(null);
    setNotFound(false);
    return Promise.all([
      getContactProfile(session, tenantId, contactId),
      listContactConsent(session, tenantId, contactId, { limit: 100 }).catch(() => null),
    ])
      .then(([profileResult, consentResult]) => {
        if (!profileResult || !profileResult.contact) {
          setProfile(null);
          setConsent(null);
          setNotFound(true);
          return;
        }
        setProfile(profileResult);
        setConsent(consentResult);
      })
      .catch((err) => {
        setProfile(null);
        setConsent(null);
        const status = err?.status ?? err?.response?.status;
        if (status === 404) {
          setNotFound(true);
        } else {
          setError(err?.message || 'No se pudo cargar la ficha del contacto.');
        }
      })
      .finally(() => setLoading(false));
  }, [session, tenantId, contactId]);

  useEffect(() => {
    load();
  }, [load]);

  return {
    state: { profile, consent, loading, error, notFound, tenantId, contactId },
    actions: { refresh: load },
  };
}
