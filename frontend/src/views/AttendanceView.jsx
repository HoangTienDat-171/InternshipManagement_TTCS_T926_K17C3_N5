import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle, CalendarDays, Check, ChevronLeft, ChevronRight,
  Clock3, ClipboardCheck, LogIn, LogOut, RefreshCw,
} from 'lucide-react';
import { apiFetch, readJsonResponse } from '../utils/api';

function dateLabel(value) {
  if (!value) return '—';
  const [year, month, day] = String(value).slice(0, 10).split('-');
  return `${day}/${month}/${year}`;
}

function timeLabel(value) {
  if (!value) return '—';
  const text = String(value);
  return text.includes(' ') ? text.slice(11, 16) : text.slice(0, 5);
}

function AttendanceStatus({ status }) {
  const complete = status === 'COMPLETED';
  return <span className={`attendance-status${complete ? ' is-complete' : ' is-active'}`}>
    <span aria-hidden="true" />{complete ? 'Hoàn thành' : 'Đang chấm công'}
  </span>;
}

export default function AttendanceView({ onShowToast }) {
  const [today, setToday] = useState(null);
  const [todayLoading, setTodayLoading] = useState(true);
  const [todayError, setTodayError] = useState('');
  const [history, setHistory] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState('');
  const [month, setMonth] = useState('');
  const [page, setPage] = useState(1);
  const [note, setNote] = useState('');
  const [action, setAction] = useState('');
  const [reloadKey, setReloadKey] = useState(0);

  const loadToday = useCallback(async (signal) => {
    try {
      const response = await apiFetch('/api/interns/me/attendance/today', { signal });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể tải thông tin chấm công.');
      setToday(data);
      setMonth((current) => current || data.date.slice(0, 7));
    } catch (error) {
      if (error.name !== 'AbortError') setTodayError(error.message || 'Không thể tải thông tin chấm công.');
    } finally {
      if (!signal?.aborted) setTodayLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => loadToday(controller.signal), 0);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [loadToday, reloadKey]);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ page: String(page), page_size: '20' });
    if (month) params.set('month', month);
    apiFetch(`/api/interns/me/attendance?${params}`, { signal: controller.signal })
      .then(async (response) => {
        const data = await readJsonResponse(response);
        if (!response.ok) throw new Error(data.detail || 'Không thể tải lịch sử chấm công.');
        setHistory(data);
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setHistoryError(error.message || 'Không thể tải lịch sử chấm công.');
      })
      .finally(() => {
        if (!controller.signal.aborted) setHistoryLoading(false);
      });
    return () => controller.abort();
  }, [month, page, reloadKey]);

  const submitAction = async (type) => {
    setAction(type);
    try {
      const response = await apiFetch(`/api/interns/me/attendance/${type}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(type === 'check-in' ? { note } : {}),
      });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể cập nhật chấm công.');
      setNote('');
      onShowToast?.(type === 'check-in' ? 'Check-in thành công.' : 'Check-out thành công.');
      setTodayLoading(true);
      setHistoryLoading(true);
      setTodayError('');
      setHistoryError('');
      setReloadKey((value) => value + 1);
    } catch (error) {
      onShowToast?.(error.message || 'Không thể cập nhật chấm công.', 'error');
    } finally {
      setAction('');
    }
  };

  const retry = () => {
    setTodayLoading(true);
    setHistoryLoading(true);
    setTodayError('');
    setHistoryError('');
    setReloadKey((value) => value + 1);
  };
  const attendance = today?.attendance;
  const shift = today?.applicable_shift;
  const hasHistory = Boolean(history?.items?.length);

  return <div className="workspace-page attendance-page">
    <header className="workspace-heading attendance-heading">
      <div>
        <span className="workspace-eyebrow">QUẢN LÝ CHẤM CÔNG &amp; THỜI GIAN</span>
        <h2>Chấm công hôm nay</h2>
        <p>Theo dõi ca làm và thời gian vào/ra của bạn.</p>
      </div>
      <button type="button" className="btn btn-secondary" onClick={retry} disabled={todayLoading || historyLoading}>
        <RefreshCw size={15} />Làm mới
      </button>
    </header>

    {todayError && <div className="workspace-error attendance-error" role="alert">
      <AlertTriangle size={17} /><span>{todayError}</span>
      <button type="button" className="btn btn-secondary btn-sm" onClick={retry}>Thử lại</button>
    </div>}

    <section className="workspace-card attendance-today-card" aria-labelledby="attendance-today-title">
      {todayLoading ? <div className="attendance-loading" role="status">Đang tải thông tin chấm công…</div> : !todayError && <>
        <div className="attendance-card-heading">
          <div className="attendance-card-icon"><Clock3 size={22} /></div>
          <div><span className="workspace-eyebrow">CA LÀM VIỆC HÔM NAY</span><h3 id="attendance-today-title">{shift?.name || 'Chưa có ca làm việc'}</h3></div>
          {attendance && <AttendanceStatus status={attendance.status} />}
        </div>

        {today?.no_shift ? <div className="attendance-no-shift" role="status">
          <AlertTriangle size={18} /><span>Hôm nay chưa có ca làm việc được áp dụng. Check-in hiện chưa khả dụng.</span>
        </div> : shift && <>
          <div className="attendance-shift-meta">
            <span><CalendarDays size={16} />{dateLabel(today.date)}</span>
            <span><Clock3 size={16} />{timeLabel(shift.start_time)} – {timeLabel(shift.end_time)}</span>
            <span>{shift.scope_type === 'PROGRAM' ? 'Ca theo chương trình' : 'Ca toàn hệ thống'}</span>
          </div>
          <div className="attendance-times">
            <div><span>Check-in</span><strong>{timeLabel(attendance?.check_in_at)}</strong></div>
            <div><span>Check-out</span><strong>{timeLabel(attendance?.check_out_at)}</strong></div>
          </div>
          {today?.can_check_in && <label className="attendance-note-field">
            <span>Ghi chú check-in <small>(không bắt buộc)</small></span>
            <textarea value={note} maxLength={1000} rows={2} onChange={(event) => setNote(event.target.value)} placeholder="Thêm ghi chú nếu cần…" />
          </label>}
          <div className="attendance-actions">
            {today?.can_check_in && <button type="button" className="btn btn-primary" disabled={Boolean(action)} onClick={() => submitAction('check-in')}>
              <LogIn size={16} />{action === 'check-in' ? 'Đang Check-in…' : 'Check-in'}
            </button>}
            {today?.can_check_out && <button type="button" className="btn btn-primary" disabled={Boolean(action)} onClick={() => submitAction('check-out')}>
              <LogOut size={16} />{action === 'check-out' ? 'Đang Check-out…' : 'Check-out'}
            </button>}
            {attendance?.status === 'COMPLETED' && <span className="attendance-complete-note"><Check size={16} />Bạn đã hoàn tất chấm công hôm nay.</span>}
          </div>
        </>}
      </>}
    </section>

    <section className="workspace-card attendance-history-card" aria-labelledby="attendance-history-title">
      <div className="attendance-history-heading">
        <div><span className="workspace-eyebrow">THEO DÕI CỦA BẠN</span><h3 id="attendance-history-title">Lịch sử chấm công</h3></div>
        <label className="attendance-month-filter"><span>Tháng</span>
          <input type="month" value={month} onChange={(event) => { setPage(1); setHistoryLoading(true); setHistoryError(''); setMonth(event.target.value); }} />
        </label>
        {month && <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setPage(1); setHistoryLoading(true); setHistoryError(''); setMonth(''); }}>Xóa lọc</button>}
      </div>

      {historyError && <div className="workspace-error attendance-error" role="alert">
        <AlertTriangle size={17} /><span>{historyError}</span><button type="button" className="btn btn-secondary btn-sm" onClick={retry}>Thử lại</button>
      </div>}
      {historyLoading ? <div className="attendance-loading" role="status">Đang tải lịch sử…</div> : !historyError && !hasHistory ? <div className="attendance-empty" role="status">
        <ClipboardCheck size={28} /><strong>Bạn chưa có dữ liệu chấm công.</strong><span>Các lần check-in/check-out sẽ được lưu và hiển thị tại đây.</span>
      </div> : !historyError && <>
        <div className="attendance-history-table" role="table" aria-label="Lịch sử chấm công">
          <div className="attendance-history-row is-header" role="row">
            <span role="columnheader">Ngày</span><span role="columnheader">Ca làm</span><span role="columnheader">Giờ vào</span><span role="columnheader">Giờ ra</span><span role="columnheader">Trạng thái</span>
          </div>
          {history.items.map((item) => <div className="attendance-history-row" role="row" key={item.id}>
            <span role="cell" data-label="Ngày">{dateLabel(item.attendance_date)}</span>
            <span role="cell" data-label="Ca làm"><strong>{item.shift.name}</strong><small>{timeLabel(item.shift.start_time)} – {timeLabel(item.shift.end_time)}</small></span>
            <span role="cell" data-label="Giờ vào">{timeLabel(item.check_in_at)}</span>
            <span role="cell" data-label="Giờ ra">{timeLabel(item.check_out_at)}</span>
            <span role="cell" data-label="Trạng thái"><AttendanceStatus status={item.status} /></span>
          </div>)}
        </div>
        {history.total_pages > 1 && <div className="attendance-pagination">
          <button type="button" className="btn btn-secondary btn-sm" disabled={page <= 1} onClick={() => { setHistoryLoading(true); setPage((value) => value - 1); }}><ChevronLeft size={15} />Trước</button>
          <span>Trang {history.page} / {history.total_pages}</span>
          <button type="button" className="btn btn-secondary btn-sm" disabled={page >= history.total_pages} onClick={() => { setHistoryLoading(true); setPage((value) => value + 1); }}>Sau<ChevronRight size={15} /></button>
        </div>}
      </>}
    </section>
  </div>;
}
