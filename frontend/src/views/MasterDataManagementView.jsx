import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Building2, Check, Edit3, Plus, RefreshCw, Search, Users, X } from 'lucide-react';
import { apiFetch } from '../utils/api';
import ConfirmDialog from '../components/ConfirmDialog';
import './MasterDataManagementView.css';

const PAGE_SIZE = 10;

function errorMessage(payload, fallback) {
  return typeof payload?.detail === 'string' ? payload.detail : fallback;
}

export default function MasterDataManagementView({ onShowToast }) {
  const [kind, setKind] = useState('departments');
  const [departments, setDepartments] = useState([]);
  const [universities, setUniversities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [page, setPage] = useState(1);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({});
  const [confirm, setConfirm] = useState(false);

  const loadCatalog = useCallback(async () => {
    try {
      const [departmentResponse, universityResponse] = await Promise.all([
        apiFetch('/api/master/departments?include_inactive=true'),
        apiFetch('/api/master/universities?include_inactive=true'),
      ]);
      const [departmentPayload, universityPayload] = await Promise.all([
        departmentResponse.json(), universityResponse.json(),
      ]);
      if (!departmentResponse.ok) throw new Error(errorMessage(departmentPayload, 'Không thể tải danh mục phòng ban.'));
      if (!universityResponse.ok) throw new Error(errorMessage(universityPayload, 'Không thể tải danh mục trường đại học.'));
      setDepartments(departmentPayload);
      setUniversities(universityPayload);
    } catch (loadError) {
      setError(loadError.message || 'Không thể tải danh mục.');
    } finally {
      setLoading(false);
    }
  }, []);

  // eslint-disable-next-line react/set-state-in-effect -- Loads persisted catalogs on mount.
  useEffect(() => { void loadCatalog(); }, [loadCatalog]);

  const allItems = kind === 'departments' ? departments : universities;
  const filtered = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return allItems.filter((item) => {
      const active = item.is_active !== false && item.is_active !== 0;
      const matchesStatus = statusFilter === 'ALL' || (statusFilter === 'ACTIVE' ? active : !active);
      const haystack = [item.ma_dinh_danh, item.ten_viet_tat, item.ten_phong_ban, item.ten_truong, item.mo_ta]
        .filter(Boolean).join(' ').toLocaleLowerCase();
      return matchesStatus && (!needle || haystack.includes(needle));
    });
  }, [allItems, search, statusFilter]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const visiblePage = Math.min(page, pageCount);
  const pageItems = filtered.slice((visiblePage - 1) * PAGE_SIZE, visiblePage * PAGE_SIZE);

  const openCreate = () => {
    setEditing(null);
    setForm(kind === 'departments'
      ? { ma_dinh_danh: '', ten_phong_ban: '', mo_ta: '', is_active: true }
      : { ma_dinh_danh: '', ten_viet_tat: '', ten_truong: '', is_active: true });
    setError('');
    setConfirm(false);
    setDialogOpen(true);
  };

  const openEdit = (item) => {
    setEditing(item);
    setForm(kind === 'departments'
      ? { ma_dinh_danh: item.ma_dinh_danh || '', ten_phong_ban: item.ten_phong_ban || '', mo_ta: item.mo_ta || '', is_active: item.is_active !== false && item.is_active !== 0 }
      : { ma_dinh_danh: item.ma_dinh_danh || '', ten_viet_tat: item.ten_viet_tat || '', ten_truong: item.ten_truong || '', is_active: item.is_active !== false && item.is_active !== 0 });
    setError('');
    setConfirm(false);
    setDialogOpen(true);
  };

  const save = async () => {
    setSaving(true);
    setError('');
    const endpoint = `/api/master/${kind}${editing ? `/${kind === 'departments' ? editing.ma_phong_ban : editing.ma_truong}` : ''}`;
    const method = editing ? 'PATCH' : 'POST';
    const body = kind === 'departments'
      ? { ...(!editing ? { ma_dinh_danh: form.ma_dinh_danh.trim() } : {}), ten_phong_ban: form.ten_phong_ban.trim(), mo_ta: form.mo_ta.trim(), ...(editing ? { is_active: form.is_active } : {}) }
      : { ma_dinh_danh: form.ma_dinh_danh.trim() || null, ten_viet_tat: form.ten_viet_tat.trim() || null, ten_truong: form.ten_truong.trim(), ...(editing ? { is_active: form.is_active } : {}) };
    try {
      const response = await apiFetch(endpoint, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(errorMessage(payload, 'Không thể lưu danh mục.'));
      setDialogOpen(false);
      setConfirm(false);
      onShowToast(editing ? 'Đã cập nhật danh mục.' : 'Đã thêm danh mục mới.');
      await loadCatalog();
    } catch (saveError) {
      setError(saveError.message || 'Không thể lưu danh mục.');
      setConfirm(false);
    } finally {
      setSaving(false);
    }
  };

  const requestSave = (event) => {
    event.preventDefault();
    if (editing && editing.is_active && !form.is_active && (kind === 'departments' ? (editing.mentor_count + editing.intern_count) : editing.intern_count) > 0) {
      setConfirm(true);
      return;
    }
    void save();
  };

  return (
    <section className="master-catalog-page">
      <header className="master-catalog-header">
        <div>
          <span className="master-catalog-eyebrow">QUẢN TRỊ DỮ LIỆU CHUNG</span>
          <h1>Quản lý danh mục</h1>
          <p>Quản lý các giá trị dùng chung. Hồ sơ cũ giữ nguyên liên kết; danh mục ngừng dùng vẫn được lưu để bảo toàn lịch sử.</p>
        </div>
        <div className="master-catalog-header-actions">
          <button type="button" className="btn btn-secondary" onClick={() => { setError(''); setLoading(true); void loadCatalog(); }} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'master-spinning' : ''} /> Làm mới
          </button>
          <button type="button" className="btn btn-primary" onClick={openCreate}>
            <Plus size={17} /> Thêm {kind === 'departments' ? 'phòng ban' : 'trường đại học'}
          </button>
        </div>
      </header>

      <div className="master-catalog-tabs" role="tablist" aria-label="Loại danh mục">
        <button type="button" role="tab" aria-selected={kind === 'departments'} className={kind === 'departments' ? 'is-active' : ''} onClick={() => { setKind('departments'); setPage(1); }}>
          <Users size={17} /> Phòng ban <span>{departments.length}</span>
        </button>
        <button type="button" role="tab" aria-selected={kind === 'universities'} className={kind === 'universities' ? 'is-active' : ''} onClick={() => { setKind('universities'); setPage(1); }}>
          <Building2 size={17} /> Trường đại học <span>{universities.length}</span>
        </button>
      </div>

      <section className="workspace-card master-catalog-card">
        <div className="master-catalog-toolbar">
          <label className="master-catalog-search">
            <Search size={17} aria-hidden="true" />
            <input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder="Tìm theo mã, tên hoặc mô tả" />
          </label>
          <select className="form-select master-catalog-filter" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }} aria-label="Lọc theo trạng thái">
            <option value="ALL">Tất cả trạng thái</option>
            <option value="ACTIVE">Đang hoạt động</option>
            <option value="INACTIVE">Đã ngừng sử dụng</option>
          </select>
        </div>

        {error && !dialogOpen && <div className="alert-banner error" role="alert">{error}</div>}
        {loading ? <div className="master-catalog-empty" role="status">Đang tải danh mục…</div> : pageItems.length === 0 ? (
          <div className="master-catalog-empty"><Building2 size={24} /><strong>Chưa có mục phù hợp</strong><span>Thử đổi từ khóa hoặc thêm mục mới vào danh mục.</span></div>
        ) : (
          <div className="master-catalog-table-wrap">
            <table className="master-catalog-table">
              <thead><tr>
                <th>Mã</th><th>{kind === 'departments' ? 'Tên phòng ban' : 'Tên trường'}</th>
                {kind === 'departments' ? <th>Mô tả</th> : <th>Tên viết tắt</th>}
                <th>Đang tham chiếu</th><th>Trạng thái</th><th>Cập nhật</th><th>Thao tác</th>
              </tr></thead>
              <tbody>{pageItems.map((item) => {
                const active = item.is_active !== false && item.is_active !== 0;
                const references = kind === 'departments' ? (item.mentor_count || 0) + (item.intern_count || 0) : (item.intern_count || 0);
                const id = kind === 'departments' ? item.ma_phong_ban : item.ma_truong;
                return <tr key={id}>
                  <td><span className="master-code">{item.ma_dinh_danh || '—'}</span></td>
                  <td><strong>{kind === 'departments' ? item.ten_phong_ban : item.ten_truong}</strong>{kind === 'departments' && <small>ID IMS: {id}</small>}</td>
                  <td>{kind === 'departments' ? (item.mo_ta || '—') : (item.ten_viet_tat || '—')}</td>
                  <td>{references}</td>
                  <td><span className={`master-status ${active ? 'is-active' : 'is-inactive'}`}>{active ? 'Đang hoạt động' : 'Ngừng sử dụng'}</span></td>
                  <td>{item.updated_at ? new Date(item.updated_at).toLocaleString('vi-VN') : '—'}</td>
                  <td><button type="button" className="btn btn-secondary btn-sm" onClick={() => openEdit(item)}><Edit3 size={14} /> Sửa</button></td>
                </tr>;
              })}</tbody>
            </table>
          </div>
        )}

        <footer className="master-catalog-footer">
          <span>{filtered.length ? `Đang hiển thị ${(visiblePage - 1) * PAGE_SIZE + 1}–${Math.min(visiblePage * PAGE_SIZE, filtered.length)} trên ${filtered.length}` : '0 mục'}</span>
          <div>
            <button type="button" className="btn btn-secondary btn-sm" disabled={visiblePage <= 1} onClick={() => setPage(visiblePage - 1)}>Trước</button>
            <span>Trang {visiblePage} / {pageCount}</span>
            <button type="button" className="btn btn-secondary btn-sm" disabled={visiblePage >= pageCount} onClick={() => setPage(visiblePage + 1)}>Tiếp</button>
          </div>
        </footer>
      </section>

      {dialogOpen && <div className="modal-overlay" onMouseDown={(event) => event.target === event.currentTarget && !saving && setDialogOpen(false)}>
        <section className="modal-container master-catalog-modal" role="dialog" aria-modal="true" aria-labelledby="master-catalog-modal-title">
          <header className="modal-header">
            <div><span className="master-catalog-eyebrow">{kind === 'departments' ? 'DANH MỤC PHÒNG BAN' : 'DANH MỤC TRƯỜNG'}</span><h2 id="master-catalog-modal-title">{editing ? 'Chỉnh sửa danh mục' : 'Thêm danh mục mới'}</h2></div>
            <button type="button" className="modal-close-btn" aria-label="Đóng" onClick={() => setDialogOpen(false)} disabled={saving}><X size={18} /></button>
          </header>
          <form className="master-catalog-form" onSubmit={requestSave}>
            <div className="master-catalog-form-fields">
              {kind === 'departments' ? <>
                <label className="form-group"><span className="form-label">Mã phòng ban <b className="required">*</b></span><input className="form-control" required maxLength={32} value={form.ma_dinh_danh} disabled={Boolean(editing)} onChange={(event) => setForm((value) => ({ ...value, ma_dinh_danh: event.target.value.toUpperCase() }))} placeholder="Ví dụ: DATA" /><small className="form-hint">Mã ổn định dùng để tham chiếu; sau khi tạo sẽ không đổi.</small></label>
                <label className="form-group"><span className="form-label">Tên phòng ban <b className="required">*</b></span><input className="form-control" required maxLength={100} value={form.ten_phong_ban} onChange={(event) => setForm((value) => ({ ...value, ten_phong_ban: event.target.value }))} placeholder="Tên hiển thị trong IMS" /></label>
                <label className="form-group"><span className="form-label">Mô tả</span><textarea className="form-control" rows={3} maxLength={500} value={form.mo_ta} onChange={(event) => setForm((value) => ({ ...value, mo_ta: event.target.value }))} placeholder="Mô tả ngắn về phòng ban" /></label>
              </> : <>
                <label className="form-group"><span className="form-label">Tên trường đại học <b className="required">*</b></span><input className="form-control" required maxLength={255} value={form.ten_truong} onChange={(event) => setForm((value) => ({ ...value, ten_truong: event.target.value }))} placeholder="Tên trường theo danh mục chính thức" /></label>
                <label className="form-group"><span className="form-label">Mã trường (tùy chọn)</span><input className="form-control" maxLength={32} value={form.ma_dinh_danh} onChange={(event) => setForm((value) => ({ ...value, ma_dinh_danh: event.target.value.toUpperCase() }))} placeholder="Ví dụ: HUST" /></label>
                <label className="form-group"><span className="form-label">Tên viết tắt</span><input className="form-control" maxLength={50} value={form.ten_viet_tat} onChange={(event) => setForm((value) => ({ ...value, ten_viet_tat: event.target.value }))} placeholder="Ví dụ: HUST" /></label>
              </>}
              {editing && <label className="master-catalog-active-toggle"><input type="checkbox" checked={Boolean(form.is_active)} onChange={(event) => setForm((value) => ({ ...value, is_active: event.target.checked }))} /><span><strong>Danh mục đang hoạt động</strong><small>Tắt mục này để không xuất hiện khi tạo hồ sơ mới. Liên kết và lịch sử hiện có vẫn được giữ.</small></span></label>}
              {editing && <p className="master-catalog-reference-note">Đang được tham chiếu bởi <strong>{kind === 'departments' ? (editing.mentor_count || 0) + (editing.intern_count || 0) : (editing.intern_count || 0)}</strong> {kind === 'departments' ? 'tài khoản Mentor/TTS' : 'hồ sơ TTS'}. Không có thao tác xóa cứng.</p>}
              {error && <div className="alert-banner error" role="alert">{error}</div>}
            </div>
            <footer className="modal-footer"><button type="button" className="btn btn-secondary" disabled={saving} onClick={() => setDialogOpen(false)}>Hủy</button><button type="submit" className="btn btn-primary" disabled={saving} aria-busy={saving}>{saving ? 'Đang lưu…' : <><Check size={16} /> Lưu thay đổi</>}</button></footer>
          </form>
        </section>
      </div>}

      <ConfirmDialog
        open={confirm}
        title="Ngừng sử dụng danh mục?"
        message="Mục này đang được hồ sơ hoặc tài khoản sử dụng. IMS sẽ giữ nguyên mọi liên kết và lịch sử; mục chỉ bị ẩn khỏi lựa chọn mới."
        confirmLabel="Ngừng sử dụng"
        danger
        busy={saving}
        onCancel={() => setConfirm(false)}
        onConfirm={() => void save()}
      />
    </section>
  );
}
