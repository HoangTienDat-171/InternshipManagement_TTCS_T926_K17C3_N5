import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  LifeBuoy,
  Send,
  CheckCircle2,
  XCircle,
  Clock,
  AlertCircle,
  Eye,
  Download,
  Paperclip,
  UploadCloud,
  Trash2,
  Search,
  RefreshCw,
  FileText,
  FileImage,
  File,
  ChevronLeft,
  ChevronRight,
  X,
  MessageSquare,
  ShieldAlert
} from 'lucide-react';
import { apiFetch, readJsonResponse } from '../utils/api';
import ConfirmDialog from '../components/ConfirmDialog';
import './SupportRequestView.css';

const TYPE_OPTIONS = [
  { value: 'CERTIFICATE', label: 'Giấy chứng nhận' },
  { value: 'DOCUMENT', label: 'Tài liệu' },
  { value: 'OTHER', label: 'Khác' },
];

const TYPE_LABELS = {
  CERTIFICATE: 'Giấy chứng nhận',
  DOCUMENT: 'Tài liệu',
  OTHER: 'Khác',
};

const STATUS_LABELS = {
  PENDING: { label: 'Chờ xử lý', tone: 'is-warning', icon: Clock },
  RESOLVED: { label: 'Đã giải quyết', tone: 'is-success', icon: CheckCircle2 },
  REJECTED: { label: 'Đã từ chối', tone: 'is-danger', icon: XCircle },
};

function formatDateTime(val) {
  if (!val) return '—';
  try {
    const d = new Date(val);
    if (isNaN(d.getTime())) return String(val);
    return d.toLocaleString('vi-VN', {
      hour: '2-digit',
      minute: '2-digit',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric'
    });
  } catch {
    return String(val);
  }
}

function formatBytes(bytes) {
  if (!Number.isFinite(Number(bytes)) || Number(bytes) <= 0) return '—';
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function getFileIcon(filename) {
  const ext = (filename || '').split('.').pop()?.toLowerCase();
  if (['png', 'jpg', 'jpeg'].includes(ext)) return FileImage;
  if (['pdf', 'doc', 'docx'].includes(ext)) return FileText;
  return File;
}

export default function SupportRequestView({ currentUser, onShowToast }) {
  const userRole = currentUser?.vai_tro;
  const isIntern = userRole === 'ThucTapSinh';
  const isHR = ['Admin', 'HR'].includes(userRole);
  const isMentor = userRole === 'Mentor';

  // State: List
  const [requests, setRequests] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 10;

  // State: Filters
  const [filterStatus, setFilterStatus] = useState('');
  const [filterType, setFilterType] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  // State: Create Form (Intern)
  const [createType, setCreateType] = useState('CERTIFICATE');
  const [createContent, setCreateContent] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileError, setFileError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef(null);

  // State: Detail / Review Modal
  const [selectedRequest, setSelectedRequest] = useState(null);
  const [modalLoading, setModalLoading] = useState(false);

  // State: HR Response Form
  const [responseText, setResponseText] = useState('');
  const [confirmDialog, setConfirmDialog] = useState({ open: false, action: null });
  const [processingSubmitting, setProcessingSubmitting] = useState(false);

  // Fetch Requests
  const fetchRequests = useCallback(async () => {
    if (!isIntern && !isHR) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('page', String(page));
      params.set('page_size', String(pageSize));
      if (filterStatus) params.set('trang_thai', filterStatus);
      if (filterType) params.set('loai_yeu_cau', filterType);
      if (isHR && searchQuery.trim()) params.set('search', searchQuery.trim());

      const url = isIntern
        ? `/api/support-requests/my?${params.toString()}`
        : `/api/support-requests?${params.toString()}`;

      const res = await apiFetch(url);
      const data = await readJsonResponse(res);

      if (!res.ok) {
        onShowToast?.({ message: data.detail || 'Không thể tải danh sách yêu cầu hỗ trợ.', type: 'error' });
        return;
      }

      setRequests(data.items || []);
      setTotalCount(data.total || 0);
    } catch (err) {
      onShowToast?.({ message: 'Lỗi kết nối máy chủ: ' + err.message, type: 'error' });
    } finally {
      setLoading(false);
    }
  }, [isIntern, isHR, page, pageSize, filterStatus, filterType, searchQuery, onShowToast]);

  useEffect(() => {
    fetchRequests();
  }, [fetchRequests]);

  // Open Request Detail
  const handleOpenDetail = async (req) => {
    setModalLoading(true);
    setSelectedRequest(req);
    setResponseText('');
    try {
      const url = isIntern
        ? `/api/support-requests/my/${req.id}`
        : `/api/support-requests/${req.id}`;
      const res = await apiFetch(url);
      const data = await readJsonResponse(res);
      if (res.ok) {
        setSelectedRequest(data);
      } else {
        onShowToast?.({ message: data.detail || 'Không thể tải chi tiết yêu cầu.', type: 'error' });
      }
    } catch (err) {
      onShowToast?.({ message: 'Lỗi tải chi tiết: ' + err.message, type: 'error' });
    } finally {
      setModalLoading(false);
    }
  };

  // File selection & validation
  const handleFileChange = (file) => {
    setFileError('');
    if (!file) {
      setSelectedFile(null);
      return;
    }
    const maxSizeBytes = 5 * 1024 * 1024;
    if (file.size > maxSizeBytes) {
      setFileError('Kích thước tệp vượt quá 5MB. Vui lòng chọn tệp nhỏ hơn.');
      return;
    }
    const ext = file.name.split('.').pop()?.toLowerCase();
    const allowed = ['pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg'];
    if (!allowed.includes(ext)) {
      setFileError('Định dạng tệp không được hỗ trợ (chỉ chấp nhận PDF, DOC, DOCX, PNG, JPG).');
      return;
    }
    setSelectedFile(file);
  };

  // Submit Create Request (Intern)
  const handleSubmitCreate = async (e) => {
    e.preventDefault();
    if (!createContent.trim()) {
      onShowToast?.({ message: 'Vui lòng nhập nội dung yêu cầu hỗ trợ.', type: 'warning' });
      return;
    }
    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append('loai_yeu_cau', createType);
      formData.append('noi_dung', createContent.trim());
      if (selectedFile) {
        formData.append('file', selectedFile);
      }

      const res = await apiFetch('/api/support-requests', {
        method: 'POST',
        body: formData,
      });
      const data = await readJsonResponse(res);

      if (!res.ok) {
        onShowToast?.({ message: data.detail || 'Không thể gửi yêu cầu hỗ trợ.', type: 'error' });
        return;
      }

      onShowToast?.({ message: 'Gửi yêu cầu hỗ trợ thành công! HR sẽ sớm phản hồi.', type: 'success' });
      setCreateContent('');
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      setPage(1);
      fetchRequests();
    } catch (err) {
      onShowToast?.({ message: 'Lỗi khi gửi yêu cầu: ' + err.message, type: 'error' });
    } finally {
      setSubmitting(false);
    }
  };

  // Attachment Download
  const handleDownloadFile = async (requestId, fileItem) => {
    try {
      const res = await apiFetch(`/api/support-requests/${requestId}/files/${fileItem.id}`);
      if (!res.ok) {
        const data = await readJsonResponse(res);
        onShowToast?.({ message: data.detail || 'Không thể tải tệp đính kèm.', type: 'error' });
        return;
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileItem.original_filename || 'tep_dinh_kem';
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      onShowToast?.({ message: 'Lỗi khi tải tệp: ' + err.message, type: 'error' });
    }
  };

  // HR Confirm Processing
  const handleInitiateProcess = (action) => {
    if (action === 'reject' && !responseText.trim()) {
      onShowToast?.({ message: 'Vui lòng nhập lý do từ chối yêu cầu.', type: 'warning' });
      return;
    }
    setConfirmDialog({
      open: true,
      action,
    });
  };

  // HR Execute Process
  const handleExecuteProcess = async () => {
    const action = confirmDialog.action;
    setConfirmDialog({ open: false, action: null });
    setProcessingSubmitting(true);
    try {
      const endpoint = action === 'resolve'
        ? `/api/support-requests/${selectedRequest.id}/resolve`
        : `/api/support-requests/${selectedRequest.id}/reject`;

      const payload = action === 'resolve'
        ? {
            phan_hoi_hr: responseText.trim() || 'Đã giải quyết yêu cầu hỗ trợ.',
            noi_dung_phan_hoi: responseText.trim() || 'Đã giải quyết yêu cầu hỗ trợ.',
          }
        : {
            ly_do_tu_choi: responseText.trim(),
            noi_dung_phan_hoi: responseText.trim(),
          };

      const res = await apiFetch(endpoint, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await readJsonResponse(res);

      if (!res.ok) {
        if (res.status === 409) {
          onShowToast?.({ message: data.detail || 'Yêu cầu này đã được xử lý bởi nhân sự khác hoặc trạng thái đã thay đổi.', type: 'warning' });
          setSelectedRequest(null);
          fetchRequests();
          return;
        }
        onShowToast?.({ message: data.detail || 'Không thể xử lý yêu cầu.', type: 'error' });
        return;
      }

      const successMsg = action === 'resolve'
        ? 'Đã giải quyết yêu cầu hỗ trợ thành công!'
        : 'Đã từ chối yêu cầu hỗ trợ.';
      onShowToast?.({ message: successMsg, type: 'success' });
      setSelectedRequest(null);
      fetchRequests();
    } catch (err) {
      onShowToast?.({ message: 'Lỗi khi xử lý: ' + err.message, type: 'error' });
    } finally {
      setProcessingSubmitting(false);
    }
  };

  if (isMentor) {
    return (
      <div className="support-page container">
        <div className="support-empty-state">
          <ShieldAlert size={48} color="#ef4444" />
          <h2 style={{ margin: '12px 0 6px', color: 'var(--text-main)' }}>Quyền truy cập bị hạn chế</h2>
          <p>Mentor không có quyền truy cập vào module Yêu cầu hỗ trợ giữa Thực tập sinh và Bộ phận Nhân sự.</p>
        </div>
      </div>
    );
  }

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  return (
    <div className="support-page container">
      {/* Page Header */}
      <div className="support-page-header">
        <div>
          <span className="support-eyebrow">
            <LifeBuoy size={14} /> Dịch vụ hỗ trợ nội bộ
          </span>
          <h1>
            {isIntern ? 'Yêu cầu hỗ trợ của tôi' : 'Quản lý yêu cầu hỗ trợ'}
          </h1>
          <p>
            {isIntern
              ? 'Gửi yêu cầu giải quyết thủ tục, tài liệu, xác nhận thực tập đến bộ phận Nhân sự.'
              : 'Tiếp nhận, xem xét và phản hồi các yêu cầu hỗ trợ từ thực tập sinh trong hệ thống.'}
          </p>
        </div>
        <button
          type="button"
          className="support-refresh-btn"
          disabled={loading}
          onClick={() => { setPage(1); fetchRequests(); }}
        >
          <RefreshCw size={15} className={loading ? 'icon-spin' : ''} />
          Làm mới
        </button>
      </div>

      {/* Intern: Create Request Card */}
      {isIntern && (
        <section className="support-card">
          <div className="support-card-header">
            <div className="support-card-title-group">
              <span className="support-card-icon">
                <Send size={20} />
              </span>
              <div>
                <h2>Gửi yêu cầu hỗ trợ mới</h2>
                <p>Chọn đúng loại yêu cầu và mô tả rõ ràng để HR hỗ trợ nhanh chóng nhất.</p>
              </div>
            </div>
          </div>
          <div className="support-card-body">
            <form className="support-form" onSubmit={handleSubmitCreate}>
              <div className="support-form-grid">
                <div className="support-field">
                  <label htmlFor="support-type">
                    Loại yêu cầu <span className="required">*</span>
                  </label>
                  <select
                    id="support-type"
                    className="support-select"
                    value={createType}
                    onChange={(e) => setCreateType(e.target.value)}
                    disabled={submitting}
                  >
                    {TYPE_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="support-field">
                <label htmlFor="support-content">
                  Nội dung chi tiết <span className="required">*</span>
                </label>
                <textarea
                  id="support-content"
                  className="support-textarea"
                  rows={4}
                  placeholder="Mô tả cụ thể vấn đề hoặc nội dung cần HR hỗ trợ giải quyết..."
                  value={createContent}
                  onChange={(e) => setCreateContent(e.target.value)}
                  disabled={submitting}
                />
              </div>

              <div className="support-field">
                <label>Tệp đính kèm (Tùy chọn)</label>
                <div
                  className={`support-dropzone ${submitting ? 'is-disabled' : ''}`}
                  onClick={() => !submitting && fileInputRef.current?.click()}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      fileInputRef.current?.click();
                    }
                  }}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
                    style={{ display: 'none' }}
                    onChange={(e) => handleFileChange(e.target.files?.[0])}
                    disabled={submitting}
                  />
                  <span className="support-dropzone-icon">
                    <UploadCloud size={22} />
                  </span>
                  <strong>Chọn hoặc kéo thả tệp vào đây</strong>
                  <small>Định dạng: PDF, DOC, DOCX, PNG, JPG (Tối đa 5MB)</small>
                </div>

                {fileError && (
                  <p style={{ color: '#ef4444', fontSize: '12px', margin: '6px 0 0' }}>
                    <AlertCircle size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                    {fileError}
                  </p>
                )}

                {selectedFile && (
                  <div className="support-file-preview">
                    <div className="support-file-info">
                      <Paperclip size={18} color="var(--primary-600)" />
                      <div>
                        <strong>{selectedFile.name}</strong>
                        <small>{formatBytes(selectedFile.size)}</small>
                      </div>
                    </div>
                    <button
                      type="button"
                      className="support-file-remove-btn"
                      title="Gỡ tệp"
                      onClick={() => {
                        setSelectedFile(null);
                        if (fileInputRef.current) fileInputRef.current.value = '';
                      }}
                      disabled={submitting}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                )}
              </div>

              <div className="support-form-actions">
                <button
                  type="submit"
                  className="support-submit-btn"
                  disabled={submitting || !createContent.trim()}
                >
                  <Send size={16} />
                  {submitting ? 'Đang gửi…' : 'Gửi yêu cầu'}
                </button>
              </div>
            </form>
          </div>
        </section>
      )}

      {/* Main List Section */}
      <section className="support-card">
        <div className="support-card-header">
          <div className="support-card-title-group">
            <span className="support-card-icon">
              <MessageSquare size={20} />
            </span>
            <div>
              <h2>{isIntern ? 'Danh sách yêu cầu đã gửi' : 'Hàng đợi yêu cầu hỗ trợ'}</h2>
              <p>Tổng số: {totalCount} yêu cầu</p>
            </div>
          </div>
        </div>

        {/* Filter Toolbar */}
        <div className="support-filter-bar">
          {isHR && (
            <div className="support-search-box">
              <Search size={16} color="var(--text-muted)" />
              <input
                type="text"
                placeholder="Tìm tên hoặc email thực tập sinh…"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setPage(1);
                }}
              />
            </div>
          )}

          <select
            className="support-filter-select"
            value={filterStatus}
            onChange={(e) => {
              setFilterStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="">Tất cả trạng thái</option>
            <option value="PENDING">Chờ xử lý</option>
            <option value="RESOLVED">Đã giải quyết</option>
            <option value="REJECTED">Đã từ chối</option>
          </select>

          <select
            className="support-filter-select"
            value={filterType}
            onChange={(e) => {
              setFilterType(e.target.value);
              setPage(1);
            }}
          >
            <option value="">Tất cả loại yêu cầu</option>
            {TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Table Content */}
        <div className="support-table-container">
          {loading ? (
            <div className="support-empty-state">
              <RefreshCw size={24} className="icon-spin" />
              <p style={{ marginTop: 8 }}>Đang tải danh sách yêu cầu…</p>
            </div>
          ) : requests.length === 0 ? (
            <div className="support-empty-state">
              <LifeBuoy size={36} />
              <p style={{ marginTop: 8 }}>Chưa có yêu cầu hỗ trợ nào phù hợp với bộ lọc.</p>
            </div>
          ) : (
            <table className="support-table">
              <thead>
                <tr>
                  <th>Mã</th>
                  {isHR && <th>Thực tập sinh</th>}
                  <th>Loại</th>
                  <th>Nội dung</th>
                  <th>Tệp</th>
                  <th>Ngày gửi</th>
                  <th>Trạng thái</th>
                  <th style={{ textAlign: 'right' }}>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {requests.map((item) => {
                  const statusMeta = STATUS_LABELS[item.trang_thai] || STATUS_LABELS.PENDING;
                  const StatusIcon = statusMeta.icon;
                  return (
                    <tr key={item.id}>
                      <td style={{ fontWeight: 600 }}>#SR-{item.id}</td>
                      {isHR && (
                        <td>
                          <div>
                            <strong>{item.nguoi_gui?.ho_ten || 'TTS'}</strong>
                            <div style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
                              {item.nguoi_gui?.email}
                            </div>
                          </div>
                        </td>
                      )}
                      <td>
                        <span className="support-type-tag">
                          {TYPE_LABELS[item.loai_yeu_cau] || item.loai_yeu_cau}
                        </span>
                      </td>
                      <td style={{ maxWidth: 260 }}>
                        <div
                          style={{
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                          title={item.noi_dung}
                        >
                          {item.noi_dung}
                        </div>
                      </td>
                      <td>
                        {item.so_luong_tep > 0 || (item.tep_dinh_kem && item.tep_dinh_kem.length > 0) ? (
                          <Paperclip size={16} color="var(--primary-600)" title="Có tệp đính kèm" />
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>—</span>
                        )}
                      </td>
                      <td>{formatDateTime(item.ngay_tao)}</td>
                      <td>
                        <span className={`support-status-badge ${statusMeta.tone}`}>
                          <StatusIcon size={13} />
                          {statusMeta.label}
                        </span>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          type="button"
                          className={`support-action-btn ${isHR && item.trang_thai === 'PENDING' ? 'is-primary' : ''}`}
                          onClick={() => handleOpenDetail(item)}
                        >
                          <Eye size={14} />
                          {isHR && item.trang_thai === 'PENDING' ? 'Xử lý' : 'Chi tiết'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination Footer */}
        {totalCount > 0 && (
          <div className="support-pagination">
            <span>
              Trang {page} / {totalPages} (Tổng {totalCount} yêu cầu)
            </span>
            <div className="support-pagination-buttons">
              <button
                type="button"
                className="support-page-btn"
                disabled={page <= 1 || loading}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                aria-label="Trang trước"
              >
                <ChevronLeft size={16} />
              </button>
              <button
                type="button"
                className="support-page-btn"
                disabled={page >= totalPages || loading}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                aria-label="Trang sau"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Detail & Action Modal */}
      {selectedRequest && (
        <div
          className="support-modal-overlay"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget && !processingSubmitting) {
              setSelectedRequest(null);
            }
          }}
        >
          <div className="support-modal" role="dialog" aria-modal="true">
            <div className="support-modal-header">
              <div className="support-modal-header-info">
                <h3>Chi tiết yêu cầu #SR-{selectedRequest.id}</h3>
                {(() => {
                  const s = STATUS_LABELS[selectedRequest.trang_thai] || STATUS_LABELS.PENDING;
                  const Icon = s.icon;
                  return (
                    <span className={`support-status-badge ${s.tone}`}>
                      <Icon size={13} />
                      {s.label}
                    </span>
                  );
                })()}
              </div>
              <button
                type="button"
                className="support-modal-close-btn"
                onClick={() => setSelectedRequest(null)}
                disabled={processingSubmitting}
                aria-label="Đóng"
              >
                <X size={18} />
              </button>
            </div>

            <div className="support-modal-body">
              {modalLoading ? (
                <div className="support-empty-state">
                  <RefreshCw size={24} className="icon-spin" />
                  <p>Đang tải chi tiết…</p>
                </div>
              ) : (
                <>
                  {/* Sender Info (For HR) */}
                  {isHR && selectedRequest.nguoi_gui && (
                    <div className="support-detail-section">
                      <span className="support-detail-label">Người gửi yêu cầu</span>
                      <div className="support-detail-text" style={{ padding: '10px 14px' }}>
                        <strong>{selectedRequest.nguoi_gui.ho_ten}</strong> ({selectedRequest.nguoi_gui.email})
                        {selectedRequest.nguoi_gui.so_dien_thoai && (
                          <span style={{ color: 'var(--text-muted)' }}> · SĐT: {selectedRequest.nguoi_gui.so_dien_thoai}</span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Metadata */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <div className="support-detail-section">
                      <span className="support-detail-label">Loại yêu cầu</span>
                      <div>
                        <span className="support-type-tag">
                          {TYPE_LABELS[selectedRequest.loai_yeu_cau] || selectedRequest.loai_yeu_cau}
                        </span>
                      </div>
                    </div>
                    <div className="support-detail-section">
                      <span className="support-detail-label">Thời gian gửi</span>
                      <div style={{ fontSize: '13.5px', color: 'var(--text-main)', marginTop: 2 }}>
                        {formatDateTime(selectedRequest.ngay_tao)}
                      </div>
                    </div>
                  </div>

                  {/* Request Content */}
                  <div className="support-detail-section">
                    <span className="support-detail-label">Nội dung yêu cầu</span>
                    <div className="support-detail-text">
                      {selectedRequest.noi_dung}
                    </div>
                  </div>

                  {/* Attachments */}
                  {selectedRequest.tep_dinh_kem && selectedRequest.tep_dinh_kem.length > 0 && (
                    <div className="support-detail-section">
                      <span className="support-detail-label">Tệp đính kèm</span>
                      <div style={{ display: 'grid', gap: 8 }}>
                        {selectedRequest.tep_dinh_kem.map((file) => {
                          const IconComp = getFileIcon(file.original_filename);
                          return (
                            <div key={file.id} className="support-attachment-row">
                              <div className="support-attachment-row-info">
                                <IconComp size={18} color="var(--primary-600)" />
                                <div>
                                  <strong style={{ fontSize: '13px' }}>{file.original_filename}</strong>
                                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                                    {formatBytes(file.file_size)}
                                  </div>
                                </div>
                              </div>
                              <button
                                type="button"
                                className="support-download-btn"
                                onClick={() => handleDownloadFile(selectedRequest.id, file)}
                              >
                                <Download size={14} /> Tải xuống
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* HR Processing / Response Section */}
                  {selectedRequest.trang_thai === 'RESOLVED' && (
                    <div className="support-response-box is-resolved">
                      <div className="support-response-header">
                        <span><CheckCircle2 size={16} style={{ verticalAlign: 'middle', marginRight: 4 }} /> Kết quả xử lý từ Nhân sự</span>
                        {selectedRequest.ngay_xu_ly && (
                          <span style={{ fontWeight: 400, fontSize: '11.5px' }}>
                            {formatDateTime(selectedRequest.ngay_xu_ly)}
                          </span>
                        )}
                      </div>
                      <div className="support-response-body">
                        {selectedRequest.noi_dung_phan_hoi || 'Yêu cầu đã được bộ phận Nhân sự giải quyết thành công.'}
                      </div>
                      {(selectedRequest.nguoi_xu_ly_info || selectedRequest.handler_name || (typeof selectedRequest.nguoi_xu_ly === 'object' && selectedRequest.nguoi_xu_ly?.ho_ten)) && (
                        <div className="support-response-meta">
                          Người xử lý: <strong>{selectedRequest.nguoi_xu_ly_info?.ho_ten || selectedRequest.handler_name || selectedRequest.nguoi_xu_ly?.ho_ten}</strong>
                          {(selectedRequest.nguoi_xu_ly_info?.email || selectedRequest.handler_email || selectedRequest.nguoi_xu_ly?.email) && (
                            <span> ({selectedRequest.nguoi_xu_ly_info?.email || selectedRequest.handler_email || selectedRequest.nguoi_xu_ly?.email})</span>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {selectedRequest.trang_thai === 'REJECTED' && (
                    <div className="support-response-box is-rejected">
                      <div className="support-response-header">
                        <span><XCircle size={16} style={{ verticalAlign: 'middle', marginRight: 4 }} /> Lý do từ chối từ Nhân sự</span>
                        {selectedRequest.ngay_xu_ly && (
                          <span style={{ fontWeight: 400, fontSize: '11.5px' }}>
                            {formatDateTime(selectedRequest.ngay_xu_ly)}
                          </span>
                        )}
                      </div>
                      <div className="support-response-body">
                        {selectedRequest.noi_dung_phan_hoi || 'Yêu cầu không được phê duyệt.'}
                      </div>
                      {(selectedRequest.nguoi_xu_ly_info || selectedRequest.handler_name || (typeof selectedRequest.nguoi_xu_ly === 'object' && selectedRequest.nguoi_xu_ly?.ho_ten)) && (
                        <div className="support-response-meta">
                          Người xử lý: <strong>{selectedRequest.nguoi_xu_ly_info?.ho_ten || selectedRequest.handler_name || selectedRequest.nguoi_xu_ly?.ho_ten}</strong>
                          {(selectedRequest.nguoi_xu_ly_info?.email || selectedRequest.handler_email || selectedRequest.nguoi_xu_ly?.email) && (
                            <span> ({selectedRequest.nguoi_xu_ly_info?.email || selectedRequest.handler_email || selectedRequest.nguoi_xu_ly?.email})</span>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {selectedRequest.trang_thai === 'PENDING' && isIntern && (
                    <div className="support-response-box is-pending">
                      <div className="support-response-header">
                        <span><Clock size={16} style={{ verticalAlign: 'middle', marginRight: 4 }} /> Đang chờ xử lý</span>
                      </div>
                      <div className="support-response-body" style={{ fontSize: '13px' }}>
                        Yêu cầu của bạn đang trong hàng đợi xử lý. Bộ phận Nhân sự sẽ kiểm tra và phản hồi trong thời gian sớm nhất.
                      </div>
                    </div>
                  )}

                  {/* Form for HR to respond if PENDING */}
                  {selectedRequest.trang_thai === 'PENDING' && isHR && (
                    <div className="support-detail-section" style={{ marginTop: 8 }}>
                      <span className="support-detail-label">
                        Phản hồi / Lý do xử lý của Nhân sự
                      </span>
                      <textarea
                        className="support-textarea"
                        rows={3}
                        placeholder="Nhập nội dung phản hồi, kết quả xử lý, hoặc lý do (bắt buộc khi từ chối)…"
                        value={responseText}
                        onChange={(e) => setResponseText(e.target.value)}
                        disabled={processingSubmitting}
                      />
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Modal Actions for HR if PENDING */}
            {selectedRequest.trang_thai === 'PENDING' && isHR && (
              <div className="support-modal-actions">
                <button
                  type="button"
                  className="support-btn-reject"
                  onClick={() => handleInitiateProcess('reject')}
                  disabled={processingSubmitting}
                >
                  <XCircle size={16} /> Từ chối
                </button>
                <button
                  type="button"
                  className="support-btn-resolve"
                  onClick={() => handleInitiateProcess('resolve')}
                  disabled={processingSubmitting}
                >
                  <CheckCircle2 size={16} /> Giải quyết
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Confirmation Dialog for HR */}
      <ConfirmDialog
        open={confirmDialog.open}
        title={confirmDialog.action === 'resolve' ? 'Xác nhận giải quyết yêu cầu' : 'Xác nhận từ chối yêu cầu'}
        message={
          confirmDialog.action === 'resolve'
            ? 'Bạn có chắc chắn muốn đánh dấu yêu cầu này là ĐÃ GIẢI QUYẾT và gửi phản hồi cho thực tập sinh?'
            : 'Bạn có chắc chắn muốn TỪ CHỐI yêu cầu hỗ trợ này kèm theo lý do đã nhập?'
        }
        confirmLabel={confirmDialog.action === 'resolve' ? 'Giải quyết' : 'Từ chối'}
        danger={confirmDialog.action === 'reject'}
        busy={processingSubmitting}
        onConfirm={handleExecuteProcess}
        onCancel={() => setConfirmDialog({ open: false, action: null })}
      />
    </div>
  );
}
