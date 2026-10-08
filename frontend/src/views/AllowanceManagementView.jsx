import React, { useEffect, useRef, useState } from 'react';
import { Wallet, Search, Plus, RefreshCw, Eye, Pencil, X, Save, Inbox, ShieldCheck } from 'lucide-react';
import CustomSelect from '../components/CustomSelect';
import TablePagination from '../components/TablePagination';
import { apiFetch, readJsonResponse } from '../utils/api';
import './AllowanceManagementView.css';

const emptyPage = { items: [], total: 0 };
const money = (value) => {
  const [whole, fraction = '00'] = String(value).split('.');
  return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.')}${fraction !== '00' ? ',' + fraction : ''} ₫`;
};
const periodLabel = (value) => `${value.slice(5)}/${value.slice(0, 4)}`;
const timestamp = (value) => value ? new Date(value.replace(' ', 'T') + 'Z').toLocaleString('vi-VN') : '—';
function errorMessage(detail) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg || '').filter(Boolean).join('; ');
  return 'Không thể xử lý yêu cầu. Vui lòng thử lại.';
}
async function requestJson(url, options) {
  const response = await apiFetch(url, options);
  const data = await readJsonResponse(response);
  if (!response.ok) throw new Error(errorMessage(data.detail));
  return data;
}
function currentPeriod() {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
}

function AllowanceForm({ record, programs, onSaved, onClose }) {
  const [selected, setSelected] = useState(record || null);
  const [form, setForm] = useState({ ky: record?.ky || currentPeriod(), so_tien: record?.so_tien || '', ghi_chu: record?.ghi_chu || '' });
  const [search, setSearch] = useState('');
  const [program, setProgram] = useState('');
  const [page, setPage] = useState(1);
  const [options, setOptions] = useState(emptyPage);
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [optionsError, setOptionsError] = useState('');
  const [retry, setRetry] = useState(0);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const submitLock = useRef(false);
  const titleRef = useRef(null);
  useEffect(() => { titleRef.current?.focus(); }, []);
  useEffect(() => {
    if (record) return undefined;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      setOptionsLoading(true);
      setOptionsError('');
      const query = new URLSearchParams({ search, page: String(page), page_size: '25' });
      if (program) query.set('program_id', program);
      requestJson(`/api/allowances/profiles?${query}`, { signal: controller.signal })
        .then((data) => { if (!controller.signal.aborted) setOptions(data); })
        .catch((err) => { if (!controller.signal.aborted) { setOptions(emptyPage); setOptionsError(err.message); } })
        .finally(() => { if (!controller.signal.aborted) setOptionsLoading(false); });
    }, 250);
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, [record, search, program, page, retry]);
  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitLock.current) return;
    if (!selected) { setError('Vui lòng chọn hồ sơ tham gia chương trình đã được duyệt.'); return; }
    if (!/^[1-9]\d{3}-(0[1-9]|1[0-2])$/.test(form.ky)) { setError('Kỳ phụ cấp phải có định dạng YYYY-MM hợp lệ.'); return; }
    if (!/^\d{1,13}(\.\d{1,2})?$/.test(form.so_tien)) { setError('Nhập số tiền không âm, tối đa 13 chữ số nguyên và 2 chữ số lẻ.'); return; }
    submitLock.current = true;
    setSaving(true);
    setError('');
    try {
      const payload = { ...form };
      if (!record) payload.ma_ung_tuyen = selected.ma_ung_tuyen;
      await requestJson(record ? `/api/allowances/${record.id}` : '/api/allowances', {
        method: record ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      });
      onSaved();
    } catch (err) { setError(err.message); }
    finally { submitLock.current = false; setSaving(false); }
  };
  const selectedInPage = options.items.some((item) => item.ma_ung_tuyen === selected?.ma_ung_tuyen);
  return <section className="allowance-card allowance-form">
    <div className="allowance-card-heading"><h2 ref={titleRef} tabIndex={-1}>{record ? 'Cập nhật phụ cấp' : 'Thêm phụ cấp mới'}</h2><button type="button" className="btn btn-secondary" aria-label="Đóng form" disabled={saving} onClick={onClose}><X size={18} /></button></div>
    <p className="allowance-muted">Một hồ sơ có một khoản phụ cấp trong mỗi kỳ. Chương trình đã kết thúc vẫn có thể được nhập phụ cấp lịch sử.</p>
    <form onSubmit={handleSubmit}>
      <fieldset disabled={saving}>
        {!record && <div className="allowance-form-grid">
          <label>Tìm hồ sơ<input type="search" value={search} maxLength={100} placeholder="Tên hoặc email thực tập sinh" onChange={(e) => { setSearch(e.target.value); setPage(1); }} /></label>
          <label>Chương trình<CustomSelect id="allowance-form-program" value={program} onChange={(e) => { setProgram(e.target.value); setPage(1); setSelected(null); setOptions(emptyPage); setOptionsLoading(true); }}><option value="">Tất cả chương trình</option>{programs.map((item) => <option key={item.ma_chuong_trinh} value={item.ma_chuong_trinh}>{item.ten_ct} · {item.ma_ct}</option>)}</CustomSelect></label>
          <label className="allowance-full">Hồ sơ tham gia đã duyệt *<CustomSelect id="allowance-profile" value={selected?.ma_ung_tuyen || ''} disabled={optionsLoading} onChange={(e) => setSelected(options.items.find((item) => item.ma_ung_tuyen === Number(e.target.value)) || null)}><option value="">Chọn thực tập sinh và chương trình</option>{selected && !selectedInPage && <option value={selected.ma_ung_tuyen}>{selected.ho_ten} · HS #{selected.ma_ho_so} · {selected.ten_ct}</option>}{options.items.map((item) => <option key={item.ma_ung_tuyen} value={item.ma_ung_tuyen}>{item.ho_ten} · {item.email} · HS #{item.ma_ho_so} · {item.ten_ct}</option>)}</CustomSelect></label>
          {optionsLoading && <p role="status" className="allowance-muted">Đang tải hồ sơ…</p>}
          {optionsError && <p role="alert" className="allowance-error">{optionsError} <button type="button" onClick={() => setRetry((n) => n + 1)}>Thử lại</button></p>}
          {!optionsLoading && !optionsError && !options.total && <p className="allowance-muted">Không có hồ sơ đã duyệt phù hợp.</p>}
          {options.total > 25 && <div className="allowance-option-pages allowance-full"><button type="button" className="btn btn-secondary btn-sm" disabled={optionsLoading || page <= 1} onClick={() => setPage(page - 1)}>Trang trước</button><span>Trang {page} / {Math.ceil(options.total / 25)} · {options.total} hồ sơ</span><button type="button" className="btn btn-secondary btn-sm" disabled={optionsLoading || page * 25 >= options.total} onClick={() => setPage(page + 1)}>Trang sau</button></div>}
        </div>}
        {selected && <div className="allowance-selected"><ShieldCheck size={20} /><div><strong>{selected.ho_ten}</strong><span>{selected.ten_ct} · {selected.ma_ct} · Hồ sơ #{selected.ma_ho_so}</span></div></div>}
        <div className="allowance-form-grid">
          <label htmlFor="allowance-period">Kỳ phụ cấp *<input id="allowance-period" type="month" required value={form.ky} onChange={(e) => setForm({ ...form, ky: e.target.value })} /></label>
          <label htmlFor="allowance-amount">Số tiền (VNĐ) *<input id="allowance-amount" type="text" inputMode="decimal" required maxLength={16} value={form.so_tien} placeholder="Ví dụ: 1500000" onChange={(e) => setForm({ ...form, so_tien: e.target.value })} /><small>Sử dụng dấu chấm cho phần lẻ, ví dụ 1500000.50.</small></label>
          <label className="allowance-full" htmlFor="allowance-note">Ghi chú<textarea id="allowance-note" rows={3} maxLength={1000} value={form.ghi_chu} placeholder="Thông tin bổ sung cho kỳ phụ cấp…" onChange={(e) => setForm({ ...form, ghi_chu: e.target.value })} /><small className="allowance-character-count">{form.ghi_chu.length}/1000</small></label>
        </div>
      </fieldset>
      {error && <p role="alert" className="allowance-error">{error}</p>}
      <div className="allowance-form-actions"><button type="button" className="btn btn-secondary" disabled={saving} onClick={onClose}>Hủy</button><button type="submit" className="btn btn-primary" disabled={saving || !selected}><Save size={17} />{saving ? 'Đang lưu…' : 'Lưu phụ cấp'}</button></div>
    </form>
  </section>;
}

function AllowanceDetails({ recordId, endpoint, canManage, onClose }) {
  const dialog = useRef(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => { dialog.current?.showModal(); }, []);
  useEffect(() => {
    const controller = new AbortController();
    requestJson(`${endpoint}/${recordId}`, { signal: controller.signal })
      .then((value) => { if (!controller.signal.aborted) { setData(value); setError(''); } })
      .catch((err) => { if (!controller.signal.aborted) { setData(null); setError(err.message); } });
    return () => controller.abort();
  }, [recordId, endpoint, retry]);
  return <dialog className="allowance-dialog" ref={dialog} onCancel={onClose} onClose={onClose} aria-labelledby="allowance-detail-title">
    <div className="allowance-card-heading"><h2 id="allowance-detail-title">Chi tiết phụ cấp #{recordId}</h2><button type="button" className="btn btn-secondary" aria-label="Đóng chi tiết" onClick={onClose}><X size={18} /></button></div>
    {error ? <p role="alert" className="allowance-error">{error} <button type="button" onClick={() => setRetry((n) => n + 1)}>Thử lại</button></p> : !data ? <p role="status">Đang tải chi tiết…</p> : <>
      <div className="allowance-detail-amount"><span>Kỳ {periodLabel(data.ky)}</span><strong>{money(data.so_tien)}</strong></div>
      <dl className="allowance-details"><dt>Thực tập sinh</dt><dd>{data.ho_ten} · {data.email}</dd><dt>Hồ sơ / chương trình</dt><dd>#{data.ma_ho_so} · {data.ten_ct} ({data.ma_ct})</dd><dt>Ghi chú</dt><dd className="allowance-note-text">{data.ghi_chu || 'Không có ghi chú.'}</dd>{canManage && <><dt>Người tạo</dt><dd>{data.nguoi_tao} · {timestamp(data.created_at)}</dd><dt>Người cập nhật</dt><dd>{data.nguoi_cap_nhat} · {timestamp(data.updated_at)}</dd></>}{!canManage && <><dt>Cập nhật lúc</dt><dd>{timestamp(data.updated_at)}</dd></>}</dl>
    </>}
    <div className="allowance-form-actions"><button type="button" className="btn btn-secondary" onClick={onClose}>Đóng</button></div>
  </dialog>;
}

export default function AllowanceManagementView({ currentUser, onShowToast }) {
  const canManage = ['HR', 'Admin'].includes(currentUser?.vai_tro);
  const canRead = canManage || currentUser?.vai_tro === 'ThucTapSinh';
  const endpoint = canManage ? '/api/allowances' : '/api/interns/me/allowances';
  const [result, setResult] = useState(emptyPage);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [programs, setPrograms] = useState([]);
  const [programError, setProgramError] = useState('');
  const [filters, setFilters] = useState({ search: '', program_id: '', ky: '', year: '' });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [revision, setRevision] = useState(0);
  const [form, setForm] = useState(null);
  const [detailId, setDetailId] = useState(null);
  useEffect(() => {
    if (!canRead) return undefined;
    const controller = new AbortController();
    requestJson(canManage ? '/api/allowances/programs' : '/api/interns/me/allowance-programs', { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) { setPrograms(data); setProgramError(''); } })
      .catch((err) => { if (!controller.signal.aborted) { setPrograms([]); setProgramError(err.message); } });
    return () => controller.abort();
  }, [canManage, canRead, revision]);
  useEffect(() => {
    if (!canRead) return undefined;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      setLoading(true);
      setError('');
      const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      for (const [key, value] of Object.entries(filters)) if (value && (canManage || key !== 'search')) query.set(key, value);
      requestJson(`${endpoint}?${query}`, { signal: controller.signal })
        .then((data) => {
          if (controller.signal.aborted) return;
          if (page > 1 && page > Math.max(1, Math.ceil(data.total / pageSize))) { setPage(Math.max(1, Math.ceil(data.total / pageSize))); return; }
          setResult(data);
        })
        .catch((err) => { if (!controller.signal.aborted) { setResult(emptyPage); setError(err.message); } })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 250);
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, [endpoint, canRead, canManage, filters, page, pageSize, revision]);
  const changeFilter = (key, value) => { setFilters((old) => ({ ...old, [key]: value })); setPage(1); };
  if (!canRead) return <p role="alert">Bạn không có quyền xem phụ cấp.</p>;
  return <div className="allowance-page">
    <header className="allowance-page-heading"><div><span className="allowance-eyebrow"><Wallet size={16} />PHỤ CẤP THỰC TẬP</span><h1>{canManage ? 'Quản lý phụ cấp' : 'Lịch sử phụ cấp'}</h1><p>{canManage ? 'Nhập và cập nhật phụ cấp theo hồ sơ, chương trình và kỳ thực tập.' : 'Theo dõi các khoản phụ cấp được HR ghi nhận cho từng chương trình của bạn.'}</p></div><div className="allowance-heading-actions"><button type="button" className="btn btn-secondary" disabled={loading} onClick={() => setRevision((n) => n + 1)}><RefreshCw size={17} />Làm mới</button>{canManage && <button type="button" className="btn btn-primary" onClick={() => setForm({ record: null })}><Plus size={18} />Thêm phụ cấp</button>}</div></header>
    {form && canManage && <AllowanceForm key={form.record?.id || 'new'} record={form.record} programs={programs} onClose={() => setForm(null)} onSaved={() => { setForm(null); setRevision((n) => n + 1); onShowToast?.('Đã lưu thông tin phụ cấp.'); }} />}
    <section className="allowance-card allowance-filters" aria-label="Bộ lọc phụ cấp">
      {canManage && <label className="allowance-search"><Search size={18} /><input aria-label="Tìm thực tập sinh" type="search" maxLength={100} value={filters.search} placeholder="Tìm tên hoặc email TTS…" onChange={(e) => changeFilter('search', e.target.value)} /></label>}
      <label>Chương trình<CustomSelect id="allowance-filter-program" value={filters.program_id} onChange={(e) => changeFilter('program_id', e.target.value)}><option value="">Tất cả chương trình</option>{programs.map((item) => <option key={item.ma_chuong_trinh} value={item.ma_chuong_trinh}>{item.ten_ct}</option>)}</CustomSelect></label>
      <label>Kỳ phụ cấp<input type="month" value={filters.ky} onChange={(e) => changeFilter('ky', e.target.value)} /></label>
      <label>Năm<input type="number" min={1000} max={9999} placeholder="Tất cả" value={filters.year} onChange={(e) => changeFilter('year', e.target.value)} /></label>
      <button type="button" className="btn btn-secondary" onClick={() => { setFilters({ search: '', program_id: '', ky: '', year: '' }); setPage(1); }}>Xóa bộ lọc</button>
      {programError && <p className="allowance-error" role="alert">Không tải được bộ lọc chương trình: {programError} <button type="button" onClick={() => setRevision((n) => n + 1)}>Thử lại</button></p>}
    </section>
    <section className="allowance-card" aria-busy={loading}>
      <div className="allowance-card-heading"><div><h2>{canManage ? 'Danh sách phụ cấp thực tập sinh' : 'Phụ cấp của bạn'}</h2><p className="allowance-muted">{result.total} bản ghi · Sắp xếp theo kỳ mới nhất</p></div><Wallet size={25} className="allowance-accent" /></div>
      {loading ? <div role="status" className="allowance-empty"><RefreshCw size={27} /><h3>Đang tải phụ cấp…</h3></div> : error ? <div className="allowance-empty"><p role="alert" className="allowance-error">{error}</p><button type="button" className="btn btn-secondary" onClick={() => setRevision((n) => n + 1)}>Thử lại</button></div> : !result.items.length ? <div className="allowance-empty"><Inbox size={38} /><h3>Chưa có thông tin phụ cấp</h3><p>{canManage ? 'Thêm phụ cấp cho hồ sơ đã duyệt hoặc điều chỉnh bộ lọc.' : 'Phụ cấp do HR nhập sẽ xuất hiện tại đây. Bạn có thể thử đổi bộ lọc.'}</p></div> : <div className="allowance-table-wrap"><table className="allowance-table"><thead><tr>{canManage && <th>Thực tập sinh</th>}<th>Chương trình</th><th>Kỳ</th><th>Số tiền</th><th>Ghi chú</th>{canManage && <th>Cập nhật</th>}<th className="allowance-actions-cell">Thao tác</th></tr></thead><tbody>{result.items.map((item) => <tr key={item.id}>
        {canManage && <td data-label="Thực tập sinh"><strong>{item.ho_ten}</strong><small>{item.email}</small></td>}<td data-label="Chương trình"><strong>{item.ten_ct}</strong><small>{item.ma_ct} · HS #{item.ma_ho_so}</small></td><td data-label="Kỳ"><span className="allowance-period-badge">{periodLabel(item.ky)}</span></td><td data-label="Số tiền"><strong className="allowance-money">{money(item.so_tien)}</strong></td><td data-label="Ghi chú"><span className="allowance-note-preview" title={item.ghi_chu}>{item.ghi_chu || '—'}</span></td>{canManage && <td data-label="Cập nhật"><span>{item.nguoi_cap_nhat}</span><small>{timestamp(item.updated_at)}</small></td>}<td data-label="Thao tác" className="allowance-actions-cell"><div className="allowance-row-actions"><button type="button" className="btn btn-secondary btn-sm" title="Xem chi tiết" aria-label={`Xem phụ cấp #${item.id}`} onClick={() => setDetailId(item.id)}><Eye size={17} /></button>{canManage && <button type="button" className="btn btn-secondary btn-sm" title="Sửa phụ cấp" aria-label={`Sửa phụ cấp #${item.id}`} onClick={() => setForm({ record: item })}><Pencil size={17} /></button>}</div></td>
      </tr>)}</tbody></table></div>}
      <TablePagination page={page} pageSize={pageSize} totalItems={result.total} totalPages={Math.ceil(result.total / pageSize)} itemLabel="khoản phụ cấp" disabled={loading} onPageChange={setPage} onPageSizeChange={(value) => { setPageSize(value); setPage(1); }} />
    </section>
    {detailId && <AllowanceDetails key={detailId} recordId={detailId} endpoint={endpoint} canManage={canManage} onClose={() => setDetailId(null)} />}
  </div>;
}
