import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Archive, Check, Clock3, HardDriveDownload, RefreshCw, ShieldCheck } from 'lucide-react';
import { apiFetch, readJsonResponse } from '../utils/api';
import './BackupManagementView.css';

function formatSize(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

const STATUS_LABELS = { RUNNING: 'Đang chạy', SUCCESS: 'Thành công', FAILED: 'Thất bại', EXPIRED: 'Đã hết hạn theo retention' };
const CHECKSUM_LABELS = { PENDING: 'Chưa kiểm tra', VALID: 'Hợp lệ', INVALID: 'Không hợp lệ' };

export default function BackupManagementView({ onShowToast }) {
  const [settings, setSettings] = useState(null);
  const [form, setForm] = useState({ schedule_enabled: false, interval_hours: 24, retention_count: 0 });
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');

  const load = useCallback(async (signal) => {
    setError('');
    try {
      const [settingsResponse, jobsResponse] = await Promise.all([
        apiFetch('/api/admin/backups/settings', { signal }),
        apiFetch('/api/admin/backups?page=1&page_size=30', { signal }),
      ]);
      const [settingsData, jobsData] = await Promise.all([readJsonResponse(settingsResponse), readJsonResponse(jobsResponse)]);
      if (!settingsResponse.ok) throw new Error(settingsData.detail || 'Không thể tải cấu hình backup.');
      if (!jobsResponse.ok) throw new Error(jobsData.detail || 'Không thể tải lịch sử backup.');
      setSettings(settingsData);
      setForm({ schedule_enabled: settingsData.schedule_enabled, interval_hours: settingsData.interval_hours, retention_count: settingsData.retention_count });
      setJobs(jobsData.items || []);
    } catch (loadError) {
      if (loadError.name !== 'AbortError') setError(loadError.message || 'Không thể tải dữ liệu backup.');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  const refresh = () => { setLoading(true); void load(); };

  useEffect(() => {
    const controller = new AbortController();
    // oxlint-disable-next-line react/set-state-in-effect -- starts an abortable server query; response updates the view.
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const latestJob = jobs[0];
  const saveSettings = async (event) => {
    event.preventDefault();
    setBusy('settings');
    setError('');
    try {
      const response = await apiFetch('/api/admin/backups/settings', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
          schedule_enabled: form.schedule_enabled,
          interval_hours: Number(form.interval_hours),
          retention_count: Number(form.retention_count),
        }),
      });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể lưu cấu hình backup.');
      setSettings(data);
      onShowToast?.('Đã lưu lịch và retention backup.', 'success');
      setLoading(true);
      await load();
    } catch (saveError) {
      setError(saveError.message || 'Không thể lưu cấu hình backup.');
    } finally {
      setBusy('');
    }
  };

  const createBackup = async () => {
    setBusy('backup');
    setError('');
    try {
      const response = await apiFetch('/api/admin/backups', { method: 'POST' });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể tạo bản sao lưu.');
      onShowToast?.(`Backup đã hoàn tất · ${formatSize(data.file_size_bytes)}.`, 'success');
      setLoading(true);
      await load();
    } catch (backupError) {
      setError(backupError.message || 'Backup thất bại. Xem mã lỗi trong lịch sử rồi kiểm tra log backend.');
    } finally {
      setBusy('');
    }
  };

  const verifyBackup = async (jobId) => {
    setBusy(`verify-${jobId}`);
    try {
      const response = await apiFetch(`/api/admin/backups/${jobId}/verify`, { method: 'POST' });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể kiểm tra checksum.');
      onShowToast?.(data.checksum_status === 'VALID' ? 'Checksum hợp lệ.' : 'Checksum không hợp lệ hoặc tệp đã mất.', data.checksum_status === 'VALID' ? 'success' : 'error');
      setLoading(true);
      await load();
    } catch (verifyError) {
      setError(verifyError.message || 'Không thể kiểm tra checksum.');
    } finally {
      setBusy('');
    }
  };

  const scheduleLabel = useMemo(() => settings?.schedule_enabled ? `Mỗi ${settings.interval_hours} giờ` : 'Đang tắt', [settings]);

  return <div className="workspace-page backup-management-page">
    <header className="workspace-heading"><div><span className="workspace-eyebrow">QUẢN TRỊ · US41</span><h2>Sao lưu &amp; khôi phục</h2>
      <p>Sao lưu MySQL cùng uploads vào thư mục riêng tư trên máy chủ. Mặc định chưa bật lịch hoặc tự xóa backup cũ.</p></div>
      <div className="backup-heading-actions"><button type="button" className="btn btn-secondary" onClick={refresh} disabled={loading || Boolean(busy)}><RefreshCw size={15} />Làm mới</button>
        <button type="button" className="btn btn-primary" onClick={createBackup} disabled={loading || Boolean(busy)}><HardDriveDownload size={16} />{busy === 'backup' ? 'Đang tạo bản sao…' : 'Tạo bản sao lưu'}</button></div>
    </header>

    {error && <div className="workspace-error backup-error" role="alert"><AlertTriangle size={17} /><span>{error}</span><button type="button" className="btn btn-secondary btn-sm" onClick={refresh}>Thử lại</button></div>}

    <section className="backup-summary-grid">
      <article className="workspace-card backup-summary-card"><span>Backup gần nhất</span><strong>{latestJob ? new Date(latestJob.finished_at || latestJob.started_at).toLocaleString('vi-VN') : 'Chưa có'}</strong><small>{latestJob ? STATUS_LABELS[latestJob.status] || latestJob.status : 'Tạo bản đầu tiên để bắt đầu'}</small></article>
      <article className="workspace-card backup-summary-card"><span>Lịch định kỳ</span><strong>{loading ? '…' : scheduleLabel}</strong><small>{settings?.schedule_enabled ? `Backup mỗi ${settings.interval_hours} giờ` : 'Chưa bật'}</small></article>
      <article className="workspace-card backup-summary-card"><span>Retention</span><strong>{settings?.retention_count ? `${settings.retention_count} bản` : 'Tắt'}</strong><small>{settings?.retention_count ? 'Các bản cũ hơn sẽ được đánh dấu hết hạn' : 'Không tự xóa backup'}</small></article>
    </section>

    <section className="workspace-card backup-settings-card">
      <div className="backup-section-heading"><div><span className="workspace-eyebrow">LỊCH VÀ LƯU TRỮ</span><h3>Cấu hình backup</h3></div><ShieldCheck size={20} /></div>
      {loading ? <div role="status" className="backup-loading">Đang tải cấu hình…</div> : settings && <>
        <div className="backup-storage-path"><span>Thư mục riêng tư</span><code>{settings.storage_directory}</code></div>
        <form className="backup-settings-form" onSubmit={saveSettings}>
          <label className="backup-checkbox"><input type="checkbox" checked={form.schedule_enabled} onChange={(event) => setForm({ ...form, schedule_enabled: event.target.checked })} /><span>Bật sao lưu định kỳ</span></label>
          <label>Chu kỳ (giờ)<input type="number" min="1" max="8760" value={form.interval_hours} onChange={(event) => setForm({ ...form, interval_hours: event.target.value })} disabled={!form.schedule_enabled} /></label>
          <label>Giữ lại số bản<input type="number" min="0" max="365" value={form.retention_count} onChange={(event) => setForm({ ...form, retention_count: event.target.value })} /><small>0 = không tự xóa bản sao lưu.</small></label>
          <button type="submit" className="btn btn-primary" disabled={busy === 'settings'}><Check size={15} />{busy === 'settings' ? 'Đang lưu…' : 'Lưu cấu hình'}</button>
        </form>
        <p className="backup-settings-note"><AlertTriangle size={15} />Retention chỉ xóa các file backup do IMS tạo. Hãy chọn số bản rõ ràng trước khi bật.</p>
      </>}
    </section>

    <section className="workspace-card backup-history-card">
      <div className="backup-section-heading"><div><span className="workspace-eyebrow">LỊCH SỬ</span><h3>Các bản sao lưu gần đây</h3></div><Archive size={20} /></div>
      {loading ? <div className="backup-loading" role="status">Đang tải lịch sử…</div> : !jobs.length ? <div className="backup-empty"><Archive size={28} /><strong>Chưa tạo bản sao lưu.</strong><span>Nhấn “Tạo bản sao lưu” để tạo bản đầu tiên.</span></div> : <div className="backup-table-wrap"><table className="backup-table"><thead><tr><th>Thời gian</th><th>Loại</th><th>Trạng thái</th><th>Dung lượng</th><th>Checksum</th><th>Thao tác</th></tr></thead><tbody>
        {jobs.map((job) => <tr key={job.id}><td><strong>{new Date(job.started_at).toLocaleString('vi-VN')}</strong><small>Job #{job.id} · {job.file_name || job.error_code || 'Khôi phục thử'}</small>{job.manifest?.restore_database && <small>Schema: {job.manifest.restore_database}</small>}</td>
          <td>{job.backup_type === 'SCHEDULED' ? 'Định kỳ' : job.backup_type === 'MANUAL' ? 'Thủ công' : 'Khôi phục thử'}</td>
          <td><span className={`backup-status is-${String(job.status).toLowerCase()}`}>{STATUS_LABELS[job.status] || job.status}</span>{job.error_code && <small>{job.error_code}</small>}</td>
          <td>{job.file_size_bytes ? formatSize(job.file_size_bytes) : '—'}</td>
          <td><span className={`backup-checksum is-${String(job.checksum_status).toLowerCase()}`}>{CHECKSUM_LABELS[job.checksum_status] || job.checksum_status}</span></td>
          <td>{job.status === 'SUCCESS' && job.backup_type !== 'RESTORE_VERIFICATION' && <button type="button" className="btn btn-secondary btn-sm" onClick={() => verifyBackup(job.id)} disabled={Boolean(busy)}><Check size={14} />{busy === `verify-${job.id}` ? 'Đang kiểm tra…' : 'Kiểm tra'}</button>}</td>
        </tr>)}
      </tbody></table></div>}
    </section>

    <section className="workspace-card backup-restore-guide">
      <div className="backup-section-heading"><div><span className="workspace-eyebrow">RUNBOOK KHÔI PHỤC</span><h3>Khôi phục thử trong schema riêng</h3></div><Clock3 size={20} /></div>
      <ol><li>Chọn backup <strong>SUCCESS</strong> và kiểm tra checksum hợp lệ.</li><li>Tạo schema mới chưa tồn tại có tiền tố <code>ims_restore_drill_</code>; không chọn schema IMS đang dùng.</li><li>Giải nén `database.sql` và `uploads/` vào thư mục tạm; import SQL vào schema thử, sau đó đối chiếu các bảng trong manifest.</li><li>Chạy hướng dẫn đầy đủ trong <code>docs/us41-backup-restore.md</code>; không restore đè database đang hoạt động.</li></ol>
      <p>Nút khôi phục trực tiếp chưa được bật. Cần xác nhận đích và quyền MySQL trước mỗi restore drill.</p>
    </section>
  </div>;
}
