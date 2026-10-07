import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  Calendar,
  CalendarCheck,
  CalendarDays,
  CheckCircle2,
  Clock,
  Filter,
  RefreshCw,
  Send,
  XCircle,
} from 'lucide-react';
import { apiFetch, readJsonResponse } from '../utils/api';

const statusBadgeMap = {
  ChoDuyet: { label: 'Chờ duyệt', tone: 'warning' },
  DaDuyet: { label: 'Đã duyệt', tone: 'success' },
  TuChoi: { label: 'Từ chối', tone: 'danger' },
  DaHuy: { label: 'Đã hủy', tone: 'neutral' },
};

function StatusBadge({ status }) {
  const meta = statusBadgeMap[status] || { label: status || 'Không rõ', tone: 'neutral' };
  const badgeClass = meta.tone === 'success'
    ? 'badge-success'
    : meta.tone === 'warning'
      ? 'badge-warning'
      : meta.tone === 'danger'
        ? 'badge-danger'
        : 'badge-secondary';

  return (
    <span className={`badge ${badgeClass}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      {meta.tone === 'success' && <CheckCircle2 size={12} />}
      {meta.tone === 'warning' && <Clock size={12} />}
      {meta.tone === 'danger' && <XCircle size={12} />}
      {meta.tone === 'neutral' && <AlertCircle size={12} />}
      {meta.label}
    </span>
  );
}

export default function LeaveManagementView({ currentUser, onShowToast }) {
  const isIntern = currentUser?.vai_tro === 'ThucTapSinh';
  const canReview = ['Admin', 'HR'].includes(currentUser?.vai_tro);

  // Intern state
  const [applications, setApplications] = useState([]);
  const [selectedAppId, setSelectedAppId] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  // Common list state
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState('');

  // Reviewer state
  const [statusFilter, setStatusFilter] = useState('');
  const [rejectingId, setRejectingId] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [actionLoadingId, setActionLoadingId] = useState(null);

  // Load Intern eligible applications
  const loadInternContext = useCallback(async () => {
    if (!isIntern) return;
    try {
      const res = await apiFetch('/api/interns/me/workspace');
      const data = await readJsonResponse(res);
      if (!res.ok) throw new Error(data.detail || 'Không thể tải thông tin thực tập.');
      const approvedApps = (data.applications || []).filter(
        (a) => a.trang_thai_ung_tuyen === 'DaDuyet'
      );
      setApplications(approvedApps);
      if (approvedApps.length > 0 && !selectedAppId) {
        setSelectedAppId(String(approvedApps[0].ma_ung_tuyen));
      }
    } catch (err) {
      setFetchError(err.message);
    }
  }, [isIntern, selectedAppId]);

  // Load Requests
  const loadRequests = useCallback(async () => {
    setLoading(true);
    setFetchError('');
    try {
      const url = isIntern
        ? '/api/interns/me/leave-requests'
        : `/api/leave-requests${statusFilter ? `?status=${statusFilter}` : ''}`;
      const res = await apiFetch(url);
      const data = await readJsonResponse(res);
      if (!res.ok) throw new Error(data.detail || 'Không thể tải danh sách đơn nghỉ phép.');
      setRequests(Array.isArray(data) ? data : []);
    } catch (err) {
      setFetchError(err.message);
    } finally {
      setLoading(false);
    }
  }, [isIntern, statusFilter]);

  useEffect(() => {
    loadInternContext();
  }, [loadInternContext]);

  useEffect(() => {
    loadRequests();
  }, [loadRequests]);

  // Submit Leave Request (Intern)
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (submitting) return;

    setFormError('');
    if (!selectedAppId) {
      setFormError('Vui lòng chọn chương trình thực tập.');
      return;
    }
    if (!startDate || !endDate) {
      setFormError('Vui lòng chọn ngày bắt đầu và ngày kết thúc nghỉ.');
      return;
    }
    if (startDate > endDate) {
      setFormError('Ngày bắt đầu không được sau ngày kết thúc.');
      return;
    }
    if (!reason.trim()) {
      setFormError('Vui lòng nhập lý do nghỉ phép.');
      return;
    }

    setSubmitting(true);
    try {
      const res = await apiFetch('/api/interns/me/leave-requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ma_ung_tuyen: Number(selectedAppId),
          start_date: startDate,
          end_date: endDate,
          ly_do: reason.trim(),
        }),
      });
      const data = await readJsonResponse(res);
      if (!res.ok) {
        throw new Error(data.detail || 'Không thể gửi đơn nghỉ phép.');
      }
      onShowToast?.('Đã gửi đơn nghỉ phép thành công! Đơn đang ở trạng thái Chờ duyệt.');
      setReason('');
      setStartDate('');
      setEndDate('');
      loadRequests();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  // Cancel Request (Intern)
  const handleCancel = async (requestId) => {
    if (!window.confirm('Bạn có chắc chắn muốn hủy đơn nghỉ phép này không?')) return;
    setActionLoadingId(requestId);
    try {
      const res = await apiFetch(`/api/interns/me/leave-requests/${requestId}/cancel`, {
        method: 'POST',
      });
      const data = await readJsonResponse(res);
      if (!res.ok) {
        throw new Error(data.detail || 'Không thể hủy đơn nghỉ phép.');
      }
      onShowToast?.('Đã hủy đơn nghỉ phép thành công.');
      loadRequests();
    } catch (err) {
      alert(err.message);
    } finally {
      setActionLoadingId(null);
    }
  };

  // Review Request (HR/Admin)
  const handleReview = async (requestId, decision, rejectNote = '') => {
    if (decision === 'TuChoi' && !rejectNote.trim()) {
      alert('Vui lòng nhập lý do từ chối đơn nghỉ phép.');
      return;
    }
    setActionLoadingId(requestId);
    try {
      const res = await apiFetch(`/api/leave-requests/${requestId}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trang_thai: decision,
          ly_do_tu_choi: decision === 'TuChoi' ? rejectNote.trim() : null,
        }),
      });
      const data = await readJsonResponse(res);
      if (!res.ok) {
        throw new Error(data.detail || 'Không thể xét duyệt đơn nghỉ phép.');
      }
      onShowToast?.(decision === 'DaDuyet' ? 'Đã duyệt đơn nghỉ phép.' : 'Đã từ chối đơn nghỉ phép.');
      setRejectingId(null);
      setRejectReason('');
      loadRequests();
    } catch (err) {
      alert(err.message);
    } finally {
      setActionLoadingId(null);
    }
  };

  return (
    <div className="workspace-container" style={{ padding: '24px 0' }}>
      <div className="section-header" style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: 10, margin: 0, fontSize: '1.4rem' }}>
            <CalendarCheck className="text-primary" size={24} />
            {isIntern ? 'Đăng ký nghỉ phép' : 'Quản lý đơn nghỉ phép'}
          </h2>
          <p style={{ margin: '6px 0 0', color: 'var(--text-muted, #64748b)', fontSize: '0.9rem' }}>
            {isIntern
              ? 'Tạo đơn xin nghỉ phép gắn với chương trình thực tập và theo dõi kết quả xét duyệt.'
              : 'Duyệt hoặc từ chối các đơn xin nghỉ phép của thực tập sinh.'}
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={loadRequests}
          disabled={loading}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
        >
          <RefreshCw size={14} className={loading ? 'spin' : ''} />
          Làm mới
        </button>
      </div>

      {fetchError && (
        <div className="alert alert-danger" style={{ marginBottom: 20 }}>
          <AlertCircle size={18} />
          <span>{fetchError}</span>
        </div>
      )}

      {/* Intern Create Form */}
      {isIntern && (
        <div className="card" style={{ marginBottom: 28, padding: 24, borderRadius: 12, border: '1px solid var(--border-color, #e2e8f0)' }}>
          <h3 style={{ fontSize: '1.1rem', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Calendar size={18} />
            Tạo đơn xin nghỉ phép mới
          </h3>

          {applications.length === 0 ? (
            <div className="alert alert-warning" style={{ margin: 0 }}>
              <AlertCircle size={18} />
              <span>Bạn chưa có chương trình thực tập nào được duyệt để đăng ký nghỉ phép.</span>
            </div>
          ) : (
            <form onSubmit={handleSubmit}>
              {formError && (
                <div className="alert alert-danger" style={{ marginBottom: 16 }}>
                  <AlertCircle size={16} />
                  <span>{formError}</span>
                </div>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16, marginBottom: 16 }}>
                <div>
                  <label className="form-label" htmlFor="leave-program">Chương trình thực tập *</label>
                  <select
                    id="leave-program"
                    className="form-control"
                    value={selectedAppId}
                    onChange={(e) => setSelectedAppId(e.target.value)}
                    required
                  >
                    {applications.map((app) => (
                      <option key={app.ma_ung_tuyen} value={app.ma_ung_tuyen}>
                        {app.ten_ct} ({app.ngay_bat_dau || '...'} → {app.ngay_ket_thuc || '...'})
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="form-label" htmlFor="leave-start-date">Nghỉ từ ngày *</label>
                  <input
                    id="leave-start-date"
                    type="date"
                    className="form-control"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    required
                  />
                </div>

                <div>
                  <label className="form-label" htmlFor="leave-end-date">Đến ngày *</label>
                  <input
                    id="leave-end-date"
                    type="date"
                    className="form-control"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div style={{ marginBottom: 16 }}>
                <label className="form-label" htmlFor="leave-reason">Lý do nghỉ phép *</label>
                <textarea
                  id="leave-reason"
                  className="form-control"
                  rows={3}
                  placeholder="Nhập lý do xin nghỉ phép cụ thể..."
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  maxLength={1000}
                  required
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={submitting}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}
                >
                  <Send size={16} />
                  {submitting ? 'Đang gửi...' : 'Gửi đơn nghỉ phép'}
                </button>
              </div>
            </form>
          )}
        </div>
      )}

      {/* Reviewer Filter Controls */}
      {canReview && (
        <div className="card" style={{ marginBottom: 20, padding: '16px 20px', borderRadius: 10, display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Filter size={16} className="text-muted" />
            <span style={{ fontSize: '0.9rem', fontWeight: 600 }}>Lọc theo trạng thái:</span>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {[
              { val: '', label: 'Tất cả' },
              { val: 'ChoDuyet', label: 'Chờ duyệt' },
              { val: 'DaDuyet', label: 'Đã duyệt' },
              { val: 'TuChoi', label: 'Từ chối' },
              { val: 'DaHuy', label: 'Đã hủy' },
            ].map((tab) => (
              <button
                key={tab.val}
                type="button"
                className={`btn btn-sm ${statusFilter === tab.val ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setStatusFilter(tab.val)}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Leave Requests Table */}
      <div className="card" style={{ padding: 0, borderRadius: 12, overflow: 'hidden', border: '1px solid var(--border-color, #e2e8f0)' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-color, #e2e8f0)', fontWeight: 600, fontSize: '1rem', display: 'flex', alignItems: 'center', gap: 8 }}>
          <CalendarDays size={18} />
          {isIntern ? 'Danh sách đơn nghỉ phép của bạn' : 'Danh sách đơn xin nghỉ phép'}
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted, #64748b)', fontWeight: 400 }}>
            ({requests.length} đơn)
          </span>
        </div>

        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted, #64748b)' }}>
            <RefreshCw size={24} className="spin" style={{ margin: '0 auto 12px' }} />
            Đang tải danh sách đơn nghỉ phép...
          </div>
        ) : requests.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted, #64748b)' }}>
            Chưa có đơn nghỉ phép nào.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="table" style={{ margin: 0, width: '100%' }}>
              <thead>
                <tr>
                  <th style={{ width: 60 }}>Mã</th>
                  {canReview && <th>Thực tập sinh</th>}
                  <th>Chương trình</th>
                  <th>Thời gian nghỉ</th>
                  <th>Lý do</th>
                  <th>Trạng thái</th>
                  <th>Người / Thời gian duyệt</th>
                  <th style={{ textAlign: 'right', width: 180 }}>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {requests.map((item) => (
                  <tr key={item.id}>
                    <td>#{item.id}</td>
                    {canReview && (
                      <td>
                        <strong>{item.intern_name}</strong>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted, #64748b)' }}>
                          {item.intern_email}
                        </div>
                      </td>
                    )}
                    <td>
                      <span title={item.ten_ct}>{item.ten_ct}</span>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted, #64748b)' }}>
                        {item.ma_ct}
                      </div>
                    </td>
                    <td>
                      <strong>{item.start_date}</strong>
                      <span style={{ color: 'var(--text-muted, #64748b)', margin: '0 4px' }}>→</span>
                      <strong>{item.end_date}</strong>
                    </td>
                    <td style={{ maxWidth: 220, wordBreak: 'break-word' }}>
                      {item.ly_do}
                      {item.ly_do_tu_choi && (
                        <div style={{ fontSize: '0.8rem', color: 'var(--danger, #ef4444)', marginTop: 4 }}>
                          <em>Lý do từ chối: {item.ly_do_tu_choi}</em>
                        </div>
                      )}
                    </td>
                    <td>
                      <StatusBadge status={item.trang_thai} />
                    </td>
                    <td style={{ fontSize: '0.85rem' }}>
                      {item.reviewed_by ? (
                        <>
                          <div>{item.reviewer_name || `ID #${item.reviewed_by}`}</div>
                          <div style={{ color: 'var(--text-muted, #64748b)', fontSize: '0.78rem' }}>
                            {item.reviewed_at}
                          </div>
                        </>
                      ) : (
                        <span style={{ color: 'var(--text-muted, #94a3b8)' }}>Chưa duyệt</span>
                      )}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      {/* TTS actions */}
                      {isIntern && item.trang_thai === 'ChoDuyet' && (
                        <button
                          type="button"
                          className="btn btn-sm btn-outline-danger"
                          disabled={actionLoadingId === item.id}
                          onClick={() => handleCancel(item.id)}
                        >
                          {actionLoadingId === item.id ? 'Đang hủy...' : 'Hủy đơn'}
                        </button>
                      )}

                      {/* HR/Admin review actions */}
                      {canReview && item.trang_thai === 'ChoDuyet' && (
                        <div style={{ display: 'inline-flex', gap: 6, justifyContent: 'flex-end' }}>
                          <button
                            type="button"
                            className="btn btn-sm btn-success"
                            disabled={actionLoadingId === item.id}
                            onClick={() => handleReview(item.id, 'DaDuyet')}
                          >
                            Duyệt
                          </button>
                          <button
                            type="button"
                            className="btn btn-sm btn-danger"
                            disabled={actionLoadingId === item.id}
                            onClick={() => {
                              setRejectingId(item.id);
                              setRejectReason('');
                            }}
                          >
                            Từ chối
                          </button>
                        </div>
                      )}

                      {item.trang_thai !== 'ChoDuyet' && (
                        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted, #94a3b8)' }}>
                          Đã hoàn tất
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Rejection Reason Modal */}
      {rejectingId && (
        <div className="modal-backdrop" style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div className="card" style={{ width: '100%', maxWidth: 440, padding: 24, borderRadius: 12 }}>
            <h4 style={{ margin: '0 0 12px', fontSize: '1.1rem' }}>Từ chối đơn xin nghỉ phép #{rejectingId}</h4>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-muted, #64748b)', margin: '0 0 16px' }}>
              Vui lòng nhập lý do từ chối để thực tập sinh nắm rõ thông tin:
            </p>
            <textarea
              className="form-control"
              rows={3}
              placeholder="Nhập lý do từ chối..."
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              style={{ marginBottom: 16 }}
              required
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setRejectingId(null)}
                disabled={actionLoadingId === rejectingId}
              >
                Hủy bỏ
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={actionLoadingId === rejectingId || !rejectReason.trim()}
                onClick={() => handleReview(rejectingId, 'TuChoi', rejectReason)}
              >
                {actionLoadingId === rejectingId ? 'Đang xử lý...' : 'Xác nhận từ chối'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
