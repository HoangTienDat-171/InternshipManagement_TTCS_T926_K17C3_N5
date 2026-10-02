import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, CalendarDays, CalendarOff, CalendarRange, ChevronLeft,
  ChevronRight, List, RefreshCw, UserRound,
} from 'lucide-react';
import dayjs from 'dayjs';
import 'dayjs/locale/vi';
import { apiFetch, readJsonResponse } from '../utils/api';
import CustomSelect from '../components/CustomSelect';

const weekdays = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật'];

function localDate(value) {
  // SQL DATE strings are calendar dates; parse them locally without timezone conversion.
  const [year, month, day] = String(value).slice(0, 10).split('-').map(Number);
  return dayjs(new Date(year, month - 1, day));
}

function weekStart(value) {
  const parsed = dayjs.isDayjs(value) ? value : localDate(value);
  return parsed.startOf('day').subtract((parsed.day() + 6) % 7, 'day').format('YYYY-MM-DD');
}

function periodLabel(event) {
  const start = localDate(event.start_date);
  const end = localDate(event.end_date);
  return start.isSame(end, 'day')
    ? start.locale('vi').format('DD/MM/YYYY')
    : `${start.locale('vi').format('DD/MM/YYYY')} – ${end.locale('vi').format('DD/MM/YYYY')}`;
}

function placeEvents(events, firstDay) {
  const lanes = [];
  return [...events].sort((left, right) => left.start_date.localeCompare(right.start_date)).map((event) => {
    const start = Math.max(0, localDate(event.start_date).diff(firstDay, 'day'));
    const end = Math.min(6, localDate(event.end_date).diff(firstDay, 'day'));
    let lane = lanes.findIndex((laneEnd) => laneEnd < start);
    if (lane < 0) lane = lanes.length;
    lanes[lane] = end;
    return { ...event, lane, startColumn: start + 1, span: end - start + 1 };
  });
}

function ScheduleSkeleton() {
  return <section className="workspace-card personal-schedule-card" aria-label="Đang tải lịch thực tập">
    <div className="personal-schedule-skeleton-header" />
    <div className="personal-schedule-skeleton-grid">
      {weekdays.map((day) => <div className="personal-schedule-skeleton-day" key={day}><i /><i /></div>)}
    </div>
  </section>;
}

function ScheduleEvent({ event, compact = false }) {
  return <article className={`personal-schedule-event is-approved${compact ? ' is-compact' : ''}`}>
    <span className="personal-schedule-event-time"><CalendarDays size={12} />Khoảng thời gian · {periodLabel(event)}</span>
    <strong>{event.title}</strong>
    <span className="personal-schedule-event-meta">
      <span className="personal-schedule-state is-approved">Đã duyệt</span>
      {event.mentor && <span><UserRound size={12} />{event.mentor.name}</span>}
    </span>
  </article>;
}

export default function PersonalScheduleView() {
  const [week, setWeek] = useState(() => weekStart(dayjs()));
  const [programId, setProgramId] = useState('');
  const [viewMode, setViewMode] = useState('week');
  const [schedule, setSchedule] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retryVersion, setRetryVersion] = useState(0);

  const requestUrl = useMemo(() => {
    const params = new URLSearchParams({ week_start: week });
    if (programId) params.set('program_id', programId);
    return `/api/interns/me/schedule?${params.toString()}`;
  }, [week, programId]);

  useEffect(() => {
    const controller = new AbortController();
    apiFetch(requestUrl, { signal: controller.signal })
      .then(async (response) => {
        const data = await readJsonResponse(response);
        if (!response.ok) throw new Error(data.detail || 'Không thể tải lịch thực tập.');
        setSchedule(data);
      })
      .catch((requestError) => {
        if (requestError.name !== 'AbortError') setError(requestError.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [requestUrl, retryVersion]);

  const start = localDate(week);
  const end = start.add(6, 'day');
  const today = localDate(dayjs().format('YYYY-MM-DD'));
  const days = Array.from({ length: 7 }, (_, index) => start.add(index, 'day'));
  const events = schedule?.events || [];
  const positionedEvents = placeEvents(events, start);
  const laneCount = positionedEvents.reduce((count, event) => Math.max(count, event.lane + 1), 1);

  const beginReload = () => { setLoading(true); setError(''); };
  const moveWeek = (amount) => {
    beginReload();
    setWeek((value) => localDate(value).add(amount * 7, 'day').format('YYYY-MM-DD'));
  };
  const resetWeek = () => { beginReload(); setWeek(weekStart(dayjs())); };
  const retry = () => { beginReload(); setRetryVersion((value) => value + 1); };

  return <div className="workspace-page personal-schedule-page">
    <header className="workspace-heading personal-schedule-heading">
      <div>
        <span className="workspace-eyebrow">KHÔNG GIAN THỰC TẬP</span>
        <h2>Lịch thực tập cá nhân</h2>
        <p>Lịch hiển thị khoảng ngày chương trình đã được duyệt và Mentor được phân công; hiện chưa có dữ liệu về ca hoặc giờ làm việc.</p>
      </div>
      <button type="button" className="btn btn-secondary" disabled={loading} onClick={retry}>
        <RefreshCw size={15} />Làm mới
      </button>
    </header>

    <section className="workspace-card personal-schedule-filters" aria-label="Bộ lọc lịch thực tập">
      <label><span>Chương trình</span><CustomSelect className="form-select" aria-label="Chọn chương trình" value={programId} onChange={(event) => { beginReload(); setProgramId(event.target.value); }}>
        <option value="">Tất cả chương trình</option>
        {(schedule?.filters?.programs || []).map((program) => <option value={program.id} key={program.id}>{program.name}</option>)}
      </CustomSelect></label>
      <div className="personal-schedule-week-picker" aria-label="Chọn tuần">
        <button type="button" className="btn btn-secondary btn-sm" aria-label="Tuần trước" onClick={() => moveWeek(-1)}><ChevronLeft size={16} /></button>
        <strong>{start.locale('vi').format('DD/MM/YYYY')} – {end.locale('vi').format('DD/MM/YYYY')}</strong>
        <button type="button" className="btn btn-secondary btn-sm" aria-label="Tuần sau" onClick={() => moveWeek(1)}><ChevronRight size={16} /></button>
        <button type="button" className="btn btn-secondary btn-sm" disabled={week === weekStart(dayjs())} onClick={resetWeek}>Hôm nay</button>
      </div>
      <div className="personal-schedule-view-toggle" role="group" aria-label="Chế độ hiển thị">
        <button type="button" className={viewMode === 'week' ? 'active' : ''} aria-pressed={viewMode === 'week'} onClick={() => setViewMode('week')}><CalendarRange size={14} />Tuần</button>
        <button type="button" className={viewMode === 'agenda' ? 'active' : ''} aria-pressed={viewMode === 'agenda'} onClick={() => setViewMode('agenda')}><List size={14} />Danh sách</button>
      </div>
    </section>

    {!loading && !error && schedule?.warning && <div className="personal-schedule-warning" role="status">
      <AlertTriangle size={17} /><span>Bạn chưa có chương trình được duyệt hoặc chưa được phân công Mentor. Vui lòng liên hệ Quản trị viên.</span>
    </div>}
    {error && <div className="workspace-error personal-schedule-error" role="alert">
        <span>{error}</span><button type="button" className="btn btn-secondary btn-sm" onClick={retry}>Thử lại</button>
    </div>}

    {loading ? <ScheduleSkeleton /> : !error && <section className="workspace-card personal-schedule-card">
      <div className="personal-schedule-card-heading">
        <div><span className="workspace-eyebrow">LỊCH CỦA BẠN</span><h3>{viewMode === 'week' ? 'Xem theo tuần' : 'Lịch dạng danh sách'}</h3></div>
      </div>
      {!events.length ? <div className="personal-schedule-empty" role="status">
        <CalendarOff size={28} /><strong>Bạn không có khoảng thời gian chương trình nào trong tuần này</strong>
        <span>Các khoảng thời gian chương trình đã duyệt sẽ xuất hiện tại đây khi trùng với tuần được chọn.</span>
      </div> : viewMode === 'week' ? <div className="personal-week-calendar">
        <div className="personal-week-headings">
          {days.map((day, index) => <div className={day.isSame(today, 'day') ? 'is-today' : ''} key={day.format('YYYY-MM-DD')}>
            <span>{weekdays[index]}</span><strong>{day.format('DD')}</strong>
          </div>)}
        </div>
        <div className="personal-week-track" style={{ '--schedule-lanes': laneCount }}>
          {days.map((day, index) => <div className={`personal-week-cell${day.isSame(today, 'day') ? ' is-today' : ''}`} style={{ gridColumn: index + 1, gridRow: '1 / -1' }} key={day.format('YYYY-MM-DD')} />)}
          {positionedEvents.map((event) => <div className="personal-week-event-slot" style={{ gridColumn: `${event.startColumn} / span ${event.span}`, gridRow: event.lane + 1 }} key={event.id}>
            <ScheduleEvent event={event} compact />
          </div>)}
        </div>
      </div> : <div className="personal-agenda-list">
        {events.map((event) => <ScheduleEvent event={event} key={event.id} />)}
      </div>}
    </section>}

    {!loading && !error && schedule && !schedule.has_program && <div className="personal-schedule-no-program" role="status">
      <CalendarDays size={16} />Hồ sơ của bạn chưa có chương trình thực tập được duyệt.
    </div>}
  </div>;
}
