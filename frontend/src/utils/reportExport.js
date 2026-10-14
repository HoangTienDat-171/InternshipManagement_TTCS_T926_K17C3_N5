import { apiFetch } from './api';

export async function downloadReport(url, fallbackName) {
  const response = await apiFetch(url);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Không thể xuất báo cáo (${response.status}).`);
  }
  const blob = await response.blob();
  if (!blob.size) throw new Error('Máy chủ trả về tệp báo cáo rỗng.');
  const disposition = response.headers.get('Content-Disposition') || '';
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || fallbackName;
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 30_000);
}
