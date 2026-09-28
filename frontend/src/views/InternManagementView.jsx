import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiFetch } from '../utils/api';
import { 
  Search, 
  UserPlus, 
  Edit3, 
  Eye, 
  RefreshCw, 
  Phone, 
  Mail,
  AlertCircle,
  Check,
  XCircle,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import InternModal from '../components/InternModal';
import CustomSelect from '../components/CustomSelect';
import FloatingTableScrollbar from '../components/FloatingTableScrollbar';
import DashboardMetrics from '../components/DashboardMetrics';
import { signalDashboardMetricsChanged } from '../utils/dashboardMetrics';

export default function InternManagementView({ 
  departments, 
  universities, 
  onShowToast,
  currentUser
}) {
  const [interns, setInterns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [totalItems, setTotalItems] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [refreshVersion, setRefreshVersion] = useState(0);

  // Filter and Search states
  const [searchTerm, setSearchTerm] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [filterDuyet, setFilterDuyet] = useState('');
  const [filterThucTap, setFilterThucTap] = useState('');
  const [filterPhongBan, setFilterPhongBan] = useState('');
  const [filterTruong, setFilterTruong] = useState('');

  // Modal states for Create / Edit
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedInternId, setSelectedInternId] = useState(null);
  const [modalSession, setModalSession] = useState(0);

  // Detail view modal
  const [detailModalIntern, setDetailModalIntern] = useState(null);
  const tableScrollRef = useRef(null);

  const requestInterns = useCallback(async ({ signal } = {}) => {
    const params = new URLSearchParams();
    if (appliedSearch) params.append('search', appliedSearch);
    if (filterDuyet) params.append('trang_thai_xet_duyet', filterDuyet);
    if (filterThucTap) params.append('trang_thai_thuc_tap', filterThucTap);
    if (filterPhongBan) params.append('ma_phong_ban', filterPhongBan);
    if (filterTruong) params.append('ma_truong', filterTruong);
    params.append('page', page);
    params.append('pageSize', pageSize);

    const res = await apiFetch(`/api/interns?${params.toString()}`, { signal });
    if (!res.ok) throw new Error('Không thể tải danh sách thực tập sinh');
    return res.json();
  }, [appliedSearch, filterDuyet, filterThucTap, filterPhongBan, filterTruong, page, pageSize]);

  useEffect(() => {
    const controller = new AbortController();
    requestInterns({ signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        const items = Array.isArray(data.items) ? data.items : [];
        setInterns(items);
        setTotalItems(Number(data.totalItems) || 0);
        setTotalPages(Number(data.totalPages) || 0);
        setErrorMsg('');
        signalDashboardMetricsChanged();
      })
      .catch((err) => {
        if (err.name !== 'AbortError' && !controller.signal.aborted) setErrorMsg(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [requestInterns, refreshVersion]);

  const refreshInterns = () => {
    setLoading(true);
    setRefreshVersion((version) => version + 1);
  };

  const openInternModal = (internId = null) => {
    setSelectedInternId(internId);
    setModalSession((session) => session + 1);
    setModalOpen(true);
  };

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setLoading(true);
    const queryUnchanged = searchTerm === appliedSearch;
    const alreadyFirstPage = page === 1;
    setAppliedSearch(searchTerm);
    setPage(1);
    if (queryUnchanged && alreadyFirstPage) setRefreshVersion((version) => version + 1);
  };

  const handleResetFilters = () => {
    const alreadyReset = !searchTerm && !appliedSearch && !filterDuyet && !filterThucTap && !filterPhongBan && !filterTruong;
    setLoading(true);
    setSearchTerm('');
    setAppliedSearch('');
    setFilterDuyet('');
    setFilterThucTap('');
    setFilterPhongBan('');
    setFilterTruong('');
    setPage(1);
    if (alreadyReset && page === 1) setRefreshVersion((version) => version + 1);
  };

  const changePage = (nextPage) => {
    if (nextPage < 1 || nextPage > totalPages || nextPage === page) return;
    setLoading(true);
    setPage(nextPage);
  };

  const changePageSize = (event) => {
    setLoading(true);
    setPageSize(Number(event.target.value));
    setPage(1);
  };

  const currentPage = totalPages ? Math.min(page, totalPages) : 0;
  const firstVisiblePage = Math.max(1, Math.min(currentPage - 2, totalPages - 4));
  const visiblePages = Array.from(
    { length: Math.min(totalPages, 5) },
    (_, index) => firstVisiblePage + index,
  );
  const firstVisibleItem = totalItems === 0 ? 0 : ((currentPage - 1) * pageSize) + 1;
  const lastVisibleItem = Math.min(currentPage * pageSize, totalItems);

  const handleApproveIntern = async (intern) => {
    try {
      const res = await apiFetch(`/api/auth/users/${intern.ma_nguoi_dung}/approve`, {
        method: 'PUT',
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Không thể duyệt');
      onShowToast(`Đã duyệt tài khoản: ${intern.ho_ten}`);
      refreshInterns();
    } catch (err) {
      onShowToast(err.message, 'error');
    }
  };

  const handleRejectIntern = async (intern) => {
    try {
      const res = await apiFetch(`/api/auth/users/${intern.ma_nguoi_dung}/reject`, {
        method: 'PUT',
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Không thể từ chối');
      onShowToast(`Đã từ chối tài khoản: ${intern.ho_ten}`);
      refreshInterns();
    } catch (err) {
      onShowToast(err.message, 'error');
    }
  };

  const getDuyetBadge = (status) => {
    switch (status) {
      case 'DaDuyet':
        return <span className="badge badge-success"><span className="badge-dot" />Đã duyệt</span>;
      case 'TuChoi':
        return <span className="badge badge-danger"><span className="badge-dot" />Từ chối</span>;
      default:
        return <span className="badge badge-warning"><span className="badge-dot" />Chờ duyệt</span>;
    }
  };

  const getThucTapBadge = (status) => {
    switch (status) {
      case 'DangThucTap':
        return <span className="badge badge-info"><span className="badge-dot" />Đang thực tập</span>;
      case 'HoanThanh':
        return <span className="badge badge-success"><span className="badge-dot" />Hoàn thành</span>;
      case 'ThoiHoc':
        return <span className="badge badge-danger"><span className="badge-dot" />Thôi học</span>;
      default:
        return <span className="badge badge-secondary">{status}</span>;
    }
  };

  const getAccountBadge = (status) => {
    switch (status) {
      case 'HoatDong':
        return <span className="badge badge-success"><span className="badge-dot" />Hoạt động</span>;
      case 'Khoa':
        return <span className="badge badge-danger"><span className="badge-dot" />Bị khóa</span>;
      default:
        return <span className="badge badge-warning"><span className="badge-dot" />Chờ duyệt</span>;
    }
  };

  return (
    <div className="intern-management-page">
      {/* Header and Actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>Danh sách Thực tập sinh</h2>
          <p style={{ fontSize: '13px', color: '#64748b' }}>
            Quản lý hồ sơ, thông tin đào tạo và trạng thái thực tập của sinh viên
          </p>
        </div>

        <button 
          className="btn btn-primary"
          onClick={() => openInternModal()}
        >
          <UserPlus size={16} />
          <span>Thêm thực tập sinh</span>
        </button>
      </div>

      <DashboardMetrics section="interns" filters={{ ma_phong_ban: filterPhongBan, ma_truong: filterTruong }} />

      {errorMsg && (
        <div className="alert-banner error" style={{ padding: '10px 14px', marginBottom: '16px' }}>
          <AlertCircle size={16} />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="filter-bar intern-filter-bar">
        <form onSubmit={handleSearchSubmit} className="search-input-box">
          <Search size={16} className="search-icon" />
          <input
            type="text"
            placeholder="Tìm theo họ tên, email, chuyên ngành..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </form>

        <CustomSelect
          className="filter-select"
          value={filterDuyet}
          onChange={(e) => { setLoading(true); setFilterDuyet(e.target.value); setPage(1); }}
        >
          <option value="">Xét duyệt: Tất cả</option>
          <option value="ChoDuyet">Chờ duyệt</option>
          <option value="DaDuyet">Đã duyệt</option>
          <option value="TuChoi">Từ chối</option>
        </CustomSelect>

        <CustomSelect
          className="filter-select"
          value={filterThucTap}
          onChange={(e) => { setLoading(true); setFilterThucTap(e.target.value); setPage(1); }}
        >
          <option value="">Tiến độ: Tất cả</option>
          <option value="DangThucTap">Đang thực tập</option>
          <option value="HoanThanh">Hoàn thành</option>
          <option value="ThoiHoc">Thôi học</option>
        </CustomSelect>

        <CustomSelect
          className="filter-select"
          value={filterPhongBan}
          onChange={(e) => { setLoading(true); setFilterPhongBan(e.target.value); setPage(1); }}
        >
          <option value="">Phòng ban: Tất cả</option>
          {departments.map((d) => (
            <option key={d.ma_phong_ban} value={d.ma_phong_ban}>
              {d.ten_phong_ban}
            </option>
          ))}
        </CustomSelect>

        <CustomSelect
          className="filter-select"
          value={filterTruong}
          onChange={(e) => { setLoading(true); setFilterTruong(e.target.value); setPage(1); }}
        >
          <option value="">Trường ĐH: Tất cả</option>
          {universities.map((u) => (
            <option key={u.ma_truong} value={u.ma_truong}>
              {u.ten_truong}
            </option>
          ))}
        </CustomSelect>

        <button 
          type="button" 
          className="btn btn-secondary btn-sm"
          onClick={handleResetFilters}
          title="Đặt lại bộ lọc"
        >
          <RefreshCw size={14} />
          <span>Đặt lại</span>
        </button>
      </div>

      {/* Table */}
      <div className="card intern-list-card">
        <div className="card-header">
          <div className="card-title-box">
            <h2>Hồ sơ sinh viên ({totalItems})</h2>
          </div>
          <button 
            className="btn btn-secondary btn-sm"
            onClick={refreshInterns}
            disabled={loading}
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            <span>Làm mới</span>
          </button>
        </div>

        <div className="table-responsive intern-table-scroll" ref={tableScrollRef}>
          <table id="intern-management-table" className="data-table intern-data-table">
            <colgroup>
              <col className="intern-col-id" />
              <col className="intern-col-name" />
              <col className="intern-col-contact" />
              <col className="intern-col-education" />
              <col className="intern-col-department" />
              <col className="intern-col-review" />
              <col className="intern-col-account" />
              <col className="intern-col-progress" />
              <col className="intern-col-actions" />
            </colgroup>
            <thead>
              <tr>
                <th>Mã HS</th>
                <th>Họ và tên</th>
                <th>Thông tin liên hệ</th>
                <th>Trường Đại học & Chuyên ngành</th>
                <th>Phòng ban</th>
                <th>Xét duyệt</th>
                <th>Tài khoản</th>
                <th>Trạng thái</th>
                <th style={{ textAlign: 'right' }}>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="9" style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>
                    Đang tải dữ liệu...
                  </td>
                </tr>
              ) : interns.length === 0 ? (
                <tr>
                  <td colSpan="9" style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                    Không tìm thấy hồ sơ nào phù hợp.
                  </td>
                </tr>
              ) : (
                interns.map((intern) => (
                  <tr key={intern.ma_ho_so}>
                    <td style={{ fontWeight: 600, color: 'var(--text-muted)' }}>
                      #{intern.ma_ho_so}
                    </td>
                    <td>
                      <div style={{ fontWeight: 600, color: '#0f172a' }}>{intern.ho_ten}</div>
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}>
                        <Mail size={13} color="var(--text-subtle)" />
                        <span>{intern.email}</span>
                      </div>
                      {intern.so_dien_thoai && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-muted)' }}>
                          <Phone size={13} color="var(--text-subtle)" />
                          <span>{intern.so_dien_thoai}</span>
                        </div>
                      )}
                    </td>
                    <td>
                      <div style={{ fontWeight: 500, fontSize: '13px' }}>
                        {intern.ten_truong || '—'}
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        {intern.chuyen_nganh || '—'}
                      </div>
                    </td>
                    <td>
                      <span style={{ fontSize: '13px' }}>
                        {intern.ten_phong_ban || 'Chưa phân'}
                      </span>
                    </td>
                    <td>{getDuyetBadge(intern.trang_thai_xet_duyet)}</td>
                    <td>{getAccountBadge(intern.trang_thai_tai_khoan)}</td>
                    <td>{getThucTapBadge(intern.trang_thai_thuc_tap)}</td>
                    <td style={{ textAlign: 'right' }}>
                      <div className="intern-row-actions">
                        {(currentUser?.vai_tro === 'HR' || currentUser?.vai_tro === 'Admin') && intern.trang_thai_xet_duyet === 'ChoDuyet' && (
                          <>
                          <button
                            className="btn btn-sm"
                            style={{ backgroundColor: '#10b981', color: 'white', padding: '4px 10px', fontSize: '12px' }}
                            title="Quản lý thực tập sinh xét duyệt kích hoạt tài khoản"
                            onClick={() => handleApproveIntern(intern)}
                          >
                            <Check size={13} />
                            <span>Duyệt</span>
                          </button>
                          <button
                            className="btn btn-danger btn-sm"
                            title="Từ chối hồ sơ"
                            onClick={() => handleRejectIntern(intern)}
                          >
                            <XCircle size={13} />
                            <span>Từ chối</span>
                          </button>
                          </>
                        )}
                        <button
                          className="btn btn-secondary btn-sm"
                          title="Xem chi tiết"
                          onClick={() => setDetailModalIntern(intern)}
                        >
                          <Eye size={13} />
                        </button>
                        <button
                          className="btn btn-outline-primary btn-sm"
                          title="Chỉnh sửa"
                          onClick={() => openInternModal(intern.ma_ho_so)}
                        >
                          <Edit3 size={13} />
                          <span>Sửa</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="table-pagination" aria-label="Phân trang hồ sơ thực tập sinh">
          <span className="table-pagination-summary">
            Đang hiển thị {firstVisibleItem}–{lastVisibleItem} trên {totalItems} hồ sơ
          </span>
          <div className="table-pagination-controls">
            <label className="table-page-size">
              <span>Số dòng</span>
              <select className="form-select" aria-label="Số dòng mỗi trang" value={pageSize} onChange={changePageSize}>
                {[10, 20, 50].map((size) => <option key={size} value={size}>{size}</option>)}
              </select>
            </label>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => changePage(currentPage - 1)} disabled={currentPage <= 1 || loading}>
              <ChevronLeft size={15} /><span>Trước</span>
            </button>
            {totalPages > 5 && visiblePages[0] > 1 && <><button type="button" className="btn btn-secondary btn-sm" onClick={() => changePage(1)}>1</button><span className="table-page-ellipsis">…</span></>}
            {visiblePages.map((pageNumber) => (
              <button
                key={pageNumber}
                type="button"
                className={`btn btn-sm table-page-number${pageNumber === currentPage ? ' is-current' : ''}`}
                aria-current={pageNumber === currentPage ? 'page' : undefined}
                onClick={() => changePage(pageNumber)}
                disabled={loading}
              >{pageNumber}</button>
            ))}
            {totalPages > 5 && visiblePages[visiblePages.length - 1] < totalPages && <><span className="table-page-ellipsis">…</span><button type="button" className="btn btn-secondary btn-sm" onClick={() => changePage(totalPages)}>{totalPages}</button></>}
            <span className="table-page-count">Trang {currentPage} / {totalPages}</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => changePage(currentPage + 1)} disabled={currentPage >= totalPages || loading}>
              <span>Tiếp</span><ChevronRight size={15} />
            </button>
          </div>
        </div>
      </div>

      <FloatingTableScrollbar
        scrollContainerRef={tableScrollRef}
        refreshKey={`${interns.length}:${loading}:${page}`}
        label="Cuộn ngang bảng thực tập sinh"
      />

      {/* Intern Create/Edit Modal */}
      <InternModal
        key={modalSession}
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        internId={selectedInternId}
        departments={departments}
        universities={universities}
        onSuccess={(msg) => {
          onShowToast(msg);
          refreshInterns();
        }}
      />

      {/* Quick Detail Modal */}
      {detailModalIntern && (
        <div className="modal-overlay" onClick={() => setDetailModalIntern(null)}>
          <div className="modal-container" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Hồ sơ sinh viên #{detailModalIntern.ma_ho_so}</h3>
              <button className="modal-close-btn" onClick={() => setDetailModalIntern(null)}>×</button>
            </div>
            <div className="modal-body">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
                <div>
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Họ và tên:</span>
                  <div style={{ fontWeight: 600, fontSize: '15px' }}>{detailModalIntern.ho_ten}</div>
                </div>
                <div>
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Email:</span>
                  <div style={{ fontWeight: 500 }}>{detailModalIntern.email}</div>
                </div>
                <div>
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Số điện thoại:</span>
                  <div>{detailModalIntern.so_dien_thoai || '—'}</div>
                </div>
                <div>
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Trường Đại học:</span>
                  <div>{detailModalIntern.ten_truong || '—'}</div>
                </div>
                <div>
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Chuyên ngành:</span>
                  <div>{detailModalIntern.chuyen_nganh || '—'}</div>
                </div>
                <div>
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Phòng ban tiếp nhận:</span>
                  <div>{detailModalIntern.ten_phong_ban || '—'}</div>
                </div>
                <div>
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Xét duyệt:</span>
                  <div>{getDuyetBadge(detailModalIntern.trang_thai_xet_duyet)}</div>
                </div>
                <div>
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Trạng thái thực tập:</span>
                  <div>{getThucTapBadge(detailModalIntern.trang_thai_thuc_tap)}</div>
                </div>
                <div style={{ gridColumn: '1 / -1', paddingTop: '12px', borderTop: '1px solid var(--border-color)' }}>
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Mentor phụ trách:</span>
                  {detailModalIntern.mentor_ho_ten ? (
                    <div style={{ marginTop: '4px' }}>
                      <div style={{ fontWeight: 600, fontSize: '15px' }}>{detailModalIntern.mentor_ho_ten}</div>
                      <div style={{ color: 'var(--text-muted)', marginTop: '4px' }}>
                        {[detailModalIntern.mentor_email, detailModalIntern.mentor_so_dien_thoai, detailModalIntern.mentor_phong_ban].filter(Boolean).join(' · ') || 'Chưa cập nhật thông tin liên hệ'}
                      </div>
                      <div style={{ color: 'var(--text-muted)', marginTop: '4px' }}>
                        Chuyên môn: {detailModalIntern.mentor_chuyen_mon || 'Chưa cập nhật'} · Kinh nghiệm: {detailModalIntern.mentor_kinh_nghiem != null ? `${detailModalIntern.mentor_kinh_nghiem} năm` : 'Chưa cập nhật'}
                      </div>
                    </div>
                  ) : (
                    <div style={{ color: 'var(--text-muted)', marginTop: '4px' }}>Chưa được phân công Mentor.</div>
                  )}
                </div>
              </div>
            </div>
            <div className="modal-footer">
              <button 
                className="btn btn-outline-primary btn-sm"
                onClick={() => {
                  openInternModal(detailModalIntern.ma_ho_so);
                  setDetailModalIntern(null);
                }}
              >
                <Edit3 size={14} />
                <span>Chỉnh sửa hồ sơ</span>
              </button>
              <button className="btn btn-secondary btn-sm" onClick={() => setDetailModalIntern(null)}>
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
