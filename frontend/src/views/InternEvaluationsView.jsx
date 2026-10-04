import React, { useCallback, useEffect, useState } from 'react';
import { Award, CalendarDays, ClipboardCheck, Eye, X } from 'lucide-react';
import { apiFetch } from '../utils/api';

const PERIOD_LABELS = { MIDTERM: 'Giữa kỳ', FINAL: 'Cuối kỳ' };
const CRITERIA = [
  ['professional_skill_score', 'Kỹ năng chuyên môn'],
  ['work_quality_score', 'Chất lượng công việc'],
  ['initiative_score', 'Tính chủ động'],
  ['communication_teamwork_score', 'Giao tiếp & phối hợp'],
  ['attitude_discipline_score', 'Thái độ & kỷ luật'],
];

async function jsonResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Yêu cầu thất bại (${response.status}).`);
  return data;
}

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(date);
}

function EvaluationDetail({ evaluation, onClose }) {
  if (!evaluation) return null;
  return <div className="modal-overlay evaluation-overlay" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section className="modal-container evaluation-detail-modal" role="dialog" aria-modal="true" aria-labelledby="my-evaluation-detail-title">
      <header className="evaluation-modal-header"><div><p>ĐÁNH GIÁ CỦA BẠN</p><h3 id="my-evaluation-detail-title">{evaluation.program_name}</h3></div><button type="button" className="modal-close-btn" aria-label="Đóng" onClick={onClose}><X size={19} /></button></header>
      <div className="evaluation-detail-meta">
        <span><strong>Kỳ đánh giá</strong>{PERIOD_LABELS[evaluation.evaluation_period]}</span>
        <span><strong>Ngày đánh giá</strong>{formatDate(evaluation.evaluated_at)}</span>
        <span><strong>Mentor</strong>{evaluation.mentor_name}</span>
      </div>
      <div className="evaluation-readonly-scores">{CRITERIA.map(([field, label]) => <div key={field}><span>{label}</span><strong>{evaluation[field]} / 5</strong></div>)}</div>
      <div className="evaluation-average"><span>Điểm trung bình</span><strong>{evaluation.average_score.toFixed(1)} / 5</strong></div>
      <section className="evaluation-comment"><h4>Nhận xét tổng kết</h4><p>{evaluation.overall_comment}</p></section>
      <footer className="evaluation-modal-actions"><button type="button" className="btn btn-secondary" onClick={onClose}>Đóng</button></footer>
    </section>
  </div>;
}

export default function InternEvaluationsView() {
  const [evaluations, setEvaluations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detail, setDetail] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setEvaluations(await apiFetch('/api/interns/me/evaluations').then(jsonResponse));
    } catch (loadError) {
      setError(loadError.message || 'Không thể tải dữ liệu đánh giá.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(load, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  return <section className="intern-evaluation-page">
    <header className="workspace-heading evaluation-page-heading"><div><span className="workspace-eyebrow">KẾT QUẢ ĐÁNH GIÁ</span><h2>Đánh giá của tôi</h2><p>Xem nhận xét và kết quả đánh giá từ Mentor theo từng chương trình, kỳ thực tập.</p></div></header>
    {error && <div className="evaluation-error" role="alert"><span>{error}</span><button type="button" onClick={load}>Thử lại</button></div>}
    {loading ? <div className="workspace-card evaluation-empty"><span className="evaluation-loading-mark" aria-hidden="true" /><strong>Đang tải đánh giá…</strong></div>
      : !evaluations.length ? <div className="workspace-card evaluation-empty"><ClipboardCheck size={32} /><strong>Chưa có đánh giá nào.</strong><span>Khi Mentor hoàn tất đánh giá, kết quả sẽ xuất hiện tại đây.</span></div>
        : <div className="evaluation-card-grid">{evaluations.map((evaluation) => <article className="workspace-card evaluation-card" key={evaluation.id}>
          <div className="evaluation-card-top"><div className="evaluation-avatar"><Award size={19} /></div><span className={`evaluation-period-badge ${evaluation.evaluation_period.toLowerCase()}`}>{PERIOD_LABELS[evaluation.evaluation_period]}</span></div>
          <h3>{evaluation.program_name}</h3>
          <p className="evaluation-program-name">Mentor: {evaluation.mentor_name}</p>
          <div className="evaluation-card-score"><div><span>Điểm trung bình</span><strong>{evaluation.average_score.toFixed(1)} <small>/ 5</small></strong></div><div className="evaluation-score-track"><span style={{ width: `${(evaluation.average_score / 5) * 100}%` }} /></div></div>
          <span className="evaluation-card-date"><CalendarDays size={15} />Đánh giá ngày {formatDate(evaluation.evaluated_at)}</span>
          <div className="evaluation-card-actions"><button type="button" className="btn btn-secondary" onClick={() => setDetail(evaluation)}><Eye size={15} />Xem chi tiết</button></div>
        </article>)}</div>}
    <EvaluationDetail evaluation={detail} onClose={() => setDetail(null)} />
  </section>;
}
