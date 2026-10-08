import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  ArrowRight,
  Calendar,
  CalendarCheck,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  Download,
  Eye,
  File as FileIcon,
  FileImage,
  FileText,
  Inbox,
  Paperclip,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Trash2,
  UploadCloud,
  UserRound,
  X,
  XCircle,
} from 'lucide-react';
import { apiFetch, apiUploadWithProgress, readJsonResponse } from '../utils/api';
import './LeaveManagementView.css';

const statusBadgeMap = {
  ChoDuyet: { label: 'Chờ duyệt', tone: 'warning' },
  DaDuyet: { label: 'Đã duyệt', tone: 'success' },
  TuChoi: { label: 'Từ chối', tone: 'danger' },
  DaHuy: { label: 'Đã hủy', tone: 'neutral' },
};

function StatusBadge({ status }) {
  const meta = statusBadgeMap[status] || { label: status || 'Không rõ', tone: 'neutral' };
  const Icon = meta.tone === 'success' ? CheckCircle2 : meta.tone === 'warning' ? Clock : meta.tone === 'danger' ? XCircle : AlertCircle;
  return <span className={'leave-status-badge is-' + meta.tone}><Icon size={14} aria-hidden="true" />{meta.label}</span>;
}

function getErrorMessage(detail, fallback) {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => typeof item === 'string' ? item : item?.msg || item?.message || '').filter(Boolean);
    if (messages.length) return messages.join(' ');
  }
  if (detail && typeof detail === 'object') return getErrorMessage(detail.detail || detail.message || detail.msg, fallback);
  return fallback;
}

function parseIsoDate(value) {
  if (!value) return null;
  const parts = String(value).slice(0, 10).split('-').map(Number);
  if (parts.length !== 3 || parts.some(Number.isNaN)) return null;
  return new Date(parts[0], parts[1] - 1, parts[2]);
}

function toIsoDate(value) {
  return [value.getFullYear(), String(value.getMonth() + 1).padStart(2, '0'), String(value.getDate()).padStart(2, '0')].join('-');
}

function formatDate(value) {
  const date = parseIsoDate(value);
  if (!date) return '—';
  return [String(date.getDate()).padStart(2, '0'), String(date.getMonth() + 1).padStart(2, '0'), date.getFullYear()].join('/');
}

function formatProgramRange(program) {
  return formatDate(program?.ngay_bat_dau) + ' – ' + formatDate(program?.ngay_ket_thuc);
}

function formatBytes(size) {
  if (!Number.isFinite(Number(size)) || Number(size) < 0) return '—';
  if (Number(size) < 1024 * 1024) return Math.max(1, Math.round(Number(size) / 1024)) + ' KB';
  return (Number(size) / (1024 * 1024)).toLocaleString('vi-VN', { maximumFractionDigits: 1 }) + ' MB';
}

function daysInclusive(start, end) {
  const first = parseIsoDate(start);
  const last = parseIsoDate(end);
  if (!first || !last) return 0;
  const firstUtc = Date.UTC(first.getFullYear(), first.getMonth(), first.getDate());
  const lastUtc = Date.UTC(last.getFullYear(), last.getMonth(), last.getDate());
  return Math.max(0, Math.floor((lastUtc - firstUtc) / 86400000) + 1);
}

function fileIconFor(name, mimeType) {
  const extension = String(name || '').split('.').pop()?.toLowerCase();
  if (String(mimeType || '').startsWith('image/') || ['png', 'jpg', 'jpeg'].includes(extension)) return FileImage;
  if (extension === 'pdf') return FileText;
  if (['doc', 'docx'].includes(extension)) return FileText;
  return FileIcon;
}

function formatDateTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('vi-VN');
}

function initials(name) {
  return String(name || '?').trim().split(/\s+/).slice(-2).map((part) => part.charAt(0)).join('').toUpperCase();
}

function EvidenceUploader({ files, onChange, onError, disabled, progress, error }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const acceptFileList = (fileList) => {
    const accepted = [];
    const errors = [];
    const allowed = new Set(['png', 'jpg', 'jpeg', 'pdf', 'doc', 'docx']);
    Array.from(fileList || []).forEach((file) => {
      const extension = String(file.name.split('.').pop() || '').toLowerCase();
      if (!allowed.has(extension)) {
        errors.push(file.name + ': định dạng tệp không được hỗ trợ.');
      } else if (file.size <= 0 || file.size > 5 * 1024 * 1024) {
        errors.push(file.name + ': dung lượng phải từ 1 byte đến 5 MB.');
      } else if (files.some((item) => item.file.name === file.name && item.file.size === file.size && item.file.lastModified === file.lastModified)
        || accepted.some((item) => item.file.name === file.name && item.file.size === file.size && item.file.lastModified === file.lastModified)) {
        errors.push(file.name + ': tệp này đã được chọn.');
      } else {
        accepted.push({ id: Date.now() + Math.random(), file });
      }
    });
    if (accepted.length) onChange([...files, ...accepted]);
    onError(errors.join(' '));
    if (inputRef.current) inputRef.current.value = '';
  };

  const previewLocalFile = (file) => {
    const url = URL.createObjectURL(file);
    const previewWindow = window.open(url, '_blank', 'noopener,noreferrer');
    if (!previewWindow) URL.revokeObjectURL(url);
    else window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  };

  return (
    <div className="leave-field leave-evidence-field">
      <div className="leave-evidence-label-row">
        <label htmlFor="leave-evidence">Tài liệu minh chứng <span>(Không bắt buộc / Khuyên dùng)</span></label>
        <Paperclip size={16} aria-hidden="true" />
      </div>
      <p className="leave-evidence-help">Tải lên giấy khám bệnh, bệnh án, giấy xác nhận hoặc hình ảnh minh chứng để đơn xin nghỉ phép được phê duyệt nhanh hơn.</p>
      <div
        className={'leave-dropzone' + (dragging ? ' is-dragging' : '') + (disabled ? ' is-disabled' : '')}
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-controls="leave-evidence"
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(event) => { if (!disabled && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); inputRef.current?.click(); } }}
        onDragOver={(event) => { event.preventDefault(); if (!disabled) setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => { event.preventDefault(); setDragging(false); if (!disabled) acceptFileList(event.dataTransfer.files); }}
      >
        <input ref={inputRef} id="leave-evidence" type="file" multiple accept=".png,.jpg,.jpeg,.pdf,.doc,.docx" hidden disabled={disabled} onChange={(event) => acceptFileList(event.target.files)} />
        <span className="leave-dropzone-icon"><UploadCloud size={24} /></span>
        <strong>Kéo thả tệp vào đây hoặc nhấn để chọn tệp từ máy tính</strong>
        <small>Hỗ trợ định dạng: PNG, JPG, JPEG, PDF, DOC, DOCX (Tối đa 5MB/tệp)</small>
      </div>
      {error && <p className="leave-evidence-error" role="alert"><AlertCircle size={14} />{error}</p>}
      {progress !== null && <div className="leave-upload-progress" role="status"><div><span>Đang gửi tài liệu minh chứng</span><strong>{progress}%</strong></div><progress max="100" value={progress} /></div>}
      {files.length > 0 && <div className="leave-evidence-list" aria-label="Tệp minh chứng đã chọn">{files.map(({ id, file }) => {
        const Icon = fileIconFor(file.name, file.type);
        return <div className="leave-evidence-item" key={id}>
          <span className="leave-file-icon"><Icon size={18} /></span>
          <span className="leave-evidence-name"><strong title={file.name}>{file.name}</strong><small>{formatBytes(file.size)} · {String(file.name.split('.').pop() || '').toUpperCase()}</small></span>
          <button type="button" className="leave-icon-button" title="Xem trước tệp" aria-label={'Xem trước ' + file.name} disabled={disabled} onClick={() => previewLocalFile(file)}><Eye size={16} /></button>
          <button type="button" className="leave-icon-button is-danger" title="Xóa tệp" aria-label={'Xóa ' + file.name} disabled={disabled} onClick={() => onChange(files.filter((item) => item.id !== id))}><Trash2 size={16} /></button>
        </div>;
      })}</div>}
    </div>
  );
}

function AttachmentList({ attachments, onOpen }) {
  if (!attachments?.length) return <p className="leave-muted">Không có tài liệu minh chứng đính kèm.</p>;
  return <div className="leave-detail-attachments">{attachments.map((attachment) => {
    const Icon = fileIconFor(attachment.original_filename, attachment.mime_type);
    const canPreview = attachment.mime_type === 'application/pdf' || String(attachment.mime_type || '').startsWith('image/');
    return <div className="leave-detail-file" key={attachment.id}>
      <span className="leave-file-icon"><Icon size={19} /></span>
      <span className="leave-evidence-name"><strong title={attachment.original_filename}>{attachment.original_filename}</strong><small>{formatBytes(attachment.file_size)} · {String(attachment.mime_type || '').split('/').pop()?.toUpperCase()}</small></span>
      <div className="leave-detail-file-actions">
        {canPreview && <button type="button" className="leave-icon-button" title="Xem trước" aria-label={'Xem trước ' + attachment.original_filename} onClick={() => onOpen(attachment, false)}><Eye size={16} /></button>}
        <button type="button" className="leave-icon-button" title="Tải xuống" aria-label={'Tải xuống ' + attachment.original_filename} onClick={() => onOpen(attachment, true)}><Download size={16} /></button>
      </div>
    </div>;
  })}</div>;
}

function ProgramSelect({ programs, selectedId, onChange, disabled }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const selected = programs.find((program) => String(program.ma_ung_tuyen) === String(selectedId));

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => { if (!rootRef.current?.contains(event.target)) setOpen(false); };
    const onKeyDown = (event) => { if (event.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  return (
    <div className="leave-program-select" ref={rootRef}>
      <button id="leave-program" type="button" className="leave-select-trigger" aria-haspopup="listbox" aria-expanded={open} aria-controls="leave-program-options" disabled={disabled} onClick={() => setOpen((value) => !value)}>
        <span className="leave-control-icon"><CalendarDays size={18} /></span>
        <span className="leave-select-value">
          <strong>{selected?.ten_ct || 'Chọn chương trình đang diễn ra'}</strong>
          <small>{selected ? (selected.ma_ct || 'Chương trình thực tập') + ' · ' + formatProgramRange(selected) : 'Đã duyệt và còn hiệu lực hôm nay'}</small>
        </span>
        <ChevronDown className={open ? 'is-open' : ''} size={18} />
      </button>
      {open && (
        <div className="leave-program-menu" id="leave-program-options" role="listbox" aria-label="Chương trình thực tập đang có hiệu lực">
          {programs.map((program) => {
            const isSelected = String(program.ma_ung_tuyen) === String(selectedId);
            return (
              <button type="button" role="option" aria-selected={isSelected} className={'leave-program-option' + (isSelected ? ' is-selected' : '')} key={program.ma_ung_tuyen} onClick={() => { onChange(String(program.ma_ung_tuyen)); setOpen(false); }}>
                <span className="leave-option-icon"><Calendar size={17} /></span>
                <span><strong>{program.ten_ct}</strong><small>{(program.ma_ct || 'Chương trình') + ' · ' + formatProgramRange(program)}</small></span>
                {isSelected && <CheckCircle2 size={17} />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function DatePicker({ id, label, value, minDate, maxDate, disabled, open, onOpenChange, onChange }) {
  const rootRef = useRef(null);
  const [visibleMonth, setVisibleMonth] = useState(() => parseIsoDate(value) || new Date());
  const todayIso = toIsoDate(new Date());

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => { if (!rootRef.current?.contains(event.target)) onOpenChange(false); };
    const onKeyDown = (event) => { if (event.key === 'Escape') onOpenChange(false); };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open, onOpenChange]);

  const firstOfMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), 1);
  const gridStart = new Date(firstOfMonth);
  gridStart.setDate(firstOfMonth.getDate() - ((firstOfMonth.getDay() + 6) % 7));
  const days = Array.from({ length: 42 }, (_, index) => {
    const day = new Date(gridStart);
    day.setDate(gridStart.getDate() + index);
    return day;
  });
  const inBounds = (iso) => (!minDate || iso >= minDate) && (!maxDate || iso <= maxDate);
  const monthLabel = new Intl.DateTimeFormat('vi-VN', { month: 'long', year: 'numeric' }).format(visibleMonth);

  return (
    <div className={'leave-date-field' + (open ? ' is-open' : '')} ref={rootRef}>
      <label htmlFor={id}>{label} <span aria-hidden="true">*</span></label>
      <button id={id} type="button" className="leave-date-trigger" aria-haspopup="dialog" aria-expanded={open} disabled={disabled} onClick={() => { setVisibleMonth(parseIsoDate(value) || new Date()); onOpenChange(!open); }}>
        <CalendarDays size={17} aria-hidden="true" />
        <span className={value ? '' : 'is-placeholder'}>{value ? formatDate(value) : 'DD/MM/YYYY'}</span>
        <ChevronDown className={open ? 'is-open' : ''} size={16} aria-hidden="true" />
      </button>
      {open && (
        <div className="leave-calendar-popover" role="dialog" aria-label={label + ' calendar'}>
          <div className="leave-calendar-heading">
            <button type="button" aria-label="Tháng trước" onClick={() => setVisibleMonth((month) => new Date(month.getFullYear(), month.getMonth() - 1, 1))}><ChevronLeft size={17} /></button>
            <strong>{monthLabel}</strong>
            <button type="button" aria-label="Tháng sau" onClick={() => setVisibleMonth((month) => new Date(month.getFullYear(), month.getMonth() + 1, 1))}><ChevronRight size={17} /></button>
          </div>
          <div className="leave-calendar-grid" role="grid">
            {['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'].map((weekday) => <span className="leave-calendar-weekday" key={weekday}>{weekday}</span>)}
            {days.map((day) => {
              const iso = toIsoDate(day);
              const selected = iso === value;
              const today = iso === todayIso;
              const otherMonth = day.getMonth() !== visibleMonth.getMonth();
              return (
                <button type="button" role="gridcell" key={iso} aria-label={formatDate(iso)} aria-pressed={selected} disabled={!inBounds(iso)} className={['leave-calendar-day', selected ? 'is-selected' : '', today ? 'is-today' : '', otherMonth ? 'is-other-month' : ''].filter(Boolean).join(' ')} onClick={() => { onChange(iso); onOpenChange(false); }}>
                  {day.getDate()}
                </button>
              );
            })}
          </div>
          <div className="leave-calendar-actions">
            <button type="button" className="leave-calendar-text-button" onClick={() => { onChange(''); onOpenChange(false); }}>Xóa ngày</button>
            <button type="button" className="leave-calendar-today-button" disabled={!inBounds(todayIso)} onClick={() => { onChange(todayIso); onOpenChange(false); }}>Hôm nay</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function LeaveManagementView({ currentUser, onShowToast }) {
  const isIntern = currentUser?.vai_tro === 'ThucTapSinh';
  const canReview = ['Admin', 'HR'].includes(currentUser?.vai_tro);
  const [applications, setApplications] = useState([]);
  const [selectedAppId, setSelectedAppId] = useState('');
  const [programsLoading, setProgramsLoading] = useState(isIntern);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [openCalendar, setOpenCalendar] = useState('');
  const [reason, setReason] = useState('');
  const [evidenceFiles, setEvidenceFiles] = useState([]);
  const [evidenceError, setEvidenceError] = useState('');
  const [uploadProgress, setUploadProgress] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [rejectingId, setRejectingId] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [actionLoadingId, setActionLoadingId] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [bulkLoading, setBulkLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [selectedDetail, setSelectedDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const selectedProgram = applications.find((program) => String(program.ma_ung_tuyen) === String(selectedAppId));

  const loadInternContext = useCallback(async () => {
    if (!isIntern) return;
    try {
      const response = await apiFetch('/api/interns/me/leave-programs');
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(getErrorMessage(data?.detail, 'Không thể tải chương trình thực tập.'));
      setFetchError('');
      const eligible = Array.isArray(data) ? data : [];
      setApplications(eligible);
      setSelectedAppId((current) => eligible.some((program) => String(program.ma_ung_tuyen) === String(current)) ? current : String(eligible[0]?.ma_ung_tuyen || ''));
    } catch (error) {
      setFetchError(getErrorMessage(error?.message, 'Không thể tải chương trình thực tập.'));
    } finally {
      setProgramsLoading(false);
    }
  }, [isIntern]);

  const loadRequests = useCallback(async () => {
    try {
      const url = isIntern ? '/api/interns/me/leave-requests' : '/api/leave-requests';
      const response = await apiFetch(url);
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(getErrorMessage(data?.detail, 'Không thể tải danh sách đơn nghỉ phép.'));
      setFetchError('');
      setRequests(Array.isArray(data) ? data : []);
    } catch (error) {
      setFetchError(getErrorMessage(error?.message, 'Không thể tải danh sách đơn nghỉ phép.'));
    } finally {
      setLoading(false);
    }
  }, [isIntern]);

  // Effects initiate network requests; callback state updates follow the awaited responses.
  useEffect(() => { loadInternContext(); }, [loadInternContext]);
  useEffect(() => { loadRequests(); }, [loadRequests]);

  const handleRefresh = () => { setFetchError(''); setLoading(true); if (isIntern) { setProgramsLoading(true); loadInternContext(); } loadRequests(); };
  const handleSelectProgram = (id) => {
    setSelectedAppId(id);
    setStartDate('');
    setEndDate('');
    setOpenCalendar('');
    setFormError('');
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    setFormError('');
    if (!selectedProgram) return setFormError('Vui lòng chọn chương trình đang diễn ra.');
    if (!startDate || !endDate) return setFormError('Vui lòng chọn ngày bắt đầu và ngày kết thúc nghỉ.');
    if (startDate > endDate) return setFormError('Ngày bắt đầu không được sau ngày kết thúc.');
    if (startDate < String(selectedProgram.ngay_bat_dau).slice(0, 10) || endDate > String(selectedProgram.ngay_ket_thuc).slice(0, 10)) return setFormError('Ngày nghỉ phải nằm trong thời gian của chương trình thực tập.');
    if (!reason.trim()) return setFormError('Vui lòng nhập lý do nghỉ phép.');
    setSubmitting(true);
    try {
      let data;
      if (evidenceFiles.length) {
        const formData = new FormData();
        formData.append('ma_ung_tuyen', String(Number(selectedAppId)));
        formData.append('start_date', startDate);
        formData.append('end_date', endDate);
        formData.append('ly_do', reason.trim());
        evidenceFiles.forEach(({ file }) => formData.append('files', file, file.name));
        setUploadProgress(0);
        const response = await apiUploadWithProgress('/api/interns/me/leave-requests', formData, setUploadProgress);
        data = response.data;
        if (!response.ok) throw new Error(getErrorMessage(data?.detail, 'Không thể gửi đơn nghỉ phép.'));
      } else {
        const response = await apiFetch('/api/interns/me/leave-requests', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ma_ung_tuyen: Number(selectedAppId), start_date: startDate, end_date: endDate, ly_do: reason.trim() }),
        });
        data = await readJsonResponse(response);
        if (!response.ok) throw new Error(getErrorMessage(data?.detail, 'Không thể gửi đơn nghỉ phép.'));
      }
      onShowToast?.('Đã gửi đơn nghỉ phép thành công! Đơn đang ở trạng thái Chờ duyệt.');
      setReason('');
      setEvidenceFiles([]);
      setEvidenceError('');
      setStartDate('');
      setEndDate('');
      setLoading(true);
      await loadRequests();
    } catch (error) {
      setFormError(getErrorMessage(error?.message, 'Không thể gửi đơn nghỉ phép. Vui lòng thử lại.'));
    } finally {
      setSubmitting(false);
      setUploadProgress(null);
    }
  };

  const handleCancel = async (requestId) => {
    if (!window.confirm('Bạn có chắc chắn muốn hủy đơn nghỉ phép này không?')) return;
    setActionLoadingId(requestId);
    try {
      const response = await apiFetch('/api/interns/me/leave-requests/' + requestId + '/cancel', { method: 'POST' });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(getErrorMessage(data?.detail, 'Không thể hủy đơn nghỉ phép.'));
      onShowToast?.('Đã hủy đơn nghỉ phép thành công.');
      setLoading(true);
      loadRequests();
    } catch (error) {
      window.alert(getErrorMessage(error?.message, 'Không thể hủy đơn nghỉ phép.'));
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleReview = async (requestId, decision, rejectNote = '') => {
    if (decision === 'TuChoi' && !rejectNote.trim()) return window.alert('Vui lòng nhập lý do từ chối đơn nghỉ phép.');
    setActionLoadingId(requestId);
    try {
      const response = await apiFetch('/api/leave-requests/' + requestId + '/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trang_thai: decision, ly_do_tu_choi: decision === 'TuChoi' ? rejectNote.trim() : null }),
      });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(getErrorMessage(data?.detail, 'Không thể xét duyệt đơn nghỉ phép.'));
      onShowToast?.(decision === 'DaDuyet' ? 'Đã duyệt đơn nghỉ phép.' : 'Đã từ chối đơn nghỉ phép.');
      setRejectingId(null);
      setRejectReason('');
      setSelectedDetail(null);
      setSelectedIds((current) => { const next = new Set(current); next.delete(requestId); return next; });
      setLoading(true);
      loadRequests();
    } catch (error) {
      window.alert(getErrorMessage(error?.message, 'Không thể xét duyệt đơn nghỉ phép.'));
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleOpenDetails = async (requestId) => {
    setSelectedDetail(null);
    setDetailError('');
    setDetailLoading(true);
    try {
      const endpoint = isIntern
        ? '/api/interns/me/leave-requests/' + requestId
        : '/api/leave-requests/' + requestId;
      const response = await apiFetch(endpoint);
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(getErrorMessage(data?.detail, 'Không thể tải chi tiết đơn nghỉ phép.'));
      setSelectedDetail(data);
    } catch (error) {
      setDetailError(getErrorMessage(error?.message, 'Không thể tải chi tiết đơn nghỉ phép.'));
    } finally {
      setDetailLoading(false);
    }
  };

  const handleAttachmentOpen = async (attachment, download) => {
    const requestId = selectedDetail?.id;
    if (!requestId) return;
    const route = isIntern
      ? '/api/interns/me/leave-requests/' + requestId + '/attachments/' + attachment.id
      : '/api/leave-requests/' + requestId + '/attachments/' + attachment.id;
    const previewWindow = download ? null : window.open('', '_blank');
    if (previewWindow) previewWindow.opener = null;
    try {
      const response = await apiFetch(route + (download ? '?download=true' : ''));
      if (!response.ok) {
        const data = await readJsonResponse(response);
        throw new Error(getErrorMessage(data?.detail, 'Không thể mở tài liệu minh chứng.'));
      }
      const blobUrl = URL.createObjectURL(await response.blob());
      if (download) {
        const link = document.createElement('a');
        link.href = blobUrl;
        link.download = attachment.original_filename || 'minh-chung';
        document.body.append(link);
        link.click();
        link.remove();
      } else if (previewWindow) {
        previewWindow.location.href = blobUrl;
      }
      window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
    } catch (error) {
      previewWindow?.close();
      onShowToast?.(getErrorMessage(error?.message, 'Không thể mở tài liệu minh chứng.'));
    }
  };

  const handleBulkApprove = async () => {
    const ids = Array.from(selectedIds).filter((id) => requests.some((item) => item.id === id && item.trang_thai === 'ChoDuyet'));
    if (!ids.length) return;
    setBulkLoading(true);
    const results = await Promise.all(ids.map(async (requestId) => {
      try {
        const response = await apiFetch('/api/leave-requests/' + requestId + '/review', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ trang_thai: 'DaDuyet', ly_do_tu_choi: null }),
        });
        const data = await readJsonResponse(response);
        return { id: requestId, ok: response.ok, error: getErrorMessage(data?.detail, '') };
      } catch (error) {
        return { id: requestId, ok: false, error: getErrorMessage(error?.message, '') };
      }
    }));
    const succeeded = results.filter((result) => result.ok).length;
    const failed = results.filter((result) => !result.ok);
    setSelectedIds(new Set(failed.map((result) => result.id)));
    onShowToast?.(failed.length
      ? `Đã duyệt ${succeeded}/${ids.length} đơn. ${failed.length} đơn chưa xử lý được.`
      : `Đã duyệt ${succeeded} đơn nghỉ phép.`);
    setLoading(true);
    await loadRequests();
    setBulkLoading(false);
  };

  const filterTabs = [
    { val: '', label: 'Tất cả' }, { val: 'ChoDuyet', label: 'Chờ duyệt' }, { val: 'DaDuyet', label: 'Đã duyệt' }, { val: 'TuChoi', label: 'Từ chối' }, { val: 'DaHuy', label: 'Đã hủy' },
  ];
  const statusCounts = useMemo(() => requests.reduce((counts, item) => {
    counts[item.trang_thai] = (counts[item.trang_thai] || 0) + 1;
    return counts;
  }, {}), [requests]);
  const filteredRequests = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase('vi-VN');
    const requestIdQuery = query.replace(/^#/, '');
    return requests.filter((item) => {
      if (statusFilter && item.trang_thai !== statusFilter) return false;
      if (!query) return true;
      return String(item.id).includes(requestIdQuery)
        || String(item.intern_name || '').toLocaleLowerCase('vi-VN').includes(query)
        || String(item.intern_email || '').toLocaleLowerCase('vi-VN').includes(query);
    });
  }, [requests, searchQuery, statusFilter]);
  const pageCount = Math.max(1, Math.ceil(filteredRequests.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const pageItems = filteredRequests.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const pendingPageIds = pageItems.filter((item) => item.trang_thai === 'ChoDuyet').map((item) => item.id);
  const allPendingSelected = pendingPageIds.length > 0 && pendingPageIds.every((id) => selectedIds.has(id));
  const selectedPendingCount = Array.from(selectedIds).filter((id) => requests.some((item) => item.id === id && item.trang_thai === 'ChoDuyet')).length;
  const toggleVisiblePending = () => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allPendingSelected) pendingPageIds.forEach((id) => next.delete(id));
      else pendingPageIds.forEach((id) => next.add(id));
      return next;
    });
  };

  return (
    <main className="workspace-container leave-page">
      <header className="leave-page-header">
        <div>
          <div className="leave-eyebrow"><ShieldCheck size={14} /> QUẢN LÝ NGHỈ PHÉP</div>
          <h1><CalendarCheck size={27} />{isIntern ? 'Đăng ký nghỉ phép' : 'Quản lý đơn nghỉ phép'}</h1>
          <p>{isIntern ? 'Tạo đơn cho chương trình đang diễn ra và theo dõi trạng thái xét duyệt.' : 'Theo dõi, lọc và xử lý đơn nghỉ phép của thực tập sinh.'}</p>
        </div>
        <button type="button" className="leave-refresh-button" onClick={handleRefresh} disabled={loading || programsLoading}><RefreshCw size={16} className={loading || programsLoading ? 'spin' : ''} /> Làm mới</button>
      </header>

      {fetchError && <div className="leave-alert is-danger" role="alert"><AlertCircle size={18} /><span>{fetchError}</span></div>}

      {isIntern && (
        <section className="leave-panel leave-create-panel" aria-labelledby="leave-create-title">
          <div className="leave-panel-heading"><span className="leave-panel-icon"><CalendarDays size={19} /></span><div><h2 id="leave-create-title">Tạo đơn xin nghỉ phép mới</h2><p>Chọn thời gian nghỉ trong chương trình bạn đang tham gia.</p></div></div>
          <form className="leave-form" onSubmit={handleSubmit}>
            {formError && <div className="leave-alert is-danger" role="alert"><AlertCircle size={18} /><span>{formError}</span></div>}
            <div className="leave-field leave-program-field">
              <label htmlFor="leave-program">Chương trình thực tập <span>*</span></label>
              <ProgramSelect programs={applications} selectedId={selectedAppId} onChange={handleSelectProgram} disabled={programsLoading || applications.length === 0} />
              <div className="leave-field-hint">{programsLoading ? 'Đang kiểm tra chương trình đủ điều kiện…' : applications.length ? 'Danh sách chỉ gồm chương trình đã duyệt, đang mở và có hiệu lực hôm nay.' : 'Hiện bạn chưa có chương trình nào đang diễn ra để đăng ký nghỉ phép.'}</div>
            </div>
            {applications.length === 0 && !programsLoading && !fetchError && <div className="leave-alert is-info"><Calendar size={18} /><span>Chương trình đã đóng hoặc chưa đến ngày bắt đầu sẽ không xuất hiện tại đây.</span></div>}

            <div className="leave-date-grid">
              <DatePicker id="leave-start-date" label="Nghỉ từ ngày" value={startDate} minDate={selectedProgram?.ngay_bat_dau ? String(selectedProgram.ngay_bat_dau).slice(0, 10) : ''} maxDate={endDate || (selectedProgram?.ngay_ket_thuc ? String(selectedProgram.ngay_ket_thuc).slice(0, 10) : '')} disabled={!selectedProgram || submitting} open={openCalendar === 'start'} onOpenChange={(value) => setOpenCalendar(value ? 'start' : '')} onChange={(value) => { setStartDate(value); if (endDate && value && value > endDate) setEndDate(''); }} />
              <DatePicker id="leave-end-date" label="Đến ngày" value={endDate} minDate={startDate || (selectedProgram?.ngay_bat_dau ? String(selectedProgram.ngay_bat_dau).slice(0, 10) : '')} maxDate={selectedProgram?.ngay_ket_thuc ? String(selectedProgram.ngay_ket_thuc).slice(0, 10) : ''} disabled={!selectedProgram || submitting} open={openCalendar === 'end'} onOpenChange={(value) => setOpenCalendar(value ? 'end' : '')} onChange={setEndDate} />
            </div>

            <div className="leave-field leave-reason-field">
              <label htmlFor="leave-reason">Lý do nghỉ phép <span>*</span></label>
              <textarea id="leave-reason" placeholder="Mô tả ngắn gọn lý do bạn cần nghỉ…" value={reason} onChange={(event) => setReason(event.target.value)} maxLength={1000} rows={4} required disabled={submitting} />
              <div className="leave-reason-meta"><span>Thông tin này sẽ được gửi đến HR để xét duyệt.</span><span>{reason.length}/1000</span></div>
            </div>
            <EvidenceUploader
              files={evidenceFiles}
              onChange={setEvidenceFiles}
              onError={setEvidenceError}
              disabled={submitting}
              progress={uploadProgress}
              error={evidenceError}
            />
            <div className="leave-form-footer">
              {selectedProgram && <span className="leave-secure-note"><ShieldCheck size={15} /> Thời gian chương trình: {formatProgramRange(selectedProgram)}</span>}
              <button type="submit" className="leave-submit-button" disabled={submitting || programsLoading || !selectedProgram}>{submitting ? <RefreshCw size={17} className="spin" /> : <Send size={17} />}{submitting ? 'Đang gửi đơn…' : 'Gửi đơn nghỉ phép'}{!submitting && <ArrowRight size={16} />}</button>
            </div>
          </form>
        </section>
      )}

      {canReview && (
        <section className="leave-filter-panel" aria-label="Lọc đơn nghỉ phép">
          <label className="leave-search-box"><Search size={17} /><input type="search" value={searchQuery} onChange={(event) => { setSearchQuery(event.target.value); setPage(1); }} placeholder="Tìm theo tên TTS, email hoặc mã đơn…" aria-label="Tìm theo tên thực tập sinh, email hoặc mã đơn" /></label>
          <div className="leave-filter-tabs" role="tablist" aria-label="Trạng thái đơn nghỉ phép">
            {filterTabs.map((tab) => {
              const count = tab.val ? statusCounts[tab.val] || 0 : requests.length;
              return <button key={tab.val || 'all'} type="button" role="tab" aria-selected={statusFilter === tab.val} className={statusFilter === tab.val ? 'is-active' : ''} onClick={() => { setStatusFilter(tab.val); setPage(1); setSelectedIds(new Set()); }}><span>{tab.label}</span><small>{count}</small></button>;
            })}
          </div>
        </section>
      )}

      <section className="leave-panel leave-list-panel" aria-labelledby="leave-list-title">
        <div className="leave-list-heading"><div className="leave-panel-icon"><CalendarDays size={19} /></div><div><h2 id="leave-list-title">{isIntern ? 'Danh sách đơn nghỉ phép của bạn' : 'Danh sách đơn xin nghỉ phép'}</h2><p>{canReview ? filteredRequests.length : requests.length} đơn</p></div></div>
        {loading ? <div className="leave-loading"><RefreshCw size={22} className="spin" />Đang tải danh sách đơn nghỉ phép…</div>
          : (canReview ? filteredRequests.length : requests.length) === 0 ? <div className="leave-empty-state"><span><Inbox size={26} /></span><h3>{canReview && requests.length ? 'Không tìm thấy đơn phù hợp' : 'Chưa có đơn nghỉ phép'}</h3><p>{canReview && requests.length ? 'Thử đổi trạng thái lọc hoặc từ khóa tìm kiếm.' : isIntern ? 'Lịch sử nghỉ phép của bạn sẽ xuất hiện tại đây khi bạn tạo đơn mới.' : 'Các đơn nghỉ phép mới sẽ hiển thị tại đây để HR xét duyệt.'}</p></div>
            : isIntern ? (
              <div className="leave-request-list">{requests.map((item) => (
                <article className="leave-request-card" key={item.id}>
                  <div className="leave-request-card-top"><div><span className="leave-request-program">{item.ten_ct}</span><span className="leave-request-code">{item.ma_ct || 'Chương trình thực tập'}</span></div><StatusBadge status={item.trang_thai} /></div>
                  <div className="leave-request-dates"><CalendarDays size={17} /><strong>{formatDate(item.start_date)}</strong><span>đến</span><strong>{formatDate(item.end_date)}</strong><small>{daysInclusive(item.start_date, item.end_date)} ngày</small></div>
                  <p className="leave-request-reason">{item.ly_do}</p>
                  {!!item.attachment_count && <span className="leave-attachment-count"><Paperclip size={13} />{item.attachment_count} tài liệu minh chứng</span>}
                  {item.ly_do_tu_choi && <div className="leave-rejection-note"><strong>Lý do từ chối:</strong> {item.ly_do_tu_choi}</div>}
                  <div className="leave-request-card-bottom"><span>{item.reviewed_by ? (item.reviewer_name || 'Đã được xét duyệt') + (item.reviewed_at ? ' · ' + formatDateTime(item.reviewed_at) : '') : 'Chưa có kết quả xét duyệt'}</span><div className="leave-request-card-actions"><button type="button" className="leave-details-button" onClick={() => handleOpenDetails(item.id)}><Eye size={14} />Chi tiết</button>{item.trang_thai === 'ChoDuyet' && <button type="button" className="leave-cancel-button" disabled={actionLoadingId === item.id} onClick={() => handleCancel(item.id)}>{actionLoadingId === item.id ? 'Đang hủy…' : 'Hủy đơn'}</button>}</div></div>
                </article>
              ))}</div>
            ) : (
              <>
                {selectedPendingCount > 0 && <div className="leave-bulk-toolbar"><span><CheckCircle2 size={17} />Đã chọn <strong>{selectedPendingCount}</strong> đơn chờ duyệt</span><button type="button" className="leave-approve-button" disabled={bulkLoading} onClick={handleBulkApprove}>{bulkLoading ? <RefreshCw size={14} className="spin" /> : <Check size={15} />}{bulkLoading ? 'Đang duyệt…' : 'Duyệt các đơn đã chọn'}</button><button type="button" className="leave-modal-cancel" disabled={bulkLoading} onClick={() => setSelectedIds(new Set())}>Bỏ chọn</button></div>}
                <div className="leave-table-scroll"><table className="leave-table leave-manager-table">
                  <colgroup><col className="leave-col-intern" /><col className="leave-col-program" /><col className="leave-col-dates" /><col className="leave-col-status" /><col className="leave-col-reviewer" /><col className="leave-col-actions" /></colgroup>
                  <thead><tr><th><div className="leave-intern-heading"><input aria-label="Chọn các đơn chờ duyệt trên trang" type="checkbox" checked={allPendingSelected} onChange={toggleVisiblePending} disabled={!pendingPageIds.length || bulkLoading} /><span>Thực tập sinh</span></div></th><th>Chương trình</th><th>Thời gian nghỉ</th><th className="is-centered">Trạng thái</th><th>Người / thời gian duyệt</th><th className="is-right">Thao tác</th></tr></thead>
                  <tbody>{pageItems.map((item) => (
                    <tr key={item.id}>
                      <td data-label="Thực tập sinh"><div className="leave-intern-cell"><input type="checkbox" aria-label={'Chọn đơn #' + item.id} checked={selectedIds.has(item.id)} disabled={item.trang_thai !== 'ChoDuyet' || bulkLoading} onChange={() => setSelectedIds((current) => { const next = new Set(current); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next; })} /><span className="leave-avatar">{initials(item.intern_name)}</span><span><strong>{item.intern_name}</strong><small>{item.intern_email}</small></span></div></td>
                      <td className="leave-program-cell" data-label="Chương trình"><strong title={item.ten_ct}>{item.ten_ct}</strong><small className="leave-program-code">{item.ma_ct || 'Chương trình thực tập'}</small></td>
                      <td className="leave-date-cell" data-label="Thời gian nghỉ"><span><CalendarDays size={16} />{formatDate(item.start_date)} – {formatDate(item.end_date)}</span><small className="leave-duration-badge">{daysInclusive(item.start_date, item.end_date)} ngày</small></td>
                      <td className="leave-status-cell" data-label="Trạng thái"><StatusBadge status={item.trang_thai} /></td>
                      <td className="leave-reviewer-cell" data-label="Người / thời gian duyệt">{item.reviewed_by ? <><strong>{item.reviewer_name || 'ID #' + item.reviewed_by}</strong><small>{formatDateTime(item.reviewed_at)}</small></> : <span className="leave-muted">Chưa duyệt</span>}</td>
                      <td className="leave-table-actions" data-label="Thao tác"><div className="leave-actions-group"><button type="button" className="leave-details-button" title="Xem lý do & minh chứng" aria-label={'Xem lý do và minh chứng đơn #' + item.id} onClick={() => handleOpenDetails(item.id)}><Eye size={17} /></button>{item.trang_thai === 'ChoDuyet' ? <><button type="button" className="leave-approve-button" disabled={actionLoadingId === item.id || bulkLoading} onClick={() => handleReview(item.id, 'DaDuyet')}>Duyệt</button><button type="button" className="leave-reject-button" disabled={actionLoadingId === item.id || bulkLoading} onClick={() => { setRejectingId(item.id); setRejectReason(''); }}>Từ chối</button></> : null}</div></td>
                    </tr>
                  ))}</tbody>
                </table></div>
                <div className="leave-pagination"><span>Hiển thị {filteredRequests.length ? (currentPage - 1) * pageSize + 1 : 0}–{Math.min(currentPage * pageSize, filteredRequests.length)} trên {filteredRequests.length} đơn</span><label>Số dòng <select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}><option value={10}>10</option><option value={25}>25</option><option value={50}>50</option></select></label><button type="button" aria-label="Trang trước" disabled={currentPage <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={17} /></button><strong>Trang {currentPage} / {pageCount}</strong><button type="button" aria-label="Trang sau" disabled={currentPage >= pageCount} onClick={() => setPage((value) => value + 1)}><ChevronRight size={17} /></button></div>
              </>
            )}
      </section>

      {(detailLoading || detailError || selectedDetail) && (
        <div className="leave-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) { setSelectedDetail(null); setDetailError(''); } }}>
          <section className="leave-details-modal" role="dialog" aria-modal="true" aria-labelledby="leave-details-title">
            {detailLoading ? <div className="leave-loading"><RefreshCw size={22} className="spin" />Đang tải chi tiết đơn…</div>
              : detailError ? <><div className="leave-details-header"><h2 id="leave-details-title">Không thể tải chi tiết đơn</h2><button type="button" className="leave-icon-button" aria-label="Đóng" onClick={() => setDetailError('')}><X size={18} /></button></div><p className="leave-detail-error">{detailError}</p><div className="leave-details-footer"><button type="button" className="leave-modal-cancel" onClick={() => setDetailError('')}>Đóng</button></div></>
                : selectedDetail && <>
                  <div className="leave-details-header"><div><div className="leave-details-title-row"><h2 id="leave-details-title">Chi tiết đơn xin nghỉ phép - #{selectedDetail.id}</h2><StatusBadge status={selectedDetail.trang_thai} /></div><p>{selectedDetail.ten_ct} <span>· {selectedDetail.ma_ct || 'Chương trình thực tập'}</span></p></div><button type="button" className="leave-icon-button" aria-label="Đóng chi tiết" onClick={() => setSelectedDetail(null)}><X size={19} /></button></div>
                  <div className="leave-details-body">
                    <section className="leave-detail-section"><h3><UserRound size={16} />Thông tin thực tập sinh</h3><div className="leave-detail-person"><span className="leave-avatar is-large">{initials(selectedDetail.intern_name || currentUser?.ho_ten)}</span><div><strong>{selectedDetail.intern_name || currentUser?.ho_ten}</strong><span>{selectedDetail.intern_email || currentUser?.email}</span><small>Mã hồ sơ: #{selectedDetail.ma_ho_so || '—'}{selectedDetail.intern_user_id ? ' · Mã tài khoản: #' + selectedDetail.intern_user_id : ''}</small></div></div></section>
                    <section className="leave-detail-section"><h3><CalendarDays size={16} />Thông tin nghỉ phép</h3><div className="leave-detail-date-grid"><div><small>Nghỉ từ ngày</small><strong>{formatDate(selectedDetail.start_date)}</strong></div><div><small>Đến ngày</small><strong>{formatDate(selectedDetail.end_date)}</strong></div><div><small>Tổng thời gian</small><strong>{daysInclusive(selectedDetail.start_date, selectedDetail.end_date)} ngày</strong></div></div></section>
                    <section className="leave-detail-section"><h3><FileText size={16} />Lý do nghỉ phép</h3><p className="leave-detail-reason">{selectedDetail.ly_do || '—'}</p></section>
                    <section className="leave-detail-section"><h3><Paperclip size={16} />Tài liệu minh chứng</h3><AttachmentList attachments={selectedDetail.attachments} onOpen={handleAttachmentOpen} /></section>
                    <section className="leave-detail-section"><h3><ShieldCheck size={16} />Lịch sử phê duyệt</h3>{selectedDetail.reviewed_by ? <div className="leave-review-history"><strong>{selectedDetail.reviewer_name || 'Người duyệt #' + selectedDetail.reviewed_by}</strong><span>{formatDateTime(selectedDetail.reviewed_at)}</span>{selectedDetail.ly_do_tu_choi && <p><strong>Ghi chú từ chối:</strong> {selectedDetail.ly_do_tu_choi}</p>}</div> : <p className="leave-muted">Đơn đang chờ xét duyệt.</p>}</section>
                  </div>
                  <div className="leave-details-footer">{canReview && selectedDetail.trang_thai === 'ChoDuyet' && <><button type="button" className="leave-approve-button" disabled={actionLoadingId === selectedDetail.id} onClick={() => handleReview(selectedDetail.id, 'DaDuyet')}>{actionLoadingId === selectedDetail.id ? 'Đang xử lý…' : <><Check size={15} />Duyệt đơn</>}</button><button type="button" className="leave-reject-button" disabled={actionLoadingId === selectedDetail.id} onClick={() => { setRejectingId(selectedDetail.id); setRejectReason(''); setSelectedDetail(null); }}><XCircle size={15} />Từ chối đơn</button></>}<button type="button" className="leave-modal-cancel" onClick={() => setSelectedDetail(null)}>Đóng</button></div>
                </>}
          </section>
        </div>
      )}

      {rejectingId && <div className="leave-modal-backdrop" role="presentation"><section className="leave-reject-modal" role="dialog" aria-modal="true" aria-labelledby="leave-reject-title"><h2 id="leave-reject-title">Từ chối đơn nghỉ phép #{rejectingId}</h2><p>Nhập lý do để thực tập sinh hiểu kết quả xét duyệt.</p><textarea rows={4} value={rejectReason} onChange={(event) => setRejectReason(event.target.value)} placeholder="Nhập lý do từ chối…" /><div><button type="button" className="leave-modal-cancel" onClick={() => setRejectingId(null)} disabled={actionLoadingId === rejectingId}>Quay lại</button><button type="button" className="leave-reject-button" disabled={actionLoadingId === rejectingId || !rejectReason.trim()} onClick={() => handleReview(rejectingId, 'TuChoi', rejectReason)}>{actionLoadingId === rejectingId ? 'Đang xử lý…' : 'Xác nhận từ chối'}</button></div></section></div>}
    </main>
  );
}
