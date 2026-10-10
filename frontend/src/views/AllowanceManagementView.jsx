import React, { useEffect, useRef, useState } from 'react';
import {
  Wallet,
  Search,
  Plus,
  RefreshCw,
  Eye,
  Pencil,
  X,
  Save,
  CheckCircle2,
  Calendar,
  Info,
  RotateCcw,
  Sparkles,
  ArrowUpDown,
  ChevronDown,
  Clock3,
  MessageCircleWarning,
  FileText,
  UserRound,
  Upload,
  Image as ImageIcon,
  Trash2,
  Check
} from 'lucide-react';
import CustomSelect from '../components/CustomSelect';
import TablePagination from '../components/TablePagination';
import MonthYearPicker from '../components/MonthYearPicker';
import ConfirmDialog from '../components/ConfirmDialog';
import { apiFetch, apiUploadWithProgress, readJsonResponse } from '../utils/api';
import './AllowanceManagementView.css';

const emptyPage = { items: [], total: 0 };
const MAX_REPORT_IMAGES = 5;
const MAX_REPORT_IMAGE_SIZE = 5 * 1024 * 1024;
const ACCEPTED_REPORT_IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp']);

const money = (value) => {
  const [whole, fraction = '00'] = String(value).split('.');
  return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.')}${fraction !== '00' ? ',' + fraction : ''} ₫`;
};

const periodLabel = (value) => `${value.slice(5)}/${value.slice(0, 4)}`;
const timestamp = (value) => value ? new Date(value.replace(' ', 'T') + 'Z').toLocaleString('vi-VN') : '—';

function getInitials(name) {
  if (!name) return 'TTS';
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function formatMoneyPreview(val) {
  if (!val) return '';
  const cleanVal = String(val).trim();
  const num = Number(cleanVal);
  if (Number.isNaN(num) || num < 0) return '';
  return money(cleanVal);
}

function errorMessage(detail) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg || '').filter(Boolean).join('; ');
  return 'Không thể xử lý yêu cầu. Vui lòng thử lại.';
}

async function requestJson(url, options) {
  const response = await apiFetch(url, options);
  const data = await readJsonResponse(response);
  if (!response.ok) throw new Error(errorMessage(data.detail));
  return data;
}

function receiptStatus(record) {
  const code = record?.trang_thai_hien_tai || record?.trang_thai_nhan || 'ChoXacNhan';
  const labels = {
    ChoXacNhan: 'Chờ xác nhận',
    DaNhan: 'Đã nhận',
    ChuaNhanDuoc: 'Chưa nhận được',
    DangXuLy: 'Đang xử lý',
  };
  return { code, label: labels[code] || 'Chờ xác nhận' };
}

function reportProgressLabel(record) {
  if (record?.trang_thai_nhan === 'DaNhan') return '';
  if (record?.latest_report_status === 'DaXuLy') return 'HR đã xử lý · xem phản hồi';
  if (record?.latest_report_status === 'DangXuLy') return 'HR đang xử lý';
  if (record?.report_count > 0) return 'Đang chờ HR tiếp nhận';
  return '';
}

function eventLabel(type) {
  const labels = {
    TaoPhuCap: 'HR tạo khoản phụ cấp',
    CapNhatPhuCap: 'HR cập nhật phụ cấp',
    DaNhan: 'TTS xác nhận đã nhận',
    TTSXacNhanPhanAnh: 'TTS xác nhận nhận phụ cấp, tự đóng phản ánh',
    BaoChuaNhanDuoc: 'TTS báo chưa nhận được',
    BatDauXuLy: 'HR bắt đầu xử lý phản ánh',
    CapNhatTienDoXuLy: 'HR cập nhật tiến độ xử lý',
    CapNhatKetQuaXuLy: 'HR cập nhật kết quả xử lý',
    TTSXacNhanDaXemPhanHoi: 'TTS xác nhận đã xem phản hồi của HR',
  };
  return labels[type] || 'Cập nhật phụ cấp';
}

function ReceiptStatusBadge({ record }) {
  const status = receiptStatus(record);
  return <span className={`allowance-receipt-badge is-${status.code.toLowerCase()}`}>
    {status.code === 'DaNhan' ? <CheckCircle2 size={14} /> : status.code === 'DangXuLy' ? <Clock3 size={14} /> : <MessageCircleWarning size={14} />}
    {status.label}
  </span>;
}

function InternFilterCombobox({ programId, value, onChange }) {
  const root = useRef(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selection, setSelection] = useState(null);
  const [options, setOptions] = useState(emptyPage);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return undefined;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      setLoading(true);
      setError('');
      const params = new URLSearchParams({ search: query.trim(), page: '1', page_size: '50' });
      if (programId) params.set('program_id', programId);
      requestJson(`/api/allowances/interns?${params}`, { signal: controller.signal })
        .then((data) => { if (!controller.signal.aborted) setOptions(data); })
        .catch((err) => { if (!controller.signal.aborted) { setOptions(emptyPage); setError(err.message); } })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 180);
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, [open, query, programId]);

  useEffect(() => {
    if (!open) return undefined;
    const closeOutside = (event) => {
      if (!root.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener('pointerdown', closeOutside, true);
    return () => document.removeEventListener('pointerdown', closeOutside, true);
  }, [open]);

  const selectIntern = (item) => {
    const display = `${item.ho_ten} · TTS #${item.ma_nguoi_dung}`;
    setSelection({ ...item, display });
    onChange?.(item);
    setQuery('');
    setOpen(false);
  };
  const hasSelection = Boolean(value) && String(value) === String(selection?.ma_nguoi_dung || '');

  return (
    <div className="allowance-intern-combobox" ref={root}>
      <div className="allowance-intern-combobox-control">
        <UserRound size={16} aria-hidden="true" />
        <input
          type="text"
          role="combobox"
          aria-label="Lọc theo thực tập sinh"
          aria-expanded={open}
          aria-controls="allowance-intern-options"
          aria-autocomplete="list"
          value={open ? query : hasSelection ? selection.display : ''}
          placeholder="Tìm tên hoặc mã TTS…"
          onFocus={() => { setOpen(true); setQuery(''); }}
          onChange={(event) => { setSelection(null); onChange?.(null); setQuery(event.target.value); setOpen(true); }}
          onKeyDown={(event) => { if (event.key === 'Escape') setOpen(false); }}
        />
        <button type="button" aria-label={hasSelection ? 'Xóa thực tập sinh đã chọn' : 'Mở danh sách thực tập sinh'} onClick={() => { if (hasSelection) { setSelection(null); onChange?.(null); } else setOpen((current) => !current); }}>
          {hasSelection ? <X size={15} /> : <ChevronDown size={16} />}
        </button>
      </div>
      {open && (
        <div className="allowance-intern-options" id="allowance-intern-options" role="listbox" aria-label="Kết quả tìm thực tập sinh">
          {loading ? <div className="allowance-intern-option-message" role="status">Đang tìm thực tập sinh…</div>
            : error ? <div className="allowance-intern-option-message is-error" role="alert">{error}</div>
              : options.items.length ? options.items.map((item) => (
                <button type="button" role="option" aria-selected={String(value || '') === String(item.ma_nguoi_dung)} key={item.ma_nguoi_dung} onClick={() => selectIntern(item)} className="allowance-intern-option">
                  <span className="allowance-intern-option-avatar">{getInitials(item.ho_ten)}</span>
                  <span className="allowance-intern-option-copy">
                    <strong>{item.ho_ten} <small>TTS #{item.ma_nguoi_dung}</small></strong>
                    <span>{item.email}</span>
                    <span>{item.chuong_trinh || 'Chưa có chương trình được duyệt'}</span>
                    {!item.eligible && <em>Chưa có hồ sơ phù hợp để ghi nhận phụ cấp</em>}
                  </span>
                </button>
              )) : <div className="allowance-intern-option-message">Không tìm thấy thực tập sinh phù hợp.</div>}
          {options.total > options.items.length && <div className="allowance-intern-option-message">Nhập tên hoặc mã TTS để thu hẹp {options.total} kết quả.</div>}
        </div>
      )}
    </div>
  );
}

function currentPeriod() {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
}

function EmptyAllowanceIllustration() {
  return (
    <svg width="150" height="120" viewBox="0 0 150 120" fill="none" xmlns="http://www.w3.org/2000/svg" className="allowance-empty-illustration" aria-hidden="true">
      <ellipse cx="75" cy="106" rx="58" ry="8" fill="#e2e8f0" opacity="0.7" />
      <rect x="25" y="32" width="100" height="66" rx="14" fill="url(#wallet-grad)" stroke="#6366f1" strokeWidth="2" />
      <rect x="35" y="22" width="80" height="20" rx="8" fill="#c7d2fe" opacity="0.9" />
      <rect x="44" y="14" width="62" height="16" rx="6" fill="#e0e7ff" opacity="0.8" />
      <rect x="25" y="46" width="100" height="8" fill="#4338ca" opacity="0.12" />
      <path d="M92 52H125V80H92C88.6863 80 86 77.3137 86 74V58C86 54.6863 88.6863 52 92 52Z" fill="#4f46e5" />
      <circle cx="104" cy="66" r="4.5" fill="#fbbf24" stroke="#ffffff" strokeWidth="1.5" />
      <circle cx="36" cy="20" r="3" fill="#818cf8" />
      <circle cx="120" cy="28" r="4" fill="#a5b4fc" opacity="0.8" />
      <path d="M124 16L126 20L130 22L126 24L124 28L122 24L118 22L122 20L124 16Z" fill="#fbbf24" />
      <defs>
        <linearGradient id="wallet-grad" x1="25" y1="32" x2="125" y2="98" gradientUnits="userSpaceOnUse">
          <stop stopColor="#f8fafc" />
          <stop offset="1" stopColor="#eef2ff" />
        </linearGradient>
      </defs>
    </svg>
  );
}

function AllowanceForm({ record, onSaved, onClose }) {
  const [selected, setSelected] = useState(record || null);
  const [form, setForm] = useState({
    ky: record?.ky || currentPeriod(),
    so_tien: record?.so_tien || '',
    ghi_chu: record?.ghi_chu || ''
  });
  const [program, setProgram] = useState('');
  const [eligiblePrograms, setEligiblePrograms] = useState([]);
  const [eligibleProgramsLoading, setEligibleProgramsLoading] = useState(!record);
  const [eligibleProgramsError, setEligibleProgramsError] = useState('');
  const [page, setPage] = useState(1);
  const [options, setOptions] = useState(emptyPage);
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [optionsError, setOptionsError] = useState('');
  const [retry, setRetry] = useState(0);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const submitLock = useRef(false);
  const titleRef = useRef(null);

  useEffect(() => { titleRef.current?.focus(); }, []);

  useEffect(() => {
    if (record) return undefined;
    const controller = new AbortController();
    requestJson('/api/allowances/eligible-programs', { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) {
          setEligiblePrograms(data);
          setEligibleProgramsError('');
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setEligiblePrograms([]);
          setEligibleProgramsError(err.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setEligibleProgramsLoading(false);
      });
    return () => controller.abort();
  }, [record, retry]);

  useEffect(() => {
    if (record) return undefined;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      setOptionsLoading(true);
      setOptionsError('');
      const query = new URLSearchParams({ page: String(page), page_size: '50' });
      if (program) query.set('program_id', program);
      requestJson(`/api/allowances/profiles?${query}`, { signal: controller.signal })
        .then((data) => { if (!controller.signal.aborted) setOptions(data); })
        .catch((err) => { if (!controller.signal.aborted) { setOptions(emptyPage); setOptionsError(err.message); } })
        .finally(() => { if (!controller.signal.aborted) setOptionsLoading(false); });
    }, 150);
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, [record, program, page, retry]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitLock.current) return;
    if (!selected) { setError('Vui lòng chọn hồ sơ tham gia chương trình đã được duyệt.'); return; }
    if (!/^[1-9]\d{3}-(0[1-9]|1[0-2])$/.test(form.ky)) { setError('Kỳ phụ cấp phải có định dạng YYYY-MM hợp lệ.'); return; }
    if (!/^\d{1,13}(\.\d{1,2})?$/.test(form.so_tien)) { setError('Nhập số tiền không âm, tối đa 13 chữ số nguyên và 2 chữ số lẻ.'); return; }
    submitLock.current = true;
    setSaving(true);
    setError('');
    try {
      const payload = { ...form };
      if (!record) payload.ma_ung_tuyen = selected.ma_ung_tuyen;
      await requestJson(record ? `/api/allowances/${record.id}` : '/api/allowances', {
        method: record ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      submitLock.current = false;
      setSaving(false);
    }
  };

  const selectedInPage = options.items.some((item) => item.ma_ung_tuyen === selected?.ma_ung_tuyen);
  const moneyPreview = formatMoneyPreview(form.so_tien);

  return (
    <section className="allowance-card allowance-form-card">
      <div className="allowance-form-header">
        <div className="allowance-form-header-copy">
          <h2 ref={titleRef} tabIndex={-1}>
            {record ? 'Cập nhật phụ cấp' : 'Thêm phụ cấp mới'}
          </h2>
          <span className="allowance-form-header-badge">
            <Sparkles size={13} />
            {record ? `Mã phụ cấp #${record.id}` : 'Biểu mẫu chuẩn'}
          </span>
        </div>
        <button
          type="button"
          className="allowance-modal-close-btn"
          aria-label="Đóng form"
          disabled={saving}
          onClick={onClose}
        >
          <X size={18} />
        </button>
      </div>

      <div className="allowance-form-info-callout" role="note">
        <Info size={18} className="allowance-info-icon" />
        <div>
          Chỉ chọn chương trình đang diễn ra trong thời gian hiệu lực. Có thể cấp nhiều khoản phụ cấp cho cùng một TTS trong một kỳ.
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <fieldset disabled={saving} className="allowance-form-fieldset">
          {!record && (
            <div className="allowance-form-section">
              <div className="allowance-section-header">
                <span className="allowance-section-badge">1</span>
                <h3>Chọn chương trình và thực tập sinh</h3>
              </div>

              <div className="allowance-form-grid">
                <label className="allowance-field">
                  <span className="allowance-field-label">Chương trình (không bắt buộc)</span>
                  <CustomSelect
                    id="allowance-form-program"
                    value={program}
                    disabled={eligibleProgramsLoading}
                    onChange={(e) => {
                      setProgram(e.target.value);
                      setPage(1);
                      setSelected(null);
                      setOptions(emptyPage);
                      setOptionsLoading(true);
                    }}
                  >
                    <option value="">Không lọc theo chương trình</option>
                    {eligiblePrograms.map((item) => (
                      <option key={item.ma_chuong_trinh} value={item.ma_chuong_trinh}>
                        {item.ten_ct} · {item.ma_ct}
                      </option>
                    ))}
                  </CustomSelect>
                </label>

                <label className="allowance-field">
                  <span className="allowance-field-label">
                    Thực tập sinh / mã TTS <span className="allowance-required">*</span>
                  </span>
                  <CustomSelect
                    id="allowance-profile"
                    value={selected?.ma_ung_tuyen || ''}
                    disabled={optionsLoading}
                    onChange={(e) => setSelected(options.items.find((item) => item.ma_ung_tuyen === Number(e.target.value)) || null)}
                  >
                    <option value="">Chọn TTS theo mã số</option>
                    {selected && !selectedInPage && (
                      <option value={selected.ma_ung_tuyen}>
                        TTS #{selected.ma_nguoi_dung} · {selected.ho_ten} · HS #{selected.ma_ho_so} · {selected.ten_ct}
                      </option>
                    )}
                    {options.items.map((item) => (
                      <option key={item.ma_ung_tuyen} value={item.ma_ung_tuyen}>
                        TTS #{item.ma_nguoi_dung} · {item.ho_ten} · HS #{item.ma_ho_so} · {item.ten_ct}
                      </option>
                    ))}
                  </CustomSelect>
                </label>

                {eligibleProgramsError && (
                  <p role="alert" className="allowance-error allowance-full">
                    Không tải được chương trình đang hiệu lực: {eligibleProgramsError}{' '}
                    <button type="button" onClick={() => { setEligibleProgramsLoading(true); setRetry((n) => n + 1); }}>Thử lại</button>
                  </p>
                )}
                {!eligibleProgramsLoading && !eligibleProgramsError && !eligiblePrograms.length && (
                  <p className="allowance-feedback-text allowance-full">Hiện không có chương trình nào đang diễn ra để cấp phụ cấp.</p>
                )}
                {optionsLoading && <p role="status" className="allowance-feedback-text allowance-full">Đang tải hồ sơ…</p>}
                {optionsError && (
                  <p role="alert" className="allowance-error allowance-full">
                    {optionsError} <button type="button" onClick={() => setRetry((n) => n + 1)}>Thử lại</button>
                  </p>
                )}
                {!optionsLoading && !optionsError && !options.total && (
                  <p className="allowance-feedback-text allowance-full">
                    {program ? 'Chương trình này hiện không có TTS với hồ sơ đã duyệt.' : 'Không có TTS nào thuộc chương trình đang hiệu lực.'}
                  </p>
                )}
                {options.total > 50 && (
                  <div className="allowance-option-pages allowance-full">
                    <button type="button" className="btn btn-secondary btn-sm" disabled={optionsLoading || page <= 1} onClick={() => setPage(page - 1)}>
                      Trang trước
                    </button>
                    <span>Trang {page} / {Math.ceil(options.total / 50)} · {options.total} hồ sơ</span>
                    <button type="button" className="btn btn-secondary btn-sm" disabled={optionsLoading || page * 50 >= options.total} onClick={() => setPage(page + 1)}>
                      Trang sau
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}

          {selected && (
            <div className="allowance-profile-card">
              <div className="allowance-profile-left">
                <div className="allowance-profile-avatar">
                  {getInitials(selected.ho_ten)}
                </div>
                <div className="allowance-profile-meta">
                  <div className="allowance-profile-title-row">
                    <strong>{selected.ho_ten}</strong>
                    <span className="allowance-profile-badge">TTS #{selected.ma_nguoi_dung}</span>
                    <span className="allowance-profile-badge">
                      Hồ sơ #{selected.ma_ho_so}
                    </span>
                  </div>
                  <div className="allowance-profile-subtext">
                    {selected.email && <span>{selected.email} · </span>}
                    <span>{selected.ten_ct}</span>
                    {selected.ma_ct && <span className="allowance-profile-code"> ({selected.ma_ct})</span>}
                  </div>
                </div>
              </div>
              <div className="allowance-profile-status">
                <CheckCircle2 size={20} className="allowance-verified-icon" />
                <span>Hợp lệ</span>
              </div>
            </div>
          )}

          <div className="allowance-form-section">
            <div className="allowance-section-header">
              <span className="allowance-section-badge">{record ? '1' : '2'}</span>
              <h3>Thông tin chi tiết phụ cấp</h3>
            </div>

            <div className="allowance-form-grid">
              <label className="allowance-field" htmlFor="allowance-period">
                <span className="allowance-field-label">
                  Kỳ phụ cấp <span className="allowance-required">*</span>
                </span>
                <MonthYearPicker
                  id="allowance-period"
                  value={form.ky}
                  onChange={(val) => setForm({ ...form, ky: val })}
                  placeholder="Chọn kỳ phụ cấp (tháng/năm)"
                />
              </label>

              <label className="allowance-field" htmlFor="allowance-amount">
                <span className="allowance-field-label">
                  Số tiền (VNĐ) <span className="allowance-required">*</span>
                </span>
                <div className="allowance-input-wrap allowance-amount-wrap">
                  <input
                    id="allowance-amount"
                    type="text"
                    inputMode="decimal"
                    required
                    maxLength={16}
                    value={form.so_tien}
                    placeholder="Ví dụ: 1500000"
                    onChange={(e) => setForm({ ...form, so_tien: e.target.value })}
                  />
                  <span className="allowance-currency-suffix">VNĐ</span>
                </div>
                <div className="allowance-amount-helpers">
                  <small className="allowance-help-text">Sử dụng dấu chấm cho phần lẻ, ví dụ 1500000.50.</small>
                  {moneyPreview && (
                    <span className="allowance-money-preview">
                      Xem trước: <strong>{moneyPreview}</strong>
                    </span>
                  )}
                </div>
              </label>

              <label className="allowance-field allowance-full" htmlFor="allowance-note">
                <span className="allowance-field-label">Ghi chú</span>
                <textarea
                  id="allowance-note"
                  rows={3}
                  maxLength={1000}
                  value={form.ghi_chu}
                  placeholder="Thông tin bổ sung cho kỳ phụ cấp…"
                  onChange={(e) => setForm({ ...form, ghi_chu: e.target.value })}
                />
                <div className="allowance-textarea-footer">
                  <small className="allowance-character-count">{form.ghi_chu.length}/1000 ký tự</small>
                </div>
              </label>
            </div>
          </div>
        </fieldset>

        {error && <p role="alert" className="allowance-error">{error}</p>}

        <div className="allowance-form-footer">
          <button type="button" className="btn btn-ghost allowance-cancel-btn" disabled={saving} onClick={onClose}>
            Hủy
          </button>
          <button type="submit" className="btn btn-primary allowance-save-btn" disabled={saving || !selected}>
            <Save size={16} />
            {saving ? 'Đang lưu…' : record ? 'Cập nhật phụ cấp' : 'Lưu phụ cấp'}
          </button>
        </div>
      </form>
    </section>
  );
}

function formatFileSize(value) {
  const bytes = Number(value) || 0;
  return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function LocalEvidencePreview({ file }) {
  const [url] = useState(() => URL.createObjectURL(file));
  useEffect(() => () => URL.revokeObjectURL(url), [url]);
  return <img src={url} alt={`Xem trước ${file.name}`} />;
}

function AllowanceEvidenceCard({ reportId, attachment, onShowToast }) {
  const [previewUrl, setPreviewUrl] = useState('');
  const [error, setError] = useState('');
  const [previewOpen, setPreviewOpen] = useState(false);
  const url = `/api/allowance-reports/${reportId}/attachments/${attachment.id}`;

  useEffect(() => {
    let objectUrl = '';
    const controller = new AbortController();
    apiFetch(url, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error('Không tải được ảnh minh chứng.');
        objectUrl = URL.createObjectURL(await response.blob());
        if (!controller.signal.aborted) setPreviewUrl(objectUrl);
      })
      .catch((err) => { if (!controller.signal.aborted) setError(err.message); });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);

  const download = async () => {
    try {
      const response = await apiFetch(`${url}?download=true`);
      if (!response.ok) throw new Error('Không tải được ảnh minh chứng.');
      const blobUrl = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = attachment.original_filename;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(blobUrl), 30_000);
    } catch (err) {
      onShowToast?.(err.message, 'error');
    }
  };

  return (
    <>
      <div className="allowance-evidence-item">
        <button type="button" className="allowance-evidence-preview" disabled={!previewUrl} onClick={() => setPreviewOpen(true)}>
          {previewUrl ? <img src={previewUrl} alt={`Minh chứng: ${attachment.original_filename}`} /> : <ImageIcon size={20} />}
        </button>
        <div className="allowance-evidence-copy">
          <strong title={attachment.original_filename}>{attachment.original_filename}</strong>
          <small>{formatFileSize(attachment.file_size)} · Ảnh minh chứng</small>
          {error && <small className="allowance-evidence-error">{error}</small>}
        </div>
        <button type="button" className="btn btn-secondary btn-sm" disabled={!previewUrl} onClick={() => setPreviewOpen(true)}>Xem</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={download}>Tải xuống</button>
      </div>
      {previewOpen && previewUrl && (
        <div className="allowance-image-lightbox" role="dialog" aria-modal="true" aria-label="Xem ảnh minh chứng" onClick={() => setPreviewOpen(false)}>
          <button type="button" aria-label="Đóng ảnh" onClick={() => setPreviewOpen(false)}><X size={20} /></button>
          <img src={previewUrl} alt={`Minh chứng: ${attachment.original_filename}`} onClick={(event) => event.stopPropagation()} />
        </div>
      )}
    </>
  );
}

function AllowanceReportCard({ report, onUpdated, onAcknowledged, onShowToast }) {
  const [note, setNote] = useState(report.ghi_chu_xu_ly || '');
  const [saving, setSaving] = useState(false);
  const [acknowledging, setAcknowledging] = useState(false);

  const submit = async (event, nextStatus) => {
    event.preventDefault();
    setSaving(true);
    try {
      const data = await requestJson(`/api/allowances/reports/${report.id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trang_thai_xu_ly: nextStatus, ghi_chu_xu_ly: note }),
      });
      onUpdated(data);
      onShowToast?.('Đã lưu phản ánh và gửi thông báo cập nhật cho TTS.');
    } catch (error) {
      onShowToast?.(error.message || 'Không thể cập nhật phản ánh.', 'error');
    } finally {
      setSaving(false);
    }
  };

  const acknowledge = async () => {
    if (acknowledging) return;
    setAcknowledging(true);
    try {
      const data = await requestJson(`/api/interns/me/allowance-reports/${report.id}/acknowledge`, { method: 'POST' });
      onAcknowledged?.(data);
      onShowToast?.('Đã xác nhận bạn đã xem phản hồi của HR.');
    } catch (error) {
      onShowToast?.(error.message || 'Không thể xác nhận đã xem phản hồi.', 'error');
    } finally {
      setAcknowledging(false);
    }
  };

  return (
    <article className="allowance-report-card">
      <div className="allowance-report-heading">
        <div><strong>Phản ánh #{report.id}</strong><small>{report.nguoi_phan_anh} · {timestamp(report.created_at)}</small></div>
        <span className={`allowance-report-status is-${report.trang_thai_xu_ly.toLowerCase()}`}>
          {report.trang_thai_xu_ly === 'ChoXuLy' ? 'Chờ xử lý' : report.trang_thai_xu_ly === 'DangXuLy' ? 'Đang xử lý' : 'Đã xử lý'}
        </span>
      </div>
      <p className="allowance-report-note">{report.noi_dung}</p>
      {report.attachments?.length > 0 && (
        <section className="allowance-report-evidence" aria-label="Ảnh minh chứng đính kèm">
          <h4><ImageIcon size={15} /> Ảnh minh chứng ({report.attachments.length})</h4>
          {report.attachments.map((attachment) => (
            <AllowanceEvidenceCard key={attachment.id} reportId={report.id} attachment={attachment} onShowToast={onShowToast} />
          ))}
        </section>
      )}
      {report.nguoi_xu_ly && <p className="allowance-report-meta">Cập nhật bởi {report.nguoi_xu_ly} · {timestamp(report.updated_at)}</p>}
      {report.ghi_chu_xu_ly && <p className="allowance-report-resolution"><strong>Phản hồi của HR:</strong> {report.ghi_chu_xu_ly}</p>}
      {onUpdated && report.tts_acknowledged_at && (
        <p className="allowance-report-acknowledged-meta"><CheckCircle2 size={15} /> TTS đã xác nhận xem phản hồi · {timestamp(report.tts_acknowledged_at)}</p>
      )}
      {report.trang_thai_xu_ly === 'DaXuLy' && !onUpdated && (
        <div className="allowance-report-acknowledgment">
          {report.tts_acknowledged_at ? (
            <p><CheckCircle2 size={16} /> Bạn đã xác nhận xem phản hồi · {timestamp(report.tts_acknowledged_at)}</p>
          ) : (
            <>
              <p>HR đã hoàn tất xử lý. Hãy xem ghi chú ở trên, sau đó xác nhận để lưu lại rằng bạn đã nhận được phản hồi.</p>
              <button type="button" className="btn btn-success-soft btn-sm" onClick={acknowledge} disabled={acknowledging}>
                <Check size={15} /> {acknowledging ? 'Đang lưu…' : 'Xác nhận đã xem phản hồi'}
              </button>
            </>
          )}
        </div>
      )}
      {!onUpdated && report.trang_thai_xu_ly !== 'DaXuLy' && (
        <p className="allowance-report-progress-hint">
          {report.trang_thai_xu_ly === 'DangXuLy'
            ? 'HR đã tiếp nhận phản ánh và đang kiểm tra. Bạn sẽ nhận được thông báo khi có cập nhật.'
            : 'Phản ánh đã được gửi và đang chờ HR tiếp nhận.'}
        </p>
      )}
      {onUpdated && (
        <form className="allowance-report-resolution-form" onSubmit={(event) => submit(event, report.trang_thai_xu_ly === 'DaXuLy' ? 'DaXuLy' : 'DangXuLy')}>
          <p className="allowance-report-manager-help" role="status">
            {report.trang_thai_xu_ly === 'DaXuLy'
              ? 'Đã xử lý — TTS đã nhận được kết quả và ghi chú.'
              : report.trang_thai_xu_ly === 'DangXuLy'
                ? 'Đang xử lý — TTS đã được thông báo HR đang kiểm tra phản ánh.'
                : 'Phản ánh đang chờ tiếp nhận. Lưu tiến độ để chuyển sang Đang xử lý và thông báo cho TTS.'}
          </p>
          <label><span>Ghi chú / kết quả gửi cho TTS</span><textarea value={note} maxLength={1000} onChange={(event) => setNote(event.target.value)} placeholder="Ghi rõ nội dung đã kiểm tra, kết quả và bước tiếp theo…" disabled={saving} /></label>
          <div className="allowance-report-form-footer">
            <small>{note.length}/1000</small>
            <button type="submit" className="btn btn-primary btn-sm" disabled={saving}>
              {saving ? 'Đang lưu…' : report.trang_thai_xu_ly === 'DaXuLy' ? 'Cập nhật kết quả cho TTS' : 'Lưu tiến độ & thông báo TTS'}
            </button>
          </div>
        </form>
      )}
    </article>
  );
}

function AllowanceDetails({ recordId, endpoint, canManage, onClose, onRequestReceived, onRequestReport, onChanged, onShowToast, refreshToken }) {
  const dialog = useRef(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);

  useEffect(() => { dialog.current?.showModal(); }, []);

  useEffect(() => {
    const controller = new AbortController();
    requestJson(`${endpoint}/${recordId}`, { signal: controller.signal })
      .then((value) => { if (!controller.signal.aborted) { setData(value); setError(''); } })
      .catch((err) => { if (!controller.signal.aborted) { setData(null); setError(err.message); } });
    return () => controller.abort();
  }, [recordId, endpoint, retry, refreshToken]);

  return (
    <dialog className="allowance-dialog" ref={dialog} onCancel={onClose} onClose={onClose} aria-labelledby="allowance-detail-title">
      <div className="allowance-dialog-header">
        <div className="allowance-dialog-title-group">
          <h2 id="allowance-detail-title">Chi tiết phụ cấp #{recordId}</h2>
          {data && <ReceiptStatusBadge record={data} />}
        </div>
        <button type="button" className="allowance-modal-close-btn" aria-label="Đóng chi tiết" onClick={onClose}>
          <X size={18} />
        </button>
      </div>

      {error ? (
        <p role="alert" className="allowance-error">
          {error} <button type="button" onClick={() => setRetry((n) => n + 1)}>Thử lại</button>
        </p>
      ) : !data ? (
        <div className="allowance-dialog-loading" role="status">
          <RefreshCw size={24} className="animate-spin" />
          <p>Đang tải chi tiết phụ cấp…</p>
        </div>
      ) : (
        <>
          <div className="allowance-detail-hero">
            <div>
              <div className="allowance-detail-period-chip">
                <Calendar size={14} />
                Kỳ {periodLabel(data.ky)}
              </div>
              <span className="allowance-detail-status-note">
                {data.trang_thai_nhan === 'DaNhan'
                  ? `TTS xác nhận lúc ${timestamp(data.xac_nhan_luc)}`
                  : data.latest_report_status === 'DaXuLy' ? 'HR đã xử lý phản ánh — xem phản hồi bên dưới'
                    : data.latest_report_status === 'DangXuLy' ? 'HR đã tiếp nhận và đang xử lý phản ánh'
                      : data.report_count ? 'Phản ánh đã gửi — đang chờ HR tiếp nhận' : 'Đang chờ TTS xác nhận'}
              </span>
            </div>
            <strong className="allowance-detail-hero-amount">{money(data.so_tien)}</strong>
          </div>

          <div className="allowance-detail-user-card">
            <div className="allowance-profile-avatar">
              {getInitials(data.ho_ten)}
            </div>
            <div>
              <strong className="allowance-detail-user-name">{data.ho_ten}</strong>
              <div className="allowance-detail-user-sub">
                <span>{data.email}</span>
                <span> · Hồ sơ #{data.ma_ho_so}</span>
              </div>
              <div className="allowance-detail-program-title">
                {data.ten_ct} <span className="allowance-code-badge">({data.ma_ct})</span>
              </div>
            </div>
          </div>

          <dl className="allowance-details-list">
            <div className="allowance-details-item">
              <dt>Ghi chú</dt>
              <dd className="allowance-note-text">{data.ghi_chu || 'Không có ghi chú.'}</dd>
            </div>
            {data.trang_thai_nhan === 'DaNhan' && (
              <div className="allowance-details-item">
                <dt>Xác nhận đã nhận</dt>
                <dd>{data.nguoi_xac_nhan || `TTS #${data.xac_nhan_boi}`} · {timestamp(data.xac_nhan_luc)}</dd>
              </div>
            )}
            {canManage && (
              <>
                <div className="allowance-details-item">
                  <dt>Người tạo</dt>
                  <dd>{data.nguoi_tao} · <small>{timestamp(data.created_at)}</small></dd>
                </div>
                <div className="allowance-details-item">
                  <dt>Người cập nhật</dt>
                  <dd>{data.nguoi_cap_nhat} · <small>{timestamp(data.updated_at)}</small></dd>
                </div>
              </>
            )}
            {!canManage && (
              <div className="allowance-details-item">
                <dt>Cập nhật lần cuối</dt>
                <dd>{timestamp(data.updated_at)}</dd>
              </div>
            )}
          </dl>

          <section className="allowance-detail-history" aria-label="Lịch sử xác nhận và xử lý">
            <div className="allowance-detail-section-heading"><FileText size={17} /><h3>Phản ánh và xử lý</h3><span>{data.reports?.length || 0}</span></div>
            {data.reports?.length ? data.reports.map((report) => (
              <AllowanceReportCard
                key={`${report.id}-${report.trang_thai_xu_ly}-${report.ghi_chu_xu_ly || ''}-${report.tts_acknowledged_at || ''}`}
                report={report}
                onUpdated={canManage ? (value) => { setData(value); onChanged?.(); } : undefined}
                onAcknowledged={!canManage ? (value) => { setData(value); onChanged?.(); } : undefined}
                onShowToast={onShowToast}
              />
            )) : <p className="allowance-history-empty">Chưa có phản ánh nào cho khoản phụ cấp này.</p>}
            {data.history?.length > 0 && (
              <div className="allowance-event-timeline">
                <h4>Lịch sử cập nhật</h4>
                {data.history.map((event) => (
                  <article className="allowance-event-item" key={event.id}>
                    <span className="allowance-event-dot" />
                    <div><strong>{eventLabel(event.event_type)}</strong><small>{event.actor_name} ({event.actor_role}) · {timestamp(event.created_at)}</small>
                      {event.noi_dung && <p>{event.noi_dung}</p>}
                      {event.so_tien_snapshot && <small>Giá trị tại thời điểm này: {money(event.so_tien_snapshot)} · kỳ {periodLabel(event.ky_snapshot)}</small>}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>

          {!canManage && data.trang_thai_nhan !== 'DaNhan' && (
            <div className="allowance-detail-receipt-actions">
              <p>Hãy xác nhận sau khi đã nhận khoản phụ cấp này. Nếu chưa nhận được, gửi phản ánh để HR kiểm tra.</p>
              <div>
                <button type="button" className="btn btn-success-soft" onClick={() => onRequestReceived?.(data)}>Đã nhận</button>
                <button type="button" className="btn btn-warning-soft" onClick={() => onRequestReport?.(data)}>{data.report_count ? 'Gửi phản ánh mới' : 'Chưa nhận được'}</button>
              </div>
            </div>
          )}
        </>
      )}

      <div className="allowance-dialog-footer">
        <button type="button" className="btn btn-secondary" onClick={onClose}>
          Đóng
        </button>
      </div>
    </dialog>
  );
}

export default function AllowanceManagementView({ currentUser, onShowToast, requestedAllowanceId, onAllowanceOpened }) {
  const canManage = ['HR', 'Admin'].includes(currentUser?.vai_tro);
  const canRead = canManage || currentUser?.vai_tro === 'ThucTapSinh';
  const endpoint = canManage ? '/api/allowances' : '/api/interns/me/allowances';

  const [result, setResult] = useState(emptyPage);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [programs, setPrograms] = useState([]);
  const [programError, setProgramError] = useState('');
  const [filters, setFilters] = useState({ search: '', program_id: '', intern_id: '', ky: '', receipt_status: '' });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [revision, setRevision] = useState(0);
  const [form, setForm] = useState(null);
  const [detailId, setDetailId] = useState(null);
  const [reportInboxOpen, setReportInboxOpen] = useState(false);
  const [reportInbox, setReportInbox] = useState(emptyPage);
  const [reportInboxLoading, setReportInboxLoading] = useState(false);
  const [reportInboxError, setReportInboxError] = useState('');
  const [confirmItem, setConfirmItem] = useState(null);
  const [reportItem, setReportItem] = useState(null);
  const [reportNote, setReportNote] = useState('');
  const [reportFiles, setReportFiles] = useState([]);
  const [reportFileError, setReportFileError] = useState('');
  const [reportUploadProgress, setReportUploadProgress] = useState(null);
  const [receiptBusy, setReceiptBusy] = useState(false);

  const activeDetailId = requestedAllowanceId ? Number(requestedAllowanceId) : detailId;

  useEffect(() => {
    if (!canRead) return undefined;
    const controller = new AbortController();
    requestJson(canManage ? '/api/allowances/programs' : '/api/interns/me/allowance-programs', { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) { setPrograms(data); setProgramError(''); } })
      .catch((err) => { if (!controller.signal.aborted) { setPrograms([]); setProgramError(err.message); } });
    return () => controller.abort();
  }, [canManage, canRead, revision]);

  useEffect(() => {
    if (!canRead) return undefined;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      setLoading(true);
      setError('');
      const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      for (const [key, value] of Object.entries(filters)) {
        if (value && (canManage || key !== 'search')) query.set(key, value);
      }
      requestJson(`${endpoint}?${query}`, { signal: controller.signal })
        .then((data) => {
          if (controller.signal.aborted) return;
          if (page > 1 && page > Math.max(1, Math.ceil(data.total / pageSize))) {
            setPage(Math.max(1, Math.ceil(data.total / pageSize)));
            return;
          }
          setResult(data);
        })
        .catch((err) => {
          if (!controller.signal.aborted) {
            setResult(emptyPage);
            setError(err.message);
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 250);
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, [endpoint, canRead, canManage, filters, page, pageSize, revision]);

  useEffect(() => {
    if (!canManage) return undefined;
    const controller = new AbortController();
    const loadingTimer = window.setTimeout(() => setReportInboxLoading(true), 0);
    requestJson('/api/allowances/reports?page=1&page_size=20', { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) { setReportInbox(data); setReportInboxError(''); } })
      .catch((err) => { if (!controller.signal.aborted) { setReportInbox(emptyPage); setReportInboxError(err.message); } })
      .finally(() => { window.clearTimeout(loadingTimer); if (!controller.signal.aborted) setReportInboxLoading(false); });
    return () => { window.clearTimeout(loadingTimer); controller.abort(); };
  }, [canManage, revision]);

  const changeFilter = (key, value) => {
    setFilters((old) => ({ ...old, [key]: value }));
    setPage(1);
  };

  const handleClearFilters = () => {
    setFilters({ search: '', program_id: '', intern_id: '', ky: '', receipt_status: '' });
    setPage(1);
  };

  const handleConfirmReceived = async () => {
    if (!confirmItem || receiptBusy) return;
    setReceiptBusy(true);
    try {
      await requestJson(`/api/interns/me/allowances/${confirmItem.id}/received`, { method: 'POST' });
      onShowToast?.('Đã ghi nhận xác nhận nhận phụ cấp của bạn.');
      setConfirmItem(null);
      setRevision((value) => value + 1);
    } catch (error) {
      onShowToast?.(error.message || 'Không thể xác nhận khoản phụ cấp.', 'error');
    } finally {
      setReceiptBusy(false);
    }
  };

  const handleReportUnreceived = async (event) => {
    event.preventDefault();
    if (!reportItem || receiptBusy) return;
    setReceiptBusy(true);
    setReportUploadProgress(reportFiles.length ? 0 : null);
    try {
      const body = new FormData();
      body.append('noi_dung', reportNote);
      reportFiles.forEach((file) => body.append('files', file));
      const response = await apiUploadWithProgress(
        `/api/interns/me/allowances/${reportItem.id}/reports`,
        body,
        (progress) => setReportUploadProgress(progress),
      );
      if (!response.ok) throw new Error(errorMessage(response.data?.detail));
      onShowToast?.('Phản ánh và ảnh minh chứng đã được gửi tới HR.');
      setReportItem(null);
      setReportNote('');
      setReportFiles([]);
      setReportFileError('');
      setReportUploadProgress(null);
      setRevision((value) => value + 1);
    } catch (error) {
      onShowToast?.(error.message || 'Không thể gửi phản ánh.', 'error');
    } finally {
      setReceiptBusy(false);
      setReportUploadProgress(null);
    }
  };

  const addReportFiles = (selected) => {
    if (!selected.length) return;
    const combined = [...reportFiles, ...selected];
    if (combined.length > MAX_REPORT_IMAGES) {
      setReportFileError(`Chỉ được đính kèm tối đa ${MAX_REPORT_IMAGES} ảnh.`);
      return;
    }
    const invalidType = combined.find((file) => !ACCEPTED_REPORT_IMAGE_TYPES.has(file.type));
    if (invalidType) {
      setReportFileError('Chỉ hỗ trợ ảnh PNG, JPG, JPEG hoặc WEBP.');
      return;
    }
    const oversized = combined.find((file) => file.size > MAX_REPORT_IMAGE_SIZE);
    if (oversized) {
      setReportFileError(`Ảnh “${oversized.name}” vượt quá 5 MB.`);
      return;
    }
    setReportFiles(combined);
    setReportFileError('');
  };

  const selectReportFiles = (event) => {
    const selected = Array.from(event.target.files || []);
    event.target.value = '';
    addReportFiles(selected);
  };

  const removeReportFile = (index) => {
    setReportFiles((items) => items.filter((_, itemIndex) => itemIndex !== index));
    setReportFileError('');
  };

  const requestReceiptConfirmation = (item) => {
    setDetailId(null);
    onAllowanceOpened?.();
    setConfirmItem(item);
  };

  const requestReceiptReport = (item) => {
    setDetailId(null);
    onAllowanceOpened?.();
    setReportItem(item);
    setReportNote('');
    setReportFiles([]);
    setReportFileError('');
    setReportUploadProgress(null);
  };

  if (!canRead) return <p role="alert">Bạn không có quyền xem phụ cấp.</p>;

  return (
    <div className="allowance-page">
      <header className="allowance-page-heading">
        <div className="allowance-heading-copy">
          <span className="allowance-eyebrow">
            <Wallet size={15} />
            PHỤ CẤP THỰC TẬP
          </span>
          <h1>{canManage ? 'Quản lý phụ cấp' : 'Lịch sử phụ cấp'}</h1>
          <p>
            {canManage
              ? 'Nhập và cập nhật phụ cấp theo hồ sơ, chương trình và kỳ thực tập.'
              : 'Theo dõi các khoản phụ cấp được HR ghi nhận cho từng chương trình của bạn.'}
          </p>
        </div>
        <div className="allowance-heading-actions">
          <button
            type="button"
            className="btn btn-secondary allowance-refresh-btn"
            disabled={loading}
            onClick={() => setRevision((n) => n + 1)}
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            Làm mới
          </button>
          {canManage && (
            <button
              type="button"
              className="btn btn-primary allowance-create-btn"
              onClick={() => setForm({ record: null })}
            >
              <Plus size={17} />
              Thêm phụ cấp
            </button>
          )}
        </div>
      </header>

      {form && canManage && (
        <AllowanceForm
          key={form.record?.id || 'new'}
          record={form.record}
          onClose={() => setForm(null)}
          onSaved={() => {
            setForm(null);
            setRevision((n) => n + 1);
            onShowToast?.('Đã lưu thông tin phụ cấp.');
          }}
        />
      )}

      <section className="allowance-card allowance-filters-card" aria-label="Bộ lọc phụ cấp">
        <div className={`allowance-filters-grid ${canManage ? 'is-manager' : 'is-intern'}`}>
          {canManage && (
            <label className="allowance-filter-field allowance-search-field">
              <span className="allowance-filter-label">Tìm kiếm</span>
              <div className="allowance-input-wrap">
                <Search size={16} className="allowance-field-icon" />
                <input
                  aria-label="Tìm thực tập sinh"
                  type="search"
                  maxLength={100}
                  value={filters.search}
                  placeholder="Tên, email hoặc mã TTS…"
                  onChange={(e) => changeFilter('search', e.target.value)}
                />
              </div>
            </label>
          )}

          <label className="allowance-filter-field">
            <span className="allowance-filter-label">Chương trình</span>
            <CustomSelect
              id="allowance-filter-program"
              value={filters.program_id}
              onChange={(e) => { setFilters((old) => ({ ...old, program_id: e.target.value, intern_id: '' })); setPage(1); }}
            >
              <option value="">Tất cả chương trình</option>
              {programs.map((item) => (
                <option key={item.ma_chuong_trinh} value={item.ma_chuong_trinh}>
                  {item.ten_ct}
                </option>
              ))}
            </CustomSelect>
          </label>

          {canManage && (
            <label className="allowance-filter-field">
              <span className="allowance-filter-label">Thực tập sinh</span>
              <InternFilterCombobox
                programId={filters.program_id}
                value={filters.intern_id}
                onChange={(item) => changeFilter('intern_id', item ? String(item.ma_nguoi_dung) : '')}
              />
            </label>
          )}

          <label className="allowance-filter-field">
            <span className="allowance-filter-label">Kỳ phụ cấp</span>
            <MonthYearPicker
              id="allowance-filter-ky"
              value={filters.ky}
              onChange={(val) => changeFilter('ky', val)}
              placeholder="Chọn kỳ phụ cấp (tháng/năm)"
            />
          </label>

          <div className="allowance-filter-actions">
            <button
              type="button"
              className="btn btn-ghost allowance-clear-btn"
              title="Xóa bộ lọc"
              onClick={handleClearFilters}
            >
              <RotateCcw size={15} />
              Xóa bộ lọc
            </button>
          </div>
        </div>

        {programError && (
          <p className="allowance-error" role="alert">
            Không tải được bộ lọc chương trình: {programError}{' '}
            <button type="button" onClick={() => setRevision((n) => n + 1)}>Thử lại</button>
          </p>
        )}
      </section>

      {canManage && (reportInboxLoading || reportInboxError || reportInbox.total > 0) && (
        <section className={`allowance-report-inbox${reportInboxOpen ? ' is-open' : ''}`} aria-label="Phản ánh phụ cấp cần xử lý">
          <div className="allowance-report-inbox-header">
            <span className="allowance-report-inbox-icon"><MessageCircleWarning size={19} /></span>
            <div><h2>Phản ánh cần xử lý</h2><p>{reportInbox.total} phản ánh đang chờ hoặc đang được HR xử lý</p></div>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setReportInboxOpen((open) => !open)} aria-expanded={reportInboxOpen}>
              {reportInboxOpen ? 'Thu gọn' : 'Xem phản ánh'} <ChevronDown size={15} className={reportInboxOpen ? 'is-rotated' : ''} />
            </button>
          </div>
          {reportInboxOpen && (reportInboxLoading ? <div className="allowance-report-inbox-empty" role="status">Đang tải phản ánh…</div>
            : reportInboxError ? <p className="allowance-error" role="alert">{reportInboxError}</p>
              : !reportInbox.items.length ? <div className="allowance-report-inbox-empty">Hiện không có phản ánh cần xử lý.</div>
                : <div className="allowance-report-inbox-list">{reportInbox.items.map((report) => (
                  <article className="allowance-report-inbox-row" key={report.report_id}>
                    <div className="allowance-report-inbox-person"><span className="allowance-profile-avatar">{getInitials(report.ho_ten)}</span><div><strong>{report.ho_ten}</strong><small>TTS #{report.ma_nguoi_dung} · {report.email}</small></div></div>
                    <div className="allowance-report-inbox-program"><strong>{report.ten_ct}</strong><small>Kỳ {periodLabel(report.ky)} · {money(report.so_tien)}</small></div>
                    <p>{report.noi_dung}</p>
                    <span className={`allowance-report-status is-${report.trang_thai_xu_ly.toLowerCase()}`}>{report.trang_thai_xu_ly === 'DangXuLy' ? 'Đang xử lý' : 'Chờ xử lý'}</span>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => setDetailId(report.allowance_id)}>Mở phụ cấp</button>
                  </article>
                ))}</div>)}
        </section>
      )}

      <div className="allowance-receipt-filter" role="group" aria-label="Lọc trạng thái nhận phụ cấp">
        {[
          ['', 'Tất cả'], ['ChoXacNhan', 'Chờ xác nhận'], ['DaNhan', 'Đã nhận'],
          ['ChuaNhanDuoc', 'Chưa nhận'], ['DangXuLy', 'Đang xử lý'],
        ].map(([value, label]) => <button type="button" key={value || 'all'} className={filters.receipt_status === value ? 'is-active' : ''} aria-pressed={filters.receipt_status === value} onClick={() => changeFilter('receipt_status', value)}>{label}</button>)}
      </div>

      <section className="allowance-card allowance-list-card" aria-busy={loading}>
        <div className="allowance-list-header">
          <div className="allowance-list-title-wrap">
            <h2>{canManage ? 'Danh sách phụ cấp thực tập sinh' : 'Phụ cấp của bạn'}</h2>
            <div className="allowance-list-meta">
              <span className="allowance-badge-count">{result.total} bản ghi</span>
              <span className="allowance-badge-sort">
                <ArrowUpDown size={12} />
                Sắp xếp theo kỳ mới nhất
              </span>
            </div>
          </div>
          <div className="allowance-list-header-actions">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={loading}
              title="Làm mới bảng"
              onClick={() => setRevision((n) => n + 1)}
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              Làm mới
            </button>
          </div>
        </div>

        {loading ? (
          <div role="status" className="allowance-empty-container">
            <RefreshCw size={28} className="animate-spin allowance-accent-icon" />
            <h3>Đang tải phụ cấp…</h3>
          </div>
        ) : error ? (
          <div className="allowance-empty-container">
            <p role="alert" className="allowance-error">{error}</p>
            <button type="button" className="btn btn-secondary" onClick={() => setRevision((n) => n + 1)}>
              Thử lại
            </button>
          </div>
        ) : !result.items.length ? (
          <div className="allowance-empty-container">
            <EmptyAllowanceIllustration />
            <h3>Chưa có thông tin phụ cấp</h3>
            <p>
              {canManage
                ? 'Thêm phụ cấp cho hồ sơ đã duyệt hoặc điều chỉnh bộ lọc tìm kiếm.'
                : 'Phụ cấp do HR nhập sẽ xuất hiện tại đây. Bạn có thể thử đổi bộ lọc.'}
            </p>
            {canManage && (
              <div className="allowance-empty-action">
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => setForm({ record: null })}
                >
                  <Plus size={16} />
                  Tạo phụ cấp mới
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="allowance-table-wrap">
            <table className={`allowance-table ${canManage ? 'is-manager' : 'is-intern'}`}>
              <thead>
                <tr>
                  {canManage && <th>Thực tập sinh</th>}
                  <th>Chương trình</th>
                  <th>Kỳ</th>
                  <th>Số tiền</th>
                  <th>Trạng thái nhận</th>
                  {canManage && <th>Cập nhật</th>}
                  <th className="allowance-actions-cell">Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {result.items.map((item) => (
                  <tr key={item.id}>
                    {canManage && (
                      <td data-label="Thực tập sinh">
                        <strong>{item.ho_ten}</strong>
                        <small>{item.email}</small>
                      </td>
                    )}
                    <td data-label="Chương trình">
                      <strong>{item.ten_ct}</strong>
                      <small>{item.ma_ct} · HS #{item.ma_ho_so}</small>
                    </td>
                    <td data-label="Kỳ">
                      <span className="allowance-period-badge">
                        {periodLabel(item.ky)}
                      </span>
                    </td>
                    <td data-label="Số tiền">
                      <strong className="allowance-money">{money(item.so_tien)}</strong>
                    </td>
                    <td data-label="Trạng thái nhận">
                      <ReceiptStatusBadge record={item} />
                      {reportProgressLabel(item) && <small className="allowance-status-subtext">{item.report_count} phản ánh · {reportProgressLabel(item)}</small>}
                    </td>
                    {canManage && (
                      <td data-label="Cập nhật">
                        <span>{item.nguoi_cap_nhat}</span>
                        <small>{timestamp(item.updated_at)}</small>
                      </td>
                    )}
                    <td data-label="Thao tác" className="allowance-actions-cell">
                      <div className="allowance-row-actions">
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm allowance-action-btn"
                          title="Xem chi tiết"
                          aria-label={`Xem phụ cấp #${item.id}`}
                          onClick={() => setDetailId(item.id)}
                        >
                          <Eye size={16} />
                        </button>
                        {canManage && (
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm allowance-action-btn"
                            title={item.trang_thai_nhan === 'DaNhan' ? 'Khoản đã được TTS xác nhận, đã khóa' : 'Sửa phụ cấp'}
                            aria-label={`Sửa phụ cấp #${item.id}`}
                            disabled={item.trang_thai_nhan === 'DaNhan'}
                            onClick={() => setForm({ record: item })}
                          >
                            <Pencil size={16} />
                          </button>
                        )}
                        {!canManage && item.trang_thai_nhan !== 'DaNhan' && (
                          <>
                            <button type="button" className="btn btn-success-soft btn-sm" onClick={() => setConfirmItem(item)}>Đã nhận</button>
                            <button type="button" className="btn btn-warning-soft btn-sm" onClick={() => requestReceiptReport(item)}>Chưa nhận</button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="allowance-pagination-footer">
          <TablePagination
            page={page}
            pageSize={pageSize}
            totalItems={result.total}
            totalPages={Math.ceil(result.total / pageSize)}
            itemLabel="khoản phụ cấp"
            disabled={loading}
            onPageChange={setPage}
            onPageSizeChange={(value) => { setPageSize(value); setPage(1); }}
          />
        </div>
      </section>

      {activeDetailId && (
        <AllowanceDetails
          key={activeDetailId}
          recordId={activeDetailId}
          endpoint={endpoint}
          canManage={canManage}
          onClose={() => { setDetailId(null); onAllowanceOpened?.(); }}
          onRequestReceived={requestReceiptConfirmation}
          onRequestReport={requestReceiptReport}
          onChanged={() => setRevision((value) => value + 1)}
          onShowToast={onShowToast}
          refreshToken={revision}
        />
      )}

      <ConfirmDialog
        open={Boolean(confirmItem)}
        title="Xác nhận đã nhận phụ cấp"
        message={confirmItem ? `Bạn xác nhận đã nhận khoản phụ cấp ${money(confirmItem.so_tien)} cho kỳ ${periodLabel(confirmItem.ky)}?` : ''}
        confirmLabel="Xác nhận đã nhận"
        busy={receiptBusy}
        onCancel={() => setConfirmItem(null)}
        onConfirm={handleConfirmReceived}
      />
      <ConfirmDialog
        open={Boolean(reportItem)}
        title="Báo chưa nhận được phụ cấp"
        message={reportItem ? `HR sẽ kiểm tra khoản ${money(reportItem.so_tien)} kỳ ${periodLabel(reportItem.ky)}. Bạn có thể đính kèm ảnh biến động số dư để làm minh chứng.` : ''}
        confirmLabel="Gửi phản ánh"
        confirmDisabled={!reportNote.trim() || Boolean(reportFileError)}
        busy={receiptBusy}
        onCancel={() => { setReportItem(null); setReportNote(''); setReportFiles([]); setReportFileError(''); setReportUploadProgress(null); }}
        onConfirm={() => handleReportUnreceived({ preventDefault() {} })}
      >
        <label className="allowance-report-compose-label"><span>Nội dung phản ánh</span><textarea value={reportNote} maxLength={2000} onChange={(event) => setReportNote(event.target.value)} placeholder="Mô tả ngắn gọn tình trạng bạn chưa nhận được phụ cấp…" /><small>{reportNote.length}/2000 ký tự</small></label>
        <div
          className="allowance-report-upload-zone"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => { event.preventDefault(); addReportFiles(Array.from(event.dataTransfer.files || [])); }}
        >
          <Upload size={20} />
          <div><strong>Ảnh minh chứng (không bắt buộc)</strong><small>Kéo ảnh vào đây hoặc chọn từ thiết bị · PNG, JPG, WEBP · Tối đa 5 MB/ảnh, tối đa 5 ảnh</small></div>
          <label className="btn btn-secondary btn-sm">
            Chọn ảnh
            <input type="file" accept="image/png,image/jpeg,image/webp" multiple hidden disabled={receiptBusy} onChange={selectReportFiles} />
          </label>
        </div>
        {reportFileError && <p className="allowance-evidence-error" role="alert">{reportFileError}</p>}
        {reportFiles.length > 0 && (
          <div className="allowance-local-evidence-list" aria-label="Ảnh đã chọn">
            {reportFiles.map((file, index) => (
              <div className="allowance-local-evidence-item" key={`${file.name}-${file.lastModified}-${index}`}>
                <span><LocalEvidencePreview file={file} /></span>
                <div><strong title={file.name}>{file.name}</strong><small>{formatFileSize(file.size)}</small></div>
                <button type="button" aria-label={`Xóa ${file.name}`} title="Xóa ảnh" disabled={receiptBusy} onClick={() => removeReportFile(index)}><Trash2 size={15} /></button>
              </div>
            ))}
          </div>
        )}
        {reportUploadProgress !== null && reportFiles.length > 0 && (
          <div className="allowance-upload-progress" role="status">
            <div><span>Đang tải ảnh minh chứng…</span><span>{reportUploadProgress}%</span></div>
            <progress max="100" value={reportUploadProgress} />
          </div>
        )}
      </ConfirmDialog>
    </div>
  );
}
