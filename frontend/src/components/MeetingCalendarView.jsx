import React, { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight, Clock3, Plus, Send, Users } from 'lucide-react';
import { formatVietnamDateKey, getVietnamDateKey, getVietnamParts, meetingDisplayStatus, toVietnamTime } from '../utils/meetingCalendar';
import './MeetingCalendarView.css';

const pad = (value) => String(value).padStart(2, '0');
const parseDate = (key) => {
  const [year, month, day] = (key || '').split('-').map(Number);
  return new Date(Date.UTC(year || 2000, (month || 1) - 1, day || 1));
};
const keyForDate = (date) => date.getUTCFullYear() + '-' + pad(date.getUTCMonth() + 1) + '-' + pad(date.getUTCDate());
const shiftDate = (key, amount) => {
  const date = parseDate(key);
  date.setUTCDate(date.getUTCDate() + amount);
  return keyForDate(date);
};
const mondayOf = (key) => shiftDate(key, -((parseDate(key).getUTCDay() + 6) % 7));
const localMinutes = (value) => {
  const time = toVietnamTime(value);
  if (!time) return 0;
  const [hour, minute] = time.split(':').map(Number);
  return hour * 60 + minute;
};

const statusText = {
  UPCOMING: 'Sắp diễn ra', IN_PROGRESS: 'Đang diễn ra', COMPLETED: 'Đã kết thúc', CANCELLED: 'Đã hủy',
};
const calendarViews = [['DAY', 'Ngày'], ['WEEK', 'Tuần'], ['MONTH', 'Tháng'], ['LIST', 'Danh sách']];

function dateHeading(key, options = { weekday: 'short', day: 'numeric' }) {
  return formatVietnamDateKey(key, options);
}

function MeetingCard({ meeting, onOpen, isManager, emailSummaryText }) {
  const status = meetingDisplayStatus(meeting);
  return <article className={'meeting-card' + (status === 'CANCELLED' ? ' is-cancelled' : '')} key={meeting.id}>
    <button type="button" className="meeting-calendar-card-main" onClick={() => onOpen(meeting.id)}>
      <div className="meeting-card-title"><span className="meeting-icon"><CalendarDays size={18} /></span><div><h3>{meeting.title}</h3><span className={'meeting-status is-' + status.toLowerCase()}><i />{statusText[status]}</span></div></div>
      <p className="meeting-content-preview">{meeting.content || 'Không có nội dung bổ sung.'}</p>
      <div className="meeting-meta"><span><Clock3 size={15} />{formatMeetingRange(meeting)}</span>
        {meeting.location && <span>{meeting.location}</span>}{meeting.meeting_url && <span>Họp trực tuyến</span>}
      </div>
      <div className="meeting-card-footer"><span><Users size={15} />{meeting.attendees?.filter((person) => person.status === 'INVITED').length || 0} người tham gia</span><span>Người tổ chức: {meeting.organizer_name}</span>
        {isManager && <span className="meeting-email-summary"><Send size={14} />Email: {emailSummaryText(meeting.email_summary)}</span>}
      </div>
    </button>
    <button type="button" className="btn btn-secondary btn-sm" onClick={() => onOpen(meeting.id)}>Chi tiết</button>
  </article>;
}

function formatMeetingRange(meeting) {
  const date = formatVietnamDateKey(getVietnamDateKey(meeting.start_at), { day: 'numeric', month: 'short', year: 'numeric' });
  return date + ' · ' + toVietnamTime(meeting.start_at) + ' – ' + toVietnamTime(meeting.end_at);
}

function MonthGrid({ date, meetings, onOpen, onCreateAt }) {
  const first = date.slice(0, 7) + '-01';
  const start = mondayOf(first);
  const days = Array.from({ length: 42 }, (_, index) => shiftDate(start, index));
  const today = getVietnamDateKey(new Date());
  return <div className="meeting-month-view">
    <div className="meeting-month-weekdays">{['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật'].map((day) => <span key={day}>{day}</span>)}</div>
    <div className="meeting-month-grid">{days.map((day) => {
      const events = meetings.filter((meeting) => getVietnamDateKey(meeting.start_at) === day);
      return <section key={day} className={'meeting-month-cell' + (day === today ? ' is-today' : '') + (day.slice(0, 7) !== date.slice(0, 7) ? ' is-outside' : '')}>
        <button type="button" className="meeting-month-day" onClick={() => onCreateAt(day, '09:00')}>{Number(day.slice(-2))}</button>
        <div className="meeting-month-events">{events.slice(0, 3).map((meeting) => <button type="button" key={meeting.id} onClick={() => onOpen(meeting.id)} className={'meeting-month-event is-' + meetingDisplayStatus(meeting).toLowerCase()} title={meeting.title}>
          <time>{toVietnamTime(meeting.start_at)}</time> {meeting.title}
        </button>)}{events.length > 3 && <span className="meeting-month-more">+{events.length - 3} cuộc họp</span>}</div>
      </section>;
    })}</div>
  </div>;
}

function TimeGrid({ date, view, meetings, onOpen, onCreateAt, scrollPositionRef }) {
  const scrollElementRef = useRef(null);
  useLayoutEffect(() => {
    if (scrollElementRef.current) scrollElementRef.current.scrollTop = scrollPositionRef.current ?? 8 * 64;
  }, [scrollPositionRef]);
  const days = view === 'DAY' ? [date] : Array.from({ length: 7 }, (_, index) => shiftDate(mondayOf(date), index));
  const today = getVietnamDateKey(new Date());
  const now = new Date();
  const nowParts = getVietnamParts(now);
  const nowMinute = Number(nowParts?.hour || 0) * 60 + Number(nowParts?.minute || 0);
  const hours = Array.from({ length: 24 }, (_, index) => index);
  const gridHeight = hours.length * 64;

  return <div ref={scrollElementRef} className="meeting-time-grid-scroll" onScroll={(event) => { scrollPositionRef.current = event.currentTarget.scrollTop; }}>
    <div className={'meeting-time-grid' + (view === 'DAY' ? ' is-day' : '')} style={{ '--meeting-day-count': days.length, '--meeting-grid-height': gridHeight + 'px' }}>
      <div className="meeting-time-grid-head"><span className="meeting-time-zone">GMT+7</span>{days.map((day) => <div className={'meeting-day-heading' + (day === today ? ' is-today' : '')} key={day}>
        <small>{dateHeading(day, { weekday: 'short' })}</small><strong>{Number(day.slice(-2))}</strong>
      </div>)}</div>
      <div className="meeting-time-grid-body">
        <div className="meeting-time-rail">{hours.map((hour) => <div key={hour} className="meeting-hour-label">{pad(hour)}:00</div>)}</div>
        {days.map((day) => {
          const dayMeetings = meetings.filter((meeting) => getVietnamDateKey(meeting.start_at) === day);
          return <div className="meeting-day-column" key={day}>
            {hours.map((hour) => <button type="button" className="meeting-hour-slot" key={hour} aria-label={'Tạo cuộc họp ' + day + ' ' + pad(hour) + ':00'} onClick={() => onCreateAt(day, pad(hour) + ':00')} />)}
            {dayMeetings.map((meeting) => {
              const start = localMinutes(meeting.start_at);
              const duration = (new Date(meeting.end_at).getTime() - new Date(meeting.start_at).getTime()) / 60000;
              const end = Number.isFinite(duration) && duration > 0 ? start + duration : start + 30;
              const top = Math.max(0, start / 60 * 64);
              const bottom = Math.min(gridHeight, end / 60 * 64);
              if (bottom <= 0 || top >= gridHeight) return null;
              return <button type="button" key={meeting.id} className={'meeting-grid-event is-' + meetingDisplayStatus(meeting).toLowerCase()} style={{ top: Math.max(0, top), height: Math.max(28, bottom - top) }} onClick={() => onOpen(meeting.id)} title={meeting.title}>
                <strong>{meeting.title}</strong><span>{toVietnamTime(meeting.start_at)}–{toVietnamTime(meeting.end_at)}</span>
              </button>;
            })}
            {day === today && nowMinute <= 1440 && <div className="meeting-now-line" style={{ top: (nowMinute / 60) * 64 }}><i /></div>}
          </div>;
        })}
      </div>
    </div>
  </div>;
}

export default function MeetingCalendarView({ meetings, onOpenMeeting, onCreateAt, isManager, emailSummaryText }) {
  const [view, setView] = useState('WEEK');
  const [date, setDate] = useState(() => getVietnamDateKey(new Date()));
  const timeGridScrollPositionRef = useRef(null);
  const startOfWeek = mondayOf(date);
  const endOfWeek = shiftDate(startOfWeek, 6);
  const visibleMeetings = useMemo(() => meetings.filter((meeting) => getVietnamDateKey(meeting.start_at)).sort((a, b) => new Date(a.start_at) - new Date(b.start_at)), [meetings]);
  const heading = view === 'MONTH'
    ? formatVietnamDateKey(date, { month: 'long', year: 'numeric' })
    : view === 'DAY' ? dateHeading(date, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
      : dateHeading(startOfWeek, { day: 'numeric', month: 'short' }) + ' – ' + dateHeading(endOfWeek, { day: 'numeric', month: 'short', year: 'numeric' });
  const shift = (amount) => setDate((current) => {
    if (view === 'MONTH') {
      const nextMonth = parseDate(current);
      nextMonth.setUTCDate(1);
      nextMonth.setUTCMonth(nextMonth.getUTCMonth() + amount);
      return keyForDate(nextMonth);
    }
    return shiftDate(current, view === 'DAY' ? amount : amount * 7);
  });
  const goToday = () => setDate(getVietnamDateKey(new Date()));

  return <section className="meeting-calendar-shell" aria-label="Lịch họp">
    <header className="meeting-calendar-toolbar">
      <div className="meeting-calendar-navigation"><button type="button" className="meeting-calendar-today" onClick={goToday}>Hôm nay</button>
        <button type="button" className="meeting-calendar-arrow" onClick={() => shift(-1)} aria-label="Khoảng thời gian trước"><ChevronLeft size={18} /></button>
        <button type="button" className="meeting-calendar-arrow" onClick={() => shift(1)} aria-label="Khoảng thời gian sau"><ChevronRight size={18} /></button>
        <h3>{heading}</h3>
      </div>
      <div className="meeting-calendar-views" role="tablist" aria-label="Chế độ lịch">
        {calendarViews.map(([key, label], index) => <button type="button" role="tab" aria-selected={view === key} className={view === key ? 'is-active' : ''} key={key} onClick={() => setView(key)} onKeyDown={(event) => {
          if (!['ArrowRight', 'ArrowLeft'].includes(event.key)) return;
          event.preventDefault();
          const tabList = event.currentTarget.parentElement;
          const nextIndex = (index + (event.key === 'ArrowRight' ? 1 : calendarViews.length - 1)) % calendarViews.length;
          setView(calendarViews[nextIndex][0]);
          window.setTimeout(() => tabList?.querySelectorAll('[role="tab"]')[nextIndex]?.focus(), 0);
        }}>{label}</button>)}
      </div>
    </header>
    {view === 'MONTH' ? <MonthGrid date={date} meetings={visibleMeetings} onOpen={onOpenMeeting} onCreateAt={onCreateAt} />
      : view === 'LIST' ? <div className="meetings-list meeting-calendar-list">{visibleMeetings.length ? visibleMeetings.map((meeting) => <MeetingCard key={meeting.id} meeting={meeting} onOpen={onOpenMeeting} isManager={isManager} emailSummaryText={emailSummaryText} />)
        : <div className="meetings-state meetings-empty"><span><CalendarDays size={23} /></span><strong>Chưa có lịch họp</strong><p>Các cuộc họp trong hệ thống sẽ xuất hiện tại đây.</p></div>}</div>
        : <TimeGrid date={date} view={view} meetings={visibleMeetings} onOpen={onOpenMeeting} onCreateAt={onCreateAt} scrollPositionRef={timeGridScrollPositionRef} />}
    <footer className="meeting-calendar-footer">
      <div className="meeting-legend-group">
        <span className="meeting-legend-item"><i className="is-upcoming" /> Sắp diễn ra</span>
        <span className="meeting-legend-item"><i className="is-progress" /> Đang diễn ra</span>
        <span className="meeting-legend-item"><i className="is-completed" /> Đã kết thúc</span>
        <span className="meeting-legend-item"><i className="is-cancelled" /> Đã hủy</span>
      </div>
      {isManager && (
        <button type="button" className="meeting-footer-create-btn" onClick={() => onCreateAt(date, '09:00')}>
          <Plus size={15} /> Tạo lịch vào ngày đang xem
        </button>
      )}
    </footer>
  </section>;
}
