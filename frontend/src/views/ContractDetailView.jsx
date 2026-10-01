import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, CalendarDays, CheckCircle2, CircleX, Clock3, Download, FileText, Maximize, UploadCloud, UserRound } from 'lucide-react';
import ConfirmDialog from '../components/ConfirmDialog';
import { apiFetch, readJsonResponse } from '../utils/api';

const contractStatus = {
  PENDING_CONFIRMATION: { label: 'Chờ bạn xác nhận', tone: 'warning' },
  CONFIRMED: { label: 'Đã xác nhận', tone: 'success' },
  REJECTED: { label: 'Đã từ chối', tone: 'danger' },
};

const historyPresentation = {
  UPLOADED: { label: 'Đã tải hợp đồng lên', icon: UploadCloud, tone: 'info' },
  CONFIRMED: { label: 'Thực tập sinh đã xác nhận', icon: CheckCircle2, tone: 'success' },
  REJECTED: { label: 'Thực tập sinh đã từ chối', icon: CircleX, tone: 'danger' },
};

function formatDateTime(value) {
  if (!value) return '—';
  const parsed = new Date(String(value).replace(' ', 'T'));
  if (Number.isNaN(parsed.getTime())) return String(value);
  return new Intl.DateTimeFormat('vi-VN', {
    hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit', year: 'numeric',
  }).format(parsed);
}

function formatPeriod(detail) {
  if (!detail?.ngay_bat_dau && !detail?.ngay_ket_thuc) return 'Chưa có thông tin kỳ thực tập';
  return `${detail.ngay_bat_dau || '—'} – ${detail.ngay_ket_thuc || '—'}`;
}

function eventRole(role) {
  if (role === 'ThucTapSinh') return 'TTS';
  return role || 'Nhân sự';
}

export default function ContractDetailView({ contractId, currentUser, onBack, onShowToast }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [errorStatus, setErrorStatus] = useState(null);
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewError, setPreviewError] = useState('');
  const [downloadLoading, setDownloadLoading] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmChecked, setConfirmChecked] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [submitError, setSubmitError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const previewRef = useRef(null);
  const reasonLength = Array.from(reason).length;
  const trimmedReasonLength = Array.from(reason.trim()).length;
  const pending = detail?.trang_thai === 'PENDING_CONFIRMATION';
  const status = contractStatus[detail?.trang_thai] || { label: 'Chưa cập nhật', tone: 'warning' };

  const loadDetail = useCallback(async () => {
    try {
      const response = await apiFetch(`/api/contracts/${contractId}`, { cache: 'no-store' });
      const data = await readJsonResponse(response);
      if (!response.ok) {
        const requestError = new Error(data.detail || `Không thể tải hợp đồng (${response.status}).`);
        requestError.status = response.status;
        throw requestError;
      }
      setDetail(data);
      setError('');
      setErrorStatus(null);
      return data;
    } catch (loadError) {
      setError(loadError.message);
      setErrorStatus(loadError.status || null);
      return null;
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [contractId]);

  const loadPreview = useCallback(async () => {
    try {
      const response = await apiFetch(`/api/contracts/${contractId}/preview`);
      if (!response.ok) {
        const data = await readJsonResponse(response);
        throw new Error(data.detail || 'Không thể mở bản xem trước hợp đồng.');
      }
      const nextUrl = URL.createObjectURL(await response.blob());
      setPreviewUrl(nextUrl);
      setPreviewError('');
    } catch (loadError) {
      setPreviewError(loadError.message);
    }
  }, [contractId]);

  useEffect(() => {
    void Promise.resolve().then(loadDetail);
    void Promise.resolve().then(loadPreview);
  }, [loadDetail, loadPreview]);

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const downloadContract = async () => {
    setDownloadLoading(true);
    try {
      const response = await apiFetch(`/api/contracts/${contractId}/download`);
      if (!response.ok) {
        const data = await readJsonResponse(response);
        throw new Error(data.detail || 'Không thể tải hợp đồng.');
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = detail?.original_file_name || 'hop-dong.pdf';
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
    } catch (downloadError) {
      onShowToast?.(downloadError.message, 'error');
    } finally {
      setDownloadLoading(false);
    }
  };

  const submitDecision = async (decision) => {
    if (submitting) return;
    setSubmitting(true);
    setSubmitError('');
    try {
      const response = await apiFetch(`/api/contracts/${contractId}/${decision === 'CONFIRMED' ? 'confirm' : 'reject'}`, {
        method: 'POST',
        ...(decision === 'REJECTED' ? {
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason }),
        } : {}),
      });
      const data = await readJsonResponse(response);
      if (response.status === 409) {
        setConfirmOpen(false);
        setRejectOpen(false);
        setReason('');
        setRefreshing(true);
        await loadDetail();
        onShowToast?.('Trạng thái hợp đồng đã thay đổi trên hệ thống. Đang làm mới dữ liệu...', 'error');
        return;
      }
      if (!response.ok) throw new Error(data.detail || 'Không thể lưu quyết định hợp đồng.');
      setDetail(data);
      setConfirmOpen(false);
      setRejectOpen(false);
      setConfirmChecked(false);
      setReason('');
      onShowToast?.(
        decision === 'CONFIRMED'
          ? 'Hợp đồng đã được xác nhận thành công!'
          : 'Bạn đã từ chối hợp đồng này.',
      );
    } catch (decisionError) {
      setSubmitError(decisionError.message);
      onShowToast?.(decisionError.message, 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const closeReject = () => {
    if (submitting) return;
    setRejectOpen(false);
    setReason('');
    setSubmitError('');
  };

  const openFullscreen = async () => {
    try {
      if (!previewRef.current?.requestFullscreen) throw new Error('Trình duyệt của bạn không hỗ trợ chế độ toàn màn hình.');
      await previewRef.current.requestFullscreen();
    } catch (fullscreenError) {
      setPreviewError(fullscreenError.message);
    }
  };

  if (loading && !detail) return <div className="workspace-page contract-detail-page">
    <button type="button" className="btn btn-secondary btn-sm contract-back-button" onClick={onBack}><ArrowLeft size={15} />Quay lại hồ sơ</button>
    <div className="contract-detail-skeleton" aria-label="Đang tải chi tiết hợp đồng">
      <div className="workspace-card contract-skeleton-preview" />
      <div className="contract-skeleton-sidebar"><div className="workspace-card" /><div className="workspace-card" /><div className="workspace-card" /></div>
    </div>
  </div>;

  if (error && !detail) return <div className="workspace-page contract-detail-page">
    <button type="button" className="btn btn-secondary btn-sm contract-back-button" onClick={onBack}><ArrowLeft size={15} />Quay lại hồ sơ</button>
    <article className="workspace-card contract-detail-error" role="alert">
      <CircleX size={28} />
      <h2>{errorStatus === 403 ? 'Không có quyền truy cập' : 'Không tìm thấy hợp đồng'}</h2>
      <p>{errorStatus === 403 ? 'Bạn không có quyền truy cập hợp đồng này.' : 'Không tìm thấy hợp đồng thực tập hoặc hợp đồng chưa được khởi tạo.'}</p>
      <button type="button" className="btn btn-secondary" onClick={onBack}>Quay lại hồ sơ</button>
    </article>
  </div>;

  if (!detail) return null;

  return <div className="workspace-page contract-detail-page">
    <button type="button" className="btn btn-secondary btn-sm contract-back-button" onClick={onBack}><ArrowLeft size={15} />Quay lại hồ sơ</button>
    <nav className="contract-breadcrumb" aria-label="Điều hướng">
      <span>Trang chủ</span><span aria-hidden="true">/</span><span>Hồ sơ thực tập</span><span aria-hidden="true">/</span><strong>Chi tiết hợp đồng</strong>
    </nav>
    <header className="workspace-heading contract-detail-heading">
      <div><span className="workspace-eyebrow">HỢP ĐỒNG THỰC TẬP DOANH NGHIỆP</span><h2>{detail.original_file_name}</h2><p>{detail.ten_chuong_trinh || detail.ten_phong_ban || 'Hợp đồng thực tập'}</p></div>
      <span className={`workspace-status is-${status.tone}`}><i />{status.label}</span>
    </header>

    {error && <div className="workspace-error compact" role="alert">{error}</div>}
    <div className="contract-detail-layout">
      <section className="workspace-card contract-preview-card" aria-label="Trình xem hợp đồng PDF">
        <div className="contract-preview-toolbar">
          <div className="contract-preview-file"><span className="workspace-file-icon"><FileText size={17} /></span><strong title={detail.original_file_name}>{detail.original_file_name}</strong></div>
          <div className="contract-preview-actions">
            <button type="button" className="btn btn-secondary btn-sm" disabled={downloadLoading} onClick={() => { void downloadContract(); }}>
              <Download size={14} />{downloadLoading ? 'Đang tải…' : 'Tải file'}
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => { void openFullscreen(); }}>
              <Maximize size={14} />Toàn màn hình
            </button>
          </div>
        </div>
        <div className="contract-preview-frame" ref={previewRef}>
          {previewUrl ? <iframe src={previewUrl} title={`Xem trước ${detail.original_file_name}`} /> : <div className="contract-preview-fallback" role="status">
            <FileText size={32} /><strong>Không thể hiển thị bản xem trước</strong><span>{previewError || 'Đang tải tài liệu…'}</span>
            <button type="button" className="btn btn-primary" disabled={downloadLoading} onClick={() => { void downloadContract(); }}><Download size={16} />Tải hợp đồng PDF để xem</button>
          </div>}
        </div>
        {previewError && previewUrl && <p className="contract-inline-validation" role="alert">{previewError}</p>}
        <p className="contract-preview-hint">Nếu trình duyệt trên thiết bị di động không hỗ trợ xem PDF, hãy tải tệp xuống để mở.</p>
        <button type="button" className="btn btn-secondary contract-preview-download-fallback" disabled={downloadLoading} onClick={() => { void downloadContract(); }}>
          <Download size={15} />Tải hợp đồng xuống để xem PDF
        </button>
      </section>

      <aside className="contract-detail-sidebar">
        <section className="workspace-card contract-summary-card">
          <div className="workspace-section-heading"><div><span className="workspace-eyebrow">THÔNG TIN TÓM TẮT</span><h3>Chi tiết hợp đồng</h3></div><FileText size={19} /></div>
          <dl className="contract-summary-list">
            <div><dt>Mã hợp đồng</dt><dd>HD-{detail.ma_hop_dong}</dd></div>
            <div><dt>Thực tập sinh</dt><dd><UserRound size={14} />{detail.ho_ten || currentUser?.ho_ten || '—'}</dd></div>
            <div><dt>Kỳ thực tập</dt><dd><CalendarDays size={14} />{formatPeriod(detail)}</dd></div>
            <div><dt>Đơn vị</dt><dd>{detail.ten_phong_ban || '—'}</dd></div>
            <div><dt>Ngày tải lên</dt><dd><Clock3 size={14} />{formatDateTime(detail.uploaded_at)}</dd></div>
          </dl>
        </section>

        {pending ? <section className="workspace-card contract-action-card">
          <div className="workspace-section-heading"><div><span className="workspace-eyebrow">HÀNH ĐỘNG CỦA BẠN</span><h3>Xác nhận hợp đồng</h3></div></div>
          <p>Vui lòng đọc kỹ hợp đồng trước khi đưa ra quyết định.</p>
          <button type="button" className="btn btn-success contract-action-primary" onClick={() => {
            setConfirmChecked(false);
            setSubmitError('');
            setConfirmOpen(true);
          }}><CheckCircle2 size={17} />Xác nhận ký kết</button>
          <button type="button" className="btn btn-secondary contract-action-reject" onClick={() => {
            setReason('');
            setSubmitError('');
            setRejectOpen(true);
          }}><CircleX size={17} />Từ chối hợp đồng</button>
        </section> : <section className={`contract-final-banner is-${status.tone}`} role="status">
          {detail.trang_thai === 'CONFIRMED' ? <>
            <CheckCircle2 size={22} />
            <div><strong>Bạn đã xác nhận hợp đồng này</strong><span>Vào lúc {formatDateTime(detail.confirmed_at)}. Bản sao hợp đồng có giá trị lưu hành.</span></div>
            <button type="button" className="btn btn-success btn-sm" disabled={downloadLoading} onClick={() => { void downloadContract(); }}><Download size={14} />Tải PDF</button>
          </> : <>
            <CircleX size={22} />
            <div><strong>Hợp đồng đã bị từ chối</strong><span>Vào lúc {formatDateTime(detail.rejected_at)}. Vui lòng liên hệ HR để được hỗ trợ bản mới.</span>
              {detail.rejection_reason && <blockquote>{detail.rejection_reason}</blockquote>}
            </div>
          </>}
        </section>}

        <section className="workspace-card contract-history-card">
          <div className="workspace-section-heading"><div><span className="workspace-eyebrow">AUDIT TIMELINE</span><h3>Lịch sử xử lý</h3></div><Clock3 size={18} /></div>
          {refreshing && <span className="contract-history-refresh">Đang đồng bộ trạng thái…</span>}
          {detail.history?.length ? <ol className="contract-history-list">
            {detail.history.map((event, index) => {
              const presentation = historyPresentation[event.action] || { label: event.action, icon: Clock3, tone: 'info' };
              const EventIcon = presentation.icon;
              return <li key={`${event.action}-${event.created_at}-${index}`} className={`is-${presentation.tone}`}>
                <span className="contract-history-icon"><EventIcon size={15} /></span>
                <div className="contract-history-content">
                  <strong>{presentation.label}</strong>
                  <span><time dateTime={event.created_at} title={event.created_at}>{formatDateTime(event.created_at)}</time> · <b>{eventRole(event.actor_role)}</b> {event.actor_name}</span>
                  {event.reason && <blockquote>{event.reason}</blockquote>}
                </div>
              </li>;
            })}
          </ol> : <div className="workspace-empty"><Clock3 size={20} /><span>Chưa có lịch sử xử lý.</span></div>}
        </section>
      </aside>
    </div>

    <ConfirmDialog
      open={confirmOpen}
      title="Xác nhận đồng ý hợp đồng thực tập"
      message="Bằng việc xác nhận, bạn cam kết đã đọc, hiểu rõ và đồng ý với tất cả điều khoản trong hợp đồng đính kèm."
      confirmLabel="Xác nhận & đồng ý"
      className="contract-confirm-dialog"
      busy={submitting}
      confirmDisabled={!confirmChecked}
      onConfirm={() => { void submitDecision('CONFIRMED'); }}
      onCancel={() => { setConfirmOpen(false); setConfirmChecked(false); setSubmitError(''); }}
    >
      <div className="contract-confirm-summary"><span>Thực tập sinh: <strong>{detail.ho_ten || currentUser?.ho_ten}</strong></span><span>Mã hợp đồng: <strong>HD-{detail.ma_hop_dong}</strong></span><span>Ngày xác nhận dự kiến: <strong>{formatDateTime(new Date().toISOString())}</strong></span></div>
      <label className="contract-decision-checkbox"><input type="checkbox" checked={confirmChecked} disabled={submitting} onChange={(event) => setConfirmChecked(event.target.checked)} />Tôi đã đọc kỹ và đồng ý với các điều khoản.</label>
      {submitError && <p className="contract-submit-error" role="alert">{submitError}</p>}
    </ConfirmDialog>

    {rejectOpen && <div className="modal-overlay confirm-overlay" onMouseDown={(event) => !submitting && event.target === event.currentTarget && closeReject()}>
      <form className="confirm-dialog contract-reject-dialog" role="alertdialog" aria-modal="true" aria-labelledby="contract-reject-title" onSubmit={(event) => { event.preventDefault(); void submitDecision('REJECTED'); }}>
        <div className="confirm-icon danger"><CircleX size={22} /></div>
        <button className="modal-close-btn confirm-close" type="button" aria-label="Đóng" disabled={submitting} onClick={closeReject}><CircleX size={18} /></button>
        <h3 id="contract-reject-title">Từ chối tiếp nhận hợp đồng</h3>
        <p>Vui lòng nêu lý do cụ thể để HR có thể hỗ trợ điều chỉnh hoặc phản hồi lại bạn.</p>
        <label className="contract-reason-field" htmlFor="contract-rejection-reason">Lý do từ chối</label>
        <textarea
          id="contract-rejection-reason"
          rows="4"
          value={reason}
          disabled={submitting}
          placeholder="Ví dụ: Sai thông tin lương hỗ trợ, sai thời gian bắt đầu thực tập..."
          onChange={(event) => setReason(event.target.value)}
        />
        <div className={`contract-reason-counter${trimmedReasonLength < 10 || reasonLength > 500 ? ' is-invalid' : ''}`} aria-live="polite">{reasonLength}/500 ký tự</div>
        {trimmedReasonLength < 10 && <p className="contract-inline-validation" role="alert">Lý do cần có ít nhất 10 ký tự, không tính khoảng trắng ở đầu và cuối.</p>}
        {reasonLength > 500 && <p className="contract-inline-validation" role="alert">Lý do không được vượt quá 500 ký tự.</p>}
        {submitError && <p className="contract-submit-error" role="alert">{submitError}</p>}
        <div className="confirm-actions">
          <button type="button" className="btn btn-secondary" disabled={submitting} onClick={closeReject}>Đóng</button>
          <button type="submit" className="btn btn-danger-solid" disabled={submitting || trimmedReasonLength < 10 || reasonLength > 500} aria-busy={submitting}>
            {submitting && <span className="contract-spinner" aria-hidden="true" />} {submitting ? 'Đang xử lý…' : 'Gửi lý do từ chối'}
          </button>
        </div>
      </form>
    </div>}
  </div>;
}
