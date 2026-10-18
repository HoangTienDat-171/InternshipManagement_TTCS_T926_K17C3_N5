import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { CalendarDays, ChevronDown, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Clock3 } from 'lucide-react';
import { formatVietnamDateKey, getVietnamDateKey } from '../utils/meetingCalendar';
import './MeetingCalendarControls.css';

function usePopoverPosition(open, anchorRef, popupRef, preferredWidth, estimatedHeight) {
  const [position, setPosition] = useState(null);
  useEffect(() => {
    if (!open) return undefined;
    const update = () => {
      const anchor = anchorRef.current?.getBoundingClientRect();
      if (!anchor) return;
      const width = Math.min(Math.max(anchor.width, preferredWidth), window.innerWidth - 16);
      const height = popupRef.current?.offsetHeight || estimatedHeight;
      let top = anchor.bottom + 6;
      if (top + height > window.innerHeight - 8) top = Math.max(8, anchor.top - height - 6);
      const left = Math.min(Math.max(8, anchor.left), window.innerWidth - width - 8);
      setPosition({ top, left, width });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [anchorRef, estimatedHeight, open, popupRef, preferredWidth]);
  return position;
}

function useCloseOnOutside(open, anchorRef, popupRef, close) {
  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => {
      if (anchorRef.current?.contains(event.target) || popupRef.current?.contains(event.target)) return;
      close();
    };
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        close();
        anchorRef.current?.focus();
      }
    };
    document.addEventListener('mousedown', onPointerDown, true);
    document.addEventListener('touchstart', onPointerDown, true);
    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      document.removeEventListener('mousedown', onPointerDown, true);
      document.removeEventListener('touchstart', onPointerDown, true);
      document.removeEventListener('keydown', onKeyDown, true);
    };
  }, [anchorRef, close, open, popupRef]);
}

function parseDateKey(value) {
  const [year, month, day] = (value || '').split('-').map(Number);
  return new Date(Date.UTC(year || 2000, (month || 1) - 1, day || 1));
}

function dateKey(date) {
  return date.getUTCFullYear() + '-' + String(date.getUTCMonth() + 1).padStart(2, '0') + '-' + String(date.getUTCDate()).padStart(2, '0');
}

function addDays(value, amount) {
  const date = parseDateKey(value);
  date.setUTCDate(date.getUTCDate() + amount);
  return dateKey(date);
}

function normalizeTime(value) {
  const match = /^(\d{1,2}):(\d{2})$/.exec((value || '').trim());
  if (!match) return '';
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour > 23 || minute > 59) return '';
  return String(hour).padStart(2, '0') + ':' + String(minute).padStart(2, '0');
}

export function MeetingDatePicker({ value, onChange, disabled = false }) {
  const triggerRef = useRef(null);
  const popupRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState(() => (value || getVietnamDateKey(new Date())).slice(0, 7) + '-01');
  const close = React.useCallback(() => setOpen(false), []);
  const position = usePopoverPosition(open, triggerRef, popupRef, 320, 360);
  useCloseOnOutside(open, triggerRef, popupRef, close);

  const days = useMemo(() => {
    const first = parseDateKey(month);
    const mondayOffset = (first.getUTCDay() + 6) % 7;
    const start = addDays(dateKey(first), -mondayOffset);
    return Array.from({ length: 42 }, (_, index) => addDays(start, index));
  }, [month]);

  const moveMonth = (amount) => {
    const date = parseDateKey(month);
    date.setUTCMonth(date.getUTCMonth() + amount);
    setMonth(dateKey(new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1))));
  };

  const moveYear = (amount) => {
    const date = parseDateKey(month);
    date.setUTCFullYear(date.getUTCFullYear() + amount);
    setMonth(dateKey(new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1))));
  };

  const onCalendarKeyDown = (event) => {
    const offset = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[event.key];
    if (!offset || !event.target.dataset.date) return;
    event.preventDefault();
    const next = addDays(event.target.dataset.date, offset);
    if (!next.startsWith(month.slice(0, 7))) setMonth(next.slice(0, 7) + '-01');
    window.setTimeout(() => popupRef.current?.querySelector('[data-date="' + next + '"]')?.focus(), 0);
  };

  const popup = open && position && createPortal(<div
    ref={popupRef}
    className="meeting-picker-popup meeting-date-popup"
    role="dialog"
    aria-label="Chọn ngày họp"
    style={{ top: position.top, left: position.left, width: position.width }}
  >
    <div className="meeting-picker-heading">
      <div className="meeting-picker-nav-group">
        <button type="button" className="meeting-picker-icon" onClick={() => moveYear(-1)} aria-label="Năm trước" title="Năm trước"><ChevronsLeft size={16} /></button>
        <button type="button" className="meeting-picker-icon" onClick={() => moveMonth(-1)} aria-label="Tháng trước" title="Tháng trước"><ChevronLeft size={16} /></button>
      </div>
      <strong>{new Intl.DateTimeFormat('vi-VN', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(parseDateKey(month))}</strong>
      <div className="meeting-picker-nav-group">
        <button type="button" className="meeting-picker-icon" onClick={() => moveMonth(1)} aria-label="Tháng sau" title="Tháng sau"><ChevronRight size={16} /></button>
        <button type="button" className="meeting-picker-icon" onClick={() => moveYear(1)} aria-label="Năm sau" title="Năm sau"><ChevronsRight size={16} /></button>
      </div>
    </div>
    <div className="meeting-date-weekdays" aria-hidden="true">{['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'].map((day) => <span key={day}>{day}</span>)}</div>
    <div className="meeting-date-grid" onKeyDown={onCalendarKeyDown}>
      {days.map((day) => {
        const isSelected = day === value;
        const isToday = day === getVietnamDateKey(new Date());
        const inMonth = day.slice(0, 7) === month.slice(0, 7);
        return <button
          type="button"
          key={day}
          data-date={day}
          className={'meeting-date-day' + (isSelected ? ' is-selected' : '') + (isToday ? ' is-today' : '') + (!inMonth ? ' is-outside' : '')}
          aria-pressed={isSelected}
          aria-label={formatVietnamDateKey(day, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
          onClick={() => { onChange(day); close(); }}
        >{Number(day.slice(-2))}</button>;
      })}
    </div>
    <div className="meeting-picker-footer">
      <button type="button" className="meeting-date-clear" onClick={() => { onChange(''); close(); }}>Xóa</button>
      <button type="button" className="meeting-date-today" onClick={() => { const today = getVietnamDateKey(new Date()); setMonth(today.slice(0, 7) + '-01'); onChange(today); close(); }}>Hôm nay</button>
    </div>
  </div>, document.body);

  return <>
    <button
      ref={triggerRef}
      type="button"
      className="meeting-picker-trigger"
      aria-haspopup="dialog"
      aria-expanded={open}
      disabled={disabled}
      onClick={() => { if (value) setMonth(value.slice(0, 7) + '-01'); setOpen((current) => !current); }}
    >
      <CalendarDays size={16} />
      <span>{value ? formatVietnamDateKey(value, { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' }) : 'Chọn ngày'}</span>
      <ChevronDown size={15} className="meeting-picker-chevron" />
    </button>
    {popup}
  </>;
}

export function MeetingTimePicker({ value, onChange, label, disabled = false }) {
  const triggerRef = useRef(null);
  const popupRef = useRef(null);
  const searchRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(value || '');
  const close = React.useCallback(() => setOpen(false), []);
  const position = usePopoverPosition(open, triggerRef, popupRef, 224, 330);
  useCloseOnOutside(open, triggerRef, popupRef, close);

  useEffect(() => {
    if (open) {
      window.setTimeout(() => searchRef.current?.focus(), 0);
    }
  }, [open, value]);

  const options = useMemo(() => Array.from({ length: 96 }, (_, index) => {
    const total = index * 15;
    return String(Math.floor(total / 60)).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0');
  }), []);
  const filteredOptions = useMemo(() => {
    const normalized = normalizeTime(query) || query.trim();
    return normalized ? options.filter((option) => option.includes(normalized)) : options;
  }, [options, query]);

  const commitTypedTime = () => {
    const normalized = normalizeTime(query);
    if (normalized) {
      onChange(normalized);
      close();
    }
  };

  const popup = open && position && createPortal(<div
    ref={popupRef}
    className="meeting-picker-popup meeting-time-popup"
    role="dialog"
    aria-label={'Chọn giờ ' + label}
    style={{ top: position.top, left: position.left, width: position.width }}
  >
    <label className="meeting-time-search"><Clock3 size={15} /><input
      ref={searchRef}
      type="text"
      inputMode="numeric"
      value={query}
      onChange={(event) => setQuery(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === 'Enter') { event.preventDefault(); commitTypedTime(); }
        if (event.key === 'ArrowDown') { event.preventDefault(); popupRef.current?.querySelector('[role="option"]')?.focus(); }
      }}
      placeholder="Nhập giờ HH:mm"
      aria-label="Nhập giờ theo định dạng 24 giờ"
    /></label>
    {query && normalizeTime(query) && !options.includes(normalizeTime(query)) && <button type="button" className="meeting-time-custom" onClick={commitTypedTime}>Dùng giờ {normalizeTime(query)}</button>}
    <div className="meeting-time-options" role="listbox" aria-label={'Các giờ ' + label} onKeyDown={(event) => {
      if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return;
      const optionsInPopup = Array.from(popupRef.current?.querySelectorAll('[role="option"]') || []);
      const currentIndex = optionsInPopup.indexOf(document.activeElement);
      const nextIndex = Math.max(0, Math.min(optionsInPopup.length - 1, currentIndex + (event.key === 'ArrowDown' ? 1 : -1)));
      if (optionsInPopup[nextIndex]) { event.preventDefault(); optionsInPopup[nextIndex].focus(); }
    }}>
      {filteredOptions.length === 0 ? <p>Không tìm thấy giờ phù hợp.</p> : filteredOptions.map((option) => <button
        key={option}
        type="button"
        role="option"
        aria-selected={option === value}
        className={option === value ? 'is-selected' : ''}
        onClick={() => { onChange(option); close(); }}
      >{option}</button>)}
    </div>
  </div>, document.body);

  return <>
    <button
      ref={triggerRef}
      type="button"
      className="meeting-picker-trigger meeting-time-trigger"
      aria-haspopup="dialog"
      aria-expanded={open}
      aria-label={'Giờ ' + label + ': ' + (value || 'chưa chọn')}
      disabled={disabled}
      onClick={() => { if (!open) setQuery(value || ''); setOpen((current) => !current); }}
    >
      <Clock3 size={16} /><span>{value || 'HH:mm'}</span><ChevronDown size={15} className="meeting-picker-chevron" />
    </button>
    {popup}
  </>;
}
