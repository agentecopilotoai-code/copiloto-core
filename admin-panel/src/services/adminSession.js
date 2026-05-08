const backendOrigin = import.meta.env.VITE_ADMIN_BACKEND_ORIGIN || '';

export function adminPath(path) {
  return `${backendOrigin}${path}`;
}

export async function fetchAdminSession() {
  const response = await fetch(adminPath('/admin/api/session'), {
    credentials: 'include',
    headers: { accept: 'application/json' },
  });

  if (response.status === 401) {
    return null;
  }

  if (!response.ok) {
    throw new Error('No se pudo cargar la sesión del panel administrativo.');
  }

  return response.json();
}
