export function apiFetch(input, init = {}) {
  const headers = new Headers(init.headers || {});
  const token = localStorage.getItem('ims_token');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return fetch(input, { ...init, headers });
}
