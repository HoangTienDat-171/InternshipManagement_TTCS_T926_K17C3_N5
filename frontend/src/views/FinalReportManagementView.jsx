import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  Award,
  Calendar,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Eye,
  FileText,
  Mail,
  Phone,
  RefreshCw,
  Search,
  User,
  Users,
  X,
} from 'lucide-react';
import { apiFetch } from '../utils/api';
import CustomSelect from '../components/CustomSelect';
import './FinalReportManagementView.css';

const CRITERIA_LABELS = {
  professional_skill_score: 'Kỹ năng chuyên môn',
  work_quality_score: 'Chất lượng công việc',
  initiative_score: 'Tính chủ động',
  communication_teamwork_score: 'Giao tiếp & phối hợp',
  attitude_discipline_score: 'Thái độ & kỷ luật',
};

function formatDate(val) {
  if (!val) return '—';
  try {
    const d = new Date(val);
    if (Number.isNaN(d.getTime())) return String(val).slice(0, 10);
    return new Intl.DateTimeFormat('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(d);
  } catch {
    return String(val);
  }
}

function ReportPreviewModal({ reportMeta, onClose, onShowToast }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!reportMeta) return undefined;
    let active = true;
    const loadDetail = async () => {
      setLoading(true);
      setError('');
      try {
        const res = await apiFetch(`/api/reports/final-evaluations/${reportMeta.internship_profile_id}/${reportMeta.program_id}`);
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'Không thể tải chi tiết báo cáo.');
        if (active) setDetail(data);
      } catch (err) {
        if (active) {
          setError(err.message || 'Lỗi khi tải báo cáo.');
          onShowToast?.(err.message || 'Lỗi khi tải báo cáo.', 'error');
        }
      } finally {
        if (active) setLoading(false);
      }
    };
    loadDetail();
    return () => { active = false; };
  }, [reportMeta, onShowToast]);

  if (!reportMeta) return null;

  return (
    <div className="modal-overlay report-preview-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-container report-preview-container" role="dialog" aria-modal="true">
        <header className="report-preview-header">
          <div>
            <p>BÁO CÁO ĐÁNH GIÁ THỰC TẬP CUỐI KỲ (US20)</p>
            <h3>{reportMeta.intern_name} · #{reportMeta.internship_profile_id}</h3>
          </div>
          <button type="button" className="modal-close-btn" aria-label="Đóng xem trước" onClick={onClose}>
            <X size={20} />
          </button>
        </header>

        <div className="report-preview-body">
          {error && (
            <div className="alert-banner error">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          {loading && (
            <div className="workspace-card evaluation-empty">
              <span className="evaluation-loading-mark" aria-hidden="true" />
              <strong>Đang tổng hợp báo cáo cuối kỳ…</strong>
            </div>
          )}

          {!loading && detail && (
            <>
              {/* Data Completeness Banner */}
              <div className={`report-status-banner ${detail.data_status === 'DU_DU_LIEU' ? 'complete' : 'incomplete'}`}>
                {detail.data_status === 'DU_DU_LIEU' ? (
                  <>
                    <CheckCircle2 size={18} />
                    <span><strong>Đủ dữ liệu:</strong> {detail.status_message}. Toàn bộ tiêu chí đánh giá từ Mentor đã hoàn tất.</span>
                  </>
                ) : (
                  <>
                    <AlertTriangle size={18} />
                    <span><strong>Chưa đủ dữ liệu:</strong> {detail.status_message}. Báo cáo tổng kết chưa thể kết luận do thiếu đánh giá hoặc thông tin.</span>
                  </>
                )}
              </div>

              {/* Intern Information */}
              <section className="report-section">
                <div className="report-section-title">
                  <User size={16} />
                  <span>1. Thông tin Thực tập sinh</span>
                </div>
                <div className="report-grid-meta">
                  <div className="report-grid-meta-item">
                    <span>Họ và tên</span>
                    <strong>{detail.intern_name}</strong>
                  </div>
                  <div className="report-grid-meta-item">
                    <span>Mã hồ sơ</span>
                    <strong>#{detail.internship_profile_id}</strong>
                  </div>
                  <div className="report-grid-meta-item">
                    <span>Email liên hệ</span>
                    <strong>{detail.intern_email}</strong>
                  </div>
                  <div className="report-grid-meta-item">
                    <span>Số điện thoại</span>
                    <strong>
                      {detail.intern_phone ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                          <Phone size={13} />
                          {detail.intern_phone}
                        </span>
                      ) : '—'}
                    </strong>
                  </div>
                  <div className="report-grid-meta-item">
                    <span>Trường Đại học</span>
                    <strong>{detail.university_name || '—'}</strong>
                  </div>
                  <div className="report-grid-meta-item">
                    <span>Chuyên ngành</span>
                    <strong>{detail.major || '—'}</strong>
                  </div>
                  <div className="report-grid-meta-item">
                    <span>Phòng ban</span>
                    <strong>{detail.department_name || '—'}</strong>
                  </div>
                  <div className="report-grid-meta-item">
                    <span>Tiến độ thực tập</span>
                    <strong>{detail.internship_status || '—'}</strong>
                  </div>
                </div>
              </section>

              {/* Program Information */}
              <section className="report-section">
                <div className="report-section-title">
                  <Calendar size={16} />
                  <span>2. Thông tin Chương trình thực tập</span>
                </div>
                <div className="report-grid-meta">
                  <div className="report-grid-meta-item">
                    <span>Tên chương trình</span>
                    <strong>{detail.program_name}</strong>
                  </div>
                  <div className="report-grid-meta-item">
                    <span>Thời gian bắt đầu</span>
                    <strong>{formatDate(detail.program_start_date)}</strong>
                  </div>
                  <div className="report-grid-meta-item">
                    <span>Thời gian kết thúc</span>
                    <strong>{formatDate(detail.program_end_date)}</strong>
                  </div>
                  <div className="report-grid-meta-item">
                    <span>Trạng thái chương trình</span>
                    <strong>{detail.program_status || '—'}</strong>
                  </div>
                </div>
              </section>

              {/* Mentor Information */}
              <section className="report-section">
                <div className="report-section-title">
                  <Users size={16} />
                  <span>3. Mentor hướng dẫn</span>
                </div>
                {detail.has_mentor ? (
                  <div className="report-grid-meta">
                    <div className="report-grid-meta-item">
                      <span>Họ tên Mentor</span>
                      <strong>{detail.mentor_name}</strong>
                    </div>
                    <div className="report-grid-meta-item">
                      <span>Email</span>
                      <strong>{detail.mentor_email || '—'}</strong>
                    </div>
                    <div className="report-grid-meta-item">
                      <span>Số điện thoại</span>
                      <strong>{detail.mentor_phone || '—'}</strong>
                    </div>
                  </div>
                ) : (
                  <div className="report-missing-notice">
                    <AlertTriangle size={16} />
                    <span>Chưa có Mentor được phân công hướng dẫn cho hồ sơ này trong chương trình.</span>
                  </div>
                )}
              </section>

              {/* Midterm Evaluation */}
              <section className="report-section">
                <div className="report-section-title">
                  <Award size={16} />
                  <span>4. Kết quả đánh giá Giữa kỳ (Midterm)</span>
                </div>
                {detail.midterm_evaluation ? (
                  <>
                    <div className="report-grid-meta" style={{ marginBottom: '12px' }}>
                      <div className="report-grid-meta-item">
                        <span>Mentor đánh giá</span>
                        <strong>{detail.midterm_evaluation.evaluator_name}</strong>
                      </div>
                      <div className="report-grid-meta-item">
                        <span>Ngày đánh giá</span>
                        <strong>{formatDate(detail.midterm_evaluation.evaluated_at)}</strong>
                      </div>
                    </div>

                    <div className="report-score-matrix">
                      {Object.entries(CRITERIA_LABELS).map(([field, label]) => (
                        <div key={field} className="report-score-row">
                          <span>{label}</span>
                          <strong>{detail.midterm_evaluation[field]} / 5</strong>
                        </div>
                      ))}
                    </div>

                    <div className="report-overall-score">
                      <span>Điểm trung bình giữa kỳ:</span>
                      <strong>{detail.midterm_evaluation.average_score.toFixed(1)} / 5</strong>
                    </div>

                    <div className="report-comment-box">
                      <h5>Nhận xét của Mentor:</h5>
                      <p>{detail.midterm_evaluation.overall_comment}</p>
                    </div>
                  </>
                ) : (
                  <div className="report-missing-notice">
                    <AlertCircle size={16} />
                    <span>Chưa có dữ liệu đánh giá giữa kỳ.</span>
                  </div>
                )}
              </section>

              {/* Final Evaluation (US19) */}
              <section className="report-section" style={{ borderLeft: '4px solid var(--primary-color, #4f46e5)' }}>
                <div className="report-section-title">
                  <ClipboardCheck size={16} />
                  <span>5. Kết quả đánh giá Cuối kỳ (Final - US19)</span>
                </div>
                {detail.final_evaluation ? (
                  <>
                    <div className="report-grid-meta" style={{ marginBottom: '12px' }}>
                      <div className="report-grid-meta-item">
                        <span>Mentor đánh giá</span>
                        <strong>{detail.final_evaluation.evaluator_name}</strong>
                      </div>
                      <div className="report-grid-meta-item">
                        <span>Ngày đánh giá</span>
                        <strong>{formatDate(detail.final_evaluation.evaluated_at)}</strong>
                      </div>
                    </div>

                    <div className="report-score-matrix">
                      {Object.entries(CRITERIA_LABELS).map(([field, label]) => (
                        <div key={field} className="report-score-row">
                          <span>{label}</span>
                          <strong>{detail.final_evaluation[field]} / 5</strong>
                        </div>
                      ))}
                    </div>

                    <div className="report-overall-score">
                      <span>Điểm trung bình cuối kỳ:</span>
                      <strong>{detail.final_evaluation.average_score.toFixed(1)} / 5</strong>
                    </div>

                    <div className="report-comment-box">
                      <h5>Nhận xét tổng kết cuối kỳ:</h5>
                      <p>{detail.final_evaluation.overall_comment}</p>
                    </div>
                  </>
                ) : (
                  <div className="report-missing-notice">
                    <AlertTriangle size={16} />
                    <span>Chưa có dữ liệu đánh giá cuối kỳ từ Mentor.</span>
                  </div>
                )}
              </section>
            </>
          )}
        </div>

        <footer className="report-preview-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Đóng
          </button>
        </footer>
      </div>
    </div>
  );
}

export default function FinalReportManagementView({ onShowToast, initialProfileId = null, isModal = false, onCloseModal }) {
  const [reports, setReports] = useState([]);
  const [summary, setSummary] = useState({ total_reports: 0, complete_count: 0, incomplete_count: 0 });
  const [programs, setPrograms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [totalItems, setTotalItems] = useState(0);
  const [totalPages, setTotalPages] = useState(0);

  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [filterProgram, setFilterProgram] = useState('');
  const [filterStatus, setFilterStatus] = useState('ALL');
  const [filterProfileId] = useState(initialProfileId);

  // Preview modal
  const [previewReport, setPreviewReport] = useState(null);
  const searchTimeoutRef = useRef(null);

  // Load programs list
  useEffect(() => {
    apiFetch('/api/programs')
      .then(async (res) => {
        const data = await res.json().catch(() => []);
        if (res.ok) {
          const list = Array.isArray(data) ? data : data.items || [];
          setPrograms(list);
        }
      })
      .catch(() => setPrograms([]));
  }, []);

  // Fetch reports
  const fetchReports = useCallback(async () => {
    setLoading(true);
    setErrorMsg('');
    try {
      const params = new URLSearchParams();
      if (appliedSearch) params.append('search', appliedSearch);
      if (filterProgram) params.append('program_id', filterProgram);
      if (filterStatus) params.append('status', filterStatus);
      if (filterProfileId) params.append('internship_profile_id', filterProfileId);
      params.append('page', page);
      params.append('page_size', pageSize);

      const res = await apiFetch(`/api/reports/final-evaluations?${params.toString()}`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Không thể tải danh sách báo cáo.');

      setReports(Array.isArray(data.items) ? data.items : []);
      setTotalItems(Number(data.total_items) || 0);
      setTotalPages(Number(data.total_pages) || 0);
      if (data.summary) setSummary(data.summary);
    } catch (err) {
      setErrorMsg(err.message || 'Lỗi khi tải dữ liệu báo cáo.');
    } finally {
      setLoading(false);
    }
  }, [appliedSearch, filterProgram, filterStatus, filterProfileId, page, pageSize]);

  useEffect(() => {
    const timer = window.setTimeout(fetchReports, 0);
    return () => window.clearTimeout(timer);
  }, [fetchReports]);

  // Debounced search
  const handleSearchChange = (e) => {
    const val = e.target.value;
    setSearchTerm(val);
    window.clearTimeout(searchTimeoutRef.current);
    searchTimeoutRef.current = window.setTimeout(() => {
      setAppliedSearch(val.trim());
      setPage(1);
    }, 400);
  };

  const handleResetFilters = () => {
    setSearchTerm('');
    setAppliedSearch('');
    setFilterProgram('');
    setFilterStatus('ALL');
    setPage(1);
  };

  const content = (
    <div className="final-report-page">
      <div className="final-report-header">
        <div>
          <h2>Tổng hợp Báo cáo Đánh giá Cuối kỳ</h2>
          <p>Rà soát và xem trước báo cáo cuối kỳ của thực tập sinh theo chương trình và đánh giá Mentor (US20)</p>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button type="button" className="btn btn-secondary btn-sm" onClick={fetchReports} title="Làm mới">
            <RefreshCw size={14} />
            <span>Làm mới</span>
          </button>
          {isModal && onCloseModal && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={onCloseModal}>
              Đóng
            </button>
          )}
        </div>
      </div>

      {/* Metrics cards */}
      <div className="final-report-metrics">
        <div className="final-report-metric-card">
          <div className="final-report-metric-icon">
            <FileText size={22} />
          </div>
          <div className="final-report-metric-info">
            <span>Tổng số báo cáo</span>
            <strong>{summary.total_reports}</strong>
          </div>
        </div>

        <div className="final-report-metric-card">
          <div className="final-report-metric-icon success">
            <CheckCircle2 size={22} />
          </div>
          <div className="final-report-metric-info">
            <span>Đủ dữ liệu đánh giá</span>
            <strong>{summary.complete_count}</strong>
          </div>
        </div>

        <div className="final-report-metric-card">
          <div className="final-report-metric-icon warning">
            <AlertTriangle size={22} />
          </div>
          <div className="final-report-metric-info">
            <span>Chưa đủ dữ liệu</span>
            <strong>{summary.incomplete_count}</strong>
          </div>
        </div>
      </div>

      {errorMsg && (
        <div className="alert-banner error">
          <AlertCircle size={16} />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="filter-bar final-report-filter-bar">
        <div className="search-input-box">
          <Search size={16} className="search-icon" />
          <input
            type="text"
            placeholder="Tìm theo họ tên, email, trường, chuyên ngành..."
            value={searchTerm}
            onChange={handleSearchChange}
          />
        </div>

        <CustomSelect
          className="filter-select"
          value={filterProgram}
          onChange={(e) => { setFilterProgram(e.target.value); setPage(1); }}
        >
          <option value="">Chương trình: Tất cả</option>
          {programs.map((p) => (
            <option key={p.ma_chuong_trinh} value={p.ma_chuong_trinh}>
              {p.ten_ct}
            </option>
          ))}
        </CustomSelect>

        <CustomSelect
          className="filter-select"
          value={filterStatus}
          onChange={(e) => { setFilterStatus(e.target.value); setPage(1); }}
        >
          <option value="ALL">Dữ liệu: Tất cả</option>
          <option value="DU_DU_LIEU">Đủ dữ liệu</option>
          <option value="CHUA_DU_LIEU">Chưa đủ dữ liệu</option>
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

      {/* Reports Table */}
      <div className="card">
        <div className="card-header">
          <div className="card-title-box">
            <h2>Danh sách Báo cáo ({totalItems})</h2>
          </div>
        </div>

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Mã HS</th>
                <th>Thực tập sinh</th>
                <th>Chương trình thực tập</th>
                <th>Mentor hướng dẫn</th>
                <th style={{ textAlign: 'center' }}>ĐG Giữa kỳ</th>
                <th style={{ textAlign: 'center' }}>ĐG Cuối kỳ</th>
                <th>Trạng thái dữ liệu</th>
                <th style={{ textAlign: 'right' }}>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="8" style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                    Đang tải danh sách báo cáo cuối kỳ...
                  </td>
                </tr>
              ) : reports.length === 0 ? (
                <tr>
                  <td colSpan="8" style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                    Không tìm thấy báo cáo nào phù hợp với bộ lọc hiện tại.
                  </td>
                </tr>
              ) : (
                reports.map((r) => (
                  <tr key={`${r.internship_profile_id}-${r.program_id}`}>
                    <td style={{ fontWeight: 600, color: 'var(--text-muted)' }}>
                      #{r.internship_profile_id}
                    </td>
                    <td>
                      <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>{r.intern_name}</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-muted)' }}>
                        <Mail size={12} />
                        <span>{r.intern_email}</span>
                      </div>
                      {r.university_name && (
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                          {r.university_name}
                        </div>
                      )}
                    </td>
                    <td>
                      <div style={{ fontWeight: 500, fontSize: '13px' }}>{r.program_name}</div>
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        {formatDate(r.program_start_date)} – {formatDate(r.program_end_date)}
                      </div>
                    </td>
                    <td>
                      {r.has_mentor ? (
                        <>
                          <div style={{ fontWeight: 500, fontSize: '13px' }}>{r.mentor_name}</div>
                          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{r.mentor_email || '—'}</div>
                        </>
                      ) : (
                        <span className="badge badge-secondary">Chưa phân công</span>
                      )}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      {r.has_midterm_evaluation ? (
                        <span style={{ fontWeight: 700, color: 'var(--primary-color)' }}>
                          {r.midterm_average_score?.toFixed(1)} / 5
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>—</span>
                      )}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      {r.has_final_evaluation ? (
                        <span style={{ fontWeight: 700, color: 'var(--primary-color)' }}>
                          {r.final_average_score?.toFixed(1)} / 5
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Chưa có</span>
                      )}
                    </td>
                    <td>
                      {r.data_status === 'DU_DU_LIEU' ? (
                        <span className="data-status-badge complete">
                          <CheckCircle2 size={13} />
                          <span>Đủ dữ liệu</span>
                        </span>
                      ) : (
                        <div>
                          <span className="data-status-badge incomplete">
                            <AlertTriangle size={13} />
                            <span>Chưa đủ dữ liệu</span>
                          </span>
                          <div className="data-status-subtext">
                            {r.status_message}
                          </div>
                        </div>
                      )}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button
                        type="button"
                        className="btn btn-outline-primary btn-sm"
                        onClick={() => setPreviewReport(r)}
                        title="Xem trước báo cáo"
                      >
                        <Eye size={13} />
                        <span>Xem trước</span>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="table-pagination">
            <span className="table-pagination-summary">
              Hiển thị trang {page} / {totalPages} ({totalItems} báo cáo)
            </span>
            <div className="table-pagination-controls">
              <label className="table-page-size">
                <span>Số dòng</span>
                <CustomSelect
                  className="form-select"
                  value={pageSize}
                  onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
                >
                  <option value={10}>10</option>
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                </CustomSelect>
              </label>

              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || loading}
              >
                <ChevronLeft size={15} />
                <span>Trước</span>
              </button>

              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages || loading}
              >
                <span>Tiếp</span>
                <ChevronRight size={15} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Preview Modal */}
      {previewReport && (
        <ReportPreviewModal
          reportMeta={previewReport}
          onClose={() => setPreviewReport(null)}
          onShowToast={onShowToast}
        />
      )}
    </div>
  );

  if (isModal) {
    return (
      <div className="modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && onCloseModal?.()}>
        <div
          className="modal-container"
          role="dialog"
          aria-modal="true"
          style={{ maxWidth: '1200px', width: '95vw', maxHeight: '92vh', overflowY: 'auto' }}
        >
          {content}
        </div>
      </div>
    );
  }

  return content;
}
