import { useCallback, useEffect, useMemo, useState } from 'react';

import { adminModules, defaultModuleId } from '../data/modules.js';

function moduleFromHash() {
  const candidate = window.location.hash.replace('#', '');
  return adminModules.some((module) => module.id === candidate) ? candidate : defaultModuleId;
}

export function useActiveModule() {
  const [activeModuleId, setActiveModuleId] = useState(moduleFromHash);

  useEffect(() => {
    const onHashChange = () => setActiveModuleId(moduleFromHash());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const selectModule = useCallback((moduleId) => {
    window.location.hash = moduleId;
    setActiveModuleId(moduleId);
  }, []);

  const activeModule = useMemo(
    () => adminModules.find((module) => module.id === activeModuleId) ?? adminModules[0],
    [activeModuleId],
  );

  return { activeModule, activeModuleId, modules: adminModules, selectModule };
}
