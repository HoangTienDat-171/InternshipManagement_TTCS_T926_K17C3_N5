import React, { useCallback, useEffect, useRef, useState } from 'react';
import { BriefcaseBusiness, Building2, CalendarDays, CircleCheck, Clock3, Download, FileText, GraduationCap, Mail, Phone, UploadCloud, UserRound } from 'lucide-react';
import { apiFetch, downloadProtectedFile, readJsonResponse } from '../utils/api';

const documentStatus = { ChoDuyet: 'Chờ duyệt', DaDuyet: 'Đã duyệt', TuChoi: 'Cần bổ sung' };
const applicationStatus = { ChoDuyet: 'Chờ duyệt', DaDuyet: 'Đã duyệt', TuChoi: 'Từ chối' };

function StatusPill({ status, map = documentStatus }) {
  const tone = status === 'DaDuyet' ? 'success' : status === 'ChoDuyet' ? 'warning' : 'danger';
  return <span className={`workspace-status is-${tone}`}><i />{map[status] || status || 'Chưa cập nhật'}</span>;
}

export default function InternWorkspaceView({ currentUser }) {
  const [workspace, setWorkspace] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState('');
  const fileInput = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const response = await apiFetch('/api/interns/me/workspace');
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể tải hồ sơ thực tập.');
      setWorkspace(data);
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

  const download = async (document) => {
    try { await downloadProtectedFile(document.ma_tai_lieu, document.ten_file); }
    catch (err) { setError(err.message); }
  };

  const uploadCv = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    event.target.value = '';
    const extension = file.name.split('.').pop()?.toLowerCase();
    if (!['pdf', 'docx', 'png'].includes(extension) || file.size > 15 * 1024 * 1024) {
      setError('CV phải có định dạng PDF, DOCX hoặc PNG và dung lượng tối đa 15 MB.');
      return;
    }
    setUploading(true);
    setError('');
    setUploadMessage('');
    try {
      const formData = new FormData();
      formData.append('loai_tai_lieu', 'CV');
      formData.append('file', file);
      const response = await apiFetch('/api/documents', { method: 'POST', body: formData });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể nộp CV.');
      setUploadMessage('Đã nộp CV thành công. Hồ sơ đang chờ duyệt.');
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  if (loading && !workspace) return <div className="workspace-page"><div className="workspace-loading">Đang tải hồ sơ của bạn…</div></div>;
  if (error && !workspace) return <div className="workspace-page"><div className="workspace-error">{error}<button className="btn btn-secondary btn-sm" onClick={() => { setLoading(true); refresh(); }}>Thử lại</button></div></div>;
  if (!workspace) return null;

  const { profile, mentor, documents, applications, current_program: currentProgram, progress_percent: progress } = workspace;
  return <div className="workspace-page">
    <header className="workspace-heading"><div><span className="workspace-eyebrow">KHÔNG GIAN THỰC TẬP</span><h2>Xin chào, {profile.ho_ten || currentUser.ho_ten}</h2><p>Theo dõi người hướng dẫn, hồ sơ và chương trình thực tập của bạn.</p></div><button type="button" className="btn btn-secondary" onClick={() => { setLoading(true); refresh(); }}><Clock3 size={15} />Làm mới</button></header>
    {error && <div className="workspace-error compact">{error}</div>}
    <div className="workspace-summary-grid">
      <article className="workspace-card intern-identity-card"><div className="workspace-card-icon"><GraduationCap size={19} /></div><div><span>MÃ HỒ SƠ</span><strong>#{profile.ma_ho_so}</strong><small>{profile.ten_truong || 'Chưa cập nhật trường'} · {profile.chuyen_nganh || 'Chưa cập nhật ngành'}</small></div><StatusPill status={profile.trang_thai_xet_duyet} map={applicationStatus} /></article>
      <article className="workspace-card workspace-mentor-card"><div className="workspace-section-heading"><div><span className="workspace-eyebrow">NGƯỜI HƯỚNG DẪN</span><h3>{mentor?.ho_ten || 'Chưa được phân công'}</h3></div><span className="workspace-card-icon"><UserRound size={18} /></span></div>
        {mentor ? <div className="workspace-contact-grid"><span><Mail size={14} />{mentor.email}</span><span><Phone size={14} />{mentor.so_dien_thoai || 'Chưa cập nhật SĐT'}</span><span><Building2 size={14} />{mentor.phong_ban || 'Chưa phân phòng'}</span><span><BriefcaseBusiness size={14} />{mentor.chuyen_mon || 'Chưa cập nhật chuyên môn'} · {mentor.kinh_nghiem == null ? 'Chưa cập nhật kinh nghiệm' : `${mentor.kinh_nghiem} năm kinh nghiệm`}</span></div> : <p className="workspace-muted">Quản trị viên sẽ phân công Mentor sau khi hồ sơ được duyệt.</p>}
      </article>
    </div>

    <article className="workspace-card workspace-program-card"><div className="workspace-section-heading"><div><span className="workspace-eyebrow">CHƯƠNG TRÌNH HIỆN TẠI</span><h3>{currentProgram?.ten_ct || 'Chưa tham gia chương trình nào'}</h3></div>{currentProgram && <StatusPill status={currentProgram.trang_thai_ung_tuyen} map={applicationStatus} />}</div>
      {currentProgram ? <><div className="workspace-program-meta"><span><CalendarDays size={15} />{currentProgram.ngay_bat_dau} – {currentProgram.ngay_ket_thuc}</span><span>{currentProgram.ma_ct}</span></div><div className="workspace-progress"><div><strong>Tiến độ thực tập</strong><b>{progress ?? 0}%</b></div><span className="workspace-progress-track"><i style={{ width: `${progress ?? 0}%` }} /></span></div></> : <p className="workspace-muted">Các chương trình bạn đã ứng tuyển sẽ xuất hiện bên dưới. Chương trình được duyệt sẽ hiển thị ở đây.</p>}
    </article>

    <div className="workspace-lower-grid">
      <article className="workspace-card"><div className="workspace-section-heading"><div><span className="workspace-eyebrow">HỒ SƠ ĐÃ NỘP</span><h3>Tài liệu & CV <small>{documents.length}</small></h3></div><div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><input ref={fileInput} type="file" accept=".pdf,.docx,.png,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png" hidden onChange={uploadCv} /><button type="button" className="btn btn-primary btn-sm" disabled={uploading} onClick={() => fileInput.current?.click()}><UploadCloud size={15} />{uploading ? 'Đang tải…' : 'Nộp CV'}</button></div></div>
        {uploadMessage && <p role="status" style={{ color: '#059669', fontSize: 12, margin: '0 0 10px' }}>{uploadMessage}</p>}
        {documents.length ? <div className="workspace-document-list">{documents.map((document) => <div className="workspace-document-row" key={document.ma_tai_lieu}><span className="workspace-file-icon"><FileText size={16} /></span><div><strong>{document.ten_file || document.loai_tai_lieu}</strong><small>{document.loai_tai_lieu} · {document.ngay_tai_len || 'Ngày tải chưa rõ'}</small></div><StatusPill status={document.trang_thai_duyet} /><button type="button" className="workspace-icon-button" title="Tải tài liệu" onClick={() => download(document)}><Download size={15} /></button></div>)}</div> : <div className="workspace-empty"><FileText size={22} /><span>Bạn chưa nộp tài liệu nào.</span></div>}
      </article>
      <article className="workspace-card"><div className="workspace-section-heading"><div><span className="workspace-eyebrow">THEO DÕI ĐĂNG KÝ</span><h3>Chương trình đã ứng tuyển <small>{applications.length}</small></h3></div><CircleCheck size={19} /></div>
        {applications.length ? <div className="workspace-application-list">{applications.map((application) => <div className="workspace-application-row" key={application.ma_chuong_trinh}><div><strong>{application.ten_ct}</strong><small>{application.ma_ct} · Nộp {application.ngay_ung_tuyen || '—'}</small></div><StatusPill status={application.trang_thai_ung_tuyen} map={applicationStatus} /></div>)}</div> : <div className="workspace-empty"><CalendarDays size={22} /><span>Bạn chưa ứng tuyển chương trình nào.</span></div>}
      </article>
    </div>
  </div>;
}
