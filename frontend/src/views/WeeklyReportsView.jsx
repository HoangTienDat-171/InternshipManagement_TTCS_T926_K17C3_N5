import React, { useCallback, useEffect, useState } from 'react';
import { CalendarDays, Download, FileText, Plus, RefreshCw, UploadCloud, X } from 'lucide-react';
import ConfirmDialog from '../components/ConfirmDialog';
import CustomSelect from '../components/CustomSelect';
import { apiFetch } from '../utils/api';


const EMPTY_FORM = {
  id: null,
  program_id: '',
  week_start: '',
  work_content: '',
  results: '',
  difficulties: '',
  status: 'DRAFT',
};

function mondayFor(date = new Date()) {
  const value = new Date(date);
  const day = value.getDay();
  value.setDate(value.getDate() - (day === 0 ? 6 : day - 1));
  return value.toISOString().slice(0, 10);
}

function formatDate(value, includeTime = false) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('vi-VN', includeTime
    ? { dateStyle: 'short', timeStyle: 'short' }
    : { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(value));
}

async function jsonResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Yêu cầu thất bại (${response.status}).`);
  return data;
}

export default function WeeklyReportsView({ requestedReportId, onReportOpened, onShowToast }) {
  const [reports, setReports] = useState([]);
  const [programs, setPrograms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [programFilter, setProgramFilter] = useState('');
  const [form, setForm] = useState(null);
  const [file, setFile] = useState(null);
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirmSubmit, setConfirmSubmit] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set('status', statusFilter);
      if (programFilter) params.set('program_id', programFilter);
      const [reportData, programData] = await Promise.all([
        apiFetch(`/api/interns/me/weekly-reports${params.size ? `?${params}` : ''}`).then(jsonResponse),
        apiFetch('/api/interns/me/weekly-report-programs').then(jsonResponse),
      ]);
      setReports(reportData);
      setPrograms(programData);
    } catch (loadError) {
      setError(loadError.message || 'Không thể tải báo cáo tuần.');
    } finally {
      setLoading(false);
    }
  }, [programFilter, statusFilter]);

  useEffect(() => {
    const timer = window.setTimeout(load, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    if (!requestedReportId) return;
    apiFetch(`/api/interns/me/weekly-reports/${requestedReportId}`)
      .then(jsonResponse)
      .then((report) => setForm({ ...report, program_id: String(report.program_id), week_start: String(report.week_start).slice(0, 10) }))
      .catch((openError) => setError(openError.message));
  }, [requestedReportId]);

  const selectedProgram = programs.find((program) => String(program.id) === String(form?.program_id));

  const openCreate = () => {
    setForm({ ...EMPTY_FORM, program_id: programs[0]?.id ? String(programs[0].id) : '', week_start: mondayFor() });
    setFile(null);
    setFormError('');
  };

  const openReport = (report) => {
    window.history.pushState(null, '', `/weekly-reports/${report.id}`);
    onReportOpened?.(report.id);
    setForm({ ...report, program_id: String(report.program_id), week_start: String(report.week_start).slice(0, 10) });
    setFile(null);
    setFormError('');
  };

  const closeForm = () => {
    if (busy) return;
    window.history.pushState(null, '', '/weekly-reports');
    setForm(null);
    setFile(null);
    setFormError('');
    setConfirmSubmit(false);
  };

  const persistDraft = async () => {
    if (!form.program_id || !form.week_start) throw new Error('Vui lòng chọn chương trình và tuần báo cáo.');
    const payload = {
      work_content: form.work_content,
      results: form.results,
      difficulties: form.difficulties,
    };
    let saved;
    if (form.id) {
      saved = await apiFetch(`/api/interns/me/weekly-reports/${form.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }).then(jsonResponse);
    } else {
      saved = await apiFetch('/api/interns/me/weekly-reports', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...payload, program_id: Number(form.program_id), week_start: form.week_start }),
      }).then(jsonResponse);
    }
    if (file) {
      const upload = new FormData();
      upload.append('file', file);
      saved = await apiFetch(`/api/interns/me/weekly-reports/${saved.id}/attachment`, {
        method: 'POST', body: upload,
      }).then(jsonResponse);
    }
    return saved;
  };

  const saveDraft = async () => {
    setBusy(true);
    setFormError('');
    try {
      const saved = await persistDraft();
      setForm({ ...saved, program_id: String(saved.program_id), week_start: String(saved.week_start).slice(0, 10) });
      setFile(null);
      onShowToast('Đã lưu bản nháp báo cáo tuần.');
      await load();
    } catch (saveError) {
      setFormError(saveError.message);
      if (/đã nộp/i.test(saveError.message)) await load();
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    setBusy(true);
    setFormError('');
    try {
      const saved = await persistDraft();
      const submitted = await apiFetch(`/api/interns/me/weekly-reports/${saved.id}/submit`, { method: 'POST' }).then(jsonResponse);
      setForm({ ...submitted, program_id: String(submitted.program_id), week_start: String(submitted.week_start).slice(0, 10) });
      setFile(null);
      setConfirmSubmit(false);
      onShowToast('Đã nộp báo cáo tuần thành công.');
      await load();
    } catch (submitError) {
      setConfirmSubmit(false);
      setFormError(submitError.message);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const downloadAttachment = async () => {
    setBusy(true);
    setFormError('');
    try {
      const response = await apiFetch(`/api/interns/me/weekly-reports/${form.id}/attachment`);
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'Không thể tải tệp đính kèm.');
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = form.attachment_original_name || 'bao-cao-tuan';
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (downloadError) {
      setFormError(downloadError.message);
    } finally {
      setBusy(false);
    }
  };

  const readOnly = form?.status === 'SUBMITTED';

  return <section className="weekly-reports-page">
    <header className="weekly-reports-header">
      <div><p>BÁO CÁO TIẾN ĐỘ</p><h2>Báo cáo tuần</h2><span>Theo dõi và nộp báo cáo tiến độ thực tập hàng tuần.</span></div>
      <button type="button" className="btn btn-primary" onClick={openCreate} disabled={!programs.length}><Plus size={17} />Tạo báo cáo</button>
    </header>

    <div className="weekly-report-filters">
      <CustomSelect value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
        <option value="">Trạng thái: Tất cả</option><option value="DRAFT">Bản nháp</option><option value="SUBMITTED">Đã nộp</option>
      </CustomSelect>
      <CustomSelect value={programFilter} onChange={(event) => setProgramFilter(event.target.value)}>
        <option value="">Chương trình: Tất cả</option>{programs.map((program) => <option key={program.id} value={program.id}>{program.name}</option>)}
      </CustomSelect>
      <button type="button" className="btn btn-secondary" onClick={load} disabled={loading}><RefreshCw size={15} />Làm mới</button>
    </div>

    {error && <div className="weekly-report-error"><span>{error}</span><button type="button" onClick={load}>Thử lại</button></div>}
    {loading ? <div className="weekly-report-empty">Đang tải báo cáo tuần…</div> : !reports.length ? <div className="weekly-report-empty"><FileText size={34} /><strong>Bạn chưa có báo cáo tuần nào.</strong><button type="button" className="btn btn-primary" onClick={openCreate} disabled={!programs.length}>Tạo báo cáo đầu tiên</button></div> : <div className="weekly-report-grid">
      {reports.map((report) => <article className="weekly-report-card" key={report.id}>
        <div className="weekly-report-card-top"><span className="weekly-report-week"><CalendarDays size={17} />Tuần {formatDate(report.week_start)} – {formatDate(report.week_end)}</span><span className={`weekly-report-status ${report.status.toLowerCase()}`}>{report.status === 'SUBMITTED' ? 'Đã nộp' : 'Bản nháp'}</span></div>
        <h3>{report.program_name}</h3>
        <dl><div><dt>Cập nhật</dt><dd>{formatDate(report.updated_at, true)}</dd></div>{report.submitted_at && <div><dt>Nộp lúc</dt><dd>{formatDate(report.submitted_at, true)}</dd></div>}</dl>
        <button type="button" className="btn btn-secondary" onClick={() => openReport(report)}>{report.status === 'SUBMITTED' ? 'Xem báo cáo' : 'Tiếp tục chỉnh sửa'}</button>
      </article>)}
    </div>}

    {form && <div className="modal-overlay weekly-report-overlay" onMouseDown={(event) => event.target === event.currentTarget && closeForm()}>
      <section className="weekly-report-modal" role="dialog" aria-modal="true" aria-labelledby="weekly-report-title">
        <header><div><p>{readOnly ? 'BÁO CÁO ĐÃ NỘP' : form.id ? 'CHỈNH SỬA BẢN NHÁP' : 'TẠO BẢN NHÁP'}</p><h3 id="weekly-report-title">Báo cáo tuần</h3></div><button type="button" aria-label="Đóng" onClick={closeForm} disabled={busy}><X size={20} /></button></header>
        <div className="weekly-report-form">
          {formError && <div className="weekly-report-error">{formError}</div>}
          <div className="weekly-report-form-row">
            <label>Chương trình thực tập<span>*</span><CustomSelect value={form.program_id} disabled={Boolean(form.id)} onChange={(event) => setForm({ ...form, program_id: event.target.value })}><option value="">Chọn chương trình</option>{programs.map((program) => <option key={program.id} value={program.id}>{program.name}</option>)}</CustomSelect></label>
            <label>Tuần báo cáo<span>*</span><input type="date" value={form.week_start} disabled={Boolean(form.id)} onChange={(event) => setForm({ ...form, week_start: event.target.value })} /></label>
          </div>
          {selectedProgram && <small className="weekly-report-program-period">Thời gian chương trình: {formatDate(selectedProgram.start_date)} – {formatDate(selectedProgram.end_date)}</small>}
          <label>Nội dung công việc<span>*</span><textarea rows="5" maxLength="10000" readOnly={readOnly} value={form.work_content} onChange={(event) => setForm({ ...form, work_content: event.target.value })} /></label>
          <label>Kết quả đạt được<span>*</span><textarea rows="4" maxLength="10000" readOnly={readOnly} value={form.results} onChange={(event) => setForm({ ...form, results: event.target.value })} /></label>
          <label>Khó khăn / vướng mắc<textarea rows="3" maxLength="10000" readOnly={readOnly} value={form.difficulties} onChange={(event) => setForm({ ...form, difficulties: event.target.value })} /></label>
          <div className="weekly-report-attachment">
            <div><strong>File đính kèm</strong><small>PDF, DOCX hoặc PNG · tối đa 10 MB</small></div>
            {form.has_attachment && <button type="button" className="btn btn-secondary" onClick={downloadAttachment} disabled={busy}><Download size={15} />{form.attachment_original_name}</button>}
            {!readOnly && <label className="weekly-report-file"><UploadCloud size={16} /><span>{file?.name || (form.has_attachment ? 'Thay tệp' : 'Chọn tệp')}</span><input type="file" accept=".pdf,.docx,.png,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png" onChange={(event) => setFile(event.target.files?.[0] || null)} /></label>}
          </div>
          {readOnly && <p className="weekly-report-submitted-at">Đã nộp lúc {formatDate(form.submitted_at, true)}. Báo cáo được khóa chỉ đọc.</p>}
        </div>
        <footer><button type="button" className="btn btn-secondary" onClick={closeForm} disabled={busy}>{readOnly ? 'Đóng' : 'Hủy'}</button>{!readOnly && <><button type="button" className="btn btn-secondary" onClick={saveDraft} disabled={busy}>{busy ? 'Đang lưu…' : 'Lưu nháp'}</button><button type="button" className="btn btn-primary" onClick={() => setConfirmSubmit(true)} disabled={busy || !form.work_content.trim() || !form.results.trim()}>Nộp báo cáo</button></>}</footer>
      </section>
    </div>}

    <ConfirmDialog open={confirmSubmit} title="Nộp báo cáo tuần?" message="Sau khi nộp, bạn sẽ không thể chỉnh sửa báo cáo." confirmLabel="Xác nhận nộp" cancelLabel="Quay lại" busy={busy} onCancel={() => setConfirmSubmit(false)} onConfirm={submit} />
  </section>;
}
