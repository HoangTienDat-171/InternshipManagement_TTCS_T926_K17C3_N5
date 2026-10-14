import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CalendarDays, Check, Clock3, Edit3, ExternalLink, MapPin, Plus, RefreshCw, Search, Send, Trash2, Users, Video, X } from 'lucide-react';
import { apiFetch, readJsonResponse } from '../utils/api';
import './MeetingsView.css';

const emptyForm = {
  title: '', content: '', start_at: '', end_at: '', location: '', meeting_url: '', attendee_ids: [],
};

async function readChecked(response, fallback) {
  const data = await readJsonResponse(response);
  if (!response.ok) throw new Error(data.detail || fallback);
  return data;
}

function toLocalDateTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (part) => String(part).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatDate(value) {
  if (!value) return 'Chưa có thời gian';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('vi-VN', {
    dateStyle: 'medium', timeStyle: 'short',
  }).format(date);
}

function roleLabel(role) {
  return ({ ThucTapSinh: 'Thực tập sinh', Mentor: 'Mentor', HR: 'HR', Admin: 'Admin' })[role] || role;
}

function emailSummaryText(summary = {}) {
  const parts = [];
  if (summary.sent) parts.push(`${summary.sent} đã gửi`);
  if (summary.queued) parts.push(`${summary.queued} đang chờ`);
  if (summary.failed) parts.push(`${summary.failed} lỗi`);
  return summary.total ? parts.join(' · ') || 'Đang xử lý' : 'Chưa có email';
}

export default function MeetingsView({ currentUser, onShowToast, requestedMeetingId, onRequestedMeetingHandled }) {
  const isManager = ['Admin', 'HR'].includes(currentUser?.vai_tro);
  const [meetings, setMeetings] = useState([]);
  const [participants, setParticipants] = useState([]);
  const [participantSearch, setParticipantSearch] = useState('');
  const [meetingSearch, setMeetingSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);
  const [formOpen, setFormOpen] = useState(false);
  const [editingMeeting, setEditingMeeting] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [cancelTarget, setCancelTarget] = useState(null);
  const requestKeyRef = useRef(null);
  const detailRequestRef = useRef(null);
  const modalDetail = requestedMeetingId
    ? (String(detail?.id) === String(requestedMeetingId) ? detail : null)
    : detail;
  const requestedDetailLoading = Boolean(requestedMeetingId && !modalDetail && !detailError);

  const refresh = useCallback(() => {
    setLoading(true);
    setRefreshKey((value) => value + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    apiFetch('/api/meetings', { signal: controller.signal })
      .then((response) => readChecked(response, 'Không thể tải lịch họp.'))
      .then((data) => { setMeetings(Array.isArray(data) ? data : []); setError(''); })
      .catch((reason) => { if (reason.name !== 'AbortError') setError(reason.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [refreshKey]);

  useEffect(() => {
    if (!isManager || !formOpen) return undefined;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      const query = new URLSearchParams();
      if (participantSearch.trim()) query.set('search', participantSearch.trim());
      apiFetch(`/api/meetings/participants?${query}`, { signal: controller.signal })
        .then((response) => readChecked(response, 'Không thể tải danh sách người tham gia.'))
        .then((data) => setParticipants(Array.isArray(data) ? data : []))
        .catch((reason) => { if (reason.name !== 'AbortError') setFormError(reason.message); });
    }, 180);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [isManager, formOpen, participantSearch]);

  const openDetail = useCallback(async (meetingId) => {
    detailRequestRef.current?.abort();
    const controller = new AbortController();
    detailRequestRef.current = controller;
    setDetail(null);
    setDetailError('');
    setDetailLoading(true);
    try {
      const response = await apiFetch(`/api/meetings/${meetingId}`, { signal: controller.signal });
      const data = await readChecked(response, 'Không thể mở lịch họp.');
      setDetail(data);
    } catch (reason) {
      if (reason.name !== 'AbortError') setDetailError(reason.message || 'Không thể mở lịch họp.');
    } finally {
      if (detailRequestRef.current === controller) {
        detailRequestRef.current = null;
        setDetailLoading(false);
      }
    }
  }, []);

  const closeDetail = useCallback(() => {
    detailRequestRef.current?.abort();
    detailRequestRef.current = null;
    setDetail(null);
    setDetailLoading(false);
    setDetailError('');
    onRequestedMeetingHandled?.();
  }, [onRequestedMeetingHandled]);

  useEffect(() => {
    if (!requestedMeetingId) return;
    detailRequestRef.current?.abort();
    const controller = new AbortController();
    detailRequestRef.current = controller;
    apiFetch(`/api/meetings/${requestedMeetingId}`, { signal: controller.signal })
      .then((response) => readChecked(response, 'Không thể mở lịch họp.'))
      .then((data) => setDetail(data))
      .catch((reason) => {
        if (reason.name !== 'AbortError') setDetailError(reason.message || 'Không thể mở lịch họp.');
      })
      .finally(() => {
        if (detailRequestRef.current === controller) {
          detailRequestRef.current = null;
          onRequestedMeetingHandled?.();
        }
      });
    return () => {
      if (detailRequestRef.current === controller) {
        detailRequestRef.current = null;
        controller.abort();
      }
    };
  }, [requestedMeetingId, onRequestedMeetingHandled]);

  useEffect(() => {
    if (!formOpen && !detail && !detailLoading && !cancelTarget && !requestedMeetingId) return undefined;
    const closeOnEscape = (event) => {
      if (event.key !== 'Escape' || saving) return;
      if (cancelTarget) setCancelTarget(null);
      else if (formOpen) setFormOpen(false);
      else closeDetail();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [cancelTarget, closeDetail, detail, detailLoading, formOpen, requestedMeetingId, saving]);

  const visibleMeetings = useMemo(() => meetings.filter((meeting) => {
    const matchesStatus = statusFilter === 'ALL' || meeting.status === statusFilter;
    const search = meetingSearch.trim().toLocaleLowerCase('vi');
    const matchesSearch = !search || [meeting.title, meeting.content, meeting.location, meeting.organizer_name]
      .some((value) => String(value || '').toLocaleLowerCase('vi').includes(search));
    return matchesStatus && matchesSearch;
  }), [meetings, meetingSearch, statusFilter]);

  const selectedParticipants = useMemo(() => {
    const byId = new Map();
    participants.forEach((person) => byId.set(Number(person.ma_nguoi_dung), person));
    meetings.forEach((meeting) => meeting.attendees?.forEach((person) => byId.set(Number(person.user_id), {
      ma_nguoi_dung: person.user_id, ho_ten: person.ho_ten, email: person.email,
      vai_tro: person.vai_tro, programs: [],
    })));
    detail?.attendees?.forEach((person) => byId.set(Number(person.user_id), {
      ma_nguoi_dung: person.user_id, ho_ten: person.ho_ten, email: person.email,
      vai_tro: person.vai_tro, programs: [],
    }));
    return form.attendee_ids.map((id) => byId.get(Number(id))).filter(Boolean);
  }, [detail, form.attendee_ids, meetings, participants]);

  const startCreate = () => {
    setDetail(null);
    setEditingMeeting(null);
    setForm(emptyForm);
    setFormError('');
    setParticipantSearch('');
    requestKeyRef.current = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setFormOpen(true);
  };

  const startEdit = (meeting) => {
    setDetail(null);
    const invitees = (meeting.attendees || []).filter((person) => person.status === 'INVITED');
    setEditingMeeting(meeting);
    setForm({
      title: meeting.title || '', content: meeting.content || '',
      start_at: toLocalDateTime(meeting.start_at), end_at: toLocalDateTime(meeting.end_at),
      location: meeting.location || '', meeting_url: meeting.meeting_url || '',
      attendee_ids: invitees.map((person) => Number(person.user_id)),
    });
    setFormError('');
    setParticipantSearch('');
    setFormOpen(true);
  };

  const toggleParticipant = (id) => {
    const value = Number(id);
    setForm((current) => ({
      ...current,
      attendee_ids: current.attendee_ids.includes(value)
        ? current.attendee_ids.filter((item) => item !== value)
        : [...current.attendee_ids, value],
    }));
  };

  const saveMeeting = async (event) => {
    event.preventDefault();
    setFormError('');
    if (!form.title.trim()) return setFormError('Vui lòng nhập tiêu đề cuộc họp.');
    if (!form.start_at || !form.end_at || new Date(form.end_at) <= new Date(form.start_at)) {
      return setFormError('Thời gian kết thúc phải sau thời gian bắt đầu.');
    }
    if (!form.location.trim() && !form.meeting_url.trim()) return setFormError('Vui lòng nhập địa điểm hoặc link họp.');
    if (!form.attendee_ids.length) return setFormError('Chọn ít nhất một người tham gia.');
    if (form.meeting_url.trim()) {
      try {
        const url = new URL(form.meeting_url.trim());
        if (!['http:', 'https:'].includes(url.protocol)) throw new Error();
      } catch { return setFormError('Link họp phải là URL HTTP hoặc HTTPS hợp lệ.'); }
    }

    setSaving(true);
    try {
      const payload = {
        title: form.title.trim(), content: form.content.trim(),
        start_at: new Date(form.start_at).toISOString(), end_at: new Date(form.end_at).toISOString(),
        location: form.location.trim() || null, meeting_url: form.meeting_url.trim() || null,
        attendee_ids: form.attendee_ids,
      };
      if (editingMeeting) payload.expected_version = editingMeeting.version;
      const response = await apiFetch(editingMeeting ? `/api/meetings/${editingMeeting.id}` : '/api/meetings', {
        method: editingMeeting ? 'PUT' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(!editingMeeting ? { 'Idempotency-Key': requestKeyRef.current } : {}),
        },
        body: JSON.stringify(payload),
      });
      const saved = await readChecked(response, 'Không thể lưu lịch họp.');
      setFormOpen(false);
      refresh();
      const queueResult = saved.email_queue_result || {};
      const queueNote = queueResult.not_queued
        ? ` ${queueResult.not_queued} email chưa được đưa vào hàng đợi; thông báo ứng dụng vẫn đã lưu.`
        : queueResult.unchanged ? ' Không có thông tin nào thay đổi.' : ' Email đã được đưa vào hàng đợi.';
      onShowToast?.(`${editingMeeting ? 'Đã cập nhật' : 'Đã tạo'} lịch họp.${queueNote}`);
      setDetail(saved);
    } catch (reason) {
      setFormError(reason.message || 'Không thể lưu lịch họp.');
    } finally {
      setSaving(false);
    }
  };

  const confirmCancel = async () => {
    if (!cancelTarget) return;
    setSaving(true);
    try {
      const response = await apiFetch(`/api/meetings/${cancelTarget.id}/cancel`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_version: cancelTarget.version }),
      });
      const cancelled = await readChecked(response, 'Không thể hủy lịch họp.');
      setCancelTarget(null);
      setDetail(cancelled);
      refresh();
      const queueNote = cancelled.email_queue_result?.not_queued
        ? ` ${cancelled.email_queue_result.not_queued} email chưa được đưa vào hàng đợi; thông báo ứng dụng vẫn đã lưu.`
        : ' Email hủy đã được đưa vào hàng đợi.';
      onShowToast?.(`Đã hủy lịch họp.${queueNote}`);
    } catch (reason) {
      setError(reason.message || 'Không thể hủy lịch họp.');
      setCancelTarget(null);
    } finally {
      setSaving(false);
    }
  };

  return <section className="meetings-page">
    <header className="meetings-heading">
      <div><span className="meetings-eyebrow">IMS PORTAL · US35 / US36</span><h2>Lịch họp</h2>
        <p>{isManager ? 'Tạo lịch, mời người tham gia và theo dõi email thông báo.' : 'Các cuộc họp được mời tham gia sẽ hiển thị tại đây.'}</p>
      </div>
      <div className="meetings-heading-actions">
        <button type="button" className="btn btn-secondary" onClick={refresh} disabled={loading}><RefreshCw size={16} className={loading ? 'meeting-spin' : ''} /> Làm mới</button>
        {isManager && <button type="button" className="btn btn-primary" onClick={startCreate}><Plus size={17} /> Tạo lịch họp</button>}
      </div>
    </header>

    <div className="meetings-toolbar">
      <label className="meeting-search"><Search size={17} /><input value={meetingSearch} onChange={(event) => setMeetingSearch(event.target.value)} placeholder="Tìm theo tiêu đề, nội dung, địa điểm…" aria-label="Tìm lịch họp" /></label>
      <label className="meeting-filter"><span>Trạng thái</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
        <option value="ALL">Tất cả</option><option value="SCHEDULED">Đã lên lịch</option><option value="CANCELLED">Đã hủy</option>
      </select></label>
    </div>

    {error && <div className="meeting-alert" role="alert">{error}<button type="button" onClick={() => setError('')} aria-label="Đóng thông báo lỗi"><X size={15} /></button></div>}
    {loading ? <div className="meetings-state" role="status"><RefreshCw size={19} className="meeting-spin" /> Đang tải lịch họp…</div>
      : visibleMeetings.length === 0 ? <div className="meetings-state meetings-empty"><span><CalendarDays size={23} /></span><strong>{meetings.length ? 'Không có lịch họp phù hợp' : 'Chưa có lịch họp'}</strong>
        <p>{meetings.length ? 'Hãy đổi bộ lọc hoặc từ khóa tìm kiếm.' : isManager ? 'Tạo lịch đầu tiên và chọn đúng những người cần tham dự.' : 'Khi được mời, lịch họp sẽ xuất hiện ở đây.'}</p>
      </div> : <div className="meetings-list">
        {visibleMeetings.map((meeting) => <article className={`meeting-card${meeting.status === 'CANCELLED' ? ' is-cancelled' : ''}`} key={meeting.id}>
          <div className="meeting-card-main">
            <div className="meeting-card-title"><span className="meeting-icon"><CalendarDays size={19} /></span><div><h3>{meeting.title}</h3><span className={`meeting-status ${meeting.status === 'CANCELLED' ? 'is-cancelled' : 'is-scheduled'}`}><i />{meeting.status === 'CANCELLED' ? 'Đã hủy' : 'Đã lên lịch'}</span></div></div>
            <p className="meeting-content-preview">{meeting.content || 'Không có nội dung bổ sung.'}</p>
            <div className="meeting-meta">
              <span><Clock3 size={15} />{formatDate(meeting.start_at)} – {formatDate(meeting.end_at)}</span>
              {meeting.location && <span><MapPin size={15} />{meeting.location}</span>}
              {meeting.meeting_url && <a href={meeting.meeting_url} target="_blank" rel="noreferrer"><Video size={15} />Mở link họp<ExternalLink size={12} /></a>}
            </div>
            <div className="meeting-card-footer"><span><Users size={15} />{meeting.attendees?.filter((person) => person.status === 'INVITED').length || 0} người tham gia</span>
              <span>Người tổ chức: {meeting.organizer_name}</span>
              {isManager && <span className="meeting-email-summary"><Send size={14} />Email: {emailSummaryText(meeting.email_summary)}</span>}
            </div>
          </div>
          <div className="meeting-card-actions">
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => openDetail(meeting.id)}>Chi tiết</button>
            {isManager && meeting.status === 'SCHEDULED' && <>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => startEdit(meeting)} aria-label={`Sửa ${meeting.title}`}><Edit3 size={15} />Sửa</button>
              <button type="button" className="btn btn-danger-soft btn-sm" onClick={() => setCancelTarget(meeting)} aria-label={`Hủy ${meeting.title}`}><Trash2 size={15} />Hủy</button>
            </>}
          </div>
        </article>)}
      </div>}

    {formOpen && <div className="meeting-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) setFormOpen(false); }}>
      <section className="meeting-dialog meeting-form-dialog" role="dialog" aria-modal="true" aria-labelledby="meeting-form-title">
        <header className="meeting-dialog-header"><div><span className="meetings-eyebrow">THÔNG TIN CUỘC HỌP</span><h3 id="meeting-form-title">{editingMeeting ? 'Sửa lịch họp' : 'Tạo lịch họp mới'}</h3></div><button type="button" className="meeting-icon-button" onClick={() => setFormOpen(false)} disabled={saving} aria-label="Đóng"><X size={19} /></button></header>
        <form onSubmit={saveMeeting}>
          <div className="meeting-dialog-body">
            <label className="meeting-field meeting-field-full"><span>Tiêu đề <b>*</b></span><input className="form-control" maxLength={200} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required placeholder="Ví dụ: Trao đổi tiến độ thực tập" /></label>
            <div className="meeting-form-grid">
              <label className="meeting-field"><span>Bắt đầu <b>*</b></span><input className="form-control" type="datetime-local" value={form.start_at} onChange={(event) => setForm({ ...form, start_at: event.target.value })} required /></label>
              <label className="meeting-field"><span>Kết thúc <b>*</b></span><input className="form-control" type="datetime-local" value={form.end_at} onChange={(event) => setForm({ ...form, end_at: event.target.value })} required /></label>
              <label className="meeting-field"><span>Địa điểm</span><input className="form-control" maxLength={500} value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} placeholder="Phòng họp hoặc địa chỉ" /></label>
              <label className="meeting-field"><span>Link họp online</span><input className="form-control" type="url" maxLength={2000} value={form.meeting_url} onChange={(event) => setForm({ ...form, meeting_url: event.target.value })} placeholder="https://…" /></label>
            </div>
            <label className="meeting-field meeting-field-full"><span>Nội dung</span><textarea className="form-control" rows={3} maxLength={10000} value={form.content} onChange={(event) => setForm({ ...form, content: event.target.value })} placeholder="Nội dung cần trao đổi" /></label>
            <div className="meeting-field meeting-field-full">
              <span>Người tham gia <b>*</b><small>Chọn ít nhất một tài khoản đang hoạt động. Tìm theo tên, email hoặc chương trình.</small></span>
              {selectedParticipants.length > 0 && <div className="meeting-selected-list">{selectedParticipants.map((person) => <button type="button" key={person.ma_nguoi_dung} onClick={() => toggleParticipant(person.ma_nguoi_dung)} title="Bỏ người tham gia">{person.ho_ten}<X size={13} /></button>)}</div>}
              <label className="meeting-search meeting-participant-search"><Search size={16} /><input value={participantSearch} onChange={(event) => setParticipantSearch(event.target.value)} placeholder="Tìm tên hoặc email…" aria-label="Tìm người tham gia" /></label>
              <div className="meeting-participant-results" role="group" aria-label="Chọn người tham gia">
                {participants.length === 0 ? <p>{participantSearch ? 'Không tìm thấy tài khoản phù hợp.' : 'Chưa có tài khoản đang hoạt động.'}</p> : participants.map((person) => {
                  const checked = form.attendee_ids.includes(Number(person.ma_nguoi_dung));
                  return <label className={`meeting-participant-option${checked ? ' is-selected' : ''}`} key={person.ma_nguoi_dung}>
                    <input type="checkbox" checked={checked} onChange={() => toggleParticipant(person.ma_nguoi_dung)} />
                    <span className="meeting-participant-check">{checked && <Check size={13} />}</span>
                    <span className="meeting-participant-copy"><strong>{person.ho_ten}</strong><small>{person.email} · {roleLabel(person.vai_tro)}{person.ten_phong_ban ? ` · ${person.ten_phong_ban}` : ''}</small>{person.programs?.length > 0 && <small>Chương trình: {person.programs.join(', ')}</small>}</span>
                  </label>;
                })}
              </div>
            </div>
            {formError && <p className="meeting-form-error" role="alert">{formError}</p>}
          </div>
          <footer className="meeting-dialog-footer"><button type="button" className="btn btn-secondary" onClick={() => setFormOpen(false)} disabled={saving}>Hủy</button><button type="submit" className="btn btn-primary" disabled={saving}>{saving ? <><RefreshCw size={16} className="meeting-spin" />Đang lưu…</> : <><Check size={16} />{editingMeeting ? 'Lưu thay đổi' : 'Tạo lịch họp'}</>}</button></footer>
        </form>
      </section>
    </div>}

    {(modalDetail || detailLoading || detailError || requestedMeetingId) && <div className="meeting-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeDetail(); }}>
      <section className="meeting-dialog meeting-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="meeting-detail-title">
        <header className="meeting-dialog-header"><div><span className="meetings-eyebrow">CHI TIẾT LỊCH HỌP</span><h3 id="meeting-detail-title">{modalDetail?.title || (detailLoading || requestedDetailLoading ? 'Đang tải…' : 'Không mở được lịch họp')}</h3></div><button type="button" className="meeting-icon-button" onClick={closeDetail} aria-label="Đóng"><X size={19} /></button></header>
        <div className="meeting-dialog-body">
          {(detailLoading || requestedDetailLoading) && <div className="meetings-state"><RefreshCw size={18} className="meeting-spin" />Đang tải chi tiết…</div>}
          {detailError && <p className="meeting-form-error" role="alert">{detailError}</p>}
          {modalDetail && <>
            <span className={`meeting-status ${modalDetail.status === 'CANCELLED' ? 'is-cancelled' : 'is-scheduled'}`}><i />{modalDetail.status === 'CANCELLED' ? 'Đã hủy' : 'Đã lên lịch'}</span>
            <dl className="meeting-detail-grid"><div><dt>Thời gian</dt><dd>{formatDate(modalDetail.start_at)} – {formatDate(modalDetail.end_at)}</dd></div><div><dt>Người tổ chức</dt><dd>{modalDetail.organizer_name} · {modalDetail.organizer_email}</dd></div>
              {modalDetail.location && <div><dt>Địa điểm</dt><dd>{modalDetail.location}</dd></div>}{modalDetail.meeting_url && <div><dt>Link họp</dt><dd><a href={modalDetail.meeting_url} target="_blank" rel="noreferrer">Mở link họp <ExternalLink size={13} /></a></dd></div>}
              <div className="meeting-detail-full"><dt>Nội dung</dt><dd>{modalDetail.content || 'Không có nội dung bổ sung.'}</dd></div>
            </dl>
            <div className="meeting-detail-attendees"><strong><Users size={16} />Người tham gia ({modalDetail.attendees?.filter((person) => person.status === 'INVITED').length || 0})</strong>
              {modalDetail.attendees?.map((person) => <span key={person.user_id} className={person.status === 'REMOVED' ? 'is-removed' : ''}>{person.ho_ten}<small>{person.email} · {roleLabel(person.vai_tro)}{person.status === 'REMOVED' ? ' · Đã gỡ' : ''}</small></span>)}
            </div>
            {isManager && <p className="meeting-detail-email"><Send size={15} />Email: {emailSummaryText(modalDetail.email_summary)}</p>}
          </>}
        </div>
        {modalDetail && isManager && modalDetail.status === 'SCHEDULED' && <footer className="meeting-dialog-footer"><button type="button" className="btn btn-secondary" onClick={() => { startEdit(modalDetail); }}>Sửa lịch</button><button type="button" className="btn btn-danger-soft" onClick={() => setCancelTarget(modalDetail)}><Trash2 size={15} />Hủy lịch</button></footer>}
      </section>
    </div>}

    {cancelTarget && <div className="meeting-overlay meeting-confirm-overlay" role="presentation"><section className="meeting-dialog meeting-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="meeting-cancel-title">
      <header className="meeting-dialog-header"><div><span className="meetings-eyebrow">XÁC NHẬN</span><h3 id="meeting-cancel-title">Hủy lịch họp?</h3></div><button type="button" className="meeting-icon-button" onClick={() => setCancelTarget(null)} disabled={saving} aria-label="Đóng"><X size={19} /></button></header>
      <div className="meeting-dialog-body"><p>Lịch “{cancelTarget.title}” sẽ được đánh dấu đã hủy. Người tham gia sẽ nhận thông báo trong ứng dụng và email được đưa vào hàng đợi.</p></div>
      <footer className="meeting-dialog-footer"><button type="button" className="btn btn-secondary" onClick={() => setCancelTarget(null)} disabled={saving}>Giữ lịch</button><button type="button" className="btn btn-danger-soft" onClick={confirmCancel} disabled={saving}>{saving ? 'Đang hủy…' : 'Xác nhận hủy'}</button></footer>
    </section></div>}
  </section>;
}
