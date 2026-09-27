export function apiFetch(input, init = {}) {
  const headers = new Headers(init.headers || {});
  const token = localStorage.getItem('ims_token');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return fetch(input, { ...init, headers });
}

export async function readJsonResponse(response) {
  try {
    return await response.json();
  } catch {
    return {
      detail: response.ok
        ? 'Máy chủ trả về dữ liệu không hợp lệ.'
        : `Máy chủ gặp lỗi (${response.status}). Vui lòng thử lại.`,
    };
  }
}

export async function downloadProtectedFile(documentId, filename = 'tai-lieu') {
  const response = await apiFetch(`/api/documents/${documentId}/file`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Không thể tải tài liệu (${response.status}).`);
  }
  const blobUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = blobUrl;
  link.download = filename || 'tai-lieu';
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(blobUrl), 30_000);
}
