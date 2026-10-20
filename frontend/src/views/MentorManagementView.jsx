import React, { useCallback, useEffect, useRef, useState } from 'react';
import { UserPlus, Mail, Phone, RefreshCw, Users, Pencil, X, UserRoundPlus, Trash2, ShieldCheck } from 'lucide-react';
import PhoneField from '../components/PhoneField';
import MasterDataSelect from '../components/MasterDataSelect';
import FloatingTableScrollbar from '../components/FloatingTableScrollbar';
import DashboardMetrics from '../components/DashboardMetrics';
import TablePagination from '../components/TablePagination';
import ConfirmDialog from '../components/ConfirmDialog';
import { signalDashboardMetricsChanged } from '../utils/dashboardMetrics';
import { isValidVietnamPhone } from '../utils/phone';
import { apiFetch, readJsonResponse } from '../utils/api';

const candidateKey = (intern) => `${intern.ma_ho_so}:${intern.ma_chuong_trinh ?? 'profile'}`;
const normalizeSearch = (value) => String(value || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/\u0111/g, 'd');

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
  const [assignmentSearch, setAssignmentSearch] = useState('');
  const [assignmentProgram, setAssignmentProgram] = useState('');
  const [assignmentStatus, setAssignmentStatus] = useState('all');
  const [manualAssignments, setManualAssignments] = useState(true);
  const [confirmMentorTransfer, setConfirmMentorTransfer] = useState(false);
  const [creatingMentor, setCreatingMentor] = useState(false);
  const mutationBusyRef = useRef(false);
  const [profileForm, setProfileForm] = useState({ chuyen_mon: '', kinh_nghiem: '' });

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
    kinh_nghiem: ''
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
    if (mutationBusyRef.current) return;
    if (!form.ho_ten.trim()) return onShowToast('Vui lòng nhập họ và tên Mentor.', 'error');
    if (!/^\S+@\S+\.\S+$/.test(form.email.trim())) return onShowToast('Vui lòng nhập email Mentor hợp lệ.', 'error');
    if (form.so_dien_thoai && !isValidVietnamPhone(form.so_dien_thoai)) {
      onShowToast('Số điện thoại phải gồm 10 chữ số và bắt đầu bằng 03, 05, 07, 08 hoặc 09.', 'error');
      return;
    }
    mutationBusyRef.current = true;
    setCreatingMentor(true);
    try {
      const response = await apiFetch('/api/mentors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          ma_phong_ban: form.ma_phong_ban ? Number(form.ma_phong_ban) : null,
          kinh_nghiem: form.kinh_nghiem === '' ? null : Number(form.kinh_nghiem),
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Không thể thêm Mentor.');
      onShowToast(data.message);
      setForm({ ho_ten: '', email: '', so_dien_thoai: '', ma_phong_ban: '', chuyen_mon: '', kinh_nghiem: '' });
      setShowAddForm(false);
      setPage(1);
      setLoading(true);
      await loadMentors(1, pageSize);
    } catch (error) {
      onShowToast(error.message, 'error');
    } finally {
      mutationBusyRef.current = false;
      setCreatingMentor(false);
    }
  };

  const openProfileEditor = (mentor) => {
    setProfileForm({
      chuyen_mon: mentor.chuyen_mon || '',
      kinh_nghiem: mentor.kinh_nghiem ?? '',
    });
    setEditingMentor(mentor);
  };

  const saveProfile = async (e) => {
    e.preventDefault();
    setModalLoading(true);
    try {
      const response = await apiFetch(`/api/mentors/${editingMentor.ma_nguoi_dung}/profile`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chuyen_mon: profileForm.chuyen_mon.trim() || null,
          kinh_nghiem: profileForm.kinh_nghiem === '' ? null : Number(profileForm.kinh_nghiem),
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

  const openAssignmentPicker = async (mentor, manual = manualAssignments) => {
    setAssignmentMentor(mentor);
    setSelectedInternIds([]);
    setUnassignedInterns([]);
    setAssignmentSearch('');
    setAssignmentProgram('');
    setAssignmentStatus('all');
    setModalLoading(true);
    try {
      const response = await apiFetch(`/api/mentors/unassigned-interns?include_unavailable=true&manual_override=${manual}`);
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

  const assignIntern = async (e, transferConfirmed = false) => {
    e?.preventDefault();
    const changingMentor = selectedInternIds.some((key) => {
      const candidate = unassignedInterns.find((item) => candidateKey(item) === key);
      return candidate?.mentor_id && candidate.mentor_id !== assignmentMentor?.ma_nguoi_dung;
    });
    if (changingMentor && !transferConfirmed) { setConfirmMentorTransfer(true); return; }
    if (selectedInternIds.length === 0 || mutationBusyRef.current) return;
    mutationBusyRef.current = true;
    setModalLoading(true);
    try {
      const response = await apiFetch(`/api/mentors/${assignmentMentor.ma_nguoi_dung}/assignments/batch`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ manual_override: manualAssignments, replace_existing: transferConfirmed, assignments: selectedInternIds.map((key) => {
          const intern = unassignedInterns.find((item) => candidateKey(item) === key);
          return { ma_ho_so: intern.ma_ho_so, ma_chuong_trinh: intern.ma_chuong_trinh };
        }) }),
      });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể phân công thực tập sinh.');
      onShowToast(data.message);
      setConfirmMentorTransfer(false);
      setAssignmentMentor(null);
      await refreshMentors();
    } catch (error) {
      onShowToast(error.message, 'error');
    } finally {
      mutationBusyRef.current = false;
      setModalLoading(false);
    }
  };

  const openAssignedInterns = async (mentor) => {
    setAssignedMentor(mentor);
    setModalLoading(true);
    try {
      const response = await apiFetch(`/api/mentors/${mentor.ma_nguoi_dung}/interns?manual_override=${manualAssignments}`);
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
    if (!profileId || !assignedMentor || mutationBusyRef.current) return;
    if (!manualAssignments && pendingUnassignment.timeline_status === 'HISTORICAL') {
      onShowToast('Không thể gỡ phân công lịch sử của chương trình đã kết thúc.', 'error');
      setPendingUnassignment(null);
      return;
    }
    mutationBusyRef.current = true;
    setRemovingProfileId(profileId);
    try {
      const params = new URLSearchParams({ manual_override: String(manualAssignments) });
      if (pendingUnassignment.ma_chuong_trinh) params.set('program_id', pendingUnassignment.ma_chuong_trinh);
      const response = await apiFetch(`/api/mentors/${assignedMentor.ma_nguoi_dung}/interns/${profileId}?${params}`, { method: 'DELETE' });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể gỡ phân công.');
      onShowToast(data.message);
      setPendingUnassignment(null);
      await openAssignedInterns(assignedMentor);
      await refreshMentors();
    } catch (error) {
      onShowToast(error.message, 'error');
    } finally {
      mutationBusyRef.current = false;
      setRemovingProfileId(null);
    }
  };

  const currentAssignedInterns = assignedInterns.filter((intern) => manualAssignments || intern.timeline_status !== 'HISTORICAL');
  const currentAssignedCount = new Set(currentAssignedInterns.filter((intern) => intern.counts_as_current).map((intern) => intern.ma_nguoi_dung)).size;
  const upcomingAssignedCount = new Set(currentAssignedInterns.filter((intern) => intern.timeline_status === 'UPCOMING').map((intern) => intern.ma_nguoi_dung)).size;
  const contextPriority = (intern) => (intern.application_approved ? 0 : 5) + ({ CURRENT: 0, UPCOMING: 1, HISTORICAL: 10 }[intern.timeline_status] ?? 2);
  const displayedCandidates = assignmentProgram ? unassignedInterns : [...unassignedInterns.reduce((items, intern) => {
    const previous = items.get(intern.ma_ho_so);
    if (!previous || contextPriority(intern) < contextPriority(previous)) items.set(intern.ma_ho_so, intern);
    return items;
  }, new Map()).values()];
  const filteredCandidates = displayedCandidates.filter((intern) => {
    const query = normalizeSearch(assignmentSearch);
    return (!query || normalizeSearch(`${intern.ho_ten} ${intern.email} ${intern.ma_ho_so} ${intern.ma_ct || ''} ${intern.ten_ct || ''}`).includes(query))
      && (!assignmentProgram || String(intern.ma_chuong_trinh ?? 'profile') === assignmentProgram)
      && (assignmentStatus === 'all' || (assignmentStatus === 'available' ? intern.eligible : Boolean(intern.mentor_id)));
  });
  const candidatePrograms = [...new Map(unassignedInterns.filter((intern) => intern.ma_chuong_trinh).map((intern) => [intern.ma_chuong_trinh, intern])).values()];

  return (
    <div className="mentor-management-page">
      <div className="mentor-page-header">
        <div>
          <h2>Quản lý Mentor</h2>
          <p>
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

              <PhoneField value={form.so_dien_thoai} onChange={(value) => setForm((prev) => ({ ...prev, so_dien_thoai: value }))} placeholder="0905555666" />

              <div className="form-group">
                <label className="form-label">Phòng ban</label>
                <MasterDataSelect
                  id="mentor-department"
                  name="ma_phong_ban"
                  value={form.ma_phong_ban}
                  items={departments}
                  idKey="ma_phong_ban"
                  labelKey="ten_phong_ban"
                  placeholder="Tìm hoặc chọn phòng ban"
                  onChange={handleChange}
                />
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
                <button type="button" className="btn btn-secondary" disabled={creatingMentor} onClick={() => setShowAddForm(false)}>
                  Hủy
                </button>
                <button type="submit" className="btn btn-primary" disabled={creatingMentor}>
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
              <col className="mentor-col-capacity mentor-col-count" />
              <col className="mentor-col-actions" />
            </colgroup>
            <thead>
              <tr>
                <th className="mentor-th-name">Họ và tên</th>
                <th className="mentor-th-contact">Thông tin liên hệ</th>
                <th className="mentor-th-department">Phòng ban</th>
                <th className="mentor-th-expertise">Chuyên môn</th>
                <th className="mentor-th-experience">Kinh nghiệm</th>
                <th className="mentor-th-capacity">TTS đang hướng dẫn</th>
                <th className="mentor-th-actions">Thao tác</th>
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
                  <td className="mentor-td-name">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div className="user-avatar" style={{ width: '32px', height: '32px', fontSize: '12px' }}>
                        {m.ho_ten.charAt(0)}
                      </div>
                      <div>
                        <div style={{ fontWeight: 600 }}>{m.ho_ten}</div>
                      </div>
                    </div>
                  </td>
                  <td className="mentor-td-contact">
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
                  <td className="mentor-td-department">
                    <div style={{ fontSize: '13px' }}>{m.phong_ban || 'Chưa phân phòng'}</div>
                  </td>
                  <td className="mentor-td-expertise">
                    <span className="badge badge-info" style={{ fontSize: '12px' }}>
                      {m.chuyen_mon || 'Chưa cập nhật'}
                    </span>
                  </td>
                  <td className="mentor-td-experience" style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                    {(m.kinh_nghiem ?? m.years_of_experience ?? m.experience) == null
                      ? 'Chưa cập nhật'
                      : `${m.kinh_nghiem ?? m.years_of_experience ?? m.experience} năm`}
                  </td>
                  <td className="mentor-td-capacity">
                    <button type="button" className="mentor-assigned-count" onClick={() => openAssignedInterns(m)} title="Xem danh sách TTS được phân công">
                      <Users size={14} /> <span>{m.so_tts_dang_huong_dan || 0} TTS</span>
                    </button>
                  </td>
                  <td className="mentor-td-actions">
                    <div className="mentor-action-buttons">
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => openAssignedInterns(m)} title="Xem TTS đang quản lý">
                        <Users size={14} /><span>Danh sách</span>
                      </button>
                      {['Admin', 'HR'].includes(currentUser?.vai_tro) && <button type="button" className="btn btn-primary btn-sm" onClick={() => openAssignmentPicker(m)} title="Phân công TTS">
                        <UserRoundPlus size={14} /><span>Phân công</span>
                      </button>}
                      {currentUser?.vai_tro === 'Admin' && <>
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => openProfileEditor(m)} title="Cập nhật chuyên môn và kinh nghiệm">
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
            </div>
            <div className="modal-footer"><button type="button" className="btn btn-secondary" onClick={() => setEditingMentor(null)}>Hủy</button><button className="btn btn-primary" disabled={modalLoading}>Lưu thay đổi</button></div>
          </form>
        </div>
      </div>}

      {assignmentMentor && <div className="modal-overlay" onClick={() => !modalLoading && setAssignmentMentor(null)}>
        <div className="modal-container mentor-assignment-dialog" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header"><div><h3>Phân công thực tập sinh</h3><p>{assignmentMentor.ho_ten} · {assignmentMentor.phong_ban || 'Chưa phân phòng'}</p></div><button className="modal-close-btn" type="button" disabled={modalLoading} onClick={() => setAssignmentMentor(null)}><X size={18} /></button></div>
          <form noValidate onSubmit={assignIntern}>
            <div className="modal-body mentor-assignment-body">
              <label className="manual-assignment-option"><input type="checkbox" checked={manualAssignments} disabled={modalLoading} onChange={(event) => { setManualAssignments(event.target.checked); openAssignmentPicker(assignmentMentor, event.target.checked); }} /><span><strong>Phân công thủ công (tạm thời)</strong><small>Admin/HR được chọn mọi TTS, bỏ qua điều kiện duyệt, thời gian và trùng thời gian giữa các chương trình. Chuyển Mentor cần xác nhận; lịch sử vẫn được lưu.</small></span></label>
              <div className="mentor-assignment-filters">
                <input className="form-control" aria-label="Tìm TTS theo tên, email hoặc mã hồ sơ" placeholder="Tìm tên, email, mã hồ sơ…" value={assignmentSearch} onChange={(event) => setAssignmentSearch(event.target.value)} />
                <select className="form-control" aria-label="Lọc chương trình" value={assignmentProgram} onChange={(event) => setAssignmentProgram(event.target.value)}><option value="">Tất cả chương trình</option><option value="profile">Hồ sơ chưa gắn chương trình</option>{candidatePrograms.map((intern) => <option key={intern.ma_chuong_trinh} value={intern.ma_chuong_trinh}>{intern.ten_ct}</option>)}</select>
                <select className="form-control" aria-label="Lọc trạng thái phân công" value={assignmentStatus} onChange={(event) => setAssignmentStatus(event.target.value)}><option value="all">Tất cả trạng thái</option><option value="available">Có thể phân công</option><option value="assigned">Đã phân công</option></select>
              </div>
                <div className="assignment-selection-summary">
                  <span>TTS đang hướng dẫn: <strong>{assignmentMentor.so_tts_dang_huong_dan || 0} TTS</strong></span>
                  <span>Đang chọn: <strong>{selectedInternIds.length} TTS</strong></span>
                </div>
              {modalLoading ? <p className="workspace-empty">Đang tải danh sách thực tập sinh…</p> : <div className="assignment-transfer-grid">
                <section className="assignment-transfer-column">
                  <header><div><strong>Hồ sơ và chương trình</strong><small>{filteredCandidates.length} hồ sơ · Chọn chương trình cụ thể để xem các lượt khác</small></div></header>
                  <div className="assignment-transfer-list">
                    {filteredCandidates.length === 0 ? <p className="workspace-empty">Không có hồ sơ phù hợp với bộ lọc. Hồ sơ cần được duyệt và có chương trình hiện tại/sắp tới hợp lệ; hồ sơ đang thực tập chưa đăng ký chương trình cũng có thể phân công.</p> : filteredCandidates.map((intern) => {
                      const key = candidateKey(intern);
                      const selected = selectedInternIds.includes(key);
                      return <button type="button" key={key} disabled={!intern.eligible} className={`assignment-candidate${selected ? ' selected' : ''}`}
                        onClick={() => setSelectedInternIds((items) => selected ? items.filter((id) => id !== key) : [...items, key])}>
                        <span className="assignment-check-mark">{selected ? '✓' : '+'}</span><span><strong>{intern.ho_ten} · #{intern.ma_ho_so}</strong><small>{intern.eligible ? 'Chưa phân công' : (intern.mentor_id ? `Đã phân công: ${intern.mentor_name}` : 'Chưa đủ điều kiện')}</small>{intern.reason && <small className="assignment-ineligible-reason">{intern.reason}</small>}<small>{intern.email}</small><small>{intern.ten_truong || 'Chưa cập nhật trường'} · {intern.chuyen_nganh || 'Chưa cập nhật chuyên ngành'}</small><small>Chương trình: {intern.ten_ct || 'Hồ sơ chưa gắn chương trình'}{intern.timeline_status === 'UPCOMING' ? ' · Sắp tới' : ''}</small></span>
                      </button>;
                    })}
                  </div>
                </section>
                <section className="assignment-transfer-column assignment-selected-column">
                  <header><div><strong>Danh sách sẽ gán</strong><small>{selectedInternIds.length} đã chọn</small></div><button type="button" className="btn btn-secondary btn-sm" onClick={() => setSelectedInternIds([])} disabled={!selectedInternIds.length}>Bỏ chọn</button></header>
                  <div className="assignment-transfer-list">
                    {selectedInternIds.length === 0 ? <p className="workspace-empty">Chọn TTS ở cột bên trái để thêm vào đợt phân công.</p> : selectedInternIds.map((id) => {
                      const intern = unassignedInterns.find((item) => candidateKey(item) === id);
                      return intern ? <button type="button" key={id} className="assignment-candidate selected" onClick={() => setSelectedInternIds((items) => items.filter((item) => item !== id))}>
                        <span className="assignment-check-mark">−</span><span><strong>{intern.ho_ten} · #{intern.ma_ho_so}</strong><small>{intern.email}</small><small>{intern.ten_ct || 'Hồ sơ chưa gắn chương trình'}</small></span>
                      </button> : null;
                    })}
                  </div>
                </section>
              </div>}
            </div>
            <div className="modal-footer"><button type="button" className="btn btn-secondary" disabled={modalLoading} onClick={() => setAssignmentMentor(null)}>Đóng</button><button className="btn btn-primary" disabled={modalLoading || selectedInternIds.length === 0}><Users size={15} />Phân công {selectedInternIds.length || ''}</button></div>
          </form>
        </div>
      </div>}

      {assignedMentor && <div className="modal-overlay" onClick={() => setAssignedMentor(null)}>
        <div className="modal-container" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header"><h3>TTS do {assignedMentor.ho_ten} hướng dẫn</h3><button className="modal-close-btn" type="button" onClick={() => setAssignedMentor(null)}><X size={18} /></button></div>
          <div className="modal-body">
            {manualAssignments && <p className="mentor-unassign-note">Chế độ thủ công: có thể gỡ cả phân công cũ. Quan hệ được chuyển vào lịch sử, hồ sơ và dữ liệu nghiệp vụ được giữ nguyên.</p>}
            <p className="mentor-capacity-summary">Đang hướng dẫn: {currentAssignedCount} TTS · Đã phân công sắp tới: {upcomingAssignedCount} TTS. KPI đang hướng dẫn chỉ tính chương trình hiện tại.</p>
            {modalLoading ? <p>Đang tải danh sách...</p> : currentAssignedInterns.length === 0 ? <p>Mentor chưa có thực tập sinh đang tham gia chương trình hiện tại.</p> : <div className="mentor-intern-list">
              {currentAssignedInterns.map((intern) => <div className="mentor-intern-item" key={`${intern.ma_ho_so}-${intern.ma_chuong_trinh ?? 'legacy'}`}>
                <div>
                  <strong>{intern.ho_ten}</strong>
                  <div className="text-muted">{intern.email} · {intern.ten_truong || 'Chưa có trường'} · {intern.chuyen_nganh || 'Chưa có chuyên ngành'}</div>
                  {intern.ten_ct && <div style={{ fontSize: '12px', color: 'var(--brand-primary, #0284c7)', marginTop: '2px' }}>Chương trình: <strong>{intern.ten_ct}</strong> {intern.timeline_status ? `(${intern.timeline_status === 'CURRENT' ? 'Đang thực tập' : (intern.timeline_status === 'UPCOMING' ? 'Sắp tới' : 'Lịch sử')})` : ''}</div>}
                </div>
                {(manualAssignments || intern.timeline_status !== 'HISTORICAL') && ['Admin', 'HR'].includes(currentUser?.vai_tro) && <button type="button" className="btn btn-danger btn-sm" onClick={() => setPendingUnassignment(intern)} disabled={removingProfileId === intern.ma_ho_so} title="Gỡ phân công khỏi chương trình hiện tại" aria-label={`Gỡ phân công ${intern.ho_ten}`}><Trash2 size={14} />Gỡ phân công</button>}
              </div>)}
            </div>}
          </div>
          <div className="modal-footer"><button type="button" className="btn btn-secondary" onClick={() => setAssignedMentor(null)}>Đóng</button></div>
        </div>
      </div>}

      <ConfirmDialog
        open={confirmMentorTransfer}
        title="Xác nhận chuyển Mentor?"
        message="Một số hồ sơ đã có Mentor trong chương trình được chọn. Tiếp tục sẽ chuyển các hồ sơ đó sang Mentor này và lưu Mentor trước vào lịch sử."
        confirmLabel="Xác nhận chuyển"
        busy={modalLoading}
        onCancel={() => setConfirmMentorTransfer(false)}
        onConfirm={() => assignIntern(null, true)}
      />
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
