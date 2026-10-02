import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CalendarClock, CheckCircle2, ClipboardList, Filter, Pencil, Plus,
  RefreshCw, Trash2, UserRound, X,
} from 'lucide-react';
import ConfirmDialog from '../components/ConfirmDialog';
import { apiFetch, readJsonResponse } from '../utils/api';

const priorities = {
  LOW: { label: 'Thấp', tone: 'muted' },
  MEDIUM: { label: 'Trung bình', tone: 'info' },
  HIGH: { label: 'Cao', tone: 'warning' },
  URGENT: { label: 'Khẩn cấp', tone: 'danger' },
};
const statuses = {
  TODO: { label: 'Cần thực hiện', tone: 'warning' },
  IN_PROGRESS: { label: 'Đang thực hiện', tone: 'info' },
  COMPLETED: { label: 'Hoàn thành', tone: 'success' },
  CANCELLED: { label: 'Đã hủy', tone: 'muted' },
};
const emptyForm = { internship_profile_id: '', title: '', description: '', due_date: '', priority: 'MEDIUM' };

function displayDate(value, withTime = false) {
  if (!value) return '—';
  const text = String(value);
  if (!withTime) {
    const [year, month, day] = text.slice(0, 10).split('-');
    return `${day}/${month}/${year}`;
  }
  const parsed = new Date(text.includes('T') ? text : text.replace(' ', 'T'));
  return Number.isNaN(parsed.getTime()) ? text : parsed.toLocaleString('vi-VN');
}

function TaskBadge({ value, map }) {
  const item = map[value] || { label: value, tone: 'muted' };
  return <span className={`task-badge is-${item.tone}`}>{item.label}</span>;
}

export default function InternshipTasksView({ currentUser, onShowToast }) {
  const isMentor = currentUser?.vai_tro === 'Mentor';
  const [tasks, setTasks] = useState([]);
  const [interns, setInterns] = useState([]);
  const [selectedTask, setSelectedTask] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [filters, setFilters] = useState({ internship_profile_id: '', status: '', priority: '', due_date: '' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [editing, setEditing] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const taskUrl = useMemo(() => {
    if (!isMentor) return '/api/interns/me/tasks';
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => value && params.set(key, value));
    const query = params.toString();
    return `/api/mentor/tasks${query ? `?${query}` : ''}`;
  }, [filters, isMentor]);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const requests = [apiFetch(taskUrl)];
      if (isMentor && !interns.length) requests.push(apiFetch('/api/mentor/me/interns'));
      const responses = await Promise.all(requests);
      const taskData = await readJsonResponse(responses[0]);
      if (!responses[0].ok) throw new Error(taskData.detail || 'Không thể tải danh sách nhiệm vụ.');
      setTasks(taskData);
      setSelectedTask((current) => current && taskData.find((task) => task.id === current.id) || null);
      if (responses[1]) {
        const internData = await readJsonResponse(responses[1]);
        if (!responses[1].ok) throw new Error(internData.detail || 'Không thể tải danh sách thực tập sinh.');
        setInterns(internData);
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, [interns.length, isMentor, taskUrl]);

  useEffect(() => { void Promise.resolve().then(loadTasks); }, [loadTasks]);

  const openDetail = async (task) => {
    setError('');
    try {
      const response = await apiFetch(`/api/tasks/${task.id}`);
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể mở nhiệm vụ.');
      setSelectedTask(data);
      setEditing(false);
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const updateForm = (event) => setForm((current) => ({ ...current, [event.target.name]: event.target.value }));

  const submitCreate = async (event) => {
    event.preventDefault();
    setSaving(true);
    setFormError('');
    try {
      const response = await apiFetch('/api/mentor/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, internship_profile_id: Number(form.internship_profile_id) }),
      });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail?.[0]?.msg || data.detail || 'Không thể giao nhiệm vụ.');
      setForm(emptyForm);
      setSelectedTask(data);
      onShowToast?.('Đã giao nhiệm vụ cho thực tập sinh.');
      await loadTasks();
    } catch (requestError) {
      setFormError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const beginEdit = () => {
    setForm({
      internship_profile_id: String(selectedTask.internship_profile_id),
      title: selectedTask.title,
      description: selectedTask.description || '',
      due_date: String(selectedTask.due_date).slice(0, 10),
      priority: selectedTask.priority,
    });
    setFormError('');
    setEditing(true);
  };

  const submitEdit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setFormError('');
    try {
      const response = await apiFetch(`/api/mentor/tasks/${selectedTask.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: form.title, description: form.description, due_date: form.due_date, priority: form.priority }),
      });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail?.[0]?.msg || data.detail || 'Không thể cập nhật nhiệm vụ.');
      setSelectedTask(data);
      setEditing(false);
      setForm(emptyForm);
      onShowToast?.('Đã cập nhật nhiệm vụ.');
      await loadTasks();
    } catch (requestError) {
      setFormError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = async () => {
    setSaving(true);
    setFormError('');
    try {
      const response = await apiFetch(`/api/mentor/tasks/${deleteTarget.id}`, { method: 'DELETE' });
      if (!response.ok) {
        const data = await readJsonResponse(response);
        throw new Error(data.detail || 'Không thể xóa nhiệm vụ.');
      }
      setDeleteTarget(null);
      setSelectedTask(null);
      onShowToast?.('Đã xóa nhiệm vụ.');
      await loadTasks();
    } catch (requestError) {
      setError(requestError.message);
      setDeleteTarget(null);
    } finally {
      setSaving(false);
    }
  };

  const renderTaskForm = (edit = false) => <form className="task-form" onSubmit={edit ? submitEdit : submitCreate}>
    {!edit && <label><span>Thực tập sinh</span><select name="internship_profile_id" value={form.internship_profile_id} onChange={updateForm} required>
      <option value="">Chọn thực tập sinh</option>
      {interns.map((intern) => <option key={intern.internship_profile_id} value={intern.internship_profile_id}>{intern.intern_name}</option>)}
    </select></label>}
    <label><span>Tiêu đề</span><input name="title" value={form.title} onChange={updateForm} maxLength={200} required placeholder="Ví dụ: Hoàn thiện API đăng nhập" /></label>
    <label><span>Nội dung</span><textarea name="description" value={form.description} onChange={updateForm} maxLength={5000} rows={5} placeholder="Mô tả kết quả mong đợi và yêu cầu thực hiện" /></label>
    <div className="task-form-row">
      <label><span>Hạn hoàn thành</span><input type="date" name="due_date" value={form.due_date} onChange={updateForm} required /></label>
      <label><span>Độ ưu tiên</span><select name="priority" value={form.priority} onChange={updateForm} required>
        {Object.entries(priorities).map(([value, item]) => <option value={value} key={value}>{item.label}</option>)}
      </select></label>
    </div>
    {formError && <p className="task-form-error" role="alert">{formError}</p>}
    <div className="task-form-actions">
      {edit && <button type="button" className="btn btn-secondary" disabled={saving} onClick={() => { setEditing(false); setForm(emptyForm); }}><X size={15} />Hủy</button>}
      <button type="submit" className="btn btn-primary" disabled={saving || (!edit && !interns.length)}>{edit ? <Pencil size={15} /> : <Plus size={15} />}{saving ? 'Đang lưu…' : edit ? 'Lưu thay đổi' : 'Giao nhiệm vụ'}</button>
    </div>
  </form>;

  return <div className="workspace-page task-page">
    <header className="workspace-heading"><div><span className="workspace-eyebrow">QUẢN LÝ CÔNG VIỆC & ĐÁNH GIÁ</span><h2>Nhiệm vụ thực tập</h2><p>{isMentor ? 'Giao và theo dõi nhiệm vụ của các thực tập sinh bạn đang phụ trách.' : 'Xem nhiệm vụ được Mentor giao và thông tin hạn hoàn thành.'}</p></div><button className="btn btn-secondary" type="button" disabled={loading} onClick={loadTasks}><RefreshCw size={15} />Làm mới</button></header>

    {isMentor && <section className="workspace-card task-filters" aria-label="Bộ lọc nhiệm vụ">
      <Filter size={17} />
      <select aria-label="Lọc theo thực tập sinh" value={filters.internship_profile_id} onChange={(event) => setFilters((current) => ({ ...current, internship_profile_id: event.target.value }))}><option value="">Tất cả TTS</option>{interns.map((intern) => <option value={intern.internship_profile_id} key={intern.internship_profile_id}>{intern.intern_name}</option>)}</select>
      <select aria-label="Lọc theo trạng thái" value={filters.status} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}><option value="">Tất cả trạng thái</option>{Object.entries(statuses).map(([value, item]) => <option value={value} key={value}>{item.label}</option>)}</select>
      <select aria-label="Lọc theo độ ưu tiên" value={filters.priority} onChange={(event) => setFilters((current) => ({ ...current, priority: event.target.value }))}><option value="">Tất cả ưu tiên</option>{Object.entries(priorities).map(([value, item]) => <option value={value} key={value}>{item.label}</option>)}</select>
      <input aria-label="Lọc theo hạn hoàn thành" type="date" value={filters.due_date} onChange={(event) => setFilters((current) => ({ ...current, due_date: event.target.value }))} />
    </section>}

    {error && <div className="workspace-error" role="alert"><span>{error}</span><button className="btn btn-secondary btn-sm" type="button" onClick={loadTasks}>Thử lại</button></div>}

    <div className={`task-layout${isMentor ? '' : ' is-intern'}`}>
      <section className="workspace-card task-list-card">
        <div className="workspace-section-heading"><div><span className="workspace-eyebrow">DANH SÁCH</span><h3>{isMentor ? 'Nhiệm vụ đã giao' : 'Nhiệm vụ của tôi'} <small>{tasks.length}</small></h3></div><ClipboardList size={19} /></div>
        {loading ? <div className="workspace-loading">Đang tải nhiệm vụ…</div> : tasks.length ? <div className="task-list">{tasks.map((task) => <button type="button" className={`task-list-item${selectedTask?.id === task.id ? ' selected' : ''}`} key={task.id} onClick={() => openDetail(task)}>
          <div className="task-list-title"><strong>{task.title}</strong><TaskBadge value={task.priority} map={priorities} /></div>
          <span><UserRound size={13} />{isMentor ? task.intern_name : task.mentor_name}</span>
          <span><CalendarClock size={13} />Hạn {displayDate(task.due_date)}</span>
          <TaskBadge value={task.status} map={statuses} />
        </button>)}</div> : <div className="workspace-empty"><ClipboardList size={25} /><strong>Chưa có nhiệm vụ</strong><span>{isMentor ? 'Hãy dùng biểu mẫu để giao nhiệm vụ đầu tiên.' : 'Nhiệm vụ Mentor giao sẽ xuất hiện tại đây.'}</span></div>}
      </section>

      {isMentor && <section className="workspace-card task-create-card"><div className="workspace-section-heading"><div><span className="workspace-eyebrow">GIAO VIỆC</span><h3>Nhiệm vụ mới</h3></div><Plus size={19} /></div>{interns.length ? renderTaskForm() : <div className="workspace-empty"><UserRound size={24} /><span>Bạn chưa có thực tập sinh được phân công nên chưa thể giao nhiệm vụ.</span></div>}</section>}
    </div>

    {selectedTask && <section className="workspace-card task-detail-card">
      <div className="workspace-section-heading"><div><span className="workspace-eyebrow">CHI TIẾT NHIỆM VỤ</span><h3>{selectedTask.title}</h3></div><div className="task-detail-actions">{isMentor && !editing && <><button type="button" className="btn btn-secondary btn-sm" onClick={beginEdit}><Pencil size={14} />Chỉnh sửa</button><button type="button" className="btn btn-danger btn-sm" onClick={() => setDeleteTarget(selectedTask)}><Trash2 size={14} />Xóa</button></>}</div></div>
      {editing ? renderTaskForm(true) : <div className="task-detail-content">
        <p>{selectedTask.description || 'Không có nội dung bổ sung.'}</p>
        <dl className="task-detail-grid">
          <div><dt>Thực tập sinh</dt><dd>{selectedTask.intern_name}</dd></div>
          <div><dt>Mentor giao</dt><dd>{selectedTask.mentor_name}</dd></div>
          <div><dt>Độ ưu tiên</dt><dd><TaskBadge value={selectedTask.priority} map={priorities} /></dd></div>
          <div><dt>Trạng thái</dt><dd><TaskBadge value={selectedTask.status} map={statuses} /></dd></div>
          <div><dt>Hạn hoàn thành</dt><dd>{displayDate(selectedTask.due_date)}</dd></div>
          <div><dt>Thời gian tạo</dt><dd>{displayDate(selectedTask.created_at, true)}</dd></div>
          <div><dt>Cập nhật gần nhất</dt><dd>{displayDate(selectedTask.updated_at, true)}</dd></div>
        </dl>
        {selectedTask.status === 'COMPLETED' && <p className="task-complete-note"><CheckCircle2 size={16} />Nhiệm vụ đã hoàn thành.</p>}
      </div>}
    </section>}

    <ConfirmDialog open={Boolean(deleteTarget)} title="Xóa nhiệm vụ" message={`Nhiệm vụ “${deleteTarget?.title || ''}” sẽ bị xóa khỏi hệ thống.`} confirmLabel="Xóa nhiệm vụ" danger busy={saving} onCancel={() => !saving && setDeleteTarget(null)} onConfirm={confirmDelete} />
  </div>;
}
