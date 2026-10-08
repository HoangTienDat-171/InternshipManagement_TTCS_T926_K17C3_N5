import React, { useCallback, useEffect, useRef, useState } from 'react';
import { UserPlus, Mail, Phone, RefreshCw, Users, Pencil, X, UserRoundPlus, Trash2, ShieldCheck } from 'lucide-react';
import PhoneField from '../components/PhoneField';
import CustomSelect from '../components/CustomSelect';
import FloatingTableScrollbar from '../components/FloatingTableScrollbar';
import DashboardMetrics from '../components/DashboardMetrics';
import TablePagination from '../components/TablePagination';
import ConfirmDialog from '../components/ConfirmDialog';
import { signalDashboardMetricsChanged } from '../utils/dashboardMetrics';
import { isValidVietnamPhone } from '../utils/phone';
import { apiFetch, readJsonResponse } from '../utils/api';

export default function MentorManagementView({ departments, onShowToast, currentUser }) {
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingMentor, setEditingMentor] = useState(null);
  const [assignmentMentor, setAssignmentMentor] = useState(null);
  const [assignedMentor, setAssignedMentor] = useState(null);
  const [pendingUnassignment, setPendingUnassignment] = useState(null);
  const [unassignedInterns, setUnassignedInterns] = useState([]);
  const [assignedInterns, setAssignedInterns] = useState([]);
  const [selectedInternIds, setSelectedInternIds] = useState([]);
  const [removingProfileId, setRemovingProfileId] = useState(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [profileForm, setProfileForm] = useState({ chuyen_mon: '', kinh_nghiem: '', so_tts_toi_da: '3' });

  const [mentors, setMentors] = useState([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [totalMentors, setTotalMentors] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');
  const tableScrollRef = useRef(null);

  const [form, setForm] = useState({
    ho_ten: '',
    email: '',
    so_dien_thoai: '',
    ma_phong_ban: '',
    chuyen_mon: '',
    kinh_nghiem: '',
    so_tts_toi_da: 3
  });

  const requestMentors = useCallback(async (requestedPage, requestedPageSize, signal) => {
    const params = new URLSearchParams({ page: String(requestedPage), pageSize: String(requestedPageSize) });
    const response = await apiFetch('/api/mentors?' + params.toString(), { signal });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Không thể tải danh sách Mentor.');
    return data;
  }, []);

  const loadMentors = useCallback(async (requestedPage, requestedPageSize, signal) => {
    try {
      const data = await requestMentors(requestedPage, requestedPageSize, signal);
      setMentors(Array.isArray(data) ? data : (Array.isArray(data.items) ? data.items : []));
      setPage(Array.isArray(data) ? 1 : Number(data.page) || requestedPage);
      setPageSize(Array.isArray(data) ? requestedPageSize : Number(data.pageSize) || requestedPageSize);
      setTotalMentors(Array.isArray(data) ? data.length : Number(data.totalItems) || 0);
      setTotalPages(Array.isArray(data) ? (data.length ? 1 : 0) : Number(data.totalPages) || 0);
      setErrorMsg('');
      signalDashboardMetricsChanged();
    } catch (error) {
      if (error.name !== 'AbortError') setErrorMsg(error.message);
    } finally {
      setLoading(false);
    }
  }, [requestMentors]);

  const refreshMentors = () => {
    setLoading(true);
    return loadMentors(page, pageSize);
  };

  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    requestMentors(page, pageSize, controller.signal)
      .then((data) => {
        if (!current) return;
        const rows = Array.isArray(data) ? data : (Array.isArray(data.items) ? data.items : []);
        setMentors(rows);
        setPage(Array.isArray(data) ? 1 : Number(data.page) || page);
        setPageSize(Array.isArray(data) ? pageSize : Number(data.pageSize) || pageSize);
        setTotalMentors(Array.isArray(data) ? rows.length : Number(data.totalItems) || 0);
        setTotalPages(Array.isArray(data) ? (rows.length ? 1 : 0) : Number(data.totalPages) || 0);
        setErrorMsg('');
        signalDashboardMetricsChanged();
      })
      .catch((error) => { if (current && error.name !== 'AbortError') setErrorMsg(error.message); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; controller.abort(); };
  }, [requestMentors, page, pageSize]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleAddMentor = async (e) => {
    e.preventDefault();
    if (!form.ho_ten.trim()) return onShowToast('Vui lòng nhập họ và tên Mentor.', 'error');
    if (!/^\S+@\S+\.\S+$/.test(form.email.trim())) return onShowToast('Vui lòng nhập email Mentor hợp lệ.', 'error');
    if (form.so_dien_thoai && !isValidVietnamPhone(form.so_dien_thoai)) {
      onShowToast('Số điện thoại phải gồm 10 chữ số và bắt đầu bằng 03, 05, 07, 08 hoặc 09.', 'error');
      return;
    }
    try {
      const response = await apiFetch('/api/mentors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          ma_phong_ban: form.ma_phong_ban ? Number(form.ma_phong_ban) : null,
          kinh_nghiem: form.kinh_nghiem === '' ? null : Number(form.kinh_nghiem),
          so_tts_toi_da: Number(form.so_tts_toi_da),
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Không thể thêm Mentor.');
      onShowToast(data.message);
      setForm({ ho_ten: '', email: '', so_dien_thoai: '', ma_phong_ban: '', chuyen_mon: '', kinh_nghiem: '', so_tts_toi_da: 3 });
      setShowAddForm(false);
      setPage(1);
      setLoading(true);
      await loadMentors(1, pageSize);
    } catch (error) {
      onShowToast(error.message, 'error');
    }
  };

  const openProfileEditor = (mentor) => {
    setProfileForm({
      chuyen_mon: mentor.chuyen_mon || '',
      kinh_nghiem: mentor.kinh_nghiem ?? '',
      so_tts_toi_da: mentor.so_tts_toi_da ?? 3,
    });
    setEditingMentor(mentor);
  };

  const saveProfile = async (e) => {
    e.preventDefault();
    if (profileForm.so_tts_toi_da === '' || Number(profileForm.so_tts_toi_da) < 0) {
      onShowToast('Sức chứa TTS phải là số từ 0 trở lên.', 'error');
      return;
    }
    setModalLoading(true);
    try {
      const response = await apiFetch(`/api/mentors/${editingMentor.ma_nguoi_dung}/profile`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chuyen_mon: profileForm.chuyen_mon.trim() || null,
          kinh_nghiem: profileForm.kinh_nghiem === '' ? null : Number(profileForm.kinh_nghiem),
          so_tts_toi_da: Number(profileForm.so_tts_toi_da),
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Không thể cập nhật hồ sơ Mentor.');
      onShowToast(data.message);
      setEditingMentor(null);
      await refreshMentors();
    } catch (error) {
      onShowToast(error.message, 'error');
    } finally {
      setModalLoading(false);
    }
  };

  const openAssignmentPicker = async (mentor) => {
    setAssignmentMentor(mentor);
    setSelectedInternIds([]);
    setModalLoading(true);
    try {
      const response = await apiFetch('/api/mentors/unassigned-interns');
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Không thể tải danh sách thực tập sinh.');
      setUnassignedInterns(data);
    } catch (error) {
      onShowToast(error.message, 'error');
      setAssignmentMentor(null);
    } finally {
      setModalLoading(false);
    }
  };

  const assignIntern = async (e) => {
    e.preventDefault();
    if (selectedInternIds.length === 0) return;
    setModalLoading(true);
    try {
      const response = await apiFetch(`/api/mentors/${assignmentMentor.ma_nguoi_dung}/assignments/batch`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ma_ho_so_list: selectedInternIds }),
      });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể phân công thực tập sinh.');
      onShowToast(data.message);
      setAssignmentMentor(null);
      await refreshMentors();
    } catch (error) {
      onShowToast(error.message, 'error');
    } finally {
      setModalLoading(false);
    }
  };

  const openAssignedInterns = async (mentor) => {
    setAssignedMentor(mentor);
    setModalLoading(true);
    try {
      const response = await apiFetch(`/api/mentors/${mentor.ma_nguoi_dung}/interns`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Không thể tải danh sách TTS của Mentor.');
      setAssignedInterns(data);
    } catch (error) {
      onShowToast(error.message, 'error');
      setAssignedMentor(null);
    } finally {
      setModalLoading(false);
    }
  };

  const removeAssignment = async () => {
    const profileId = pendingUnassignment?.ma_ho_so;
    if (!profileId || !assignedMentor) return;
    if (pendingUnassignment.timeline_status !== 'CURRENT') {
      onShowToast('Chỉ có thể gỡ phân công trong chương trình hiện tại.', 'error');
      setPendingUnassignment(null);
      return;
    }
    setRemovingProfileId(profileId);
    try {
      const programQuery = pendingUnassignment.ma_chuong_trinh
        ? `?program_id=${encodeURIComponent(pendingUnassignment.ma_chuong_trinh)}`
        : '';
      const response = await apiFetch(`/api/mentors/${assignedMentor.ma_nguoi_dung}/interns/${profileId}${programQuery}`, { method: 'DELETE' });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể gỡ phân công.');
      onShowToast(data.message);
      setPendingUnassignment(null);
      await openAssignedInterns(assignedMentor);
      await refreshMentors();
    } catch (error) {
      onShowToast(error.message, 'error');
    } finally {
      setRemovingProfileId(null);
    }
  };

  const currentAssignedInterns = assignedInterns.filter((intern) => intern.timeline_status === 'CURRENT');

  return (
    <div className="mentor-management-page">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>Quản lý Mentor</h2>
          <p style={{ fontSize: '13px', color: '#64748b' }}>
            Danh sách và quản lý thông tin người hướng dẫn thực tập sinh
          </p>
        </div>

        <button 
          className="btn btn-primary"
          onClick={() => setShowAddForm(!showAddForm)}
        >
          <UserPlus size={16} />
          <span>{showAddForm ? 'Đóng biểu mẫu' : 'Thêm Mentor'}</span>
        </button>
      </div>

      <DashboardMetrics section="mentors" />

      {/* Form Thêm mới Mentor */}
      {showAddForm && (
        <div className="card" style={{ marginBottom: '24px' }}>
          <div className="card-header">
            <div className="card-title-box">
              <h2>Thêm người hướng dẫn mới</h2>
            </div>
          </div>
          <div className="card-body">
            <form noValidate onSubmit={handleAddMentor} className="form-grid">
              <div className="form-group">
                <label className="form-label">
                  Họ và tên <span className="required">*</span>
                </label>
                <input
                  type="text"
                  name="ho_ten"
                  className="form-control"
                  placeholder="Ví dụ: Nguyễn Văn Hướng"
                  required
                  value={form.ho_ten}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Email <span className="required">*</span>
                </label>
                <input
                  type="email"
                  name="email"
                  className="form-control"
                  placeholder="mentor@internship.vn"
                  required
                  value={form.email}
                  onChange={handleChange}
                />
              </div>

              <p className="form-hint">Hệ thống sẽ gửi email đăng nhập kèm mật khẩu tạm và yêu cầu đổi mật khẩu lần đầu.</p>

              <PhoneField value={form.so_dien_thoai} onChange={(value) => setForm((prev) => ({ ...prev, so_dien_thoai: value }))} placeholder="0905555666" />

              <div className="form-group">
                <label className="form-label">Phòng ban</label>
                <CustomSelect
                  name="ma_phong_ban"
                  className="form-select"
                  value={form.ma_phong_ban}
                  onChange={handleChange}
                >
                  <option value="">-- Chọn phòng ban --</option>
                  {departments.map((d) => (
                    <option key={d.ma_phong_ban} value={d.ma_phong_ban}>
                      {d.ten_phong_ban}
                    </option>
                  ))}
                </CustomSelect>
              </div>

              <div className="form-group">
                <label className="form-label">Chuyên môn</label>
                <input
                  type="text"
                  name="chuyen_mon"
                  className="form-control"
                  placeholder="Frontend / Backend / AI / QA"
                  value={form.chuyen_mon}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Số năm kinh nghiệm</label>
                <input
                  type="number"
                  name="kinh_nghiem"
                  className="form-control"
                  placeholder="5"
                  min="0"
                  value={form.kinh_nghiem}
                  onChange={handleChange}
                />
              </div>

              <div className="form-full" style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowAddForm(false)}>
                  Hủy
                </button>
                <button type="submit" className="btn btn-primary btn-sm">
                  <UserPlus size={15} />
                  <span>Xác nhận thêm</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Danh sách Mentor */}
      <div className="card mentor-list-card">
        <div className="card-header">
          <div className="card-title-box">
            <h2>Danh sách Người hướng dẫn{loading || errorMsg ? '' : ` (${totalMentors})`}</h2>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={refreshMentors} disabled={loading}>
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /><span>Làm mới</span>
          </button>
        </div>

        <div className="table-responsive mentor-table-scroll" ref={tableScrollRef}>
          <table className="data-table mentor-data-table">
            <colgroup>
              <col className="mentor-col-name" />
              <col className="mentor-col-contact" />
              <col className="mentor-col-department" />
              <col className="mentor-col-expertise" />
              <col className="mentor-col-experience" />
              <col className="mentor-col-capacity" />
              <col className="mentor-col-actions" />
            </colgroup>
            <thead>
              <tr>
                <th>Họ và tên</th>
                <th>Thông tin liên hệ</th>
                <th>Phòng ban</th>
                <th>Chuyên môn</th>
                <th>Kinh nghiệm</th>
                <th>TTS đang quản lý / sức chứa</th>
                <th>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan="7" style={{ textAlign: 'center', padding: '30px' }}>Đang tải dữ liệu...</td></tr>
              ) : errorMsg ? (
                <tr><td colSpan="7" style={{ textAlign: 'center', padding: '30px', color: '#b91c1c' }}>{errorMsg}</td></tr>
              ) : mentors.length === 0 ? (
                <tr><td colSpan="7" style={{ textAlign: 'center', padding: '30px' }}>Chưa có tài khoản Mentor.</td></tr>
              ) : mentors.map((m) => (
                <tr key={m.ma_nguoi_dung}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div className="user-avatar" style={{ width: '32px', height: '32px', fontSize: '12px' }}>
                        {m.ho_ten.charAt(0)}
                      </div>
                      <div>
                        <div style={{ fontWeight: 600 }}>{m.ho_ten}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <div style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Mail size={12} color="var(--text-subtle)" />
                      <span>{m.email}</span>
                    </div>
                    {m.so_dien_thoai && (
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Phone size={12} color="var(--text-subtle)" />
                        <span>{m.so_dien_thoai}</span>
                      </div>
                    )}
                  </td>
                  <td>
                    <div style={{ fontSize: '13px' }}>{m.phong_ban || 'Chưa phân phòng'}</div>
                  </td>
                  <td>
                    <span className="badge badge-info" style={{ fontSize: '12px' }}>
                      {m.chuyen_mon || 'Chưa cập nhật'}
                    </span>
                  </td>
                  <td style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                    {(m.kinh_nghiem ?? m.years_of_experience ?? m.experience) == null
                      ? 'Chưa cập nhật'
                      : `${m.kinh_nghiem ?? m.years_of_experience ?? m.experience} năm`}
                  </td>
                  <td>
                    <button type="button" className="mentor-assigned-count" onClick={() => openAssignedInterns(m)} title="Xem danh sách TTS được phân công">
                      <Users size={14} /> {m.so_tts_dang_huong_dan || 0} / {m.so_tts_toi_da ?? 3}
                    </button>
                  </td>
                  <td>
                    <div className="mentor-action-buttons">
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => openAssignedInterns(m)} title="Xem TTS đang quản lý">
                        <Users size={14} /><span>Danh sách</span>
                      </button>
                      {['Admin', 'HR'].includes(currentUser?.vai_tro) && <button type="button" className="btn btn-primary btn-sm" onClick={() => openAssignmentPicker(m)} disabled={(m.so_tts_dang_huong_dan || 0) >= (m.so_tts_toi_da ?? 3)} title="Phân công TTS">
                        <UserRoundPlus size={14} /><span>Phân công</span>
                      </button>}
                      {currentUser?.vai_tro === 'Admin' && <>
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => openProfileEditor(m)} title="Cập nhật kinh nghiệm và sức chứa">
                          <Pencil size={14} /><span>Sửa</span>
                        </button>
                      </>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <TablePagination
          page={page}
          pageSize={pageSize}
          totalItems={totalMentors}
          totalPages={totalPages}
          itemLabel="Mentor"
          disabled={loading}
          onPageChange={(nextPage) => { setLoading(true); setPage(nextPage); }}
          onPageSizeChange={(size) => { setLoading(true); setPage(1); setPageSize(size); }}
        />
      </div>

      <FloatingTableScrollbar
        scrollContainerRef={tableScrollRef}
        refreshKey={`${mentors.length}:${loading}`}
        label="Cuộn ngang danh sách Mentor"
      />

      {editingMentor && <div className="modal-overlay" onClick={() => setEditingMentor(null)}>
        <div className="modal-container" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header"><h3>Cập nhật Mentor: {editingMentor.ho_ten}</h3><button className="modal-close-btn" type="button" onClick={() => setEditingMentor(null)}><X size={18} /></button></div>
          <form noValidate onSubmit={saveProfile}>
            <div className="modal-body mentor-modal-fields">
              <div className="form-group"><label className="form-label">Chuyên môn</label><input className="form-control" value={profileForm.chuyen_mon} onChange={(e) => setProfileForm((prev) => ({ ...prev, chuyen_mon: e.target.value }))} /></div>
              <div className="form-group"><label className="form-label">Số năm kinh nghiệm</label><input type="number" min="0" className="form-control" value={profileForm.kinh_nghiem} onChange={(e) => setProfileForm((prev) => ({ ...prev, kinh_nghiem: e.target.value }))} /></div>
              <div className="form-group"><label className="form-label">Sức chứa TTS tối đa</label><input type="number" min="0" required className="form-control" value={profileForm.so_tts_toi_da} onChange={(e) => setProfileForm((prev) => ({ ...prev, so_tts_toi_da: e.target.value }))} /></div>
            </div>
            <div className="modal-footer"><button type="button" className="btn btn-secondary" onClick={() => setEditingMentor(null)}>Hủy</button><button className="btn btn-primary" disabled={modalLoading}>Lưu thay đổi</button></div>
          </form>
        </div>
      </div>}

      {assignmentMentor && <div className="modal-overlay" onClick={() => setAssignmentMentor(null)}>
        <div className="modal-container mentor-assignment-dialog" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header"><div><h3>Phân công thực tập sinh</h3><p>{assignmentMentor.ho_ten} · {assignmentMentor.phong_ban || 'Chưa phân phòng'}</p></div><button className="modal-close-btn" type="button" onClick={() => setAssignmentMentor(null)}><X size={18} /></button></div>
          <form noValidate onSubmit={assignIntern}>
            <div className="modal-body mentor-assignment-body">
                {(() => {
                  const capacity = assignmentMentor.so_tts_toi_da ?? 3;
                  const assigned = assignmentMentor.so_tts_dang_huong_dan || 0;
                  const availableSlots = Math.max(0, capacity - assigned);
                  const percent = capacity ? Math.min(100, Math.round((assigned / capacity) * 100)) : 100;
                return <div className="assignment-capacity-card">
                  <div><strong>Sức chứa hiện tại</strong><span>{assigned} / {capacity} TTS</span></div>
                  <div className="assignment-progress-track"><span className={percent >= 100 ? 'is-full' : ''} style={{ width: `${percent}%` }} /></div>
                  <small>{availableSlots} chỗ có thể phân công</small>
                  <small className="assignment-selection-count">Đang chọn {selectedInternIds.length}/{availableSlots}</small>
                </div>;
              })()}
              {modalLoading ? <p className="workspace-empty">Đang tải danh sách thực tập sinh…</p> : <div className="assignment-transfer-grid">
                <section className="assignment-transfer-column">
                  <header><div><strong>TTS chưa phân công</strong><small>{unassignedInterns.length} hồ sơ đủ điều kiện</small></div></header>
                  <div className="assignment-transfer-list">
                    {unassignedInterns.length === 0 ? <p className="workspace-empty">Hiện không có hồ sơ đủ điều kiện.</p> : unassignedInterns.map((intern) => {
                      const selected = selectedInternIds.includes(intern.ma_ho_so);
                      return <button type="button" key={intern.ma_ho_so} className={`assignment-candidate${selected ? ' selected' : ''}`}
                        onClick={() => setSelectedInternIds((items) => selected ? items.filter((id) => id !== intern.ma_ho_so) : (items.length < Math.max(0, (assignmentMentor.so_tts_toi_da ?? 3) - (assignmentMentor.so_tts_dang_huong_dan || 0)) ? [...items, intern.ma_ho_so] : items))}>
                        <span className="assignment-check-mark">{selected ? '✓' : '+'}</span><span><strong>{intern.ho_ten}</strong><small>{intern.ten_truong || 'Chưa cập nhật trường'} · {intern.chuyen_nganh || 'Chưa cập nhật chuyên ngành'}</small>{intern.ten_ct && <small style={{ color: 'var(--brand-primary, #0284c7)', display: 'block', fontWeight: 600 }}>Chương trình: {intern.ten_ct}</small>}</span>
                      </button>;
                    })}
                  </div>
                </section>
                <section className="assignment-transfer-column assignment-selected-column">
                  <header><div><strong>Danh sách sẽ gán</strong><small>{selectedInternIds.length} đã chọn</small></div><button type="button" className="btn btn-secondary btn-sm" onClick={() => setSelectedInternIds([])} disabled={!selectedInternIds.length}>Bỏ chọn</button></header>
                  <div className="assignment-transfer-list">
                    {selectedInternIds.length === 0 ? <p className="workspace-empty">Chọn TTS ở cột bên trái để thêm vào đợt phân công.</p> : selectedInternIds.map((id) => {
                      const intern = unassignedInterns.find((item) => item.ma_ho_so === id);
                      return intern ? <button type="button" key={id} className="assignment-candidate selected" onClick={() => setSelectedInternIds((items) => items.filter((item) => item !== id))}>
                        <span className="assignment-check-mark">−</span><span><strong>{intern.ho_ten}</strong><small>{intern.ten_truong || 'Chưa cập nhật trường'} · {intern.chuyen_nganh || 'Chưa cập nhật chuyên ngành'}</small>{intern.ten_ct && <small style={{ color: 'var(--brand-primary, #0284c7)', display: 'block', fontWeight: 600 }}>Chương trình: {intern.ten_ct}</small>}</span>
                      </button> : null;
                    })}
                  </div>
                </section>
              </div>}
            </div>
            <div className="modal-footer"><button type="button" className="btn btn-secondary" onClick={() => setAssignmentMentor(null)}>Đóng</button><button className="btn btn-primary" disabled={modalLoading || selectedInternIds.length === 0}><Users size={15} />Phân công {selectedInternIds.length || ''}</button></div>
          </form>
        </div>
      </div>}

      {assignedMentor && <div className="modal-overlay" onClick={() => setAssignedMentor(null)}>
        <div className="modal-container" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header"><h3>TTS do {assignedMentor.ho_ten} hướng dẫn</h3><button className="modal-close-btn" type="button" onClick={() => setAssignedMentor(null)}><X size={18} /></button></div>
          <div className="modal-body">
            <p className="mentor-capacity-summary">Sức chứa: {currentAssignedInterns.length}/{assignedMentor.so_tts_toi_da ?? 3} TTS</p>
            {modalLoading ? <p>Đang tải danh sách...</p> : currentAssignedInterns.length === 0 ? <p>Mentor chưa có thực tập sinh đang tham gia chương trình hiện tại.</p> : <div className="mentor-intern-list">
              {currentAssignedInterns.map((intern) => <div className="mentor-intern-item" key={`${intern.ma_ho_so}-${intern.ma_chuong_trinh ?? 'legacy'}`}>
                <div>
                  <strong>{intern.ho_ten}</strong>
                  <div className="text-muted">{intern.email} · {intern.ten_truong || 'Chưa có trường'} · {intern.chuyen_nganh || 'Chưa có chuyên ngành'}</div>
                  {intern.ten_ct && <div style={{ fontSize: '12px', color: 'var(--brand-primary, #0284c7)', marginTop: '2px' }}>Chương trình: <strong>{intern.ten_ct}</strong> {intern.timeline_status ? `(${intern.timeline_status === 'CURRENT' ? 'Đang thực tập' : (intern.timeline_status === 'UPCOMING' ? 'Sắp tới' : 'Lịch sử')})` : ''}</div>}
                </div>
                {intern.timeline_status === 'CURRENT' && ['Admin', 'HR'].includes(currentUser?.vai_tro) && <button type="button" className="btn btn-danger btn-sm" onClick={() => setPendingUnassignment(intern)} disabled={removingProfileId === intern.ma_ho_so} title="Gỡ phân công khỏi chương trình hiện tại" aria-label={`Gỡ phân công ${intern.ho_ten}`}><Trash2 size={14} />Gỡ phân công</button>}
              </div>)}
            </div>}
          </div>
          <div className="modal-footer"><button type="button" className="btn btn-secondary" onClick={() => setAssignedMentor(null)}>Đóng</button></div>
        </div>
      </div>}

      <ConfirmDialog
        open={Boolean(pendingUnassignment)}
        title="Gỡ phân công Mentor?"
        message={pendingUnassignment && assignedMentor
          ? `Bạn sắp gỡ ${pendingUnassignment.ho_ten} khỏi danh sách hướng dẫn của ${assignedMentor.ho_ten}.`
          : ''}
        confirmLabel="Gỡ phân công"
        cancelLabel="Giữ phân công"
        danger
        className="mentor-unassign-confirm"
        busy={removingProfileId !== null}
        onCancel={() => setPendingUnassignment(null)}
        onConfirm={removeAssignment}
      >
        <div className="mentor-unassign-note">
          <ShieldCheck size={17} aria-hidden="true" />
          <span>Chỉ gỡ liên kết phân công. Hồ sơ TTS và dữ liệu liên quan vẫn được giữ nguyên.</span>
        </div>
      </ConfirmDialog>
    </div>
  );
}
