import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarDays, Download, FileText, RefreshCw, X } from 'lucide-react';
import CustomSelect from '../components/CustomSelect';
import { apiFetch } from '../utils/api';


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

export default function MentorWeeklyReportsView({ requestedReportId, onReportOpened, onShowToast }) {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [internFilter, setInternFilter] = useState('');
  const [programFilter, setProgramFilter] = useState('');
  const [reviewFilter, setReviewFilter] = useState('');
  const [detail, setDetail] = useState(null);
  const [comment, setComment] = useState('');
  const [detailError, setDetailError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setReports(await apiFetch('/api/mentor/me/weekly-reports').then(jsonResponse));
    } catch (loadError) {
      setError(loadError.message || 'Không thể tải báo cáo tuần.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(load, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const openReportById = useCallback(async (reportId) => {
    setBusy(true);
    setDetailError('');
    try {
      const report = await apiFetch(`/api/mentor/weekly-reports/${reportId}`).then(jsonResponse);
      setDetail(report);
      setComment(report.review_comment || '');
    } catch (openError) {
      setError(openError.message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (!requestedReportId) return undefined;
    const timer = window.setTimeout(() => openReportById(requestedReportId), 0);
    return () => window.clearTimeout(timer);
  }, [openReportById, requestedReportId]);

  const interns = useMemo(() => Array.from(new Map(reports.map((item) => [item.intern_user_id, { id: item.intern_user_id, name: item.intern_name }])).values()), [reports]);
  const programs = useMemo(() => Array.from(new Map(reports.map((item) => [item.program_id, { id: item.program_id, name: item.program_name }])).values()), [reports]);
  const filtered = reports.filter((item) => (
    (!internFilter || String(item.intern_user_id) === internFilter)
    && (!programFilter || String(item.program_id) === programFilter)
    && (!reviewFilter || (reviewFilter === 'reviewed' ? Boolean(item.review_id) : !item.review_id))
  ));

  const openReport = (report) => {
    window.history.pushState(null, '', `/weekly-reports/${report.id}`);
    onReportOpened?.(report.id);
    openReportById(report.id);
  };

  const closeDetail = () => {
    if (busy) return;
    window.history.pushState(null, '', '/weekly-reports');
    setDetail(null);
    setComment('');
    setDetailError('');
  };

  const saveReview = async () => {
    if (!comment.trim()) {
      setDetailError('Vui lòng nhập nhận xét trước khi lưu.');
      return;
    }
    setBusy(true);
    setDetailError('');
    try {
      const reviewed = await apiFetch(`/api/mentor/weekly-reports/${detail.id}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ comment }),
      }).then(jsonResponse);
      setDetail(reviewed);
      setComment(reviewed.review_comment || '');
      onShowToast('Đã lưu nhận xét báo cáo.');
      await load();
    } catch (reviewError) {
      setDetailError(reviewError.message);
    } finally {
      setBusy(false);
    }
  };

  const downloadAttachment = async () => {
    setBusy(true);
    setDetailError('');
    try {
      const response = await apiFetch(`/api/mentor/weekly-reports/${detail.id}/attachment`);
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'Không thể tải tệp đính kèm.');
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = detail.attachment_original_name || 'bao-cao-tuan';
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (downloadError) {
      setDetailError(downloadError.message);
    } finally {
      setBusy(false);
    }
  };

  return <section className="weekly-reports-page mentor-weekly-reports">
    <header className="weekly-reports-header"><div><p>THEO DÕI BÁO CÁO</p><h2>Báo cáo tuần</h2><span>Theo dõi báo cáo của thực tập sinh được phân công.</span></div></header>
    <div className="weekly-report-filters mentor-report-filters">
      <CustomSelect value={internFilter} onChange={(event) => setInternFilter(event.target.value)}><option value="">TTS: Tất cả</option>{interns.map((intern) => <option key={intern.id} value={intern.id}>{intern.name}</option>)}</CustomSelect>
      <CustomSelect value={programFilter} onChange={(event) => setProgramFilter(event.target.value)}><option value="">Chương trình: Tất cả</option>{programs.map((program) => <option key={program.id} value={program.id}>{program.name}</option>)}</CustomSelect>
      <CustomSelect value={reviewFilter} onChange={(event) => setReviewFilter(event.target.value)}><option value="">Nhận xét: Tất cả</option><option value="unreviewed">Chưa nhận xét</option><option value="reviewed">Đã nhận xét</option></CustomSelect>
      <button type="button" className="btn btn-secondary" onClick={load} disabled={loading}><RefreshCw size={15} />Làm mới</button>
    </div>
    {error && <div className="weekly-report-error"><span>{error}</span><button type="button" onClick={load}>Thử lại</button></div>}
    {loading ? <div className="weekly-report-empty">Đang tải báo cáo tuần…</div> : !filtered.length ? <div className="weekly-report-empty"><FileText size={34} /><strong>Không có báo cáo phù hợp.</strong><span>Các báo cáo đã nộp của TTS được phân công sẽ xuất hiện tại đây.</span></div> : <div className="weekly-report-grid">
      {filtered.map((report) => <article className="weekly-report-card" key={report.id}><div className="weekly-report-card-top"><strong>{report.intern_name}</strong><span className={`weekly-report-status ${report.review_id ? 'submitted' : 'draft'}`}>{report.review_id ? 'Đã nhận xét' : 'Chưa nhận xét'}</span></div><h3>{report.program_name}</h3><span className="weekly-report-week"><CalendarDays size={17} />Tuần {formatDate(report.week_start)} – {formatDate(report.week_end)}</span><dl><div><dt>Nộp lúc</dt><dd>{formatDate(report.submitted_at, true)}</dd></div></dl><button type="button" className="btn btn-primary" onClick={() => openReport(report)}>Xem &amp; nhận xét</button></article>)}
    </div>}

    {detail && <div className="modal-overlay weekly-report-overlay" onMouseDown={(event) => event.target === event.currentTarget && closeDetail()}><section className="weekly-report-modal mentor-report-modal" role="dialog" aria-modal="true" aria-labelledby="mentor-report-title"><header><div><p>CHI TIẾT BÁO CÁO</p><h3 id="mentor-report-title">{detail.intern_name}</h3></div><button type="button" aria-label="Đóng" onClick={closeDetail} disabled={busy}><X size={20} /></button></header><div className="weekly-report-form mentor-report-detail">
      {detailError && <div className="weekly-report-error">{detailError}</div>}
      <section className="mentor-report-meta"><div><span>Chương trình</span><strong>{detail.program_name}</strong></div><div><span>Tuần báo cáo</span><strong>{formatDate(detail.week_start)} – {formatDate(detail.week_end)}</strong></div><div><span>Nộp lúc</span><strong>{formatDate(detail.submitted_at, true)}</strong></div></section>
      <section><h4>Nội dung công việc</h4><p>{detail.work_content}</p></section><section><h4>Kết quả đạt được</h4><p>{detail.results}</p></section><section><h4>Khó khăn / vướng mắc</h4><p>{detail.difficulties || 'Không có.'}</p></section>
      <section className="weekly-report-attachment"><div><strong>File đính kèm</strong><small>{detail.has_attachment ? detail.attachment_original_name : 'Không có tệp đính kèm'}</small></div>{detail.has_attachment && <button type="button" className="btn btn-secondary" onClick={downloadAttachment} disabled={busy}><Download size={15} />Tải xuống</button>}</section>
      <label>Nhận xét Mentor<span>*</span><textarea rows="6" maxLength="10000" value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Nhập nhận xét về báo cáo tuần…" /></label>
      {detail.review_id && <small className="weekly-report-program-period">Nhận xét gần nhất: {detail.reviewer_name} · {formatDate(detail.reviewed_at, true)}</small>}
    </div><footer><button type="button" className="btn btn-secondary" onClick={closeDetail} disabled={busy}>Đóng</button><button type="button" className="btn btn-primary" onClick={saveReview} disabled={busy || !comment.trim()}>{busy ? 'Đang lưu…' : 'Lưu nhận xét'}</button></footer></section></div>}
  </section>;
}
