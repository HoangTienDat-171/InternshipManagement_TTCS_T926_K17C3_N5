import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Check, History, LoaderCircle, RefreshCw, RotateCcw, Search, UsersRound, X } from 'lucide-react';
import { apiFetch } from '../utils/api';
import MasterDataSelect from '../components/MasterDataSelect';

async function apiJson(path, options) {
  const response = await apiFetch(path, options);
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = result.detail || `Yêu cầu thất bại (${response.status}).`;
    if (response.status === 404 && (!result.detail || result.detail === 'Not Found')) {
      throw new Error(`Backend trả 404 cho ${path}. Hãy kiểm tra backend có đang chạy từ worktree feature US37 trên cổng 8000 không, rồi tải lại trang.`);
    }
    throw new Error(detail);
  }
  return result;
}

const PAGE_SIZE = 25;
const stateLabels = { UNMAPPED: 'Chưa ánh xạ', DEFAULT: 'Mặc định', OVERRIDE: 'Ngoại lệ', CONFLICT: 'Cần xem lại' };
const mappingFilterItems = [
  { value: '', label: 'Tất cả trạng thái ánh xạ' },
  { value: 'UNMAPPED', label: 'Chưa ánh xạ' },
  { value: 'DEFAULT', label: 'Mặc định' },
  { value: 'OVERRIDE', label: 'Ngoại lệ' },
  { value: 'CONFLICT', label: 'Cần xem lại' },
];

function dateLabel(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('vi-VN');
}

export default function HrmDepartmentMappingPanel({ onMappingChanged, onNotice, onError, busy: pageBusy }) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [globalRows, setGlobalRows] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [audit, setAudit] = useState([]);
  const [globalDraft, setGlobalDraft] = useState({});
  const [employeeDraft, setEmployeeDraft] = useState({});
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [query, setQuery] = useState('');
  const [departmentFilter, setDepartmentFilter] = useState('');
  const [mappingFilter, setMappingFilter] = useState('');
  const [page, setPage] = useState(1);
  const [bulkDepartmentId, setBulkDepartmentId] = useState('');
  const [pending, setPending] = useState(null);
  const [reason, setReason] = useState('');

  const load = async (quiet = false) => {
    if (!quiet) setLoading(true);
    setError('');
    try {
      const [globalData, employeeData, auditData] = await Promise.all([
        apiJson('/api/integrations/hrm/department-mappings'),
        apiJson('/api/integrations/hrm/employee-department-mappings'),
        apiJson('/api/integrations/hrm/department-mapping-audit?page=1&page_size=20'),
      ]);
      setGlobalRows(globalData.hrm_departments || []);
      setDepartments(employeeData.ims_departments || globalData.ims_departments || []);
      setEmployees(employeeData.employees || []);
      const currentIds = new Set((employeeData.employees || []).map((item) => item.external_employee_id));
      setSelectedIds((current) => new Set([...current].filter((id) => currentIds.has(id))));
      setAudit(auditData.items || []);
      setGlobalDraft(Object.fromEntries((globalData.hrm_departments || []).map((item) => [
        item.department_code, item.mapped_department_id ? String(item.mapped_department_id) : '',
      ])));
      setEmployeeDraft(Object.fromEntries((employeeData.employees || []).map((item) => [
        item.external_employee_id, item.override_revision ? String(item.mapped_department_id || '') : '',
      ])));
    } catch (cause) {
      setError(cause.message || 'Không tải được dữ liệu ánh xạ phòng ban.');
    } finally {
      if (!quiet) setLoading(false);
    }
  };

  useEffect(() => {
    Promise.resolve().then(() => { void load(); });
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return employees.filter((employee) => {
      const matchText = !needle || [employee.external_employee_id, employee.full_name, employee.work_email]
        .some((value) => String(value || '').toLocaleLowerCase().includes(needle));
      const matchDepartment = !departmentFilter || employee.department_code === departmentFilter;
      const matchMapping = !mappingFilter || employee.mapping_state === mappingFilter;
      return matchText && matchDepartment && matchMapping;
    });
  }, [employees, query, departmentFilter, mappingFilter]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const visiblePage = Math.min(page, pageCount);
  const pageRows = filtered.slice((visiblePage - 1) * PAGE_SIZE, visiblePage * PAGE_SIZE);
  const pageSelected = pageRows.length > 0 && pageRows.every((employee) => selectedIds.has(employee.external_employee_id));
  const selectedEmployees = employees.filter((employee) => selectedIds.has(employee.external_employee_id));
  const departmentFilterItems = useMemo(() => [
    { department_code: '', department_name: 'Tất cả phòng ban HRM' },
    ...[...new Set(employees.map((employee) => employee.department_code).filter(Boolean))]
      .sort()
      .map((code) => ({ department_code: code, department_name: code })),
  ], [employees]);

  const begin = (operation) => {
    setError('');
    onError?.('');
    setReason('');
    setPending(operation);
  };

  const invalidateAndReload = async (message) => {
    setPending(null);
    setReason('');
    setSelectedIds(new Set());
    onMappingChanged?.();
    onNotice?.(message);
    await load(true);
  };

  const setAllOnPage = () => setSelectedIds((current) => {
    const next = new Set(current);
    if (pageSelected) pageRows.forEach((employee) => next.delete(employee.external_employee_id));
    else pageRows.forEach((employee) => next.add(employee.external_employee_id));
    return next;
  });

  const confirm = async () => {
    if (!pending || reason.trim().length < 3) {
      setError('Nhập lý do ít nhất 3 ký tự để lưu và ghi nhật ký.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      if (pending.kind === 'global-save') {
        const row = pending.row;
        const departmentId = Number(globalDraft[row.department_code]);
        await apiJson('/api/integrations/hrm/department-mappings', {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ department_code: row.department_code, ma_phong_ban: departmentId,
            expected_ma_phong_ban: row.mapped_department_id ?? null, reason: reason.trim() }),
        });
        await invalidateAndReload(`Đã lưu ánh xạ mặc định ${row.department_code}. Preview cũ đã hết hiệu lực; hãy xem trước lại.`);
      } else if (pending.kind === 'global-reset') {
        const row = pending.row;
        await apiJson('/api/integrations/hrm/department-mappings/reset', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ department_code: row.department_code,
            expected_ma_phong_ban: row.mapped_department_id, reason: reason.trim() }),
        });
        await invalidateAndReload(`Đã xóa ánh xạ mặc định ${row.department_code}; nhân viên sẽ theo ngoại lệ riêng hoặc ở trạng thái chưa ánh xạ.`);
      } else if (pending.kind === 'employee-save' || pending.kind === 'bulk-save') {
        const targets = pending.kind === 'employee-save'
          ? [pending.employee]
          : pending.employees;
        await apiJson('/api/integrations/hrm/employee-department-mappings', {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ma_phong_ban: Number(pending.departmentId), reason: reason.trim(),
            employees: targets.map((employee) => ({ external_employee_id: employee.external_employee_id,
              expected_revision: employee.override_revision ?? null })) }),
        });
        const count = targets.length;
        await invalidateAndReload(`Đã lưu ngoại lệ phòng ban cho ${count} nhân viên. Preview cũ đã hết hiệu lực; hãy xem trước lại.`);
      } else if (pending.kind === 'employee-reset') {
        await apiJson('/api/integrations/hrm/employee-department-mappings/reset', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ external_employee_id: pending.employee.external_employee_id,
            expected_revision: pending.employee.override_revision, reason: reason.trim() }),
        });
        await invalidateAndReload(`Đã khôi phục ${pending.employee.external_employee_id} về ánh xạ mặc định.`);
      }
    } catch (cause) {
      setError(cause.message || 'Không lưu được ánh xạ. Tải lại danh sách để kiểm tra trạng thái mới nhất.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <section className="hrm-panel">
        <div className="hrm-panel-heading">
          <div><h2>Ánh xạ mặc định theo phòng ban</h2><p>Ánh xạ mã HRM sang danh mục IMS. Ánh xạ mặc định áp dụng cho nhân viên thuộc mã HRM này, ngoại trừ người có ánh xạ riêng.</p></div>
          <button type="button" className="btn btn-secondary" onClick={() => load()} disabled={loading || saving || Boolean(pageBusy)}>
            {loading ? <LoaderCircle className="hrm-spin" size={15} /> : <RefreshCw size={15} />} Tải danh mục
          </button>
        </div>
        {globalRows.length === 0 && !loading ? <p className="hrm-empty">HRM Sandbox chưa có mã phòng ban để ánh xạ.</p> : (
          <div className="hrm-mapping-list">
            {globalRows.map((row) => {
              const dirty = String(globalDraft[row.department_code] || '') !== String(row.mapped_department_id || '');
              return <div className="hrm-mapping-row" key={row.department_code}>
                <div className="hrm-mapping-source"><strong>{row.department_code}</strong><span>{row.department_name || 'Chưa có tên'}</span></div>
                <MasterDataSelect id={`hrm-global-${row.department_code}`} value={globalDraft[row.department_code] || ''}
                  items={departments} idKey="ma_phong_ban" labelKey="ten_phong_ban" placeholder="Chọn phòng ban IMS"
                  itemName="phòng ban IMS" disabled={loading || saving || Boolean(pageBusy)}
                  onChange={(event) => setGlobalDraft((current) => ({ ...current, [row.department_code]: event.target.value }))} />
                <div className="hrm-map-actions">
                  <button type="button" className="btn btn-secondary" onClick={() => begin({ kind: 'global-save', row })}
                    disabled={!dirty || !globalDraft[row.department_code] || saving || Boolean(pageBusy)}><Check size={15} />Lưu ánh xạ</button>
                  {row.mapped_department_id && <button type="button" className="btn btn-secondary" onClick={() => begin({ kind: 'global-reset', row })}
                    disabled={saving || Boolean(pageBusy)}><X size={15} />Xóa</button>}
                </div>
              </div>;
            })}
          </div>
        )}
      </section>

      <section className="hrm-panel">
        <div className="hrm-panel-heading">
          <div><h2>Ánh xạ phòng ban theo nhân viên</h2><p>Chọn phòng ban IMS riêng cho từng external ID HRM. Thao tác này không sửa HRM, mapping mặc định, tài khoản IMS hay phân công Mentor–TTS.</p></div>
          <UsersRound size={19} aria-hidden="true" />
        </div>
        <div className="hrm-map-filters">
          <label className="hrm-map-search"><Search size={16} aria-hidden="true" /><input value={query} placeholder="Tìm mã, tên hoặc email" onChange={(event) => { setQuery(event.target.value); setPage(1); }} /></label>
          <MasterDataSelect id="hrm-department-code-filter" value={departmentFilter} items={departmentFilterItems}
            idKey="department_code" labelKey="department_name" placeholder="Lọc phòng ban HRM" itemName="phòng ban HRM"
            disabled={loading || saving} onChange={(event) => { setDepartmentFilter(event.target.value); setPage(1); }} />
          <MasterDataSelect id="hrm-mapping-state-filter" value={mappingFilter} items={mappingFilterItems}
            idKey="value" labelKey="label" placeholder="Lọc trạng thái ánh xạ" itemName="trạng thái ánh xạ"
            disabled={loading || saving} onChange={(event) => { setMappingFilter(event.target.value); setPage(1); }} />
        </div>
        <div className="hrm-bulk-toolbar">
          <div className="hrm-bulk-selection"><label><input type="checkbox" checked={pageSelected} onChange={setAllOnPage} disabled={!pageRows.length || saving} /> Chọn trang này ({pageRows.length})</label>
            <button type="button" className="btn btn-secondary" onClick={() => setSelectedIds(new Set(filtered.map((employee) => employee.external_employee_id)))} disabled={!filtered.length || saving}>Chọn tất cả {filtered.length} kết quả lọc</button>
            <button type="button" className="btn btn-secondary" onClick={() => setSelectedIds(new Set())} disabled={!selectedIds.size || saving}>Bỏ chọn</button>
            <span>Đang chọn <strong>{selectedIds.size}</strong> nhân viên</span>
          </div>
          <div className="hrm-bulk-action">
            <div className="hrm-bulk-select"><MasterDataSelect id="hrm-bulk-department" value={bulkDepartmentId} items={departments}
              idKey="ma_phong_ban" labelKey="ten_phong_ban" placeholder="Chọn phòng ban IMS cho nhóm" itemName="phòng ban IMS"
              disabled={!selectedIds.size || saving || Boolean(pageBusy)} onChange={(event) => setBulkDepartmentId(event.target.value)} /></div>
            <button type="button" className="btn btn-primary" disabled={!selectedIds.size || !bulkDepartmentId || saving || Boolean(pageBusy)}
              onClick={() => begin({ kind: 'bulk-save', employees: selectedEmployees, departmentId: bulkDepartmentId })}>Áp dụng cho {selectedIds.size} người</button>
          </div>
        </div>
        {loading && employees.length === 0 ? <p className="hrm-empty"><LoaderCircle className="hrm-spin" size={15} /> Đang tải danh sách HRM…</p> : filtered.length === 0 ? <p className="hrm-empty">Không có nhân viên phù hợp với bộ lọc.</p> : (
          <div className="hrm-table-wrap"><table className="hrm-table hrm-department-table">
            <thead><tr><th><span className="sr-only">Chọn</span></th><th>Mã HRM</th><th>Nhân viên HRM</th><th>Phòng ban gốc HRM</th><th>Phòng ban IMS sau ánh xạ</th><th>Nguồn / trạng thái</th><th>Thao tác</th></tr></thead>
            <tbody>{pageRows.map((employee) => {
              const isOverride = employee.mapping_state === 'OVERRIDE' || employee.mapping_state === 'CONFLICT' && employee.override_revision;
              const draft = employeeDraft[employee.external_employee_id] || '';
              return <tr key={employee.external_employee_id}>
                <td><input type="checkbox" aria-label={`Chọn ${employee.external_employee_id}`} checked={selectedIds.has(employee.external_employee_id)} disabled={saving}
                  onChange={() => setSelectedIds((current) => { const next = new Set(current); if (next.has(employee.external_employee_id)) next.delete(employee.external_employee_id); else next.add(employee.external_employee_id); return next; })} /></td>
                <td>{employee.external_employee_id}</td>
                <td><strong>{employee.full_name}</strong><small>{employee.work_email || 'Không có email'}</small></td>
                <td><strong>{employee.department_code || '—'}</strong><small>{employee.department || 'Không có tên phòng ban nguồn'}</small></td>
                <td><div className="hrm-employee-department-select"><MasterDataSelect id={`hrm-employee-${employee.external_employee_id}`} value={draft}
                  items={departments} idKey="ma_phong_ban" labelKey="ten_phong_ban" placeholder="Chọn phòng ban IMS" itemName="phòng ban IMS"
                  disabled={saving || Boolean(pageBusy)} onChange={(event) => setEmployeeDraft((current) => ({ ...current, [employee.external_employee_id]: event.target.value }))} /></div>
                  {employee.mapping_state === 'CONFLICT' && <small className="hrm-map-warning">Mã HRM đã đổi; ánh xạ riêng đang chờ xác nhận.</small>}
                  {employee.mapping_state === 'DEFAULT' && <small>Theo mặc định: {employee.global_department_name}</small>}
                  {employee.mapping_state === 'OVERRIDE' && <small>Ngoại lệ so với mặc định: {employee.global_department_name || 'chưa có mặc định'}</small>}
                  {employee.mapping_state === 'CONFLICT' && employee.override_department_name && <small>Override cũ: {employee.override_department_name}; cần xác nhận lại.</small>}
                </td>
                <td><span className={`hrm-map-badge state-${employee.mapping_state.toLowerCase()}`}>{stateLabels[employee.mapping_state] || employee.mapping_state}</span>
                  {employee.mapping_state === 'CONFLICT' && <small>Đang dùng mặc định nếu có; override cũ chưa được áp dụng.</small>}
                </td>
                <td><div className="hrm-map-actions">
                  <button type="button" className="btn btn-secondary" disabled={!draft || String(draft) === String(employee.override_revision ? employee.mapped_department_id || '' : '') || saving || Boolean(pageBusy)}
                    onClick={() => begin({ kind: 'employee-save', employee, departmentId: draft })}>Lưu riêng</button>
                  {isOverride && <button type="button" className="btn btn-secondary" disabled={saving || Boolean(pageBusy)} onClick={() => begin({ kind: 'employee-reset', employee })}>
                    <RotateCcw size={14} />Dùng mặc định</button>}
                </div></td>
              </tr>;
            })}</tbody>
          </table></div>
        )}
        <div className="hrm-pagination"><span>Hiển thị {filtered.length ? (visiblePage - 1) * PAGE_SIZE + 1 : 0}–{Math.min(visiblePage * PAGE_SIZE, filtered.length)} / {filtered.length} nhân viên</span>
          <div><button type="button" className="btn btn-secondary" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={visiblePage <= 1}>Trước</button><span>Trang {visiblePage} / {pageCount}</span><button type="button" className="btn btn-secondary" onClick={() => setPage((current) => Math.min(pageCount, current + 1))} disabled={visiblePage >= pageCount}>Sau</button></div>
        </div>
      </section>

      <section className="hrm-panel">
        <div className="hrm-panel-heading"><div><h2>Lịch sử thay đổi ánh xạ</h2><p>Ghi người xác nhận, thời điểm, lý do và giá trị trước/sau.</p></div><History size={19} aria-hidden="true" /></div>
        {!audit.length ? <p className="hrm-empty">Chưa có thay đổi ánh xạ được ghi nhận.</p> : <div className="hrm-table-wrap"><table className="hrm-table">
          <thead><tr><th>Thời gian</th><th>Phạm vi</th><th>HRM</th><th>IMS trước → sau</th><th>Lý do</th><th>Người xác nhận</th></tr></thead>
          <tbody>{audit.map((entry) => <tr key={entry.id}><td>{dateLabel(entry.created_at)}</td><td>{entry.mapping_scope === 'GLOBAL' ? 'Mặc định' : 'Nhân viên'}</td>
            <td>{entry.mapping_scope === 'GLOBAL' ? entry.external_department_code : <>{entry.external_employee_id}<small>Phòng ban nguồn: {entry.external_department_code || '—'}</small></>}</td>
            <td>{entry.before_department_name || '—'} → {entry.after_department_name || '—'}</td><td>{entry.reason}</td><td>{entry.actor_name || 'Admin'}</td></tr>)}</tbody>
        </table></div>}
      </section>

      {error && <div className="hrm-message is-error" role="alert"><AlertTriangle size={17} />{error}<button type="button" className="hrm-inline-dismiss" onClick={() => setError('')} aria-label="Đóng thông báo lỗi"><X size={15} /></button></div>}
      {pending && <div className="hrm-map-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) setPending(null); }}>
        <section className="hrm-map-modal" role="dialog" aria-modal="true" aria-labelledby="hrm-map-confirm-title">
          <header><div><span className="hrm-eyebrow">XÁC NHẬN ÁNH XẠ</span><h2 id="hrm-map-confirm-title">{pending.kind === 'bulk-save' ? `Áp dụng riêng cho ${pending.employees.length} nhân viên` : pending.kind === 'employee-save' ? 'Lưu ánh xạ riêng cho nhân viên' : pending.kind === 'employee-reset' ? 'Khôi phục ánh xạ mặc định' : pending.kind === 'global-reset' ? 'Xóa ánh xạ mặc định' : 'Lưu ánh xạ mặc định'}</h2></div>
            <button type="button" className="btn btn-secondary" aria-label="Đóng xác nhận" disabled={saving} onClick={() => setPending(null)}><X size={17} /></button></header>
          <p>{pending.kind === 'global-save' || pending.kind === 'global-reset'
            ? `Mã ${pending.row.department_code} áp dụng mặc định cho nhân viên HRM trong phòng ban này; ánh xạ riêng từng nhân viên được ưu tiên.`
            : pending.kind === 'employee-reset'
              ? `${pending.employee.external_employee_id} sẽ dùng lại ánh xạ mặc định hiện tại (${pending.employee.global_department_name || 'chưa ánh xạ'}).`
              : `Phòng ban IMS được chọn chỉ tạo ngoại lệ theo external ID; không đổi mã/phòng ban gốc HRM hoặc mapping mặc định.`}</p>
          {(pending.kind === 'employee-save' || pending.kind === 'bulk-save') && <div className="hrm-map-review-list">
            {(pending.kind === 'employee-save' ? [pending.employee] : pending.employees).map((employee) => <div key={employee.external_employee_id}><strong>{employee.external_employee_id} · {employee.full_name}</strong><span>{employee.department_code || 'Chưa có mã phòng ban HRM'} → {departments.find((item) => String(item.ma_phong_ban) === String(pending.departmentId))?.ten_phong_ban || 'Phòng ban IMS'}</span></div>)}
          </div>}
          {pending.kind === 'global-save' && <p className="hrm-map-confirm-target">{pending.row.department_code} → {departments.find((item) => String(item.ma_phong_ban) === String(globalDraft[pending.row.department_code]))?.ten_phong_ban}</p>}
          <label className="hrm-map-reason"><span>Lý do xác nhận <b>*</b></span><textarea value={reason} maxLength={500} aria-describedby="hrm-map-reason-hint" onChange={(event) => setReason(event.target.value)} placeholder="Ví dụ: HR xác nhận cơ cấu DATA tương ứng với phòng AI/Data" rows={3} autoFocus /><small id="hrm-map-reason-hint">Bắt buộc nhập ít nhất 3 ký tự để lưu nhật ký · {reason.trim().length}/500 ký tự.</small></label>
          <footer><button type="button" className="btn btn-secondary" onClick={() => setPending(null)} disabled={saving}>Hủy</button>
            <button type="button" className="btn btn-primary" onClick={confirm} disabled={saving || reason.trim().length < 3}>
              {saving ? <LoaderCircle className="hrm-spin" size={15} /> : <Check size={15} />}Xác nhận và lưu
            </button></footer>
        </section>
      </div>}
    </>
  );
}
