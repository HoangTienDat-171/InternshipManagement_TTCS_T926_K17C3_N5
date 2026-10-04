import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Award, CalendarDays, ClipboardCheck, Eye, Pencil, Plus, RefreshCw, X } from 'lucide-react';
import CustomSelect from '../components/CustomSelect';
import { apiFetch } from '../utils/api';

const PERIOD_LABELS = { MIDTERM: 'Giữa kỳ', FINAL: 'Cuối kỳ' };
const CRITERIA = [
  { field: 'professional_skill_score', label: 'Kỹ năng chuyên môn' },
  { field: 'work_quality_score', label: 'Chất lượng công việc' },
  { field: 'initiative_score', label: 'Tính chủ động' },
  { field: 'communication_teamwork_score', label: 'Giao tiếp & phối hợp' },
  { field: 'attitude_discipline_score', label: 'Thái độ & kỷ luật' },
];

function emptyForm() {
  return {
    internship_profile_id: '',
    program_id: '',
    evaluation_period: 'MIDTERM',
    professional_skill_score: null,
    work_quality_score: null,
    initiative_score: null,
    communication_teamwork_score: null,
    attitude_discipline_score: null,
    overall_comment: '',
  };
}

async function jsonResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || `Yêu cầu thất bại (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(date);
}

function averageFor(form) {
  const scores = CRITERIA.map(({ field }) => form[field]);
  if (scores.some((score) => !Number.isInteger(score))) return null;
  return Math.round((scores.reduce((total, score) => total + score, 0) / scores.length) * 10) / 10;
}

function ScoreCriteria({ form, onChange, readOnly = false }) {
  return <div className="evaluation-criteria-list">
    {CRITERIA.map(({ field, label }) => <fieldset className="evaluation-criterion" key={field}>
      <legend>{label}</legend>
      <div className="evaluation-score-options" role="radiogroup" aria-label={label}>
        {[1, 2, 3, 4, 5].map((score) => <label className={`evaluation-score-option${form[field] === score ? ' is-selected' : ''}`} key={score}>
          <input
            type="radio"
            name={field}
            value={score}
            checked={form[field] === score}
            disabled={readOnly}
            onChange={() => onChange?.(field, score)}
          />
          <span>{score}</span>
        </label>)}
      </div>
      {!readOnly && <div className="evaluation-score-hints"><span>1 · Chưa đạt</span><span>3 · Đạt</span><span>5 · Xuất sắc</span></div>}
      {readOnly && <span className="evaluation-read-score">{form[field]}/5</span>}
    </fieldset>)}
  </div>;
}

function EvaluationDetail({ evaluation, onClose, onEdit }) {
  if (!evaluation) return null;
  return <div className="modal-overlay evaluation-overlay" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section className="modal-container evaluation-detail-modal" role="dialog" aria-modal="true" aria-labelledby="evaluation-detail-title">
      <header className="evaluation-modal-header">
        <div><p>CHI TIẾT ĐÁNH GIÁ</p><h3 id="evaluation-detail-title">{evaluation.intern_name}</h3></div>
        <button type="button" className="modal-close-btn" aria-label="Đóng" onClick={onClose}><X size={19} /></button>
      </header>
      <div className="evaluation-detail-meta">
        <span><strong>Chương trình</strong>{evaluation.program_name}</span>
        <span><strong>Kỳ đánh giá</strong>{PERIOD_LABELS[evaluation.evaluation_period]}</span>
        <span><strong>Ngày đánh giá</strong>{formatDate(evaluation.evaluated_at)}</span>
        <span><strong>Mentor</strong>{evaluation.mentor_name}</span>
      </div>
      <ScoreCriteria form={evaluation} readOnly />
      <div className="evaluation-average"><span>Điểm trung bình</span><strong>{evaluation.average_score.toFixed(1)} / 5</strong></div>
      <section className="evaluation-comment"><h4>Nhận xét tổng kết</h4><p>{evaluation.overall_comment}</p></section>
      <footer className="evaluation-modal-actions">
        <button type="button" className="btn btn-secondary" onClick={onClose}>Đóng</button>
        <button type="button" className="btn btn-primary" onClick={() => onEdit(evaluation)}><Pencil size={15} />Chỉnh sửa</button>
      </footer>
    </section>
  </div>;
}

export default function MentorEvaluationsView({ onShowToast }) {
  const [evaluations, setEvaluations] = useState([]);
  const [interns, setInterns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [internFilter, setInternFilter] = useState('');
  const [programFilter, setProgramFilter] = useState('');
  const [periodFilter, setPeriodFilter] = useState('');
  const [filterPrograms, setFilterPrograms] = useState([]);
  const [filterProgramsLoading, setFilterProgramsLoading] = useState(false);
  const [form, setForm] = useState(null);
  const [programs, setPrograms] = useState([]);
  const [programLoading, setProgramLoading] = useState(false);
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState(null);

  const loadRegisteredPrograms = useCallback(async (assignedInterns) => {
    setFilterProgramsLoading(true);
    try {
      const details = await Promise.all(assignedInterns.map((intern) => (
        apiFetch(`/api/mentors/me/interns/${intern.ma_ho_so}`).then(jsonResponse)
      )));
      const programsByIntern = [];
      details.forEach((detail, index) => {
        (detail.programs || []).forEach((program) => {
          if (program.ma_chuong_trinh == null) return;
          programsByIntern.push({
            id: program.ma_chuong_trinh,
            name: program.ten_ct,
            profileId: assignedInterns[index].ma_ho_so,
          });
        });
      });
      setFilterPrograms(programsByIntern);
    } catch (programError) {
      setFilterPrograms([]);
      setError(programError.message || 'Không thể tải danh sách chương trình TTS đã đăng ký.');
    } finally {
      setFilterProgramsLoading(false);
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [rows, workspace] = await Promise.all([
        apiFetch('/api/mentor/me/evaluations').then(jsonResponse),
        apiFetch('/api/mentors/me/workspace').then(jsonResponse),
      ]);
      const assignedInterns = workspace.interns || [];
      setEvaluations(rows);
      setInterns(assignedInterns);
      await loadRegisteredPrograms(assignedInterns);
    } catch (loadError) {
      setError(loadError.message || 'Không thể tải dữ liệu đánh giá.');
    } finally {
      setLoading(false);
    }
  }, [loadRegisteredPrograms]);

  useEffect(() => {
    const timer = window.setTimeout(load, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    const profileId = form?.internship_profile_id;
    if (!profileId) return undefined;
    let active = true;
    apiFetch(`/api/mentors/me/interns/${profileId}`)
      .then(jsonResponse)
      .then((result) => {
        if (active) setPrograms((result.programs || []).filter((program) => program.trang_thai_ung_tuyen === 'DaDuyet'));
      })
      .catch((programError) => {
        if (active) {
          setPrograms([]);
          setFormError(programError.message || 'Không thể tải chương trình đã duyệt của thực tập sinh.');
        }
      })
      .finally(() => { if (active) setProgramLoading(false); });
    return () => { active = false; };
  }, [form?.internship_profile_id, form?.id]);

  const programsForFilter = useMemo(() => {
    const visiblePrograms = internFilter
      ? filterPrograms.filter((program) => String(program.profileId) === internFilter)
      : filterPrograms;
    return Array.from(new Map(visiblePrograms.map((program) => [String(program.id), program])).values())
      .sort((left, right) => left.name.localeCompare(right.name, 'vi'));
  }, [filterPrograms, internFilter]);

  const selectFilterIntern = (event) => {
    setInternFilter(event.target.value);
    setProgramFilter('');
  };

  const filtered = evaluations.filter((item) => (
    (!internFilter || String(item.internship_profile_id) === internFilter)
    && (!programFilter || String(item.program_id) === programFilter)
    && (!periodFilter || item.evaluation_period === periodFilter)
  ));

  const duplicate = form && !form.id && form.internship_profile_id && form.program_id
    ? evaluations.find((item) => (
      String(item.internship_profile_id) === String(form.internship_profile_id)
      && String(item.program_id) === String(form.program_id)
      && item.evaluation_period === form.evaluation_period
    ))
    : null;

  const openCreate = () => {
    setForm({ ...emptyForm() });
    setPrograms([]);
    setProgramLoading(false);
    setFormError('');
    setDetail(null);
  };

  const openEdit = (evaluation) => {
    setDetail(null);
    setPrograms([]);
    setProgramLoading(true);
    setForm({
      id: evaluation.id,
      internship_profile_id: evaluation.internship_profile_id,
      program_id: evaluation.program_id,
      evaluation_period: evaluation.evaluation_period,
      ...Object.fromEntries(CRITERIA.map(({ field }) => [field, evaluation[field]])),
      overall_comment: evaluation.overall_comment,
    });
    setFormError('');
  };

  const closeForm = () => {
    if (busy) return;
    setForm(null);
    setFormError('');
  };

  const updateForm = (field, value) => setForm((current) => ({ ...current, [field]: value }));
  const selectIntern = (profileId) => {
    setPrograms([]);
    setProgramLoading(Boolean(profileId));
    setForm((current) => ({ ...current, internship_profile_id: profileId, program_id: '' }));
    setFormError('');
  };

  const save = async (event) => {
    event.preventDefault();
    if (!form.internship_profile_id) { setFormError('Vui lòng chọn thực tập sinh.'); return; }
    if (!form.program_id) { setFormError('Vui lòng chọn chương trình đã được duyệt.'); return; }
    if (CRITERIA.some(({ field }) => !Number.isInteger(form[field]) || form[field] < 1 || form[field] > 5)) {
      setFormError('Vui lòng chấm đủ 5 tiêu chí theo thang điểm từ 1 đến 5.');
      return;
    }
    if (!form.overall_comment.trim()) { setFormError('Vui lòng nhập nhận xét tổng kết.'); return; }
    if (duplicate) { setFormError('Thực tập sinh đã có đánh giá cho chương trình và kỳ này. Hãy chỉnh sửa đánh giá hiện có.'); return; }

    setBusy(true);
    setFormError('');
    const isEdit = Boolean(form.id);
    const payload = {
      ...Object.fromEntries(CRITERIA.map(({ field }) => [field, form[field]])),
      overall_comment: form.overall_comment,
    };
    if (!isEdit) {
      payload.internship_profile_id = Number(form.internship_profile_id);
      payload.program_id = Number(form.program_id);
      payload.evaluation_period = form.evaluation_period;
    }
    try {
      await apiFetch(isEdit ? `/api/mentor/me/evaluations/${form.id}` : '/api/mentor/me/evaluations', {
        method: isEdit ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }).then(jsonResponse);
      setForm(null);
      onShowToast?.(isEdit ? 'Đã cập nhật đánh giá.' : 'Đã lưu đánh giá thực tập sinh.');
      await load();
    } catch (saveError) {
      if (saveError.status === 409) {
        await load();
        setFormError('Thực tập sinh đã có đánh giá cho chương trình và kỳ này. Hãy mở đánh giá hiện có để chỉnh sửa.');
      } else {
        setFormError(saveError.message || 'Không thể lưu đánh giá. Vui lòng thử lại.');
      }
    } finally {
      setBusy(false);
    }
  };

  return <section className="intern-evaluation-page">
    <header className="workspace-heading evaluation-page-heading">
      <div><span className="workspace-eyebrow">QUẢN LÝ CÔNG VIỆC &amp; ĐÁNH GIÁ</span><h2>Đánh giá thực tập sinh</h2><p>Đánh giá kỹ năng và thái độ của các thực tập sinh bạn đang phụ trách.</p></div>
      <div className="evaluation-heading-actions">
        <button type="button" className="btn btn-secondary" onClick={load} disabled={loading}><RefreshCw size={15} />Làm mới</button>
        <button type="button" className="btn btn-primary" onClick={openCreate}><Plus size={16} />Tạo đánh giá</button>
      </div>
    </header>

    <section className="workspace-card evaluation-filters" aria-label="Bộ lọc đánh giá">
      <CustomSelect value={internFilter} onChange={selectFilterIntern}>
        <option value="">TTS: Tất cả</option>
        {interns.map((intern) => <option key={intern.ma_ho_so} value={intern.ma_ho_so}>{intern.ho_ten}</option>)}
      </CustomSelect>
      <CustomSelect value={programFilter} disabled={filterProgramsLoading} onChange={(event) => setProgramFilter(event.target.value)}>
        <option value="">Chương trình: Tất cả</option>
        {programsForFilter.map((program) => <option key={program.id} value={program.id}>{program.name}</option>)}
      </CustomSelect>
      <CustomSelect value={periodFilter} onChange={(event) => setPeriodFilter(event.target.value)}>
        <option value="">Kỳ đánh giá: Tất cả</option>
        <option value="MIDTERM">Giữa kỳ</option>
        <option value="FINAL">Cuối kỳ</option>
      </CustomSelect>
    </section>

    {error && <div className="evaluation-error" role="alert"><span>{error}</span><button type="button" onClick={load}>Thử lại</button></div>}
    {loading ? <div className="workspace-card evaluation-empty"><span className="evaluation-loading-mark" aria-hidden="true" /><strong>Đang tải đánh giá…</strong></div>
      : !filtered.length ? <div className="workspace-card evaluation-empty"><ClipboardCheck size={32} /><strong>Chưa có đánh giá nào.</strong><span>Các đánh giá theo chương trình và kỳ sẽ xuất hiện tại đây.</span>{!evaluations.length && <button type="button" className="btn btn-primary" onClick={openCreate}><Plus size={15} />Tạo đánh giá đầu tiên</button>}</div>
        : <div className="evaluation-card-grid">{filtered.map((evaluation) => <article className="workspace-card evaluation-card" key={evaluation.id}>
          <div className="evaluation-card-top"><div className="evaluation-avatar"><Award size={19} /></div><span className={`evaluation-period-badge ${evaluation.evaluation_period.toLowerCase()}`}>{PERIOD_LABELS[evaluation.evaluation_period]}</span></div>
          <h3>{evaluation.intern_name}</h3>
          <p className="evaluation-program-name">{evaluation.program_name}</p>
          <div className="evaluation-card-score"><div><span>Điểm trung bình</span><strong>{evaluation.average_score.toFixed(1)} <small>/ 5</small></strong></div><div className="evaluation-score-track"><span style={{ width: `${(evaluation.average_score / 5) * 100}%` }} /></div></div>
          <span className="evaluation-card-date"><CalendarDays size={15} />Đánh giá ngày {formatDate(evaluation.evaluated_at)}</span>
          <div className="evaluation-card-actions"><button type="button" className="btn btn-secondary" onClick={() => setDetail(evaluation)}><Eye size={15} />Xem chi tiết</button><button type="button" className="btn btn-primary" onClick={() => openEdit(evaluation)}><Pencil size={15} />Chỉnh sửa</button></div>
        </article>)}</div>}

    {form && <div className="modal-overlay evaluation-overlay" onMouseDown={(event) => event.target === event.currentTarget && closeForm()}>
      <section className="modal-container evaluation-form-modal" role="dialog" aria-modal="true" aria-labelledby="evaluation-form-title">
        <header className="evaluation-modal-header"><div><p>{form.id ? 'CẬP NHẬT KẾT QUẢ' : 'ĐÁNH GIÁ ĐỊNH KỲ'}</p><h3 id="evaluation-form-title">{form.id ? 'Chỉnh sửa đánh giá' : 'Đánh giá thực tập sinh'}</h3></div><button type="button" className="modal-close-btn" aria-label="Đóng" onClick={closeForm} disabled={busy}><X size={19} /></button></header>
        <form onSubmit={save} noValidate>
          <div className="evaluation-form-context">
            <label>Thực tập sinh
              <CustomSelect value={form.internship_profile_id} disabled={Boolean(form.id)} onChange={(event) => selectIntern(event.target.value)}>
                <option value="">Chọn thực tập sinh</option>{interns.map((intern) => <option key={intern.ma_ho_so} value={intern.ma_ho_so}>{intern.ho_ten}</option>)}
              </CustomSelect>
            </label>
            <label>Chương trình
              <CustomSelect value={form.program_id} disabled={Boolean(form.id) || programLoading || !form.internship_profile_id} onChange={(event) => updateForm('program_id', event.target.value)}>
                <option value="">{programLoading ? 'Đang tải chương trình…' : 'Chọn chương trình đã duyệt'}</option>{programs.map((program) => <option key={program.ma_chuong_trinh} value={program.ma_chuong_trinh}>{program.ten_ct}</option>)}
              </CustomSelect>
            </label>
            <label>Kỳ đánh giá
              <CustomSelect value={form.evaluation_period} disabled={Boolean(form.id)} onChange={(event) => updateForm('evaluation_period', event.target.value)}>
                <option value="MIDTERM">Giữa kỳ</option><option value="FINAL">Cuối kỳ</option>
              </CustomSelect>
            </label>
          </div>
          {!interns.length && <div className="evaluation-context-note">Bạn chưa được phân công thực tập sinh để đánh giá.</div>}
          {form.internship_profile_id && !programLoading && !programs.length && !formError && <div className="evaluation-context-note">Thực tập sinh này chưa có chương trình được duyệt để đánh giá.</div>}
          {duplicate && <div className="evaluation-duplicate-notice" role="status"><span>Thực tập sinh đã có đánh giá {PERIOD_LABELS[duplicate.evaluation_period].toLowerCase()} cho chương trình này.</span><button type="button" onClick={() => openEdit(duplicate)}>Chỉnh sửa đánh giá hiện có</button></div>}
          <div className="evaluation-form-divider" />
          <ScoreCriteria form={form} onChange={updateForm} />
          <div className="evaluation-average"><span>Điểm trung bình{averageFor(form) === null ? ' (chấm đủ 5 tiêu chí để xem)' : ''}</span><strong>{averageFor(form) === null ? '—' : `${averageFor(form).toFixed(1)} / 5`}</strong></div>
          <label className="evaluation-comment-field">Nhận xét tổng kết
            <textarea value={form.overall_comment} maxLength={10000} rows={4} onChange={(event) => updateForm('overall_comment', event.target.value)} placeholder="Nhập nhận xét tổng kết về quá trình thực tập…" />
          </label>
          {formError && <div className="evaluation-form-error" role="alert">{formError}</div>}
          <footer className="evaluation-modal-actions"><button type="button" className="btn btn-secondary" onClick={closeForm} disabled={busy}>Hủy</button><button type="submit" className="btn btn-primary" disabled={busy || programLoading || !interns.length}>{busy ? 'Đang lưu…' : form.id ? 'Lưu cập nhật' : 'Lưu đánh giá'}</button></footer>
        </form>
      </section>
    </div>}

    <EvaluationDetail evaluation={detail} onClose={() => setDetail(null)} onEdit={openEdit} />
  </section>;
}
