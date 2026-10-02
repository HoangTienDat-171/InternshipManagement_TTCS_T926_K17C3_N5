import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CalendarClock, CheckCircle2, ClipboardList, Filter, Pencil, Plus,
  History, RefreshCw, Save, Trash2, TrendingUp, UserRound, X,
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
const emptyProgressForm = { progress_percent: 0, status: 'TODO', note: '' };

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

function ProgressBar({ value = 0 }) {
  const percent = Math.max(0, Math.min(100, Number(value) || 0));
  return <div className="task-progress" aria-label={`Tiến độ ${percent}%`}>
    <div><span>Tiến độ</span><strong>{percent}%</strong></div>
    <span className="task-progress-track"><i style={{ width: `${percent}%` }} /></span>
  </div>;
}

export default function InternshipTasksView({ currentUser, onShowToast }) {
  const isMentor = currentUser?.vai_tro === 'Mentor';
  const [tasks, setTasks] = useState([]);
  const [interns, setInterns] = useState([]);
  const [selectedTask, setSelectedTask] = useState(null);
  const canManageSelectedTask = isMentor && selectedTask?.mentor_id === currentUser?.ma_nguoi_dung;
  const [form, setForm] = useState(emptyForm);
  const [filters, setFilters] = useState({ internship_profile_id: '', status: '', priority: '', due_date: '' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [progressForm, setProgressForm] = useState(emptyProgressForm);
  const [progressError, setProgressError] = useState('');

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
    setProgressError('');
    setHistoryLoading(true);
    try {
      const [detailResponse, historyResponse] = await Promise.all([
        apiFetch(`/api/tasks/${task.id}`),
        apiFetch(`/api/tasks/${task.id}/progress-history`),
      ]);
      const [data, historyData] = await Promise.all([
        readJsonResponse(detailResponse),
        readJsonResponse(historyResponse),
      ]);
      if (!detailResponse.ok) throw new Error(data.detail || 'Không thể mở nhiệm vụ.');
      if (!historyResponse.ok) throw new Error(historyData.detail || 'Không thể tải lịch sử tiến độ.');
      setSelectedTask(data);
      setHistory(historyData);
      setProgressForm({
        progress_percent: data.progress_percent ?? 0,
        status: data.status,
        note: data.progress_note || '',
      });
      setEditing(false);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setHistoryLoading(false);
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
      setHistory([]);
      setCreating(false);
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
      onShowToast?.('Đã xử lý yêu cầu xóa hoặc hủy nhiệm vụ.');
      await loadTasks();
    } catch (requestError) {
      setError(requestError.message);
      setDeleteTarget(null);
    } finally {
      setSaving(false);
    }
  };

  const submitProgress = async (event) => {
    event.preventDefault();
    const progress = Number(progressForm.progress_percent);
    setProgressError('');
    if (!Number.isInteger(progress) || progress < 0 || progress > 100) {
      setProgressError('Tiến độ phải là số nguyên từ 0 đến 100.');
      return;
    }
    if ((progress === 100) !== (progressForm.status === 'COMPLETED')) {
      setProgressError('Tiến độ 100% phải đi cùng trạng thái Hoàn thành.');
      return;
    }
    setSaving(true);
    try {
      const response = await apiFetch(`/api/interns/me/tasks/${selectedTask.id}/progress`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...progressForm, progress_percent: progress }),
      });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail?.[0]?.msg || data.detail || 'Không thể cập nhật tiến độ.');
      const historyResponse = await apiFetch(`/api/tasks/${selectedTask.id}/progress-history`);
      const historyData = await readJsonResponse(historyResponse);
      if (!historyResponse.ok) throw new Error(historyData.detail || 'Không thể tải lại lịch sử tiến độ.');
      setSelectedTask(data);
      setHistory(historyData);
      setTasks((current) => current.map((task) => task.id === data.id ? data : task));
      setProgressForm({ progress_percent: data.progress_percent, status: data.status, note: data.progress_note || '' });
      onShowToast?.('Đã cập nhật tiến độ nhiệm vụ.');
    } catch (requestError) {
      setProgressError(requestError.message);
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
      <button type="button" className="btn btn-secondary" disabled={saving} onClick={() => { setEditing(false); setCreating(false); setForm(emptyForm); setFormError(''); }}><X size={15} />Hủy</button>
      <button type="submit" className="btn btn-primary" disabled={saving || (!edit && !interns.length)}>{edit ? <Pencil size={15} /> : <Plus size={15} />}{saving ? 'Đang lưu…' : edit ? 'Lưu thay đổi' : 'Giao nhiệm vụ'}</button>
    </div>
  </form>;

  const renderProgressForm = () => {
    const terminal = ['COMPLETED', 'CANCELLED'].includes(selectedTask.status);
    const statusOptions = selectedTask.status === 'TODO'
      ? ['TODO', 'IN_PROGRESS', 'COMPLETED']
      : ['IN_PROGRESS', 'COMPLETED'];
    if (terminal) return <p className="task-progress-locked" role="status">
      <CheckCircle2 size={16} />Nhiệm vụ đã ở trạng thái cuối và không thể cập nhật thêm.
    </p>;
    return <form className="task-progress-form" onSubmit={submitProgress}>
      <div className="task-form-row">
        <label><span>Phần trăm hoàn thành</span><input type="number" min="0" max="100" step="1" value={progressForm.progress_percent} onChange={(event) => setProgressForm((current) => ({ ...current, progress_percent: event.target.value }))} required /></label>
        <label><span>Trạng thái tiến độ</span><select value={progressForm.status} onChange={(event) => setProgressForm((current) => ({ ...current, status: event.target.value }))} required>
          {statusOptions.map((value) => <option value={value} key={value}>{statuses[value].label}</option>)}
        </select></label>
      </div>
      <label><span>Ghi chú tiến độ</span><textarea rows={4} maxLength={2000} value={progressForm.note} onChange={(event) => setProgressForm((current) => ({ ...current, note: event.target.value }))} placeholder="Mô tả phần việc đã hoàn thành hoặc vướng mắc hiện tại" /></label>
      {progressError && <p className="task-form-error" role="alert">{progressError}</p>}
      <div className="task-form-actions"><button type="submit" className="btn btn-primary" disabled={saving}><Save size={15} />{saving ? 'Đang lưu…' : 'Cập nhật tiến độ'}</button></div>
    </form>;
  };

  return <div className="workspace-page task-page">
    <header className="workspace-heading"><div><span className="workspace-eyebrow">QUẢN LÝ CÔNG VIỆC & ĐÁNH GIÁ</span><h2>Nhiệm vụ thực tập</h2><p>{isMentor ? 'Giao và theo dõi nhiệm vụ của các thực tập sinh bạn đang phụ trách.' : 'Xem nhiệm vụ được Mentor giao và thông tin hạn hoàn thành.'}</p></div><div className="task-heading-actions">{isMentor && <button className="btn btn-primary" type="button" onClick={() => { setCreating(true); setEditing(false); setForm(emptyForm); setFormError(''); }}><Plus size={15} />Giao nhiệm vụ</button>}<button className="btn btn-secondary" type="button" disabled={loading} onClick={loadTasks}><RefreshCw size={15} />Làm mới</button></div></header>

    {isMentor && <section className="workspace-card task-filters" aria-label="Bộ lọc nhiệm vụ">
      <Filter size={17} />
      <select aria-label="Lọc theo thực tập sinh" value={filters.internship_profile_id} onChange={(event) => setFilters((current) => ({ ...current, internship_profile_id: event.target.value }))}><option value="">Tất cả TTS</option>{interns.map((intern) => <option value={intern.internship_profile_id} key={intern.internship_profile_id}>{intern.intern_name}</option>)}</select>
      <select aria-label="Lọc theo trạng thái" value={filters.status} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}><option value="">Tất cả trạng thái</option>{Object.entries(statuses).map(([value, item]) => <option value={value} key={value}>{item.label}</option>)}</select>
      <select aria-label="Lọc theo độ ưu tiên" value={filters.priority} onChange={(event) => setFilters((current) => ({ ...current, priority: event.target.value }))}><option value="">Tất cả ưu tiên</option>{Object.entries(priorities).map(([value, item]) => <option value={value} key={value}>{item.label}</option>)}</select>
      <input aria-label="Lọc theo hạn hoàn thành" type="date" value={filters.due_date} onChange={(event) => setFilters((current) => ({ ...current, due_date: event.target.value }))} />
    </section>}

    {error && <div className="workspace-error" role="alert"><span>{error}</span><button className="btn btn-secondary btn-sm" type="button" onClick={loadTasks}>Thử lại</button></div>}

    <div className={`task-layout${isMentor && creating ? '' : ' is-intern'}`}>
      <section className="workspace-card task-list-card">
        <div className="workspace-section-heading"><div><span className="workspace-eyebrow">DANH SÁCH</span><h3>{isMentor ? 'Nhiệm vụ đang phụ trách' : 'Nhiệm vụ của tôi'} <small>{tasks.length}</small></h3></div><ClipboardList size={19} /></div>
        {loading ? <div className="workspace-loading">Đang tải nhiệm vụ…</div> : tasks.length ? <div className="task-list">{tasks.map((task) => <button type="button" className={`task-list-item${selectedTask?.id === task.id ? ' selected' : ''}`} key={task.id} onClick={() => openDetail(task)}>
          <div className="task-list-title"><strong>{task.title}</strong><TaskBadge value={task.priority} map={priorities} /><span className="task-list-progress">{task.progress_percent ?? 0}%</span></div>
          <span><UserRound size={13} />{isMentor ? task.intern_name : task.mentor_name}</span>
          <span><CalendarClock size={13} />Hạn {displayDate(task.due_date)}</span>
          <TaskBadge value={task.status} map={statuses} />
        </button>)}</div> : <div className="workspace-empty"><ClipboardList size={25} /><strong>Chưa có nhiệm vụ</strong><span>{isMentor ? 'Chọn Giao nhiệm vụ để tạo nhiệm vụ đầu tiên.' : 'Nhiệm vụ Mentor giao sẽ xuất hiện tại đây.'}</span></div>}
      </section>

      {isMentor && creating && <section className="workspace-card task-create-card"><div className="workspace-section-heading"><div><span className="workspace-eyebrow">GIAO VIỆC</span><h3>Giao nhiệm vụ mới</h3></div><Plus size={19} /></div>{interns.length ? renderTaskForm() : <div className="workspace-empty"><UserRound size={24} /><span>Bạn chưa có thực tập sinh được phân công nên chưa thể giao nhiệm vụ.</span></div>}</section>}
    </div>

    {selectedTask && <section className="workspace-card task-detail-card">
      <div className="workspace-section-heading"><div><span className="workspace-eyebrow">CHI TIẾT NHIỆM VỤ</span><h3>{selectedTask.title}</h3></div><div className="task-detail-actions">{canManageSelectedTask && !editing && <><button type="button" className="btn btn-secondary btn-sm" onClick={beginEdit}><Pencil size={14} />Chỉnh sửa</button><button type="button" className="btn btn-danger btn-sm" onClick={() => setDeleteTarget(selectedTask)}><Trash2 size={14} />Xóa / hủy</button></>}</div></div>
      {editing ? renderTaskForm(true) : <div className="task-detail-content">
        <p>{selectedTask.description || 'Không có nội dung bổ sung.'}</p>
        <dl className="task-detail-grid">
          <div><dt>Thực tập sinh</dt><dd>{selectedTask.intern_name}</dd></div>
          <div><dt>Mentor giao</dt><dd>{selectedTask.mentor_name}</dd></div>
          <div><dt>Độ ưu tiên</dt><dd><TaskBadge value={selectedTask.priority} map={priorities} /></dd></div>
          <div><dt>Trạng thái</dt><dd><TaskBadge value={selectedTask.status} map={statuses} /></dd></div>
          <div><dt>Tiến độ hiện tại</dt><dd>{selectedTask.progress_percent ?? 0}%</dd></div>
          <div><dt>Hạn hoàn thành</dt><dd>{displayDate(selectedTask.due_date)}</dd></div>
          <div><dt>Thời gian tạo</dt><dd>{displayDate(selectedTask.created_at, true)}</dd></div>
          <div><dt>Cập nhật gần nhất</dt><dd>{displayDate(selectedTask.updated_at, true)}</dd></div>
        </dl>
        <div className="task-current-progress">
          <ProgressBar value={selectedTask.progress_percent} />
          <div className="task-latest-note"><strong>Ghi chú gần nhất</strong><p>{selectedTask.progress_note || 'Chưa có ghi chú tiến độ.'}</p></div>
        </div>
        {selectedTask.status === 'COMPLETED' && <p className="task-complete-note"><CheckCircle2 size={16} />Nhiệm vụ đã hoàn thành.</p>}
      </div>}
    </section>}

    {selectedTask && !editing && <div className={`task-progress-layout${isMentor ? ' is-mentor' : ''}`}>
      {!isMentor && <section className="workspace-card task-progress-update-card">
        <div className="workspace-section-heading"><div><span className="workspace-eyebrow">CẬP NHẬT TIẾN ĐỘ</span><h3>Tiến độ của bạn</h3></div><TrendingUp size={19} /></div>
        {renderProgressForm()}
      </section>}
      <section className="workspace-card task-history-card">
        <div className="workspace-section-heading"><div><span className="workspace-eyebrow">NHẬT KÝ THAY ĐỔI</span><h3>Lịch sử tiến độ <small>{history.length}</small></h3></div><History size={19} /></div>
        {historyLoading ? <div className="workspace-loading small">Đang tải lịch sử…</div> : history.length ? <ol className="task-history-list">
          {[...history].reverse().map((entry) => <li key={entry.id}>
            <span className="task-history-dot" />
            <div className="task-history-main">
              <time>{displayDate(entry.created_at, true)}</time>
              <div className="task-history-change"><strong>{entry.old_progress}%</strong><span>→</span><strong>{entry.new_progress}%</strong><TaskBadge value={entry.new_status} map={statuses} /></div>
              <p>{entry.note || 'Không có ghi chú.'}</p>
              <small>Cập nhật bởi {entry.updated_by_name}</small>
            </div>
          </li>)}
        </ol> : <div className="workspace-empty"><History size={24} /><span>Chưa có lần cập nhật tiến độ nào.</span></div>}
      </section>
    </div>}

    <ConfirmDialog open={Boolean(deleteTarget)} title="Xóa hoặc hủy nhiệm vụ" message={`Nhiệm vụ “${deleteTarget?.title || ''}” sẽ bị xóa nếu chưa có tiến độ; nếu đã có lịch sử, nhiệm vụ sẽ chuyển sang Đã hủy để giữ dữ liệu.`} confirmLabel="Tiếp tục" danger busy={saving} onCancel={() => !saving && setDeleteTarget(null)} onConfirm={confirmDelete} />
  </div>;
}
