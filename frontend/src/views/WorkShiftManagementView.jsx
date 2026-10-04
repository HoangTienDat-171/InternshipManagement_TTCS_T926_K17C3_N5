import React, { useEffect, useState } from 'react';
import { Clock3, Edit3, Plus, RefreshCw, ShieldCheck, X } from 'lucide-react';
import ConfirmDialog from '../components/ConfirmDialog';
import { apiFetch, readJsonResponse } from '../utils/api';

const emptyForm = {
  name: '',
  start_time: '09:00',
  end_time: '17:00',
  scope_type: 'GLOBAL',
  program_id: '',
  effective_from: '',
  effective_to: '',
  status: 'ACTIVE',
};

function formatDate(value) {
  if (!value) return 'Không giới hạn';
  return new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString('vi-VN');
}

function localDateValue() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

async function checkedJson(response, fallback) {
  const data = await readJsonResponse(response);
  if (!response.ok) throw new Error(data.detail || fallback);
  return data;
}

function ShiftStatus({ status }) {
  return <span className={`shift-status ${status === 'ACTIVE' ? 'is-active' : 'is-inactive'}`}>
    <i aria-hidden="true" />{status === 'ACTIVE' ? 'Đang áp dụng' : 'Ngừng áp dụng'}
  </span>;
}

export default function WorkShiftManagementView({ onShowToast }) {
  const [shifts, setShifts] = useState([]);
  const [programs, setPrograms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [programError, setProgramError] = useState('');
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('ACTIVE');
  const [scopeFilter, setScopeFilter] = useState('');
  const [programFilter, setProgramFilter] = useState('');
  const [dateFilter, setDateFilter] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);
  const [formOpen, setFormOpen] = useState(false);
  const [editingShift, setEditingShift] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);
  const [deactivateTarget, setDeactivateTarget] = useState(null);

  const refreshShifts = () => {
    setLoading(true);
    setRefreshKey((value) => value + 1);
  };

  useEffect(() => {
    const controller = new AbortController();
    apiFetch('/api/programs', { signal: controller.signal })
      .then((response) => checkedJson(response, 'Không thể tải chương trình thực tập.'))
      .then((data) => setPrograms(Array.isArray(data) ? data : (data.items || [])))
      .catch((reason) => {
        if (reason.name !== 'AbortError') setProgramError(reason.message);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams();
    if (statusFilter) params.set('status', statusFilter);
    if (scopeFilter) params.set('scope_type', scopeFilter);
    if (scopeFilter === 'PROGRAM' && programFilter) params.set('program_id', programFilter);
    if (dateFilter) params.set('effective_date', dateFilter);
    apiFetch(`/api/work-shifts?${params}`, { signal: controller.signal })
      .then((response) => checkedJson(response, 'Không thể tải danh sách ca làm việc.'))
      .then((data) => {
        setShifts(Array.isArray(data) ? data : []);
        setError('');
      })
      .catch((reason) => {
        if (reason.name !== 'AbortError') setError(reason.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [statusFilter, scopeFilter, programFilter, dateFilter, refreshKey]);

  const startCreate = () => {
    setEditingShift(null);
    setForm({ ...emptyForm, effective_from: localDateValue() });
    setFormError('');
    setFormOpen(true);
  };

  const startEdit = (shift) => {
    setEditingShift(shift);
    setForm({
      name: shift.name,
      start_time: shift.start_time.slice(0, 5),
      end_time: shift.end_time.slice(0, 5),
      scope_type: shift.scope_type,
      program_id: shift.program_id ? String(shift.program_id) : '',
      effective_from: shift.effective_from,
      effective_to: shift.effective_to || '',
      status: shift.status,
    });
    setFormError('');
    setFormOpen(true);
  };

  const saveShift = async (event) => {
    event.preventDefault();
    setSaving(true);
    setFormError('');
    const payload = {
      ...form,
      name: form.name.trim(),
      program_id: form.scope_type === 'PROGRAM' ? Number(form.program_id) : null,
      effective_to: form.effective_to || null,
    };
    try {
      const response = await apiFetch(editingShift ? `/api/work-shifts/${editingShift.id}` : '/api/work-shifts', {
        method: editingShift ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      await checkedJson(response, 'Không thể lưu cấu hình ca.');
      setFormOpen(false);
      refreshShifts();
      onShowToast?.(editingShift ? 'Đã cập nhật cấu hình ca.' : 'Đã tạo cấu hình ca.');
    } catch (reason) {
      setFormError(reason.message);
    } finally {
      setSaving(false);
    }
  };

  const deactivate = async () => {
    if (!deactivateTarget) return;
    setSaving(true);
    try {
      const response = await apiFetch(`/api/work-shifts/${deactivateTarget.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'INACTIVE' }),
      });
      await checkedJson(response, 'Không thể ngừng áp dụng ca.');
      setDeactivateTarget(null);
      refreshShifts();
      onShowToast?.('Ca đã được chuyển sang trạng thái ngừng áp dụng.');
    } catch (reason) {
      setError(reason.message);
      setDeactivateTarget(null);
    } finally {
      setSaving(false);
    }
  };

  return <section className="workspace-page shift-management-page">
    <header className="workspace-heading shift-page-heading">
      <div><span className="workspace-eyebrow">CẤU HÌNH NHÂN SỰ · US23</span><h2>Quản lý ca làm việc</h2><p>Thiết lập khung giờ và thời gian áp dụng cho toàn hệ thống hoặc từng chương trình.</p></div>
      <div className="shift-heading-actions">
        <button type="button" className="btn btn-secondary" onClick={refreshShifts} disabled={loading}><RefreshCw size={16} />Làm mới</button>
        <button type="button" className="btn btn-primary" onClick={startCreate}><Plus size={17} />Tạo ca làm việc</button>
      </div>
    </header>

    <section className="workspace-card shift-filter-card" aria-label="Bộ lọc ca làm việc">
      <label>Trạng thái<select className="form-select" value={statusFilter} onChange={(event) => { setLoading(true); setStatusFilter(event.target.value); }}><option value="">Tất cả</option><option value="ACTIVE">Đang áp dụng</option><option value="INACTIVE">Ngừng áp dụng</option></select></label>
      <label>Phạm vi<select className="form-select" value={scopeFilter} onChange={(event) => { setLoading(true); setScopeFilter(event.target.value); if (event.target.value !== 'PROGRAM') setProgramFilter(''); }}><option value="">Tất cả phạm vi</option><option value="GLOBAL">Toàn hệ thống</option><option value="PROGRAM">Theo chương trình</option></select></label>
      <label>Chương trình<select className="form-select" value={programFilter} disabled={scopeFilter !== 'PROGRAM'} onChange={(event) => { setLoading(true); setProgramFilter(event.target.value); }}><option value="">Tất cả chương trình</option>{programs.map((program) => <option key={program.ma_chuong_trinh} value={program.ma_chuong_trinh}>{program.ten_ct}</option>)}</select></label>
      <label>Ngày hiệu lực<input className="form-control" type="date" value={dateFilter} onChange={(event) => { setLoading(true); setDateFilter(event.target.value); }} /></label>
    </section>
    {programError && <div className="workspace-error" role="alert">{programError}</div>}
    {error && <div className="workspace-error" role="alert"><span>{error}</span><button type="button" className="btn btn-secondary" onClick={refreshShifts}>Thử lại</button></div>}

    <section className="workspace-card shift-list-card" aria-label="Danh sách ca làm việc">
      <div className="workspace-section-heading"><div><span className="workspace-eyebrow">DANH SÁCH CẤU HÌNH</span><h3>Ca làm việc <small>{shifts.length}</small></h3></div><Clock3 size={20} /></div>
      {loading ? <div className="workspace-loading" role="status">Đang tải cấu hình ca…</div> : !shifts.length ? <div className="workspace-empty"><Clock3 size={30} /><strong>Chưa có ca làm việc phù hợp.</strong><span>Tạo ca mới hoặc điều chỉnh bộ lọc để xem cấu hình.</span></div> : <div className="shift-list">
        <div className="shift-list-header" aria-hidden="true"><span>Ca làm việc</span><span>Khung giờ</span><span>Phạm vi</span><span>Thời gian hiệu lực</span><span>Trạng thái & thao tác</span></div>
        {shifts.map((shift) => <article className="shift-row" key={shift.id}>
          <div className="shift-cell shift-name-cell" data-label="Ca làm việc"><span className="shift-clock-icon"><Clock3 size={17} /></span><span><strong>{shift.name}</strong><small>Mã ca #{shift.id}</small></span></div>
          <div className="shift-cell shift-hours-cell" data-label="Khung giờ"><strong>{shift.start_time.slice(0, 5)} – {shift.end_time.slice(0, 5)}</strong><small>Giờ địa phương</small></div>
          <div className="shift-cell" data-label="Phạm vi"><span className={`shift-scope ${shift.scope_type === 'GLOBAL' ? 'is-global' : 'is-program'}`}><ShieldCheck size={13} />{shift.scope_type === 'GLOBAL' ? 'Toàn hệ thống' : 'Chương trình'}</span><small>{shift.scope_type === 'PROGRAM' ? shift.program_name || `Chương trình #${shift.program_id}` : 'Áp dụng mặc định'}</small></div>
          <div className="shift-cell" data-label="Thời gian hiệu lực"><strong>{formatDate(shift.effective_from)} – {formatDate(shift.effective_to)}</strong><small>{shift.effective_to ? 'Khoảng ngày bao gồm cả hai đầu' : 'Không đặt ngày kết thúc'}</small></div>
          <div className="shift-cell shift-actions-cell" data-label="Trạng thái & thao tác"><ShiftStatus status={shift.status} /><div className="shift-row-actions"><button type="button" className="btn btn-secondary btn-sm" onClick={() => startEdit(shift)}><Edit3 size={14} />Chỉnh sửa</button>{shift.status === 'ACTIVE' && <button type="button" className="btn btn-danger btn-sm" onClick={() => setDeactivateTarget(shift)}>Ngừng áp dụng</button>}</div></div>
        </article>)}
      </div>}
    </section>

    {formOpen && <div className="modal-overlay shift-modal-overlay" onMouseDown={(event) => event.target === event.currentTarget && !saving && setFormOpen(false)}>
      <section className="shift-form-modal" role="dialog" aria-modal="true" aria-labelledby="shift-form-title">
        <header><div><span className="workspace-eyebrow">CẤU HÌNH CA</span><h3 id="shift-form-title">{editingShift ? 'Chỉnh sửa ca làm việc' : 'Tạo ca làm việc'}</h3></div><button type="button" className="modal-close-btn" aria-label="Đóng" disabled={saving} onClick={() => setFormOpen(false)}><X size={18} /></button></header>
        <form onSubmit={saveShift}>
          <label className="form-label">Tên ca <span className="required">*</span><input className="form-control" required maxLength={120} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Ví dụ: Ca hành chính" /></label>
          <div className="shift-form-grid">
            <label className="form-label">Giờ bắt đầu <span className="required">*</span><input className="form-control" type="time" required value={form.start_time} onChange={(event) => setForm({ ...form, start_time: event.target.value })} /></label>
            <label className="form-label">Giờ kết thúc <span className="required">*</span><input className="form-control" type="time" required value={form.end_time} onChange={(event) => setForm({ ...form, end_time: event.target.value })} /></label>
          </div>
          <div className="shift-form-grid">
            <label className="form-label">Phạm vi <span className="required">*</span><select className="form-select" value={form.scope_type} onChange={(event) => setForm({ ...form, scope_type: event.target.value, program_id: event.target.value === 'PROGRAM' ? form.program_id : '' })}><option value="GLOBAL">Toàn hệ thống</option><option value="PROGRAM">Theo chương trình</option></select></label>
            <label className="form-label">Chương trình {form.scope_type === 'PROGRAM' && <span className="required">*</span>}<select className="form-select" required={form.scope_type === 'PROGRAM'} disabled={form.scope_type !== 'PROGRAM' || Boolean(programError)} value={form.program_id} onChange={(event) => setForm({ ...form, program_id: event.target.value })}><option value="">Chọn chương trình</option>{programs.map((program) => <option key={program.ma_chuong_trinh} value={program.ma_chuong_trinh}>{program.ten_ct}</option>)}</select></label>
          </div>
          <div className="shift-form-grid">
            <label className="form-label">Hiệu lực từ <span className="required">*</span><input className="form-control" type="date" required value={form.effective_from} onChange={(event) => setForm({ ...form, effective_from: event.target.value })} /></label>
            <label className="form-label">Hiệu lực đến<input className="form-control" type="date" value={form.effective_to} onChange={(event) => setForm({ ...form, effective_to: event.target.value })} /><small>Để trống nếu chưa xác định ngày kết thúc.</small></label>
          </div>
          <label className="form-label">Trạng thái<select className="form-select" value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}><option value="ACTIVE">Đang áp dụng</option><option value="INACTIVE">Ngừng áp dụng</option></select></label>
          <p className="shift-form-note">Ca qua đêm không được hỗ trợ. Các khoảng giờ tiếp giáp nhau (ví dụ 08:00–12:00 và 12:00–17:00) vẫn hợp lệ.</p>
          {formError && <div className="evaluation-form-error" role="alert">{formError}</div>}
          <footer className="shift-form-actions"><button type="button" className="btn btn-secondary" disabled={saving} onClick={() => setFormOpen(false)}>Hủy</button><button type="submit" className="btn btn-primary" disabled={saving || (form.scope_type === 'PROGRAM' && !programs.length)}>{saving ? 'Đang lưu…' : editingShift ? 'Lưu thay đổi' : 'Tạo ca'}</button></footer>
        </form>
      </section>
    </div>}

    <ConfirmDialog open={Boolean(deactivateTarget)} title="Ngừng áp dụng ca?" message={`Ca “${deactivateTarget?.name || ''}” sẽ chuyển sang INACTIVE và không còn được chọn khi phân giải ca cho ngày hiệu lực.`} confirmLabel="Ngừng áp dụng" danger busy={saving} onCancel={() => !saving && setDeactivateTarget(null)} onConfirm={deactivate} />
  </section>;
}
