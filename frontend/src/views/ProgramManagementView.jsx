import React, { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch, readJsonResponse } from '../utils/api';
import CustomSelect from '../components/CustomSelect';
import FloatingTableScrollbar from '../components/FloatingTableScrollbar';
import DashboardMetrics from '../components/DashboardMetrics';
import TablePagination from '../components/TablePagination';
import { signalDashboardMetricsChanged } from '../utils/dashboardMetrics';
import {
  Check,
  Clock,
  Eye,
  FileText,
  Lock,
  Pencil,
  PlusCircle,
  RefreshCw,
  Send,
  Users,
  X,
  XCircle,
} from 'lucide-react';
import ConfirmDialog from '../components/ConfirmDialog';

const emptyForm = {
  ma_ct: '',
  ten_ct: '',
  ma_phong_ban: '',
  ngay_bat_dau: '',
  ngay_ket_thuc: '',
  chi_tieu: 10,
  mo_ta_cong_viec: '',
  yeu_cau: '',
};

const statusLabels = {
  DangMo: 'Đang nhận hồ sơ',
  TamDung: 'Tạm dừng',
  DaDong: 'Đã đóng',
  ChoDuyet: 'Chờ duyệt',
  DaDuyet: 'Đã duyệt',
  TuChoi: 'Từ chối',
};

function StatusBadge({ status }) {
  const badgeClass = status === 'DangMo' || status === 'DaDuyet'
    ? 'badge-success'
    : status === 'ChoDuyet' || status === 'TamDung'
      ? 'badge-warning'
      : 'badge-danger';
  return <span className={`badge ${badgeClass}`}><span className="badge-dot" />{statusLabels[status] || status}</span>;
}

function formatDate(value) {
  return value ? new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString('vi-VN') : 'Chưa thiết lập';
}

export default function ProgramManagementView({ departments, onShowToast, currentUser }) {
  const isAdmin = currentUser?.vai_tro === 'Admin';
  const canCreateProgram = ['Admin', 'HR'].includes(currentUser?.vai_tro);
  const isManager = ['Admin', 'HR'].includes(currentUser?.vai_tro);
  const isIntern = currentUser?.vai_tro === 'ThucTapSinh';

  const [programs, setPrograms] = useState([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [totalPrograms, setTotalPrograms] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingProgram, setEditingProgram] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [detailProgram, setDetailProgram] = useState(null);
  const [applicantProgram, setApplicantProgram] = useState(null);
  const [applicationProgram, setApplicationProgram] = useState(null);
  const [applicationCv, setApplicationCv] = useState(null);
  const [applicationProfile, setApplicationProfile] = useState(null);
  const [applicationProfileLoading, setApplicationProfileLoading] = useState(false);
  const [applicationProfileError, setApplicationProfileError] = useState('');
  const [useApprovedProfile, setUseApprovedProfile] = useState(false);
  const [applicants, setApplicants] = useState([]);
  const [applicantPage, setApplicantPage] = useState(1);
  const [applicantPageSize, setApplicantPageSize] = useState(10);
  const [applicantTotal, setApplicantTotal] = useState(0);
  const [applicantTotalPages, setApplicantTotalPages] = useState(0);
  const [applicantsLoading, setApplicantsLoading] = useState(false);
  const [pendingClose, setPendingClose] = useState(null);
  const [pendingReject, setPendingReject] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [reviewSubmitting, setReviewSubmitting] = useState(false);
  const tableScrollRef = useRef(null);
  const applicationLookupRef = useRef(0);

  const requestPrograms = useCallback(async (requestedPage, requestedPageSize, signal) => {
    const params = new URLSearchParams({ page: String(requestedPage), pageSize: String(requestedPageSize) });
    const response = await apiFetch('/api/programs?' + params.toString(), { signal });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Không thể tải danh sách chương trình.');
    return data;
  }, []);

  const refreshPrograms = useCallback(async (requestedPage = page, requestedPageSize = pageSize, signal) => {
    try {
      const data = await requestPrograms(requestedPage, requestedPageSize, signal);
      setPrograms(Array.isArray(data) ? data : (Array.isArray(data.items) ? data.items : []));
      setPage(Array.isArray(data) ? 1 : Number(data.page) || requestedPage);
      setPageSize(Array.isArray(data) ? requestedPageSize : Number(data.pageSize) || requestedPageSize);
      setTotalPrograms(Array.isArray(data) ? data.length : Number(data.totalItems) || 0);
      setTotalPages(Array.isArray(data) ? (data.length ? 1 : 0) : Number(data.totalPages) || 0);
      setErrorMsg('');
      signalDashboardMetricsChanged();
    } catch (error) {
      if (error.name !== 'AbortError') setErrorMsg(error.message);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, requestPrograms]);

  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    requestPrograms(page, pageSize, controller.signal)
      .then((data) => {
        if (!current) return;
        const rows = Array.isArray(data) ? data : (Array.isArray(data.items) ? data.items : []);
        setPrograms(rows);
        setPage(Array.isArray(data) ? 1 : Number(data.page) || page);
        setPageSize(Array.isArray(data) ? pageSize : Number(data.pageSize) || pageSize);
        setTotalPrograms(Array.isArray(data) ? rows.length : Number(data.totalItems) || 0);
        setTotalPages(Array.isArray(data) ? (rows.length ? 1 : 0) : Number(data.totalPages) || 0);
        setErrorMsg('');
        signalDashboardMetricsChanged();
      })
      .catch((error) => { if (current && error.name !== 'AbortError') setErrorMsg(error.message); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; controller.abort(); };
  }, [requestPrograms, page, pageSize]);

  const resetForm = () => {
    setForm(emptyForm);
    setEditingProgram(null);
    setShowForm(false);
  };

  const openCreateForm = () => {
    setEditingProgram(null);
    setForm(emptyForm);
    setShowForm(true);
  };

  const openEditForm = (program) => {
    setEditingProgram(program);
    setForm({
      ma_ct: program.ma_ct,
      ten_ct: program.ten_ct,
      ma_phong_ban: program.ma_phong_ban ? String(program.ma_phong_ban) : '',
      ngay_bat_dau: program.ngay_bat_dau || '',
      ngay_ket_thuc: program.ngay_ket_thuc || '',
      chi_tieu: program.chi_tieu,
      mo_ta_cong_viec: program.mo_ta_cong_viec || '',
      yeu_cau: program.yeu_cau || '',
    });
    setShowForm(true);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((previous) => ({ ...previous, [name]: value }));
  };

  const handleSaveProgram = async (event) => {
    event.preventDefault();
    if (!form.ma_ct.trim() || !form.ten_ct.trim() || !form.ma_phong_ban || !form.ngay_bat_dau || !form.ngay_ket_thuc || !form.mo_ta_cong_viec.trim() || !form.yeu_cau.trim()) {
      onShowToast('Vui lòng nhập đầy đủ các trường bắt buộc của chương trình.', 'error');
      return;
    }
    if (form.ngay_ket_thuc < form.ngay_bat_dau) {
      onShowToast('Ngày kết thúc phải sau hoặc bằng ngày bắt đầu.', 'error');
      return;
    }
    setSubmitting(true);
    try {
      const response = await apiFetch(
        editingProgram ? `/api/programs/${editingProgram.ma_chuong_trinh}` : '/api/programs',
        {
          method: editingProgram ? 'PUT' : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ...form,
            ma_ct: form.ma_ct.trim(),
            ten_ct: form.ten_ct.trim(),
            ma_phong_ban: Number(form.ma_phong_ban),
            chi_tieu: Number(form.chi_tieu),
            mo_ta_cong_viec: form.mo_ta_cong_viec.trim(),
            yeu_cau: form.yeu_cau.trim(),
          }),
        },
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Không thể lưu chương trình.');
      onShowToast(data.message);
      resetForm();
      setPage(1);
      setLoading(true);
      await refreshPrograms(1, pageSize);
    } catch (error) {
      onShowToast(error.message, 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const closeApplication = () => {
    applicationLookupRef.current += 1;
    setApplicationProgram(null);
    setApplicationCv(null);
    setApplicationProfile(null);
    setApplicationProfileError('');
    setApplicationProfileLoading(false);
    setUseApprovedProfile(false);
  };

  const openApplication = async (program) => {
    const lookup = applicationLookupRef.current + 1;
    applicationLookupRef.current = lookup;
    setApplicationProgram(program);
    setApplicationCv(null);
    setApplicationProfile(null);
    setApplicationProfileError('');
    setUseApprovedProfile(false);
    setApplicationProfileLoading(true);
    try {
      const response = await apiFetch('/api/interns/me/workspace');
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể kiểm tra hồ sơ đã duyệt.');
      if (lookup !== applicationLookupRef.current) return;
      const approvedCv = (data.documents || []).find((document) => (
        document.loai_tai_lieu === 'CV' && document.trang_thai_duyet === 'DaDuyet'
      ));
      const canReuse = data.profile?.trang_thai_xet_duyet === 'DaDuyet' && Boolean(approvedCv);
      setApplicationProfile({ profile: data.profile, approvedCv, canReuse });
      setUseApprovedProfile(canReuse);
    } catch (error) {
      if (lookup === applicationLookupRef.current) {
        setApplicationProfileError(error.message || 'Không thể kiểm tra hồ sơ đã duyệt. Bạn có thể tải CV lên riêng.');
      }
    } finally {
      if (lookup === applicationLookupRef.current) setApplicationProfileLoading(false);
    }
  };

  const handleApply = async (event) => {
    event.preventDefault();
    if (!applicationProgram || (!useApprovedProfile && !applicationCv)) {
      onShowToast('Vui lòng chọn hồ sơ đã duyệt hoặc đính kèm CV.', 'error');
      return;
    }
    setSubmitting(true);
    try {
      const payload = new FormData();
      payload.append('use_approved_profile', String(useApprovedProfile));
      if (!useApprovedProfile) payload.append('cv', applicationCv);
      const response = await apiFetch(`/api/programs/${applicationProgram.ma_chuong_trinh}/apply`, { method: 'POST', body: payload });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể ứng tuyển chương trình.');
      onShowToast(data.message);
      closeApplication();
      await refreshPrograms();
    } catch (error) {
      onShowToast(error.message, 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const loadApplicants = async (program, requestedPage = applicantPage, requestedPageSize = applicantPageSize) => {
    setApplicantProgram(program);
    setApplicantsLoading(true);
    try {
      const params = new URLSearchParams({ page: String(requestedPage), pageSize: String(requestedPageSize) });
      const response = await apiFetch(`/api/programs/${program.ma_chuong_trinh}/applications?${params.toString()}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Không thể tải danh sách ứng viên.');
      setApplicants(Array.isArray(data) ? data : (Array.isArray(data.items) ? data.items : []));
      setApplicantPage(Array.isArray(data) ? 1 : Number(data.page) || requestedPage);
      setApplicantPageSize(Array.isArray(data) ? requestedPageSize : Number(data.pageSize) || requestedPageSize);
      setApplicantTotal(Array.isArray(data) ? data.length : Number(data.totalItems) || 0);
      setApplicantTotalPages(Array.isArray(data) ? (data.length ? 1 : 0) : Number(data.totalPages) || 0);
    } catch (error) {
      onShowToast(error.message, 'error');
      setApplicantProgram(null);
    } finally {
      setApplicantsLoading(false);
    }
  };

  const reviewApplicant = async (application, status, reason = '') => {
    setReviewSubmitting(true);
    try {
      const response = await apiFetch(
        `/api/programs/${application.ma_chuong_trinh}/applications/${application.ma_ung_tuyen}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ trang_thai: status, reject_reason: status === 'TuChoi' ? reason : undefined }),
        },
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Không thể cập nhật đơn ứng tuyển.');
      onShowToast(data.message);
      if (status === 'TuChoi') {
        setPendingReject(null);
        setRejectReason('');
      }
      await loadApplicants(applicantProgram);
      await refreshPrograms();
    } catch (error) {
      onShowToast(error.message, 'error');
    } finally {
      setReviewSubmitting(false);
    }
  };

  const closeProgram = async () => {
    if (!pendingClose) return;
    try {
      const response = await apiFetch(`/api/programs/${pendingClose.ma_chuong_trinh}/close`, { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Không thể đóng chương trình.');
      onShowToast(data.message);
      setPendingClose(null);
      await refreshPrograms();
    } catch (error) {
      onShowToast(error.message, 'error');
    }
  };

  return (
    <div className="program-management-page">
      <div className="program-page-heading">
        <div>
          <h2>{isIntern ? 'Chương trình thực tập đang mở' : 'Chương trình Thực tập'}</h2>
          <p>{isIntern ? 'Khám phá và đăng ký các chương trình phù hợp với hồ sơ của bạn' : 'Thiết lập các đợt thực tập và quản lý danh sách ứng viên'}</p>
        </div>
        {canCreateProgram && (
          <button type="button" className="btn btn-primary" onClick={showForm ? resetForm : openCreateForm}>
            {showForm ? <X size={16} /> : <PlusCircle size={16} />}
            <span>{showForm ? 'Đóng biểu mẫu' : 'Tạo chương trình'}</span>
          </button>
        )}
      </div>

      {isManager && <DashboardMetrics section="programs" />}

      {canCreateProgram && showForm && (!editingProgram || isAdmin) && (
        <div className="card program-form-card">
          <div className="card-header">
            <div className="card-title-box"><h2>{editingProgram ? 'Chỉnh sửa chương trình' : 'Tạo mới chương trình thực tập'}</h2></div>
          </div>
          <div className="card-body">
            <form noValidate onSubmit={handleSaveProgram} className="form-grid program-form-grid">
              <div className="form-group">
                <label className="form-label">Mã CT <span className="required">*</span></label>
                <input type="text" name="ma_ct" className="form-control" maxLength="40" required
                  placeholder="CT-2026-01" value={form.ma_ct} onChange={handleChange} />
              </div>
              <div className="form-group">
                <label className="form-label">Tên chương trình <span className="required">*</span></label>
                <input type="text" name="ten_ct" className="form-control" maxLength="200" required
                  placeholder="Thực tập Backend mùa hè 2026" value={form.ten_ct} onChange={handleChange} />
              </div>
              <div className="form-group">
                <label className="form-label">Phòng ban <span className="required">*</span></label>
                <CustomSelect name="ma_phong_ban" className="form-select" required value={form.ma_phong_ban} onChange={handleChange}>
                  <option value="">-- Chọn phòng ban --</option>
                  {departments.map((department) => (
                    <option key={department.ma_phong_ban} value={department.ma_phong_ban}>{department.ten_phong_ban}</option>
                  ))}
                </CustomSelect>
              </div>
              <div className="form-group">
                <label className="form-label">Chỉ tiêu số lượng <span className="required">*</span></label>
                <input type="number" name="chi_tieu" className="form-control" min="1" required value={form.chi_tieu} onChange={handleChange} />
              </div>
              <div className="form-group">
                <label className="form-label">Thời gian bắt đầu <span className="required">*</span></label>
                <input type="date" name="ngay_bat_dau" className="form-control" required value={form.ngay_bat_dau} onChange={handleChange} />
              </div>
              <div className="form-group">
                <label className="form-label">Thời gian kết thúc <span className="required">*</span></label>
                <input type="date" name="ngay_ket_thuc" className="form-control" min={form.ngay_bat_dau || undefined}
                  required value={form.ngay_ket_thuc} onChange={handleChange} />
              </div>
              <div className="form-group form-full">
                <label className="form-label">Mô tả công việc <span className="required">*</span></label>
                <textarea name="mo_ta_cong_viec" className="form-textarea" rows="4" required
                  placeholder="Mô tả nhiệm vụ, công nghệ và phạm vi công việc..." value={form.mo_ta_cong_viec} onChange={handleChange} />
              </div>
              <div className="form-group form-full">
                <label className="form-label">Yêu cầu ứng viên <span className="required">*</span></label>
                <textarea name="yeu_cau" className="form-textarea" rows="4" required
                  placeholder="Kiến thức, kỹ năng và điều kiện ứng tuyển..." value={form.yeu_cau} onChange={handleChange} />
              </div>
              <div className="form-full program-form-actions">
                <button type="button" className="btn btn-secondary" onClick={resetForm} disabled={submitting}>Hủy</button>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {editingProgram ? <Pencil size={15} /> : <PlusCircle size={15} />}
                  <span>{submitting ? 'Đang lưu...' : editingProgram ? 'Lưu thay đổi' : 'Xác nhận tạo'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="card program-list-card">
        <div className="card-header">
          <div className="card-title-box"><h2>{isIntern ? 'Danh sách chương trình đang mở' : 'Các chương trình đào tạo'}{loading || errorMsg ? '' : ` (${totalPrograms})`}</h2></div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setLoading(true); refreshPrograms(); }} disabled={loading}>
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /><span>Làm mới</span>
          </button>
        </div>
        <div className="table-responsive program-table-scroll" ref={tableScrollRef}>
          <table className="data-table program-data-table">
            <thead><tr>
              <th>Mã CT</th><th>Tên chương trình</th><th>Phòng ban</th><th>Thời gian</th>
              <th>Chỉ tiêu</th>{isManager && <th>Ứng viên</th>}<th>Trạng thái</th><th>Thao tác</th>
            </tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={isManager ? 8 : 7} className="program-empty-cell">Đang tải dữ liệu...</td></tr>
                : errorMsg ? <tr><td colSpan={isManager ? 8 : 7} className="program-empty-cell program-error-cell">{errorMsg}</td></tr>
                  : programs.length === 0 ? <tr><td colSpan={isManager ? 8 : 7} className="program-empty-cell">{isIntern ? 'Hiện chưa có chương trình nào đang mở.' : 'Chưa có chương trình thực tập.'}</td></tr>
                    : programs.map((program) => (
                      <tr key={program.ma_chuong_trinh}>
                        <td className="program-code-cell">{program.ma_ct}</td>
                        <td><strong>{program.ten_ct}</strong></td>
                        <td>{program.phong_ban || 'Chưa phân phòng'}</td>
                        <td><span className="program-date"><Clock size={13} />{formatDate(program.ngay_bat_dau)} – {formatDate(program.ngay_ket_thuc)}</span></td>
                        <td><strong>{program.chi_tieu}</strong></td>
                        {isManager && <td><span className="program-applicant-count">{program.so_ung_vien} hồ sơ{program.so_cho_duyet > 0 ? ` · ${program.so_cho_duyet} chờ` : ''}</span></td>}
                        <td>{isIntern && program.trang_thai_ung_tuyen ? <StatusBadge status={program.trang_thai_ung_tuyen} /> : <StatusBadge status={program.trang_thai} />}</td>
                        <td><div className="program-row-actions">
                          <button type="button" className="btn btn-secondary btn-sm" title="Xem chi tiết" onClick={() => setDetailProgram(program)}><Eye size={13} /><span>Chi tiết</span></button>
                          {isManager && <button type="button" className="btn btn-secondary btn-sm" title="Danh sách ứng viên" onClick={() => loadApplicants(program)}><Users size={13} /><span>Ứng viên</span></button>}
                          {isAdmin && <button type="button" className="btn btn-outline-primary btn-sm" title="Chỉnh sửa" onClick={() => openEditForm(program)}><Pencil size={13} /><span>Sửa</span></button>}
                          {isAdmin && program.trang_thai !== 'DaDong' && <button type="button" className="btn btn-danger btn-sm" title="Đóng đợt" onClick={() => setPendingClose(program)}><Lock size={13} /><span>Đóng đợt</span></button>}
                          {isIntern && (!program.trang_thai_ung_tuyen
                            ? <button type="button" className="btn btn-primary btn-sm" disabled={submitting} onClick={() => openApplication(program)}><Send size={13} /><span>Ứng tuyển</span></button>
                            : program.trang_thai_ung_tuyen === 'DaDuyet' ? null : <button type="button" className="btn btn-secondary btn-sm" disabled><Check size={13} /><span>{program.trang_thai_ung_tuyen === 'ChoDuyet' ? 'Chờ duyệt' : 'Đã từ chối'}</span></button>)}
                        </div></td>
                      </tr>
                    ))}
            </tbody>
          </table>
        </div>
        <TablePagination
          page={page}
          pageSize={pageSize}
          totalItems={totalPrograms}
          totalPages={totalPages}
          itemLabel="chương trình"
          disabled={loading}
          onPageChange={(nextPage) => { setLoading(true); setPage(nextPage); }}
          onPageSizeChange={(size) => { setLoading(true); setPage(1); setPageSize(size); }}
        />
      </div>

      <FloatingTableScrollbar
        scrollContainerRef={tableScrollRef}
        refreshKey={`${programs.length}:${loading}:${isManager}`}
        label="Cuộn ngang danh sách chương trình thực tập"
      />

      {detailProgram && (
        <div className="modal-overlay" onMouseDown={(event) => event.target === event.currentTarget && setDetailProgram(null)}>
          <section className="modal-container program-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="program-detail-title">
            <div className="modal-header">
              <div><h3 id="program-detail-title">{detailProgram.ten_ct}</h3><p>{detailProgram.ma_ct} · {detailProgram.phong_ban}</p></div>
              <button type="button" className="modal-close-btn" aria-label="Đóng" onClick={() => setDetailProgram(null)}><X size={18} /></button>
            </div>
            <div className="modal-body program-detail-body">
              <div className="program-detail-meta">
                <span><strong>Thời gian</strong>{formatDate(detailProgram.ngay_bat_dau)} – {formatDate(detailProgram.ngay_ket_thuc)}</span>
                <span><strong>Chỉ tiêu</strong>{detailProgram.chi_tieu} thực tập sinh</span>
                <span><strong>Trạng thái</strong><StatusBadge status={detailProgram.trang_thai_ung_tuyen || detailProgram.trang_thai} /></span>
              </div>
              <div><h4>Mô tả công việc</h4><p>{detailProgram.mo_ta_cong_viec || 'Chưa cập nhật.'}</p></div>
              <div><h4>Yêu cầu ứng viên</h4><p>{detailProgram.yeu_cau || 'Chưa cập nhật.'}</p></div>
            </div>
          </section>
        </div>
      )}

      {applicantProgram && (
        <div className="modal-overlay" onMouseDown={(event) => event.target === event.currentTarget && setApplicantProgram(null)}>
          <section className="modal-container program-applicants-dialog" role="dialog" aria-modal="true" aria-labelledby="program-applicants-title">
            <div className="modal-header">
              <div><h3 id="program-applicants-title">Danh sách ứng viên</h3><p>{applicantProgram.ten_ct}</p></div>
              <button type="button" className="modal-close-btn" aria-label="Đóng" onClick={() => setApplicantProgram(null)}><X size={18} /></button>
            </div>
            <div className="modal-body program-applicants-body">
              {applicantsLoading ? <div className="program-modal-message">Đang tải danh sách...</div>
                : applicants.length === 0 ? <div className="program-modal-message">Chưa có ứng viên đăng ký.</div>
                  : <><div className="table-responsive program-applicants-scroll"><table className="data-table program-applicants-table">
                    <thead><tr><th>Ứng viên</th><th>Trường / Chuyên ngành</th><th>Ngày ứng tuyển</th><th>Trạng thái</th>{isManager && <th>Thao tác</th>}</tr></thead>
                    <tbody>{applicants.map((application) => <tr key={application.ma_ung_tuyen}>
                      <td><strong>{application.ho_ten}</strong><small>{application.email}<br />{application.so_dien_thoai || 'Chưa có SĐT'}</small></td>
                      <td>{application.ten_truong || 'Chưa cập nhật'}<small>{application.chuyen_nganh || 'Chưa cập nhật'}</small></td>
                      <td>{application.ngay_ung_tuyen ? new Date(application.ngay_ung_tuyen).toLocaleString('vi-VN') : '—'}</td>
                      <td><StatusBadge status={application.trang_thai} /></td>
                      {isManager && <td>{application.trang_thai === 'ChoDuyet' ? <div className="program-row-actions">
                        <button type="button" className="btn btn-primary btn-sm" disabled={reviewSubmitting} onClick={() => reviewApplicant(application, 'DaDuyet')}><Check size={13} />Duyệt</button>
                        <button type="button" className="btn btn-danger btn-sm" disabled={reviewSubmitting} onClick={() => { setPendingReject(application); setRejectReason(''); }}><XCircle size={13} />Từ chối</button>
                      </div> : <span className="program-applicant-count">Đã xử lý</span>}</td>}
                    </tr>)}</tbody>
                  </table></div>
                    <TablePagination
                      page={applicantPage}
                      pageSize={applicantPageSize}
                      totalItems={applicantTotal}
                      totalPages={applicantTotalPages}
                      itemLabel="ứng viên"
                      disabled={applicantsLoading}
                      onPageChange={(nextPage) => loadApplicants(applicantProgram, nextPage, applicantPageSize)}
                      onPageSizeChange={(size) => {
                        setApplicantPage(1);
                        setApplicantPageSize(size);
                        loadApplicants(applicantProgram, 1, size);
                      }}
                    />
                  </>}
            </div>
          </section>
        </div>
      )}

      {pendingReject && (
        <div className="modal-overlay" onMouseDown={(event) => event.target === event.currentTarget && !reviewSubmitting && setPendingReject(null)}>
          <section className="modal-container program-reject-dialog" role="dialog" aria-modal="true" aria-labelledby="program-reject-title">
            <div className="modal-header">
              <div>
                <h3 id="program-reject-title">Từ chối hồ sơ ứng tuyển</h3>
                <p>{pendingReject.ho_ten} · {applicantProgram?.ten_ct}</p>
              </div>
              <button type="button" className="modal-close-btn" aria-label="Đóng" disabled={reviewSubmitting} onClick={() => setPendingReject(null)}><X size={18} /></button>
            </div>
            <div className="modal-body program-reject-body">
              <label className="form-label" htmlFor="program-reject-reason">Lý do hoặc ghi chú (không bắt buộc)</label>
              <textarea
                id="program-reject-reason"
                className="form-control program-reject-reason"
                maxLength={1000}
                value={rejectReason}
                onChange={(event) => setRejectReason(event.target.value)}
                disabled={reviewSubmitting}
                placeholder="Nhập ghi chú để gửi kèm email kết quả..."
              />
              <small className="program-reject-counter">{rejectReason.length}/1000 ký tự</small>
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-secondary" disabled={reviewSubmitting} onClick={() => setPendingReject(null)}>Hủy</button>
              <button type="button" className="btn btn-danger" disabled={reviewSubmitting} onClick={() => reviewApplicant(pendingReject, 'TuChoi', rejectReason)}>
                <XCircle size={14} /><span>{reviewSubmitting ? 'Đang xử lý...' : 'Xác nhận từ chối'}</span>
              </button>
            </div>
          </section>
        </div>
      )}

      {applicationProgram && (
        <div className="modal-overlay" onMouseDown={(event) => event.target === event.currentTarget && closeApplication()}>
          <section className="modal-container program-apply-dialog" role="dialog" aria-modal="true" aria-labelledby="program-apply-title">
            <div className="modal-header">
              <div><h3 id="program-apply-title">Ứng tuyển chương trình</h3><p>{applicationProgram.ten_ct} · {applicationProgram.ma_ct}</p></div>
              <button type="button" className="modal-close-btn" aria-label="Đóng" onClick={closeApplication}><X size={18} /></button>
            </div>
            <form noValidate onSubmit={handleApply}>
              <div className="modal-body program-apply-body">
                <div className="apply-confirm-card"><Users size={19} /><span>Ứng tuyển vào <strong>{applicationProgram.ten_ct}</strong>. Bạn có thể dùng lại hồ sơ và CV đã được duyệt, hoặc tải CV riêng. Đơn ứng tuyển vẫn chờ chương trình xét duyệt.</span></div>
                {applicationProfileLoading && <p className="apply-profile-hint">Đang kiểm tra hồ sơ và CV đã duyệt…</p>}
                {applicationProfileError && <p className="apply-profile-error">{applicationProfileError} Vui lòng tải CV riêng để tiếp tục.</p>}
                {applicationProfile?.canReuse && (
                  <div className="apply-profile-options" role="radiogroup" aria-label="Chọn hồ sơ ứng tuyển">
                    <label className={`apply-profile-option${useApprovedProfile ? ' selected' : ''}`}>
                      <input type="radio" name="application-source" checked={useApprovedProfile} onChange={() => setUseApprovedProfile(true)} />
                      <span><strong>Dùng hồ sơ đã duyệt #{applicationProfile.profile.ma_ho_so}</strong><small>CV đã duyệt: {applicationProfile.approvedCv.ten_file || 'CV của hồ sơ'} · không cần tải lại</small></span>
                    </label>
                    <label className={`apply-profile-option${!useApprovedProfile ? ' selected' : ''}`}>
                      <input type="radio" name="application-source" checked={!useApprovedProfile} onChange={() => setUseApprovedProfile(false)} />
                      <span><strong>Tải CV khác cho chương trình này</strong><small>CV riêng sẽ được thêm vào hồ sơ của bạn.</small></span>
                    </label>
                  </div>
                )}
                {!applicationProfileLoading && (!applicationProfile?.canReuse || !useApprovedProfile) && (
                  <label className="apply-cv-dropzone">
                    <input type="file" accept=".pdf,.docx,.png" required onChange={(event) => setApplicationCv(event.target.files?.[0] || null)} />
                    <span className="apply-cv-icon"><FileText size={21} /></span>
                    <strong>{applicationCv?.name || 'Đính kèm CV ứng tuyển'}</strong>
                    <small>PDF, DOCX hoặc PNG · tối đa 15 MB</small>
                  </label>
                )}
              </div>
              <div className="modal-footer"><button type="button" className="btn btn-secondary" disabled={submitting} onClick={closeApplication}>Hủy</button><button type="submit" className="btn btn-primary" disabled={submitting || applicationProfileLoading || (!useApprovedProfile && !applicationCv)}><Send size={15} />{submitting ? 'Đang gửi hồ sơ…' : 'Gửi hồ sơ'}</button></div>
            </form>
          </section>
        </div>
      )}

      <ConfirmDialog
        open={Boolean(pendingClose)}
        title="Đóng đợt thực tập?"
        message={pendingClose ? `Chương trình “${pendingClose.ten_ct}” sẽ ngừng nhận hồ sơ mới.` : ''}
        confirmLabel="Đóng đợt"
        danger
        onConfirm={closeProgram}
        onCancel={() => setPendingClose(null)}
      />
    </div>
  );
}
