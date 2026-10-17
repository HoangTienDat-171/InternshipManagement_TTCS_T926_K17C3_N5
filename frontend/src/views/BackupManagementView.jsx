import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Archive,
  Check,
  Clock3,
  Copy,
  Database,
  Eye,
  FileCheck2,
  FileText,
  Folder,
  HardDriveDownload,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  X,
} from 'lucide-react';
import { apiFetch, readJsonResponse } from '../utils/api';
import ConfirmDialog from '../components/ConfirmDialog';
import './BackupManagementView.css';

function formatSize(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

const STATUS_LABELS = {
  RUNNING: 'Đang chạy',
  SUCCESS: 'Thành công',
  FAILED: 'Thất bại',
  EXPIRED: 'Đã hết hạn',
};

const CHECKSUM_LABELS = {
  PENDING: 'Chưa kiểm tra',
  VALID: 'Hợp lệ',
  INVALID: 'Không hợp lệ',
};

const TYPE_LABELS = {
  MANUAL: 'Thủ công',
  SCHEDULED: 'Định kỳ',
  RESTORE_VERIFICATION: 'Khôi phục thử',
};

export default function BackupManagementView({ onShowToast }) {
  const [settings, setSettings] = useState(null);
  const [form, setForm] = useState({ schedule_enabled: false, interval_hours: 24, retention_count: 0 });
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [confirmCreateOpen, setConfirmCreateOpen] = useState(false);
  const [selectedJob, setSelectedJob] = useState(null);
  const [copiedPath, setCopiedPath] = useState(false);

  const load = useCallback(async (signal) => {
    setError('');
    try {
      const [settingsResponse, jobsResponse] = await Promise.all([
        apiFetch('/api/admin/backups/settings', { signal }),
        apiFetch('/api/admin/backups?page=1&page_size=50', { signal }),
      ]);
      const [settingsData, jobsData] = await Promise.all([
        readJsonResponse(settingsResponse),
        readJsonResponse(jobsResponse),
      ]);
      if (!settingsResponse.ok) throw new Error(settingsData.detail || 'Không thể tải cấu hình backup.');
      if (!jobsResponse.ok) throw new Error(jobsData.detail || 'Không thể tải lịch sử backup.');
      setSettings(settingsData);
      setForm({
        schedule_enabled: Boolean(settingsData.schedule_enabled),
        interval_hours: Number(settingsData.interval_hours) || 24,
        retention_count: Number(settingsData.retention_count) || 0,
      });
      setJobs(jobsData.items || []);
    } catch (loadError) {
      if (loadError.name !== 'AbortError') setError(loadError.message || 'Không thể tải dữ liệu backup.');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  const refresh = () => {
    setLoading(true);
    void load();
  };

  useEffect(() => {
    const controller = new AbortController();
    // oxlint-disable-next-line react/set-state-in-effect -- starts an abortable server query; response updates the view.
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const latestJob = jobs[0];

  const handleCopyPath = () => {
    if (!settings?.storage_directory) return;
    navigator.clipboard.writeText(settings.storage_directory).then(() => {
      setCopiedPath(true);
      setTimeout(() => setCopiedPath(false), 2000);
      onShowToast?.('Đã sao chép đường dẫn lưu trữ vào bộ nhớ tạm.', 'info');
    });
  };

  const saveSettings = async (event) => {
    event.preventDefault();
    setBusy('settings');
    setError('');
    try {
      const response = await apiFetch('/api/admin/backups/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          schedule_enabled: form.schedule_enabled,
          interval_hours: Number(form.interval_hours),
          retention_count: Number(form.retention_count),
        }),
      });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể lưu cấu hình backup.');
      setSettings(data);
      onShowToast?.('Đã lưu cấu hình lịch sao lưu và retention thành công.', 'success');
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
      setConfirmCreateOpen(false);
      onShowToast?.(`Bản sao lưu #${data.id} đã hoàn tất (${formatSize(data.file_size_bytes)}).`, 'success');
      setLoading(true);
      await load();
    } catch (backupError) {
      setError(backupError.message || 'Backup thất bại. Vui lòng kiểm tra log hệ thống.');
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
      const isValid = data.checksum_status === 'VALID';
      onShowToast?.(
        isValid ? `Bản sao lưu #${jobId}: Checksum SHA-256 hoàn toàn hợp lệ.` : `Cảnh báo: Bản sao lưu #${jobId} không khớp checksum hoặc file đã bị sửa đổi.`,
        isValid ? 'success' : 'error',
      );
      setLoading(true);
      await load();
    } catch (verifyError) {
      setError(verifyError.message || 'Không thể kiểm tra checksum.');
    } finally {
      setBusy('');
    }
  };

  const scheduleLabel = useMemo(() => {
    if (loading) return 'Đang tải…';
    if (!settings?.schedule_enabled) return 'Đang tắt';
    return `Mỗi ${settings.interval_hours} giờ`;
  }, [loading, settings]);

  const retentionLabel = useMemo(() => {
    if (loading) return 'Đang tải…';
    if (!settings?.retention_count) return 'Tắt (Lưu vô hạn)';
    return `${settings.retention_count} bản gần nhất`;
  }, [loading, settings]);

  return (
    <div className="workspace-page backup-management-page">
      {/* Header */}
      <header className="workspace-heading backup-header">
        <div>
          <span className="workspace-eyebrow">QUẢN TRỊ · US41</span>
          <h2>Sao lưu &amp; khôi phục</h2>
          <p>Sao lưu cơ sở dữ liệu MySQL và thư mục tải lên vào thư mục bảo mật. Quản lý lịch tự động và chính sách lưu giữ.</p>
        </div>
        <div className="backup-heading-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={refresh}
            disabled={loading || Boolean(busy)}
            title="Làm mới dữ liệu trang"
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
            <span>Làm mới</span>
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setConfirmCreateOpen(true)}
            disabled={loading || Boolean(busy)}
            title="Tạo bản sao lưu ngay lập tức"
          >
            <HardDriveDownload size={16} />
            <span>{busy === 'backup' ? 'Đang tạo bản sao lưu…' : 'Tạo bản sao lưu'}</span>
          </button>
        </div>
      </header>

      {/* Error Banner */}
      {error && (
        <div className="workspace-error backup-error" role="alert">
          <AlertTriangle size={18} />
          <div className="backup-error-text">
            <strong>Đã xảy ra lỗi:</strong>
            <span>{error}</span>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={refresh}>
            Thử lại
          </button>
        </div>
      )}

      {/* Summary Stat Cards */}
      <section className="backup-summary-grid">
        <article className="backup-summary-card tone-indigo">
          <div className="backup-summary-icon">
            <Database size={20} />
          </div>
          <div className="backup-summary-content">
            <span className="backup-summary-label">BACKUP GẦN NHẤT</span>
            {loading ? (
              <div className="backup-skeleton-line short" />
            ) : (
              <strong className="backup-summary-value">
                {latestJob ? new Date(latestJob.started_at).toLocaleString('vi-VN') : 'Chưa có bản sao lưu'}
              </strong>
            )}
            <div className="backup-summary-sub">
              {loading ? (
                <div className="backup-skeleton-line tiny" />
              ) : latestJob ? (
                <div className="backup-status-tag-row">
                  <span className={`backup-status-pill is-${String(latestJob.status).toLowerCase()}`}>
                    {STATUS_LABELS[latestJob.status] || latestJob.status}
                  </span>
                  {latestJob.file_size_bytes ? (
                    <span className="backup-size-chip">{formatSize(latestJob.file_size_bytes)}</span>
                  ) : null}
                </div>
              ) : (
                <span>Nhấn “Tạo bản sao lưu” để bắt đầu</span>
              )}
            </div>
          </div>
        </article>

        <article className="backup-summary-card tone-amber">
          <div className="backup-summary-icon">
            <Clock3 size={20} />
          </div>
          <div className="backup-summary-content">
            <span className="backup-summary-label">LỊCH ĐỊNH KỲ</span>
            {loading ? (
              <div className="backup-skeleton-line short" />
            ) : (
              <strong className="backup-summary-value">{scheduleLabel}</strong>
            )}
            <div className="backup-summary-sub">
              {loading ? (
                <div className="backup-skeleton-line tiny" />
              ) : (
                <span>{settings?.schedule_enabled ? `Tự động chạy mỗi ${settings.interval_hours} giờ` : 'Chưa kích hoạt lịch tự động'}</span>
              )}
            </div>
          </div>
        </article>

        <article className="backup-summary-card tone-green">
          <div className="backup-summary-icon">
            <ShieldCheck size={20} />
          </div>
          <div className="backup-summary-content">
            <span className="backup-summary-label">CHÍNH SÁCH LƯU TRỮ (RETENTION)</span>
            {loading ? (
              <div className="backup-skeleton-line short" />
            ) : (
              <strong className="backup-summary-value">{retentionLabel}</strong>
            )}
            <div className="backup-summary-sub">
              {loading ? (
                <div className="backup-skeleton-line tiny" />
              ) : (
                <span>{settings?.retention_count ? 'Tự động dọn dẹp các bản quá hạn' : 'Không tự động xóa bản sao lưu cũ'}</span>
              )}
            </div>
          </div>
        </article>
      </section>

      {/* Settings Card */}
      <section className="card backup-settings-card">
        <div className="card-header backup-section-header">
          <div>
            <span className="workspace-eyebrow">LỊCH VÀ LƯU TRỮ</span>
            <h3>Cấu hình sao lưu</h3>
          </div>
          <ShieldCheck size={22} className="backup-section-icon" />
        </div>

        <div className="card-body">
          {loading ? (
            <div className="backup-loading-block">
              <RefreshCw size={22} className="animate-spin" />
              <span>Đang tải cấu hình sao lưu…</span>
            </div>
          ) : settings ? (
            <div className="backup-settings-layout">
              {/* Storage path display */}
              <div className="backup-storage-box">
                <div className="backup-storage-header">
                  <div className="backup-storage-title">
                    <Folder size={16} />
                    <span>Thư mục lưu trữ an toàn trên máy chủ:</span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm backup-copy-btn"
                    onClick={handleCopyPath}
                    title="Sao chép đường dẫn"
                  >
                    {copiedPath ? <Check size={14} color="#059669" /> : <Copy size={14} />}
                    <span>{copiedPath ? 'Đã sao chép' : 'Sao chép đường dẫn'}</span>
                  </button>
                </div>
                <code className="backup-storage-code">{settings.storage_directory}</code>
              </div>

              {/* Form settings */}
              <form className="backup-form-grid" onSubmit={saveSettings}>
                {/* Schedule Switch */}
                <div className="backup-form-field">
                  <label className="form-label">Tự động sao lưu định kỳ</label>
                  <label className="backup-switch-control">
                    <input
                      type="checkbox"
                      className="backup-switch-native"
                      checked={form.schedule_enabled}
                      onChange={(e) => setForm((prev) => ({ ...prev, schedule_enabled: e.target.checked }))}
                    />
                    <span className="backup-switch-track">
                      <span className="backup-switch-thumb" />
                    </span>
                    <span className="backup-switch-caption">
                      {form.schedule_enabled ? 'Đang kích hoạt' : 'Đang tắt'}
                    </span>
                  </label>
                </div>

                {/* Interval hours */}
                <div className="backup-form-field">
                  <label className="form-label" htmlFor="backup-interval">
                    Chu kỳ sao lưu (giờ)
                  </label>
                  <input
                    id="backup-interval"
                    type="number"
                    min="1"
                    max="8760"
                    className="form-control"
                    value={form.interval_hours}
                    disabled={!form.schedule_enabled}
                    onChange={(e) => setForm((prev) => ({ ...prev, interval_hours: e.target.value }))}
                    placeholder="24"
                  />
                  <small className="backup-field-hint">Khuyến nghị: 24 giờ cho môi trường sản xuất.</small>
                </div>

                {/* Retention count */}
                <div className="backup-form-field">
                  <label className="form-label" htmlFor="backup-retention">
                    Số bản giữ lại (Retention)
                  </label>
                  <input
                    id="backup-retention"
                    type="number"
                    min="0"
                    max="365"
                    className="form-control"
                    value={form.retention_count}
                    onChange={(e) => setForm((prev) => ({ ...prev, retention_count: e.target.value }))}
                    placeholder="10"
                  />
                  <small className="backup-field-hint">Nhập 0 để lưu trữ toàn bộ, không tự xóa bản cũ.</small>
                </div>

                {/* Submit button */}
                <div className="backup-form-actions">
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={busy === 'settings'}
                  >
                    <Check size={16} />
                    <span>{busy === 'settings' ? 'Đang lưu…' : 'Lưu cấu hình'}</span>
                  </button>
                </div>
              </form>

              {/* Retention note */}
              <div className="backup-notice-alert">
                <AlertTriangle size={16} className="backup-notice-icon" />
                <span>
                  <strong>Lưu ý:</strong> Chính sách Retention chỉ áp dụng tự động dọn dẹp các tệp sao lưu do chính IMS tạo trong thư mục riêng tư. Hãy đảm bảo ổ cứng còn đủ dung lượng trước khi đặt số lượng bản lưu trữ lớn.
                </span>
              </div>
            </div>
          ) : (
            <div className="backup-error-state">
              <AlertTriangle size={24} color="#dc2626" />
              <span>Không tải được cấu hình.</span>
              <button type="button" className="btn btn-secondary btn-sm" onClick={refresh}>
                Thử lại
              </button>
            </div>
          )}
        </div>
      </section>

      {/* Backup History Table */}
      <section className="card backup-history-card">
        <div className="card-header backup-section-header">
          <div>
            <span className="workspace-eyebrow">LỊCH SỬ THỰC HIỆN</span>
            <h3>Các bản sao lưu gần đây ({jobs.length})</h3>
          </div>
          <Archive size={22} className="backup-section-icon" />
        </div>

        <div className="card-body p-0">
          {loading ? (
            <div className="backup-loading-block">
              <RefreshCw size={22} className="animate-spin" />
              <span>Đang tải danh sách bản sao lưu…</span>
            </div>
          ) : !jobs.length ? (
            <div className="backup-empty-state">
              <Archive size={36} />
              <strong>Chưa có bản sao lưu nào</strong>
              <p>Hệ thống chưa ghi nhận bản sao lưu nào. Hãy nhấn “Tạo bản sao lưu” để bắt đầu.</p>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => setConfirmCreateOpen(true)}
              >
                <HardDriveDownload size={14} />
                <span>Tạo bản sao lưu ngay</span>
              </button>
            </div>
          ) : (
            <div className="table-responsive backup-table-scroll">
              <table className="data-table backup-data-table">
                <thead>
                  <tr>
                    <th>Thời gian</th>
                    <th>Loại</th>
                    <th>Dung lượng</th>
                    <th>Trạng thái</th>
                    <th>Checksum SHA-256</th>
                    <th>Thao tác</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.id}>
                      <td>
                        <div className="backup-time-cell">
                          <strong>{new Date(job.started_at).toLocaleString('vi-VN')}</strong>
                          <span className="backup-job-tag">Job #{job.id}</span>
                          {job.manifest?.restore_database && (
                            <small className="backup-schema-tag">Schema: {job.manifest.restore_database}</small>
                          )}
                        </div>
                      </td>
                      <td>
                        <span className={`backup-type-pill is-${String(job.backup_type).toLowerCase()}`}>
                          {TYPE_LABELS[job.backup_type] || job.backup_type}
                        </span>
                      </td>
                      <td>
                        <span className="backup-size-text">
                          {job.file_size_bytes ? formatSize(job.file_size_bytes) : '—'}
                        </span>
                      </td>
                      <td>
                        <div className="backup-status-cell">
                          <span className={`backup-status-pill is-${String(job.status).toLowerCase()}`}>
                            {STATUS_LABELS[job.status] || job.status}
                          </span>
                          {job.error_code && <small className="backup-error-badge">{job.error_code}</small>}
                        </div>
                      </td>
                      <td>
                        <span className={`backup-checksum-pill is-${String(job.checksum_status).toLowerCase()}`}>
                          {job.checksum_status === 'VALID' ? <Check size={13} /> : null}
                          {job.checksum_status === 'INVALID' ? <X size={13} /> : null}
                          <span>{CHECKSUM_LABELS[job.checksum_status] || job.checksum_status}</span>
                        </span>
                      </td>
                      <td>
                        <div className="backup-row-actions">
                          {job.status === 'SUCCESS' && job.backup_type !== 'RESTORE_VERIFICATION' && (
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() => verifyBackup(job.id)}
                              disabled={Boolean(busy)}
                              title="Kiểm tra tính toàn vẹn Checksum"
                            >
                              <FileCheck2 size={14} className={busy === `verify-${job.id}` ? 'animate-spin' : ''} />
                              <span>{busy === `verify-${job.id}` ? 'Đang kiểm tra…' : 'Kiểm tra'}</span>
                            </button>
                          )}
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => setSelectedJob(job)}
                            title="Xem chi tiết bản ghi và manifest"
                          >
                            <Eye size={14} />
                            <span>Chi tiết</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* Runbook Accordion / Guidelines */}
      <section className="card backup-runbook-card">
        <div className="card-header backup-section-header">
          <div>
            <span className="workspace-eyebrow">HƯỚNG DẪN VẬN HÀNH (RUNBOOK)</span>
            <h3>Quy trình khôi phục thử nghiệm độc lập</h3>
          </div>
          <Clock3 size={22} className="backup-section-icon" />
        </div>

        <div className="card-body">
          <div className="backup-runbook-steps">
            <div className="backup-step-item">
              <div className="backup-step-number">1</div>
              <div className="backup-step-content">
                <strong>Xác thực bản sao lưu nguồn</strong>
                <p>Chọn bản sao lưu có trạng thái <code>SUCCESS</code> trong bảng và bấm nút <em>Kiểm tra</em> để xác nhận mã băm SHA-256 hoàn toàn hợp lệ.</p>
              </div>
            </div>

            <div className="backup-step-item">
              <div className="backup-step-number">2</div>
              <div className="backup-step-content">
                <strong>Tạo Schema thử nghiệm độc lập</strong>
                <p>Khởi tạo cơ sở dữ liệu tạm có tiền tố <code>ims_restore_drill_[thời_gian]</code> trên MySQL. Tuyệt đối không chọn schema chính đang chạy.</p>
              </div>
            </div>

            <div className="backup-step-item">
              <div className="backup-step-number">3</div>
              <div className="backup-step-content">
                <strong>Nạp dữ liệu SQL và đối chiếu Manifest</strong>
                <p>Giải nén <code>database.sql</code> và tệp đính kèm vào thư mục tạm; nạp vào schema thử nghiệm rồi so sánh tổng số bảng và ràng buộc khóa ngoại.</p>
              </div>
            </div>

            <div className="backup-step-item">
              <div className="backup-step-number">4</div>
              <div className="backup-step-content">
                <strong>Nghiệm thu và dọn dẹp môi trường</strong>
                <p>Thực hiện các truy vấn kiểm tra tính toàn vẹn nghiệp vụ. Sau khi hoàn tất kiểm thử, tiến hành xóa schema drill để bảo toàn tài nguyên máy chủ.</p>
              </div>
            </div>
          </div>

          <div className="backup-danger-alert">
            <ShieldAlert size={18} className="backup-danger-icon" />
            <div>
              <strong>Cảnh báo an toàn:</strong> Không thực hiện khôi phục trực tiếp đè lên cơ sở dữ liệu sản xuất. Mọi thao tác khôi phục thử nghiệm phải được tiến hành trên môi trường cách ly độc lập theo đúng quy trình.
            </div>
          </div>
        </div>
      </section>

      {/* Modal Confirm Create Backup */}
      <ConfirmDialog
        open={confirmCreateOpen}
        title="Tạo bản sao lưu hệ thống"
        message="Hệ thống sẽ tiến hành kết xuất toàn bộ cơ sở dữ liệu MySQL và các tệp đính kèm vào thư mục bảo mật. Quá trình này có thể mất từ vài giây đến một phút."
        confirmLabel="Bắt đầu sao lưu"
        cancelLabel="Hủy"
        busy={busy === 'backup'}
        onConfirm={() => { void createBackup(); }}
        onCancel={() => { if (busy !== 'backup') setConfirmCreateOpen(false); }}
      />

      {/* Modal Detail Manifest */}
      {selectedJob && (
        <div
          className="modal-overlay"
          role="presentation"
          onClick={() => setSelectedJob(null)}
        >
          <div
            className="modal-container backup-detail-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="backup-detail-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <span className="workspace-eyebrow">CHI TIẾT JOB #{selectedJob.id}</span>
                <h3 id="backup-detail-title">
                  {TYPE_LABELS[selectedJob.backup_type] || selectedJob.backup_type} · {new Date(selectedJob.started_at).toLocaleString('vi-VN')}
                </h3>
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setSelectedJob(null)}
                aria-label="Đóng chi tiết"
              >
                <X size={18} />
              </button>
            </div>

            <div className="modal-body backup-detail-body">
              <div className="backup-detail-grid">
                <div className="backup-detail-cell">
                  <span className="backup-detail-label">Mã Job:</span>
                  <strong>#{selectedJob.id}</strong>
                </div>
                <div className="backup-detail-cell">
                  <span className="backup-detail-label">Loại bản sao:</span>
                  <span className={`backup-type-pill is-${String(selectedJob.backup_type).toLowerCase()}`}>
                    {TYPE_LABELS[selectedJob.backup_type] || selectedJob.backup_type}
                  </span>
                </div>
                <div className="backup-detail-cell">
                  <span className="backup-detail-label">Trạng thái:</span>
                  <span className={`backup-status-pill is-${String(selectedJob.status).toLowerCase()}`}>
                    {STATUS_LABELS[selectedJob.status] || selectedJob.status}
                  </span>
                </div>
                <div className="backup-detail-cell">
                  <span className="backup-detail-label">Checksum:</span>
                  <span className={`backup-checksum-pill is-${String(selectedJob.checksum_status).toLowerCase()}`}>
                    {CHECKSUM_LABELS[selectedJob.checksum_status] || selectedJob.checksum_status}
                  </span>
                </div>
                <div className="backup-detail-cell">
                  <span className="backup-detail-label">Thời gian bắt đầu:</span>
                  <span>{new Date(selectedJob.started_at).toLocaleString('vi-VN')}</span>
                </div>
                <div className="backup-detail-cell">
                  <span className="backup-detail-label">Thời gian kết thúc:</span>
                  <span>{selectedJob.finished_at ? new Date(selectedJob.finished_at).toLocaleString('vi-VN') : '—'}</span>
                </div>
                <div className="backup-detail-cell full-width">
                  <span className="backup-detail-label">Tên tệp lưu trữ:</span>
                  <code>{selectedJob.file_name || '—'}</code>
                </div>
                <div className="backup-detail-cell">
                  <span className="backup-detail-label">Dung lượng:</span>
                  <strong>{selectedJob.file_size_bytes ? formatSize(selectedJob.file_size_bytes) : '—'}</strong>
                </div>
                {selectedJob.checksum_sha256 && (
                  <div className="backup-detail-cell full-width">
                    <span className="backup-detail-label">Mã băm SHA-256:</span>
                    <code className="backup-hash-code">{selectedJob.checksum_sha256}</code>
                  </div>
                )}
              </div>

              {/* Manifest information */}
              {selectedJob.manifest && Object.keys(selectedJob.manifest).length > 0 && (
                <div className="backup-manifest-box">
                  <div className="backup-manifest-title">
                    <FileText size={16} />
                    <span>Thông tin Manifest đính kèm:</span>
                  </div>
                  <div className="backup-manifest-grid">
                    {selectedJob.manifest.restore_database && (
                      <div>
                        <span>Schema nguồn:</span>
                        <strong>{selectedJob.manifest.restore_database}</strong>
                      </div>
                    )}
                    {selectedJob.manifest.table_count !== undefined && (
                      <div>
                        <span>Số lượng bảng:</span>
                        <strong>{selectedJob.manifest.table_count} bảng</strong>
                      </div>
                    )}
                    {selectedJob.manifest.upload_file_count !== undefined && (
                      <div>
                        <span>Tệp upload đính kèm:</span>
                        <strong>{selectedJob.manifest.upload_file_count} tệp</strong>
                      </div>
                    )}
                    {selectedJob.manifest.foreign_key_constraints !== undefined && (
                      <div>
                        <span>Ràng buộc khóa ngoại:</span>
                        <strong>{selectedJob.manifest.foreign_key_constraints}</strong>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setSelectedJob(null)}
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
