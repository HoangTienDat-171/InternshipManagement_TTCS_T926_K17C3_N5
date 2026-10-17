import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Clock3,
  Eye,
  FileText,
  Filter,
  Info,
  RefreshCw,
  RotateCcw,
  X,
} from 'lucide-react';
import { apiFetch, readJsonResponse } from '../utils/api';
import CustomSelect from '../components/CustomSelect';
import CustomDatePicker from '../components/CustomDatePicker';
import TablePagination from '../components/TablePagination';
import './ActivityAuditView.css';

const ACTION_LABELS = {
  // Backup & Recovery
  BACKUP_CREATED: 'Tạo bản sao lưu',
  BACKUP_FAILED: 'Sao lưu thất bại',
  BACKUP_CHECKSUM_VERIFIED: 'Kiểm tra checksum',
  BACKUP_RESTORE_VERIFIED: 'Khôi phục thử thành công',
  BACKUP_SETTINGS_UPDATED: 'Cập nhật lịch sao lưu',
  BACKUP_RETENTION_APPLIED: 'Áp dụng chính sách lưu giữ bản sao lưu',
  'backup retention applied': 'Áp dụng chính sách lưu giữ bản sao lưu',
  'backup_retention_applied': 'Áp dụng chính sách lưu giữ bản sao lưu',

  // Attendance
  ATTENDANCE_CHECK_IN: 'Chấm công vào',
  ATTENDANCE_CHECK_OUT: 'Chấm công ra',
  ATTENDANCE_QR_ISSUED: 'Tạo mã QR chấm công',
  ATTENDANCE_QR_REJECTED: 'Từ chối mã QR chấm công',

  // User & Accounts
  USER_LOGIN: 'Đăng nhập hệ thống',
  USER_LOGOUT: 'Đăng xuất hệ thống',
  USER_CREATED: 'Tạo tài khoản người dùng',
  USER_UPDATED: 'Cập nhật tài khoản',
  USER_LOCKED: 'Khóa tài khoản',
  USER_UNLOCKED: 'Mở khóa tài khoản',

  // Generic API changes
  API_POST: 'Thêm mới dữ liệu',
  API_PUT: 'Cập nhật dữ liệu',
  API_PATCH: 'Chỉnh sửa dữ liệu',
  API_DELETE: 'Xóa dữ liệu',

  // HRM
  HRM_SYNC: 'Đồng bộ nhân sự HRM',
  HRM_PREVIEW: 'Xem trước đồng bộ HRM',
};

const RESOURCE_LABELS = {
  BACKUP: 'Bản sao lưu',
  BACKUP_SETTINGS: 'Cấu hình sao lưu',
  ATTENDANCE: 'Chấm công',
  USER: 'Tài khoản người dùng',
  INTERN: 'Thực tập sinh',
  MENTOR: 'Người hướng dẫn',
  PROGRAM: 'Chương trình thực tập',
  DOCUMENT: 'Tài liệu',
  LEAVE: 'Nghỉ phép',
  SUPPORT: 'Yêu cầu hỗ trợ',
  SYSTEM: 'Hệ thống chung',
  HRM: 'Tích hợp HRM',
};

const FIELD_LABELS = {
  source: 'Nguồn phát sinh',
  shift_id: 'Mã ca làm việc',
  expires_in_seconds: 'Thời hạn (giây)',
  backup_type: 'Loại bản sao lưu',
  file_name: 'Tên tệp tin',
  file_size_bytes: 'Dung lượng (bytes)',
  checksum_sha256: 'Mã băm SHA-256',
  checksum_status: 'Trạng thái checksum',
  retention_removed: 'Số bản đã dọn dẹp theo retention',
  schedule_enabled: 'Đã bật lịch định kỳ',
  interval_hours: 'Chu kỳ lặp lại (giờ)',
  retention_count: 'Số bản lưu trữ tối đa',
  http_status: 'Mã phản hồi HTTP',
  reason: 'Lý do / Nguyên nhân',
  error_code: 'Mã lỗi hệ thống',
  source_backup_id: 'Mã bản sao lưu gốc',
  restore_database: 'Schema thử nghiệm',
  table_count: 'Tổng số bảng',
  foreign_key_constraints: 'Số ràng buộc khóa ngoại',
  upload_file_count: 'Số tệp đính kèm',
  endpoint: 'Đường dẫn API',
  method: 'Phương thức HTTP',
  client_ip: 'Địa chỉ IP',
  user_agent: 'Trình duyệt / Thiết bị',
};

function actionLabel(action) {
  if (!action) return 'Thao tác không xác định';
  if (ACTION_LABELS[action]) return ACTION_LABELS[action];

  const normalized = String(action).trim().toLowerCase();
  if (ACTION_LABELS[normalized]) return ACTION_LABELS[normalized];

  const upperUnderscored = String(action).trim().toUpperCase().replace(/\s+/g, '_');
  if (ACTION_LABELS[upperUnderscored]) return ACTION_LABELS[upperUnderscored];

  if (normalized.includes('retention')) return 'Áp dụng chính sách lưu giữ bản sao lưu';
  if (action.startsWith('API_')) {
    const verb = action.split('_').slice(0, 2).join('_');
    const path = action.split('_').slice(2).join(' ');
    return `${ACTION_LABELS[verb] || 'Thao tác'} · ${path}`;
  }

  return String(action).replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function resourceLabel(resource) {
  if (!resource) return 'Hệ thống';
  return RESOURCE_LABELS[resource] || resource;
}

export default function ActivityAuditView({ onShowToast }) {
  const [filters, setFilters] = useState({
    actor_id: '',
    action: '',
    resource: '',
    outcome: '',
    date_from: '',
    date_to: '',
  });
  const [applied, setApplied] = useState({});
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);

  const load = useCallback(async (signal) => {
    setError('');
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    Object.entries(applied).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });

    try {
      const response = await apiFetch(`/api/audit-logs?${params}`, { signal });
      const body = await readJsonResponse(response);
      if (!response.ok) throw new Error(body.detail || 'Không thể tải nhật ký hoạt động.');
      setData(body);
    } catch (loadError) {
      if (loadError.name !== 'AbortError') {
        setError(loadError.message || 'Không thể tải nhật ký hoạt động.');
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [applied, page, pageSize]);

  useEffect(() => {
    const controller = new AbortController();
    // oxlint-disable-next-line react/set-state-in-effect -- starts an abortable server query; response updates the view.
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const applyFilters = (event) => {
    event.preventDefault();
    if (filters.date_from && filters.date_to && filters.date_from > filters.date_to) {
      onShowToast?.('Thời gian "Từ ngày" không được lớn hơn "Đến ngày".', 'error');
      return;
    }

    const next = { ...filters };
    if (next.date_from) next.date_from = `${next.date_from}T00:00:00`;
    if (next.date_to) next.date_to = `${next.date_to}T23:59:59`;
    setPage(1);
    setLoading(true);
    setApplied(next);
  };

  const clearFilters = () => {
    setFilters({
      actor_id: '',
      action: '',
      resource: '',
      outcome: '',
      date_from: '',
      date_to: '',
    });
    setPage(1);
    setLoading(true);
    setApplied({});
  };

  const refresh = () => {
    setLoading(true);
    void load();
  };

  const detail = async (event) => {
    try {
      const response = await apiFetch(`/api/audit-logs/${event.event_id}`);
      const body = await readJsonResponse(response);
      if (!response.ok) throw new Error(body.detail || 'Không thể tải chi tiết sự kiện.');
      setSelected(body);
    } catch (loadError) {
      onShowToast?.(loadError.message || 'Không thể tải chi tiết sự kiện.', 'error');
    }
  };

  return (
    <div className="workspace-page activity-audit-page">
      {/* Header */}
      <header className="workspace-heading activity-header">
        <div>
          <span className="workspace-eyebrow">QUẢN TRỊ · US42</span>
          <h2>Nhật ký hoạt động</h2>
          <p>Ghi lại và tra cứu các thao tác có tác động đến dữ liệu và vận hành hệ thống. Nhật ký chỉ đọc dành cho Quản trị viên.</p>
        </div>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={refresh}
          disabled={loading}
          title="Làm mới danh sách nhật ký"
        >
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
          <span>Làm mới</span>
        </button>
      </header>

      {/* Filter Card */}
      <section className="card activity-filters-card">
        <div className="card-header activity-filter-header">
          <div className="activity-filter-title">
            <Filter size={16} />
            <span>Bộ lọc tra cứu sự kiện</span>
          </div>
          {Object.values(applied).some(Boolean) && (
            <span className="badge badge-info">Đang lọc</span>
          )}
        </div>

        <div className="card-body">
          <form className="activity-filters-form" onSubmit={applyFilters}>
            {/* Actor ID */}
            <div className="activity-filter-group">
              <label className="form-label" htmlFor="filter-actor-id">
                Người thực hiện (ID)
              </label>
              <input
                id="filter-actor-id"
                type="number"
                min="1"
                className="form-control"
                value={filters.actor_id}
                onChange={(event) => setFilters({ ...filters, actor_id: event.target.value })}
                placeholder="Nhập ID người dùng (Ví dụ: 1)"
              />
            </div>

            {/* Action Select */}
            <div className="activity-filter-group">
              <label className="form-label" htmlFor="filter-action">
                Hành động
              </label>
              <CustomSelect
                id="filter-action"
                value={filters.action}
                onChange={(event) => setFilters({ ...filters, action: event.target.value })}
              >
                <option value="">Tất cả hành động</option>
                <option value="BACKUP">Sao lưu &amp; Khôi phục (Tất cả)</option>
                <option value="BACKUP_CREATED">Tạo bản sao lưu</option>
                <option value="BACKUP_FAILED">Sao lưu thất bại</option>
                <option value="BACKUP_CHECKSUM_VERIFIED">Kiểm tra checksum</option>
                <option value="BACKUP_RESTORE_VERIFIED">Khôi phục thử thành công</option>
                <option value="BACKUP_SETTINGS_UPDATED">Cập nhật lịch sao lưu</option>
                <option value="ATTENDANCE">Chấm công (Tất cả)</option>
                <option value="ATTENDANCE_CHECK_IN">Chấm công vào</option>
                <option value="ATTENDANCE_CHECK_OUT">Chấm công ra</option>
                <option value="API_POST">Thêm mới dữ liệu (API POST)</option>
                <option value="API_PUT">Cập nhật dữ liệu (API PUT)</option>
                <option value="API_DELETE">Xóa dữ liệu (API DELETE)</option>
              </CustomSelect>
            </div>

            {/* Resource Select */}
            <div className="activity-filter-group">
              <label className="form-label" htmlFor="filter-resource">
                Đối tượng
              </label>
              <CustomSelect
                id="filter-resource"
                value={filters.resource}
                onChange={(event) => setFilters({ ...filters, resource: event.target.value })}
              >
                <option value="">Tất cả đối tượng</option>
                <option value="BACKUP">Bản sao lưu (BACKUP)</option>
                <option value="BACKUP_SETTINGS">Cấu hình sao lưu (BACKUP_SETTINGS)</option>
                <option value="ATTENDANCE">Chấm công (ATTENDANCE)</option>
                <option value="USER">Tài khoản (USER)</option>
                <option value="INTERN">Thực tập sinh (INTERN)</option>
                <option value="PROGRAM">Chương trình thực tập (PROGRAM)</option>
                <option value="DOCUMENT">Tài liệu (DOCUMENT)</option>
                <option value="HRM">Tích hợp HRM (HRM)</option>
                <option value="SYSTEM">Hệ thống (SYSTEM)</option>
              </CustomSelect>
            </div>

            {/* Outcome Select */}
            <div className="activity-filter-group">
              <label className="form-label" htmlFor="filter-outcome">
                Kết quả
              </label>
              <CustomSelect
                id="filter-outcome"
                value={filters.outcome}
                onChange={(event) => setFilters({ ...filters, outcome: event.target.value })}
              >
                <option value="">Tất cả kết quả</option>
                <option value="SUCCESS">Thành công (SUCCESS)</option>
                <option value="FAILURE">Thất bại (FAILURE)</option>
              </CustomSelect>
            </div>

            {/* Date From */}
            <div className="activity-filter-group">
              <label className="form-label" htmlFor="filter-date-from">
                Từ ngày
              </label>
              <div className="activity-date-input-wrap">
                <CustomDatePicker
                  id="filter-date-from"
                  name="date_from"
                  value={filters.date_from}
                  max={filters.date_to || undefined}
                  onChange={(event) => setFilters({ ...filters, date_from: event.target.value })}
                  placeholder="dd/mm/yyyy"
                />
              </div>
            </div>

            {/* Date To */}
            <div className="activity-filter-group">
              <label className="form-label" htmlFor="filter-date-to">
                Đến ngày
              </label>
              <div className="activity-date-input-wrap">
                <CustomDatePicker
                  id="filter-date-to"
                  name="date_to"
                  min={filters.date_from || undefined}
                  value={filters.date_to}
                  onChange={(event) => setFilters({ ...filters, date_to: event.target.value })}
                  placeholder="dd/mm/yyyy"
                />
              </div>
            </div>

            {/* Buttons */}
            <div className="activity-filter-actions-row">
              <button type="submit" className="btn btn-primary">
                <Filter size={15} />
                <span>Lọc dữ liệu</span>
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={clearFilters}
              >
                <RotateCcw size={15} />
                <span>Xóa lọc</span>
              </button>
            </div>
          </form>
        </div>
      </section>

      {/* Error banner */}
      {error && (
        <div className="workspace-error activity-audit-error" role="alert">
          <AlertTriangle size={18} />
          <span>{error}</span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={refresh}>
            Thử lại
          </button>
        </div>
      )}

      {/* Event List Table Card */}
      <section className="card activity-table-card">
        <div className="card-header activity-section-header">
          <div>
            <span className="workspace-eyebrow">SỰ KIỆN HỆ THỐNG</span>
            <h3>{loading ? 'Đang tải dữ liệu…' : `${data?.total || 0} sự kiện`}</h3>
          </div>
          <Clock3 size={20} className="activity-section-icon" />
        </div>

        <div className="card-body p-0">
          {loading ? (
            <div className="activity-loading-block">
              <RefreshCw size={24} className="animate-spin" />
              <span>Đang tải danh sách nhật ký…</span>
            </div>
          ) : !data?.items?.length ? (
            <div className="activity-empty-state">
              <Clock3 size={38} />
              <strong>Chưa có sự kiện phù hợp</strong>
              <p>Không tìm thấy bản ghi nhật ký nào theo điều kiện lọc hiện tại.</p>
              <button type="button" className="btn btn-secondary btn-sm" onClick={clearFilters}>
                <RotateCcw size={14} />
                <span>Xóa bộ lọc</span>
              </button>
            </div>
          ) : (
            <>
              <div className="table-responsive activity-table-scroll">
                <table className="data-table activity-data-table">
                  <thead>
                    <tr>
                      <th className="activity-col-time">Thời gian</th>
                      <th className="activity-col-actor">Người thực hiện</th>
                      <th className="activity-col-action">Hành động</th>
                      <th className="activity-col-resource">Đối tượng</th>
                      <th className="activity-col-outcome">Kết quả</th>
                      <th className="activity-col-actions">Thao tác</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((item) => (
                      <tr key={item.event_id}>
                        <td>
                          <div className="activity-time-cell">
                            <strong>{new Date(item.created_at).toLocaleTimeString('vi-VN')}</strong>
                            <small>{new Date(item.created_at).toLocaleDateString('vi-VN')}</small>
                          </div>
                        </td>
                        <td>
                          <div className="activity-actor-cell">
                            <strong>{item.actor_name || 'Hệ thống'}</strong>
                            <small>{item.actor_user_id ? `ID ${item.actor_user_id}` : 'Tác vụ nền'}</small>
                          </div>
                        </td>
                        <td>
                          <div className="activity-action-cell">
                            <span className="activity-action-text">{actionLabel(item.action)}</span>
                            {item.action && item.action !== actionLabel(item.action) && (
                              <code className="activity-action-raw">{item.action}</code>
                            )}
                          </div>
                        </td>
                        <td>
                          <div className="activity-resource-cell">
                            <strong>{resourceLabel(item.resource)}</strong>
                            {item.resource_id && <small className="activity-resource-id">Mã {item.resource_id}</small>}
                          </div>
                        </td>
                        <td>
                          <span
                            className={`activity-outcome-badge is-${item.outcome === 'SUCCESS' ? 'success' : 'failure'}`}
                          >
                            {item.outcome === 'SUCCESS' ? <Check size={12} /> : <X size={12} />}
                            <span>{item.outcome === 'SUCCESS' ? 'Thành công' : 'Thất bại'}</span>
                          </span>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm activity-detail-btn"
                            onClick={() => detail(item)}
                            aria-label={`Xem chi tiết sự kiện ${item.event_id}`}
                            title="Xem chi tiết sự kiện và metadata"
                          >
                            <Eye size={14} />
                            <span>Chi tiết</span>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="activity-pagination-wrap">
                <TablePagination
                  page={page}
                  pageSize={pageSize}
                  totalItems={data?.total || 0}
                  totalPages={data?.total_pages || 1}
                  itemLabel="sự kiện"
                  disabled={loading}
                  onPageChange={(nextPage) => {
                    setPage(nextPage);
                    setLoading(true);
                  }}
                  onPageSizeChange={(newSize) => {
                    setPageSize(newSize);
                    setPage(1);
                    setLoading(true);
                  }}
                />
              </div>
            </>
          )}
        </div>
      </section>

      {/* Modal Detail View */}
      {selected && (
        <div
          className="modal-overlay"
          role="presentation"
          onClick={() => setSelected(null)}
        >
          <div
            className="modal-container activity-detail-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="audit-detail-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <span className="workspace-eyebrow">SỰ KIỆN #{selected.event_id}</span>
                <h3 id="audit-detail-title">{actionLabel(selected.action)}</h3>
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setSelected(null)}
                aria-label="Đóng chi tiết"
              >
                <X size={18} />
              </button>
            </div>

            <div className="modal-body activity-detail-body">
              <div className="activity-detail-grid">
                <div className="activity-detail-cell">
                  <span className="activity-detail-label">Người thực hiện</span>
                  <strong>{selected.actor_name || 'Hệ thống'}</strong>
                  <small>{selected.actor_user_id ? `Mã người dùng: ID ${selected.actor_user_id}` : 'Tác vụ tự động chạy ngầm'}</small>
                </div>

                <div className="activity-detail-cell">
                  <span className="activity-detail-label">Đối tượng tác động</span>
                  <strong>{resourceLabel(selected.resource)}</strong>
                  <small>{selected.resource_id ? `Mã đối tượng: ${selected.resource_id}` : 'Toàn hệ thống'}</small>
                </div>

                <div className="activity-detail-cell">
                  <span className="activity-detail-label">Thời gian ghi nhận</span>
                  <strong>{new Date(selected.created_at).toLocaleString('vi-VN')}</strong>
                  <small>{new Date(selected.created_at).toISOString()}</small>
                </div>

                <div className="activity-detail-cell">
                  <span className="activity-detail-label">Kết quả thực hiện</span>
                  <span className={`activity-outcome-badge is-${selected.outcome === 'SUCCESS' ? 'success' : 'failure'}`}>
                    {selected.outcome === 'SUCCESS' ? <Check size={12} /> : <X size={12} />}
                    <span>{selected.outcome === 'SUCCESS' ? 'Thành công' : 'Thất bại'}</span>
                  </span>
                </div>
              </div>

              {/* Metadata Presentation */}
              {selected.metadata && Object.keys(selected.metadata).length > 0 ? (
                <div className="activity-detail-metadata-box">
                  <div className="activity-metadata-header">
                    <FileText size={16} />
                    <span>Dữ liệu chi tiết đính kèm:</span>
                  </div>
                  <div className="activity-metadata-list">
                    {Object.entries(selected.metadata).map(([key, value]) => (
                      <div className="activity-metadata-item" key={key}>
                        <span className="activity-metadata-key">
                          {FIELD_LABELS[key] || key.replaceAll('_', ' ')}
                        </span>
                        <div className="activity-metadata-val">
                          {typeof value === 'object' && value !== null ? (
                            <pre className="activity-metadata-pre">
                              {JSON.stringify(value, null, 2)}
                            </pre>
                          ) : (
                            <code>{String(value)}</code>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="activity-no-metadata">
                  <Info size={16} />
                  <span>Không có dữ liệu metadata bổ sung cho sự kiện này.</span>
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setSelected(null)}
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
