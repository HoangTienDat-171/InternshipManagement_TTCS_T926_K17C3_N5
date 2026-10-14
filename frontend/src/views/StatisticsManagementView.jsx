import React, { useCallback, useEffect, useState } from 'react';
import { BarChart3, Download, RefreshCw, Search, Users } from 'lucide-react';
import CustomSelect from '../components/CustomSelect';
import TablePagination from '../components/TablePagination';
import { apiFetch } from '../utils/api';
import { downloadReport } from '../utils/reportExport';
import './StatisticsManagementView.css';

const EMPTY_FILTERS = {
  program_id: '', department_id: '', date_from: '', date_to: '', school_id: '', major: '', search: '',
};

function queryFor(filters, page, pageSize) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) params.set(key, value);
  });
  if (page) params.set('page', page);
  if (pageSize) params.set('page_size', pageSize);
  return params;
}

function Chart({ title, items, selected, onSelect, missingId = false }) {
  const max = Math.max(1, ...items.map((item) => item.interns));
  return (
    <section className="statistics-panel" aria-label={title}>
      <h3>{title}</h3>
      {items.length ? (
        <div className="statistics-bars">
          {items.map((item) => {
            const key = missingId ? (item.id ?? 0) : item.name;
            const active = String(selected) === String(key);
            return (
              <button
                key={key}
                type="button"
                className={`statistics-bar-row${active ? ' is-selected' : ''}`}
                aria-pressed={active}
                title={`Xem ${item.interns} hồ sơ: ${item.name}`}
                onClick={() => onSelect(active ? '' : key)}
              >
                <span className="statistics-bar-name">{item.name}</span>
                <span className="statistics-bar-track"><span style={{ width: `${Math.max(5, item.interns / max * 100)}%` }} /></span>
                <strong>{item.interns}</strong>
              </button>
            );
          })}
        </div>
      ) : <p className="statistics-empty">Chưa có dữ liệu theo bộ lọc.</p>}
    </section>
  );
}

export default function StatisticsManagementView({ onShowToast }) {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [searchInput, setSearchInput] = useState('');
  const [options, setOptions] = useState({ programs: [], departments: [] });
  const [report, setReport] = useState(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [optionsError, setOptionsError] = useState('');
  const [exporting, setExporting] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;
    apiFetch('/api/reports/intern-statistics/options')
      .then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'Không tải được bộ lọc thống kê.');
        if (active) setOptions(data);
      })
      .catch((cause) => { if (active) setOptionsError(cause.message); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setFilters((current) => current.search === searchInput.trim()
        ? current : { ...current, search: searchInput.trim() });
      setPage(1);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const loadReport = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    setReport(null);
    try {
      const response = await apiFetch(`/api/reports/intern-statistics?${queryFor(filters, page, pageSize)}`, { signal });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Không tải được thống kê.');
      setReport(data);
    } catch (cause) {
      if (cause.name !== 'AbortError') setError(cause.message || 'Không tải được thống kê.');
    } finally {
      if (!signal.aborted) setLoading(false);
    }
  }, [filters, page, pageSize]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => loadReport(controller.signal), 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [loadReport, refreshKey]);

  const setFilter = (name, value) => {
    setFilters((current) => ({ ...current, [name]: value }));
    setPage(1);
  };

  const selectSchool = (value) => {
    setFilters((current) => ({ ...current, school_id: value, major: '' }));
    setPage(1);
  };

  const selectMajor = (value) => {
    setFilters((current) => ({ ...current, major: value, school_id: '' }));
    setPage(1);
  };

  const exportFile = async (format) => {
    setExporting(format);
    try {
      const params = queryFor(filters);
      params.set('format', format);
      await downloadReport(`/api/reports/intern-statistics/export?${params}`, `ims-intern-statistics.${format}`);
      onShowToast?.(`Đã xuất báo cáo ${format.toUpperCase()}.`, 'success');
    } catch (cause) {
      onShowToast?.(cause.message || 'Không thể xuất báo cáo.', 'error');
    } finally {
      setExporting('');
    }
  };

  const summary = report?.summary;
  return (
    <div className="statistics-page">
      <header className="statistics-header">
        <div>
          <span className="statistics-eyebrow"><BarChart3 size={16} /> BÁO CÁO & THỐNG KÊ</span>
          <h2>Thống kê thực tập sinh</h2>
          <p>Phân tích theo trường đại học và chuyên ngành. Khoảng thời gian lọc theo ngày tạo hồ sơ.</p>
        </div>
        <div className="statistics-actions">
          <button type="button" className="btn btn-secondary" disabled={loading} onClick={() => setRefreshKey((key) => key + 1)}><RefreshCw size={16} /> Làm mới</button>
          <button type="button" className="btn btn-secondary" disabled={loading || exporting !== '' || !summary?.unique_interns} onClick={() => exportFile('xlsx')}><Download size={16} /> {exporting === 'xlsx' ? 'Đang xuất…' : 'Xuất Excel'}</button>
          <button type="button" className="btn btn-secondary" disabled={loading || exporting !== '' || !summary?.unique_interns} onClick={() => exportFile('pdf')}><Download size={16} /> {exporting === 'pdf' ? 'Đang xuất…' : 'Xuất PDF'}</button>
        </div>
      </header>

      <section className="statistics-panel statistics-filters" aria-label="Bộ lọc thống kê">
        <label>Chương trình
          <CustomSelect value={filters.program_id} onChange={(event) => setFilter('program_id', event.target.value)}>
            <option value="">Tất cả chương trình</option>
            {(options.programs || []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </CustomSelect>
        </label>
        <label>Phòng ban TTS
          <CustomSelect value={filters.department_id} onChange={(event) => setFilter('department_id', event.target.value)}>
            <option value="">Tất cả phòng ban</option>
            {(options.departments || []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </CustomSelect>
        </label>
        <label>Từ ngày tạo hồ sơ<input type="date" value={filters.date_from} max={filters.date_to || undefined} onChange={(event) => setFilter('date_from', event.target.value)} /></label>
        <label>Đến ngày tạo hồ sơ<input type="date" value={filters.date_to} min={filters.date_from || undefined} onChange={(event) => setFilter('date_to', event.target.value)} /></label>
        <label className="statistics-search">Tìm thực tập sinh
          <span><Search size={16} /><input value={searchInput} maxLength={100} placeholder="Tên, email, chuyên ngành…" onChange={(event) => setSearchInput(event.target.value)} /></span>
        </label>
        <button type="button" className="btn btn-secondary" onClick={() => { setFilters(EMPTY_FILTERS); setSearchInput(''); setPage(1); }}>Xóa bộ lọc</button>
      </section>

      {optionsError && <div className="dashboard-metrics-error" role="alert"><span>{optionsError}</span></div>}
      {error && <div className="dashboard-metrics-error" role="alert"><span>{error}</span><button type="button" onClick={() => setRefreshKey((key) => key + 1)}>Thử lại</button></div>}
      {loading && !report && <div className="statistics-panel" role="status">Đang tải dữ liệu thống kê…</div>}

      {report && <>
        <section className="statistics-kpis" aria-label="Chỉ số tổng quan">
          <div className="statistics-kpi"><Users size={20} /><span>TTS duy nhất</span><strong>{summary.unique_interns}</strong></div>
          <div className="statistics-kpi"><BarChart3 size={20} /><span>Lượt tham gia đã duyệt</span><strong>{summary.approved_participations}</strong></div>
          <div className="statistics-kpi"><span>Trường có thông tin</span><strong>{summary.known_schools}</strong><small>{summary.missing_school} hồ sơ thiếu trường</small></div>
          <div className="statistics-kpi"><span>Ngành có thông tin</span><strong>{summary.known_majors}</strong><small>{summary.missing_major} hồ sơ thiếu ngành</small></div>
        </section>

        <div className="statistics-chart-grid">
          <Chart title="Theo trường đại học" items={report.schools || []} selected={filters.school_id} onSelect={selectSchool} missingId />
          <Chart title="Theo chuyên ngành" items={report.majors || []} selected={filters.major} onSelect={selectMajor} />
        </div>

        <section className="statistics-panel">
          <div className="statistics-table-title">
            <div><h3>Danh sách chi tiết ({report.total_items})</h3><p>Chọn một cột biểu đồ để xem hồ sơ tương ứng.</p></div>
            {(filters.school_id !== '' || filters.major) && <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setFilters((current) => ({ ...current, school_id: '', major: '' })); setPage(1); }}>Bỏ chọn biểu đồ</button>}
          </div>
          <div className="table-responsive">
            <table className="data-table">
              <thead><tr><th>Mã HS</th><th>Thực tập sinh</th><th>Trường</th><th>Chuyên ngành</th><th>Phòng ban</th><th>Ngày tạo</th></tr></thead>
              <tbody>
                {(report.items || []).map((item) => <tr key={item.ma_ho_so}>
                  <td>#{item.ma_ho_so}</td><td><strong>{item.ho_ten}</strong><small>{item.email}</small></td>
                  <td>{item.ten_truong}</td><td>{item.chuyen_nganh}</td><td>{item.ten_phong_ban}</td>
                  <td>{String(item.ngay_tao || '').slice(0, 10) || '—'}</td>
                </tr>)}
                {!loading && !report.items?.length && <tr><td colSpan={6} className="statistics-empty">Không có hồ sơ phù hợp bộ lọc.</td></tr>}
              </tbody>
            </table>
          </div>
          <TablePagination page={report.page} pageSize={pageSize} totalItems={report.total_items} totalPages={report.total_pages} itemLabel="hồ sơ" disabled={loading} onPageChange={setPage} onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} />
        </section>
      </>}
    </div>
  );
}
