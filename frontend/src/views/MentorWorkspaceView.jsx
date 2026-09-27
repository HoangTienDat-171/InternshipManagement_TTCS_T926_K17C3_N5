import React, { useCallback, useEffect, useState } from 'react';
import { BriefcaseBusiness, Building2, Download, FileText, Mail, Phone, RefreshCw, UserRound } from 'lucide-react';
import { apiFetch, downloadProtectedFile, readJsonResponse } from '../utils/api';

const statusLabels = { ChoDuyet: 'Chờ duyệt', DaDuyet: 'Đã duyệt', TuChoi: 'Cần bổ sung', DangThucTap: 'Đang thực tập', HoanThanh: 'Hoàn thành', ThoiHoc: 'Đã dừng' };

function StatusPill({ status }) {
  const tone = ['DaDuyet', 'HoanThanh'].includes(status) ? 'success' : ['ChoDuyet', 'DangThucTap'].includes(status) ? 'warning' : 'danger';
  return <span className={`workspace-status is-${tone}`}><i />{statusLabels[status] || status || 'Chưa cập nhật'}</span>;
}

export default function MentorWorkspaceView({ currentUser }) {
  const [workspace, setWorkspace] = useState(null);
  const [selectedIntern, setSelectedIntern] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    try {
      const response = await apiFetch('/api/mentors/me/workspace');
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể tải không gian Mentor.');
      setWorkspace(data);
      setSelectedIntern((current) => current && data.interns.some((intern) => intern.ma_ho_so === current.intern?.ma_ho_so) ? current : null);
      setError('');
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(refresh);
    const updateWorkspace = () => refresh();
    window.addEventListener('ims-workspace-updated', updateWorkspace);
    return () => window.removeEventListener('ims-workspace-updated', updateWorkspace);
  }, [refresh]);

  const showIntern = async (intern) => {
    setSelectedIntern({ intern, documents: [], programs: [] });
    setDetailLoading(true);
    try {
      const response = await apiFetch(`/api/mentors/me/interns/${intern.ma_ho_so}`);
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể mở hồ sơ thực tập sinh.');
      setSelectedIntern(data);
    } catch (err) { setError(err.message); setSelectedIntern(null); }
    finally { setDetailLoading(false); }
  };

  const download = async (document) => {
    try { await downloadProtectedFile(document.ma_tai_lieu, document.ten_file); }
    catch (err) { setError(err.message); }
  };

  if (loading && !workspace) return <div className="workspace-page"><div className="workspace-loading">Đang tải nhóm thực tập sinh…</div></div>;
  if (!workspace) return <div className="workspace-page"><div className="workspace-error">{error || 'Không thể tải dữ liệu.'}<button className="btn btn-secondary btn-sm" onClick={() => { setLoading(true); refresh(); }}>Thử lại</button></div></div>;
  const mentor = workspace.mentor || currentUser;
  const interns = workspace.interns || [];
  const capacity = mentor.so_tts_toi_da ?? 3;
  const assignedCount = interns.length;
  const percent = capacity ? Math.min(100, Math.round(assignedCount * 100 / capacity)) : 100;

  return <div className="workspace-page">
    <header className="workspace-heading"><div><span className="workspace-eyebrow">MENTOR WORKSPACE</span><h2>Nhóm thực tập sinh của tôi</h2><p>Thông tin cá nhân, sức chứa và hồ sơ các thực tập sinh được phân công.</p></div><button type="button" className="btn btn-secondary" onClick={() => { setLoading(true); refresh(); }}><RefreshCw size={15} />Làm mới</button></header>
    {error && <div className="workspace-error compact">{error}</div>}
    <div className="workspace-summary-grid mentor-workspace-summary">
      <article className="workspace-card mentor-profile-card"><div className="workspace-profile-avatar">{mentor.ho_ten?.charAt(0) || 'M'}</div><div className="workspace-profile-main"><span className="workspace-eyebrow">HỒ SƠ MENTOR</span><h3>{mentor.ho_ten}</h3><p>{mentor.chuyen_mon || 'Chưa cập nhật chuyên môn'}</p><div className="workspace-contact-grid"><span><Mail size={14} />{mentor.email}</span><span><Phone size={14} />{mentor.so_dien_thoai || 'Chưa cập nhật SĐT'}</span><span><Building2 size={14} />{mentor.phong_ban || 'Chưa phân phòng'}</span><span><BriefcaseBusiness size={14} />{mentor.kinh_nghiem == null ? 'Chưa cập nhật kinh nghiệm' : `${mentor.kinh_nghiem} năm kinh nghiệm`}</span></div></div></article>
      <article className="workspace-card mentor-capacity-card"><span className="workspace-eyebrow">SỨC CHỨA HƯỚNG DẪN</span><div className="mentor-capacity-number"><strong>{assignedCount}</strong><span>/ {capacity}</span></div><span className="workspace-progress-track"><i className={percent >= 100 ? 'is-full' : ''} style={{ width: `${percent}%` }} /></span><p>{Math.max(0, capacity - assignedCount)} vị trí còn trống</p></article>
    </div>
    <div className="mentor-workspace-layout">
      <section className="workspace-card"><div className="workspace-section-heading"><div><span className="workspace-eyebrow">NHÓM CỦA TÔI</span><h3>Thực tập sinh <small>{interns.length}</small></h3></div><UserRound size={19} /></div>
        {interns.length ? <div className="mentor-workspace-interns">{interns.map((intern) => <button type="button" key={intern.ma_ho_so} className={`mentor-workspace-intern${selectedIntern?.intern?.ma_ho_so === intern.ma_ho_so ? ' selected' : ''}`} onClick={() => showIntern(intern)}>
          <span className="workspace-profile-avatar small">{intern.ho_ten?.charAt(0) || 'T'}</span><span className="mentor-workspace-intern-info"><strong>{intern.ho_ten}</strong><small>{intern.ten_truong || 'Chưa cập nhật trường'} · {intern.chuyen_nganh || 'Chưa cập nhật chuyên ngành'}</small></span><span className="mentor-workspace-doc-count"><FileText size={14} />{intern.so_tai_lieu}</span>
        </button>)}</div> : <div className="workspace-empty"><UserRound size={22} /><span>Chưa có thực tập sinh được phân công.</span></div>}
      </section>
      <section className="workspace-card mentor-intern-detail-card"><div className="workspace-section-heading"><div><span className="workspace-eyebrow">HỒ SƠ THỰC TẬP SINH</span><h3>{selectedIntern?.intern?.ho_ten || 'Chọn một hồ sơ'}</h3></div><FileText size={19} /></div>
        {!selectedIntern ? <div className="workspace-empty"><span>Chọn một thực tập sinh để xem hồ sơ, CV và chương trình đã đăng ký.</span></div> : detailLoading ? <div className="workspace-loading small">Đang tải chi tiết…</div> : <div className="mentor-intern-detail">
          <div className="workspace-contact-grid"><span><Mail size={14} />{selectedIntern.intern.email}</span><span><Phone size={14} />{selectedIntern.intern.so_dien_thoai || 'Chưa cập nhật SĐT'}</span><span><Building2 size={14} />{selectedIntern.intern.ten_truong || 'Chưa cập nhật trường'}</span><span><BriefcaseBusiness size={14} />{selectedIntern.intern.chuyen_nganh || 'Chưa cập nhật chuyên ngành'}</span><span><StatusPill status={selectedIntern.intern.trang_thai_xet_duyet} /></span><span><StatusPill status={selectedIntern.intern.trang_thai_thuc_tap} /></span></div>
          <div className="mentor-detail-subsection"><h4>Tài liệu & CV</h4>{selectedIntern.documents.length ? selectedIntern.documents.map((document) => <div className="workspace-document-row" key={document.ma_tai_lieu}><span className="workspace-file-icon"><FileText size={16} /></span><div><strong>{document.ten_file || document.loai_tai_lieu}</strong><small>{document.loai_tai_lieu} · {document.ngay_tai_len || '—'}</small></div><StatusPill status={document.trang_thai_duyet} /><button type="button" className="workspace-icon-button" onClick={() => download(document)} title="Tải tài liệu"><Download size={15} /></button></div>) : <p className="workspace-muted">Chưa có tài liệu được nộp.</p>}</div>
          <div className="mentor-detail-subsection"><h4>Chương trình đã đăng ký</h4>{selectedIntern.programs.length ? selectedIntern.programs.map((program) => <div className="workspace-application-row" key={program.ma_ct}><div><strong>{program.ten_ct}</strong><small>{program.ma_ct} · {program.ngay_bat_dau || '—'} – {program.ngay_ket_thuc || '—'}</small></div><StatusPill status={program.trang_thai_ung_tuyen} /></div>) : <p className="workspace-muted">Chưa đăng ký chương trình nào.</p>}</div>
        </div>}
      </section>
    </div>
  </div>;
}
