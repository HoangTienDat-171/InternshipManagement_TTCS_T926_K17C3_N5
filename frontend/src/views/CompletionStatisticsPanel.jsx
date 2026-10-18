import React, { useCallback, useEffect, useState } from 'react';
import { Check, Download, RefreshCw, RotateCcw, Search } from 'lucide-react';
import CustomDatePicker from '../components/CustomDatePicker';
import CustomSelect from '../components/CustomSelect';
import TablePagination from '../components/TablePagination';
import { apiFetch } from '../utils/api';
import { downloadReport } from '../utils/reportExport';

const EMPTY_FILTERS = { program_id: '', department_id: '', date_from: '', date_to: '', search: '' };

function queryFor(filters, page, pageSize) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) params.set(key, value);
  });
  if (page) params.set('page', page);
  if (pageSize) params.set('page_size', pageSize);
  return params;
}

function CompletionChart({ items, selected, onSelect }) {
  return (
    <section className="statistics-panel" aria-label="Tỷ lệ hoàn thành theo chương trình">
      <h3>Tỷ lệ theo chương trình</h3>
      {items.length ? <div className="completion-program-list">
        {items.map((item) => {
          const active = String(selected) === String(item.id);
          return <button key={item.id} type="button" className={`completion-program-row${active ? ' is-selected' : ''}`} aria-pressed={active} onClick={() => onSelect(active ? '' : String(item.id))}>
            <span className="completion-program-heading"><strong>{item.name}</strong><span>{item.completed}/{item.eligible} · {item.completion_rate}%</span></span>
            <span className="completion-rate-track"><span style={{ width: `${item.completion_rate}%` }} /></span>
          </button>;
        })}
      </div> : <p className="statistics-empty">Chưa có lượt tham gia đủ điều kiện.</p>}
    </section>
  );
}

export default function CompletionStatisticsPanel({ options, onShowToast }) {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [searchInput, setSearchInput] = useState('');
  const [report, setReport] = useState(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState('');
  const [updatingId, setUpdatingId] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setFilters((current) => current.search === searchInput.trim() ? current : { ...current, search: searchInput.trim() });
      setPage(1);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const loadReport = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    setReport(null);
    try {
      const response = await apiFetch(`/api/reports/completion?${queryFor(filters, page, pageSize)}`, { signal });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Không tải được thống kê hoàn thành.');
      setReport(data);
    } catch (cause) {
      if (cause.name !== 'AbortError') setError(cause.message || 'Không tải được thống kê hoàn thành.');
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

  const exportFile = async (format) => {
    setExporting(format);
    try {
      const params = queryFor(filters);
      params.set('format', format);
      await downloadReport(`/api/reports/completion/export?${params}`, `ims-completion-statistics.${format}`);
      onShowToast?.(`Đã xuất báo cáo ${format.toUpperCase()}.`, 'success');
    } catch (cause) {
      onShowToast?.(cause.message || 'Không thể xuất báo cáo.', 'error');
    } finally {
      setExporting('');
    }
  };

  const updateCompletion = async (item) => {
    const nextStatus = item.completion_status === 'HoanThanh' ? 'ChuaHoanThanh' : 'HoanThanh';
    setUpdatingId(item.application_id);
    try {
      const response = await apiFetch(`/api/reports/completion/applications/${item.application_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ completion_status: nextStatus }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Không cập nhật được trạng thái.');
      onShowToast?.(data.message || 'Đã cập nhật trạng thái hoàn thành.', 'success');
      setRefreshKey((key) => key + 1);
    } catch (cause) {
      onShowToast?.(cause.message || 'Không cập nhật được trạng thái.', 'error');
    } finally {
      setUpdatingId(null);
    }
  };

  const summary = report?.summary;
  return <div className="completion-statistics">
    <section className="statistics-panel statistics-filters" aria-label="Bộ lọc tỷ lệ hoàn thành">
      <label>Chương trình
        <CustomSelect value={filters.program_id} onChange={(event) => setFilter('program_id', event.target.value)}>
          <option value="">Tất cả chương trình</option>
          {(options.programs || []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </CustomSelect>
      </label>
      <label>Phòng ban chương trình
        <CustomSelect value={filters.department_id} onChange={(event) => setFilter('department_id', event.target.value)}>
          <option value="">Tất cả phòng ban</option>
          {(options.departments || []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </CustomSelect>
      </label>
      <label>
        <span>Từ ngày kết thúc</span>
        <CustomDatePicker
          value={filters.date_from}
          max={filters.date_to || undefined}
          onChange={(event) => setFilter('date_from', event.target.value)}
        />
      </label>
      <label>
        <span>Đến ngày kết thúc</span>
        <CustomDatePicker
          value={filters.date_to}
          min={filters.date_from || undefined}
          onChange={(event) => setFilter('date_to', event.target.value)}
        />
      </label>
      <label className="statistics-search">Tìm thực tập sinh
        <span><Search size={16} /><input value={searchInput} maxLength={100} placeholder="Tên, email, chuyên ngành…" onChange={(event) => setSearchInput(event.target.value)} /></span>
      </label>
      <button type="button" className="btn btn-secondary btn-reset" onClick={() => { setFilters(EMPTY_FILTERS); setSearchInput(''); setPage(1); }}>
        <RotateCcw size={15} /> Xóa bộ lọc
      </button>
    </section>

    {error && <div className="dashboard-metrics-error" role="alert"><span>{error}</span><button type="button" onClick={() => setRefreshKey((key) => key + 1)}>Thử lại</button></div>}
    {loading && !report && <div className="statistics-panel" role="status">Đang tải tỷ lệ hoàn thành…</div>}
    {report && <>
      <div className="statistics-actions completion-actions">
        <p className="completion-rule">Eligible: đơn đã duyệt thuộc chương trình có ngày kết thúc đến {report.filters.as_of}.</p>
        <button type="button" className="btn btn-secondary" disabled={loading} onClick={() => setRefreshKey((key) => key + 1)}><RefreshCw size={16} /> Làm mới</button>
        <button type="button" className="btn btn-secondary" disabled={loading || exporting !== '' || !summary.eligible} onClick={() => exportFile('xlsx')}><Download size={16} /> {exporting === 'xlsx' ? 'Đang xuất…' : 'Xuất Excel'}</button>
        <button type="button" className="btn btn-secondary" disabled={loading || exporting !== '' || !summary.eligible} onClick={() => exportFile('pdf')}><Download size={16} /> {exporting === 'pdf' ? 'Đang xuất…' : 'Xuất PDF'}</button>
      </div>
      <section className="statistics-kpis completion-kpis" aria-label="Tổng hợp hoàn thành">
        <div className="statistics-kpi"><Check size={20} /><span>Tỷ lệ hoàn thành</span><strong>{summary.completion_rate === null ? '—' : `${summary.completion_rate}%`}</strong><small>{summary.completed} / {summary.eligible} lượt đủ điều kiện</small></div>
        <div className="statistics-kpi"><span>Completed</span><strong>{summary.completed}</strong><small>Được HR/Admin ghi nhận theo từng lượt tham gia</small></div>
        <div className="statistics-kpi"><span>Eligible</span><strong>{summary.eligible}</strong><small>Đơn đã duyệt, chương trình đã kết thúc</small></div>
        <div className="statistics-kpi"><span>Chưa hoàn thành</span><strong>{summary.incomplete}</strong><small>Trong các lượt đủ điều kiện</small></div>
      </section>
      <CompletionChart items={report.programs || []} selected={filters.program_id} onSelect={(value) => setFilter('program_id', value)} />
      <section className="statistics-panel">
        <div className="statistics-table-title"><div><h3>Lượt tham gia đủ điều kiện ({report.total_items})</h3><p>Đánh dấu hoàn thành sau khi xác minh kết quả chương trình.</p></div></div>
        <div className="table-responsive">
          <table className="data-table">
            <thead><tr><th>TTS</th><th>Chương trình</th><th>Ngày kết thúc</th><th>Phòng ban</th><th>Trạng thái</th><th>Cập nhật bởi</th><th>Thao tác</th></tr></thead>
            <tbody>
              {(report.items || []).map((item) => <tr key={item.application_id}>
                <td><strong>{item.intern_name}</strong><small>{item.intern_email} · HS #{item.profile_id}</small></td>
                <td>{item.program_name}</td><td>{String(item.program_end_date || '').slice(0, 10)}</td><td>{item.department_name}</td>
                <td><span className={`completion-status ${item.completion_status === 'HoanThanh' ? 'is-complete' : 'is-incomplete'}`}>{item.completion_status === 'HoanThanh' ? 'Hoàn thành' : 'Chưa hoàn thành'}</span></td>
                <td>{item.completion_updated_by_name || '—'}<small>{String(item.completion_updated_at || '').slice(0, 16)}</small></td>
                <td><button type="button" className="btn btn-secondary btn-sm" disabled={updatingId === item.application_id} onClick={() => updateCompletion(item)}>{updatingId === item.application_id ? 'Đang lưu…' : item.completion_status === 'HoanThanh' ? 'Đặt chưa hoàn thành' : 'Đánh dấu hoàn thành'}</button></td>
              </tr>)}
              {!report.items?.length && <tr><td colSpan={7} className="statistics-empty">Chưa có lượt tham gia đủ điều kiện theo bộ lọc.</td></tr>}
            </tbody>
          </table>
        </div>
        <TablePagination page={report.page} pageSize={pageSize} totalItems={report.total_items} totalPages={report.total_pages} itemLabel="lượt tham gia" disabled={loading} onPageChange={setPage} onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} />
      </section>
    </>}
  </div>;
}
