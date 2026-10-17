import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, ChevronLeft, ChevronRight, Clock3, Eye, Filter, RefreshCw, X } from 'lucide-react';
import { apiFetch, readJsonResponse } from '../utils/api';
import './ActivityAuditView.css';

const ACTION_LABELS = {
  ATTENDANCE_CHECK_IN: 'Chấm công vào',
  ATTENDANCE_CHECK_OUT: 'Chấm công ra',
  ATTENDANCE_QR_ISSUED: 'Tạo mã QR chấm công',
  ATTENDANCE_QR_REJECTED: 'Từ chối mã QR',
  BACKUP_CREATED: 'Tạo bản sao lưu',
  BACKUP_FAILED: 'Sao lưu thất bại',
  BACKUP_CHECKSUM_VERIFIED: 'Kiểm tra checksum',
  BACKUP_RESTORE_VERIFIED: 'Khôi phục thử thành công',
  BACKUP_SETTINGS_UPDATED: 'Cập nhật lịch sao lưu',
  API_POST: 'Tạo dữ liệu',
  API_PUT: 'Cập nhật dữ liệu',
  API_PATCH: 'Cập nhật dữ liệu',
  API_DELETE: 'Xóa dữ liệu',
};
const FIELD_LABELS = {
  source: 'Nguồn', shift_id: 'Mã ca', expires_in_seconds: 'Thời hạn (giây)',
  backup_type: 'Loại backup', file_name: 'Tệp backup', file_size_bytes: 'Dung lượng (byte)',
  checksum_sha256: 'SHA-256', checksum_status: 'Trạng thái checksum', retention_removed: 'Số bản đã giữ theo retention',
  schedule_enabled: 'Đã bật lịch', interval_hours: 'Chu kỳ (giờ)', retention_count: 'Số bản giữ lại',
  http_status: 'HTTP status', reason: 'Lý do', error_code: 'Mã lỗi',
  source_backup_id: 'Mã backup nguồn', restore_database: 'Schema restore', table_count: 'Số bảng',
  foreign_key_constraints: 'Số khóa ngoại', upload_file_count: 'Số tệp upload',
};

function actionLabel(action) {
  if (ACTION_LABELS[action]) return ACTION_LABELS[action];
  if (action.startsWith('API_')) return `${ACTION_LABELS[action.split('_').slice(0, 2).join('_')] || 'Thao tác'} · ${action.split('_').slice(2).join(' ')}`;
  return String(action || '').replaceAll('_', ' ').toLocaleLowerCase('vi-VN');
}

export default function ActivityAuditView() {
  const [filters, setFilters] = useState({ actor_id: '', action: '', resource: '', outcome: '', date_from: '', date_to: '' });
  const [applied, setApplied] = useState({});
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);

  const load = useCallback(async (signal) => {
    setError('');
    const params = new URLSearchParams({ page: String(page), page_size: '20' });
    Object.entries(applied).forEach(([key, value]) => { if (value) params.set(key, value); });
    try {
      const response = await apiFetch(`/api/audit-logs?${params}`, { signal });
      const body = await readJsonResponse(response);
      if (!response.ok) throw new Error(body.detail || 'Không thể tải nhật ký hoạt động.');
      setData(body);
    } catch (loadError) {
      if (loadError.name !== 'AbortError') setError(loadError.message || 'Không thể tải nhật ký hoạt động.');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [applied, page]);

  useEffect(() => {
    const controller = new AbortController();
    // oxlint-disable-next-line react/set-state-in-effect -- starts an abortable server query; response updates the view.
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const applyFilters = (event) => {
    event.preventDefault();
    const next = { ...filters };
    if (next.date_from) next.date_from = `${next.date_from}T00:00:00`;
    if (next.date_to) next.date_to = `${next.date_to}T23:59:59`;
    setPage(1);
    setLoading(true);
    setApplied(next);
  };

  const clearFilters = () => {
    setFilters({ actor_id: '', action: '', resource: '', outcome: '', date_from: '', date_to: '' });
    setPage(1);
    setLoading(true);
    setApplied({});
  };

  const refresh = () => { setLoading(true); void load(); };

  const detail = async (event) => {
    try {
      const response = await apiFetch(`/api/audit-logs/${event.event_id}`);
      const body = await readJsonResponse(response);
      if (!response.ok) throw new Error(body.detail || 'Không thể tải chi tiết sự kiện.');
      setSelected(body);
    } catch (loadError) {
      setError(loadError.message || 'Không thể tải chi tiết sự kiện.');
    }
  };

  return <div className="workspace-page activity-audit-page">
    <header className="workspace-heading"><div><span className="workspace-eyebrow">QUẢN TRỊ · US42</span><h2>Nhật ký hoạt động</h2>
      <p>Ghi lại các thao tác có tác động đến dữ liệu và vận hành. Nhật ký chỉ đọc, Admin mới được truy cập.</p></div>
      <button type="button" className="btn btn-secondary" onClick={refresh} disabled={loading}><RefreshCw size={15} />Làm mới</button>
    </header>

    <section className="workspace-card activity-audit-filters">
      <form onSubmit={applyFilters}>
        <label>Actor ID<input type="number" min="1" value={filters.actor_id} onChange={(event) => setFilters({ ...filters, actor_id: event.target.value })} placeholder="Mã người thực hiện" /></label>
        <label>Hành động<input value={filters.action} onChange={(event) => setFilters({ ...filters, action: event.target.value })} placeholder="Ví dụ: BACKUP" /></label>
        <label>Đối tượng<input value={filters.resource} onChange={(event) => setFilters({ ...filters, resource: event.target.value })} placeholder="Ví dụ: ATTENDANCE" /></label>
        <label>Kết quả<select value={filters.outcome} onChange={(event) => setFilters({ ...filters, outcome: event.target.value })}><option value="">Tất cả</option><option value="SUCCESS">Thành công</option><option value="FAILURE">Thất bại</option></select></label>
        <label>Từ ngày<input type="date" value={filters.date_from} onChange={(event) => setFilters({ ...filters, date_from: event.target.value })} /></label>
        <label>Đến ngày<input type="date" value={filters.date_to} onChange={(event) => setFilters({ ...filters, date_to: event.target.value })} /></label>
        <div className="activity-audit-filter-actions"><button type="submit" className="btn btn-primary"><Filter size={15} />Lọc</button><button type="button" className="btn btn-secondary" onClick={clearFilters}>Xóa lọc</button></div>
      </form>
    </section>

    {error && <div className="workspace-error activity-audit-error" role="alert"><AlertTriangle size={17} /><span>{error}</span><button type="button" className="btn btn-secondary btn-sm" onClick={refresh}>Thử lại</button></div>}
    <section className="workspace-card activity-audit-table-card">
      <div className="activity-audit-table-heading"><div><span className="workspace-eyebrow">SỰ KIỆN</span><h3>{loading ? 'Đang tải…' : `${data?.total || 0} sự kiện`}</h3></div></div>
      {loading ? <div className="activity-audit-empty" role="status">Đang tải nhật ký…</div> : !data?.items?.length ? <div className="activity-audit-empty"><Clock3 size={28} /><strong>Chưa có sự kiện phù hợp.</strong><span>Thử đổi bộ lọc hoặc làm mới danh sách.</span></div> : <>
        <div className="activity-audit-table-wrap"><table className="activity-audit-table"><thead><tr><th>Thời gian</th><th>Người thực hiện</th><th>Hành động</th><th>Đối tượng</th><th>Kết quả</th><th /></tr></thead>
          <tbody>{data.items.map((item) => <tr key={item.event_id}><td>{new Date(item.created_at).toLocaleString('vi-VN')}</td><td><strong>{item.actor_name || 'Hệ thống'}</strong><small>{item.actor_user_id ? `ID ${item.actor_user_id}` : 'Tác vụ nền'}</small></td>
            <td>{actionLabel(item.action)}</td><td><strong>{item.resource}</strong>{item.resource_id && <small>Mã {item.resource_id}</small>}</td>
            <td><span className={`activity-audit-outcome ${item.outcome === 'SUCCESS' ? 'is-success' : 'is-failure'}`}>{item.outcome === 'SUCCESS' ? 'Thành công' : 'Thất bại'}</span></td>
            <td><button type="button" className="btn btn-secondary btn-sm" onClick={() => detail(item)} aria-label={`Xem sự kiện ${item.event_id}`}><Eye size={15} />Chi tiết</button></td></tr>)}</tbody></table></div>
        <footer className="activity-audit-pagination"><span>Trang {data.page} / {Math.max(1, data.total_pages)}</span><div><button type="button" className="btn btn-secondary btn-sm" disabled={page <= 1} onClick={() => { setLoading(true); setPage((value) => value - 1); }}><ChevronLeft size={15} />Trước</button><button type="button" className="btn btn-secondary btn-sm" disabled={page >= data.total_pages} onClick={() => { setLoading(true); setPage((value) => value + 1); }}>Sau<ChevronRight size={15} /></button></div></footer>
      </>}
    </section>

    {selected && <div className="activity-audit-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelected(null); }}>
      <section className="activity-audit-dialog" role="dialog" aria-modal="true" aria-labelledby="audit-detail-title">
        <header><div><span className="workspace-eyebrow">SỰ KIỆN #{selected.event_id}</span><h3 id="audit-detail-title">{actionLabel(selected.action)}</h3></div><button type="button" className="btn btn-secondary btn-sm" aria-label="Đóng chi tiết" onClick={() => setSelected(null)}><X size={16} /></button></header>
        <dl><div><dt>Người thực hiện</dt><dd>{selected.actor_name || 'Hệ thống'}{selected.actor_user_id ? ` · ID ${selected.actor_user_id}` : ''}</dd></div>
          <div><dt>Đối tượng</dt><dd>{selected.resource}{selected.resource_id ? ` · Mã ${selected.resource_id}` : ''}</dd></div>
          <div><dt>Thời gian</dt><dd>{new Date(selected.created_at).toLocaleString('vi-VN')}</dd></div>
          <div><dt>Kết quả</dt><dd>{selected.outcome === 'SUCCESS' ? 'Thành công' : 'Thất bại'}</dd></div></dl>
        {Object.keys(selected.metadata || {}).length > 0 && <div className="activity-audit-metadata"><strong>Thông tin được ghi</strong>{Object.entries(selected.metadata).map(([key, value]) => <div key={key}><span>{FIELD_LABELS[key] || key.replaceAll('_', ' ')}</span><b>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</b></div>)}</div>}
      </section>
    </div>}
  </div>;
}
