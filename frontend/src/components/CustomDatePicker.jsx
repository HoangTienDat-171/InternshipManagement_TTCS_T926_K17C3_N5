import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Calendar, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, X } from 'lucide-react';
import './CustomDatePicker.css';

const MONTH_NAMES = [
  'Tháng 1', 'Tháng 2', 'Tháng 3', 'Tháng 4',
  'Tháng 5', 'Tháng 6', 'Tháng 7', 'Tháng 8',
  'Tháng 9', 'Tháng 10', 'Tháng 11', 'Tháng 12'
];

const WEEKDAY_NAMES = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];

function parseISODate(str) {
  if (!str || typeof str !== 'string') return null;
  const match = str.trim().match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return null;
  const year = parseInt(match[1], 10);
  const month = parseInt(match[2], 10);
  const day = parseInt(match[3], 10);
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  return { year, month, day };
}

function formatISODate(year, month, day) {
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function formatDisplayDate(year, month, day) {
  return `${String(day).padStart(2, '0')}/${String(month).padStart(2, '0')}/${year}`;
}

export default function CustomDatePicker({
  id,
  name,
  value = '',
  onChange,
  placeholder = 'dd/mm/yyyy',
  min,
  max,
  disabled = false,
  required = false,
  className = '',
  style,
  title,
  'aria-label': ariaLabel,
}) {
  const triggerRef = useRef(null);
  const popoverRef = useRef(null);
  const [open, setOpen] = useState(false);

  const parsedValue = useMemo(() => parseISODate(value), [value]);

  const today = useMemo(() => {
    const now = new Date();
    return {
      year: now.getFullYear(),
      month: now.getMonth() + 1,
      day: now.getDate(),
      iso: formatISODate(now.getFullYear(), now.getMonth() + 1, now.getDate()),
    };
  }, []);

  const [viewYear, setViewYear] = useState(() => parsedValue?.year ?? today.year);
  const [viewMonth, setViewMonth] = useState(() => parsedValue?.month ?? today.month);

  const [placement, setPlacement] = useState({ top: 0, left: 0, width: 280 });

  const updatePlacement = () => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const bounds = trigger.getBoundingClientRect();
    const popoverHeight = 330;
    const roomBelow = window.innerHeight - bounds.bottom - 12;
    const roomAbove = bounds.top - 12;
    const showAbove = roomBelow < popoverHeight && roomAbove > roomBelow;
    const width = 290;

    setPlacement({
      top: showAbove ? Math.max(8, bounds.top - popoverHeight - 6) : bounds.bottom + 6,
      left: Math.max(8, Math.min(bounds.left, window.innerWidth - width - 8)),
      width,
    });
  };

  useLayoutEffect(() => {
    if (open) {
      updatePlacement();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const closeIfOutside = (event) => {
      if (
        !triggerRef.current?.contains(event.target) &&
        !popoverRef.current?.contains(event.target)
      ) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    const reposition = () => updatePlacement();

    document.addEventListener('pointerdown', closeIfOutside, true);
    document.addEventListener('keydown', handleKeyDown);
    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', reposition, true);
    return () => {
      document.removeEventListener('pointerdown', closeIfOutside, true);
      document.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('resize', reposition);
      window.removeEventListener('scroll', reposition, true);
    };
  }, [open]);

  const emitChange = (nextValue) => {
    if (typeof onChange === 'function') {
      const syntheticEvent = {
        target: { id, name, value: nextValue },
        currentTarget: { id, name, value: nextValue },
        value: nextValue,
      };
      onChange(syntheticEvent);
    }
  };

  const handleSelectDay = (cell) => {
    if (cell.disabled) return;
    emitChange(cell.iso);
    setOpen(false);
    triggerRef.current?.focus();
  };

  const handleClear = (e) => {
    e?.stopPropagation();
    emitChange('');
    setOpen(false);
    triggerRef.current?.focus();
  };

  const handleSelectToday = () => {
    if (min && today.iso < min) return;
    if (max && today.iso > max) return;
    setViewYear(today.year);
    setViewMonth(today.month);
    emitChange(today.iso);
    setOpen(false);
    triggerRef.current?.focus();
  };

  const handlePrevMonth = () => {
    if (viewMonth === 1) {
      setViewMonth(12);
      setViewYear((y) => y - 1);
    } else {
      setViewMonth((m) => m - 1);
    }
  };

  const handleNextMonth = () => {
    if (viewMonth === 12) {
      setViewMonth(1);
      setViewYear((y) => y + 1);
    } else {
      setViewMonth((m) => m + 1);
    }
  };

  const handlePrevYear = () => {
    setViewYear((y) => y - 1);
  };

  const handleNextYear = () => {
    setViewYear((y) => y + 1);
  };

  const calendarDays = useMemo(() => {
    // Monday-based index: 0 = Mon, ..., 6 = Sun
    const firstDayOfWeek = (new Date(viewYear, viewMonth - 1, 1).getDay() + 6) % 7;
    const daysInCurrentMonth = new Date(viewYear, viewMonth, 0).getDate();
    const daysInPrevMonth = new Date(viewYear, viewMonth - 1, 0).getDate();

    const days = [];

    // Leading days from previous month
    for (let i = firstDayOfWeek - 1; i >= 0; i -= 1) {
      const d = daysInPrevMonth - i;
      const prevM = viewMonth === 1 ? 12 : viewMonth - 1;
      const prevY = viewMonth === 1 ? viewYear - 1 : viewYear;
      const iso = formatISODate(prevY, prevM, d);
      days.push({
        year: prevY,
        month: prevM,
        day: d,
        iso,
        isCurrentMonth: false,
        disabled: Boolean((min && iso < min) || (max && iso > max)),
      });
    }

    // Days in current month
    for (let d = 1; d <= daysInCurrentMonth; d += 1) {
      const iso = formatISODate(viewYear, viewMonth, d);
      days.push({
        year: viewYear,
        month: viewMonth,
        day: d,
        iso,
        isCurrentMonth: true,
        disabled: Boolean((min && iso < min) || (max && iso > max)),
      });
    }

    // Trailing days from next month (total 42 cells to prevent layout shifting)
    const trailingCount = 42 - days.length;
    for (let d = 1; d <= trailingCount; d += 1) {
      const nextM = viewMonth === 12 ? 1 : viewMonth + 1;
      const nextY = viewMonth === 12 ? viewYear + 1 : viewYear;
      const iso = formatISODate(nextY, nextM, d);
      days.push({
        year: nextY,
        month: nextM,
        day: d,
        iso,
        isCurrentMonth: false,
        disabled: Boolean((min && iso < min) || (max && iso > max)),
      });
    }

    return days;
  }, [viewYear, viewMonth, min, max]);

  const displayLabel = useMemo(() => {
    if (!parsedValue) return '';
    return formatDisplayDate(parsedValue.year, parsedValue.month, parsedValue.day);
  }, [parsedValue]);

  const popover = open && createPortal(
    <div
      ref={popoverRef}
      className="custom-datepicker-popover"
      style={{
        top: `${placement.top}px`,
        left: `${placement.left}px`,
        width: `${placement.width}px`,
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Bảng chọn ngày"
    >
      {/* Month/Year Header */}
      <div className="custom-datepicker-header">
        <div className="custom-datepicker-nav-group">
          <button
            type="button"
            className="custom-datepicker-nav-btn"
            title="Năm trước"
            aria-label="Năm trước"
            onClick={handlePrevYear}
          >
            <ChevronsLeft size={15} />
          </button>
          <button
            type="button"
            className="custom-datepicker-nav-btn"
            title="Tháng trước"
            aria-label="Tháng trước"
            onClick={handlePrevMonth}
          >
            <ChevronLeft size={15} />
          </button>
        </div>

        <span className="custom-datepicker-title">
          {MONTH_NAMES[viewMonth - 1]} năm {viewYear}
        </span>

        <div className="custom-datepicker-nav-group">
          <button
            type="button"
            className="custom-datepicker-nav-btn"
            title="Tháng sau"
            aria-label="Tháng sau"
            onClick={handleNextMonth}
          >
            <ChevronRight size={15} />
          </button>
          <button
            type="button"
            className="custom-datepicker-nav-btn"
            title="Năm sau"
            aria-label="Năm sau"
            onClick={handleNextYear}
          >
            <ChevronsRight size={15} />
          </button>
        </div>
      </div>

      {/* Weekdays header */}
      <div className="custom-datepicker-weekdays" aria-hidden="true">
        {WEEKDAY_NAMES.map((name) => (
          <div key={name} className="custom-datepicker-weekday">
            {name}
          </div>
        ))}
      </div>

      {/* 42-day Calendar Matrix */}
      <div className="custom-datepicker-grid" role="grid">
        {calendarDays.map((cell) => {
          const isSelected = parsedValue && cell.iso === value;
          const isToday = cell.iso === today.iso;

          return (
            <button
              key={cell.iso}
              type="button"
              className={`custom-datepicker-cell${isSelected ? ' is-selected' : ''}${isToday && !isSelected ? ' is-today' : ''}${!cell.isCurrentMonth ? ' is-other-month' : ''}`}
              disabled={cell.disabled}
              aria-selected={isSelected}
              aria-disabled={cell.disabled || undefined}
              title={cell.iso}
              onClick={() => handleSelectDay(cell)}
            >
              {cell.day}
            </button>
          );
        })}
      </div>

      {/* Action Footer */}
      <div className="custom-datepicker-footer">
        <button
          type="button"
          className="custom-datepicker-action-btn is-clear"
          onClick={handleClear}
        >
          Xóa
        </button>
        <button
          type="button"
          className="custom-datepicker-action-btn is-today-action"
          onClick={handleSelectToday}
          disabled={Boolean((min && today.iso < min) || (max && today.iso > max))}
        >
          Hôm nay
        </button>
        <button
          type="button"
          className="custom-datepicker-action-btn"
          onClick={() => setOpen(false)}
        >
          Đóng
        </button>
      </div>
    </div>,
    document.body
  );

  return (
    <div className={`custom-datepicker ${className}`} style={style}>
      <button
        ref={triggerRef}
        id={id}
        type="button"
        className={`custom-datepicker-trigger${open ? ' is-open' : ''}${!displayLabel ? ' is-empty' : ''}`}
        disabled={disabled}
        title={title}
        aria-label={ariaLabel}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-required={required || undefined}
        onClick={() => {
          if (!disabled) {
            if (parsedValue) {
              setViewYear(parsedValue.year);
              setViewMonth(parsedValue.month);
            } else {
              setViewYear(today.year);
              setViewMonth(today.month);
            }
            setOpen((curr) => !curr);
          }
        }}
      >
        <span className="custom-datepicker-value">
          {displayLabel || placeholder}
        </span>
        <span className="custom-datepicker-icons">
          {displayLabel && !disabled && (
            <span
              className="custom-datepicker-clear-btn"
              role="button"
              tabIndex={0}
              title="Xóa lựa chọn ngày"
              onClick={handleClear}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') handleClear(e);
              }}
            >
              <X size={14} />
            </span>
          )}
          <Calendar size={15} className="custom-datepicker-calendar-icon" aria-hidden="true" />
        </span>
      </button>

      {name && (
        <input
          type="hidden"
          name={name}
          value={value ?? ''}
        />
      )}

      {popover}
    </div>
  );
}
