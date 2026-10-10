import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Calendar, ChevronLeft, ChevronRight, X } from 'lucide-react';
import './MonthYearPicker.css';

const MONTHS = [
  'Thg1', 'Thg2', 'Thg3', 'Thg4',
  'Thg5', 'Thg6', 'Thg7', 'Thg8',
  'Thg9', 'Thg10', 'Thg11', 'Thg12'
];

export default function MonthYearPicker({
  id,
  value = '',
  onChange,
  placeholder = 'Chọn kỳ phụ cấp (tháng/năm)',
  disabled = false,
  className = '',
  style,
}) {
  const triggerRef = useRef(null);
  const popoverRef = useRef(null);
  const [open, setOpen] = useState(false);

  // Parse initial year/month from value (format: YYYY-MM)
  const parsedValue = useMemo(() => {
    if (!value || typeof value !== 'string') return null;
    const parts = value.split('-');
    if (parts.length === 2) {
      const year = parseInt(parts[0], 10);
      const month = parseInt(parts[1], 10);
      if (!isNaN(year) && !isNaN(month) && month >= 1 && month <= 12) {
        return { year, month };
      }
    }
    return null;
  }, [value]);

  const currentYear = useMemo(() => new Date().getFullYear(), []);
  const currentMonth = useMemo(() => new Date().getMonth() + 1, []);

  const [viewYear, setViewYear] = useState(() => parsedValue?.year ?? currentYear);

  const [placement, setPlacement] = useState({ top: 0, left: 0, width: 280 });

  const updatePlacement = () => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const bounds = trigger.getBoundingClientRect();
    const popoverHeight = 290;
    const roomBelow = window.innerHeight - bounds.bottom - 12;
    const roomAbove = bounds.top - 12;
    const showAbove = roomBelow < popoverHeight && roomAbove > roomBelow;
    const width = Math.max(bounds.width, 280);

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
      if (!triggerRef.current?.contains(event.target) && !popoverRef.current?.contains(event.target)) {
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

  const handleSelectMonth = (monthIndex) => {
    const monthNum = monthIndex + 1;
    const formatted = `${viewYear}-${String(monthNum).padStart(2, '0')}`;
    onChange?.(formatted);
    setOpen(false);
    triggerRef.current?.focus();
  };

  const handleClear = (e) => {
    e?.stopPropagation();
    onChange?.('');
    setOpen(false);
    triggerRef.current?.focus();
  };

  const handleSelectCurrentMonth = () => {
    const now = new Date();
    const formatted = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    setViewYear(now.getFullYear());
    onChange?.(formatted);
    setOpen(false);
    triggerRef.current?.focus();
  };

  // Label to display on the trigger
  const displayLabel = useMemo(() => {
    if (!parsedValue) return '';
    return `Tháng ${parsedValue.month}/${parsedValue.year}`;
  }, [parsedValue]);

  const popover = open && createPortal(
    <div
      ref={popoverRef}
      className="month-year-popover"
      style={{
        top: `${placement.top}px`,
        left: `${placement.left}px`,
        width: `${placement.width}px`,
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Chọn kỳ tháng và năm"
    >
      {/* Year Navigator Header */}
      <div className="month-year-header">
        <button
          type="button"
          className="month-year-nav-btn"
          aria-label="Năm trước"
          onClick={() => setViewYear((y) => y - 1)}
        >
          <ChevronLeft size={16} />
        </button>
        <span className="month-year-title">{viewYear}</span>
        <button
          type="button"
          className="month-year-nav-btn"
          aria-label="Năm sau"
          onClick={() => setViewYear((y) => y + 1)}
        >
          <ChevronRight size={16} />
        </button>
      </div>

      {/* 3x4 Month Grid */}
      <div className="month-year-grid" role="grid">
        {MONTHS.map((name, idx) => {
          const monthNum = idx + 1;
          const isSelected = parsedValue?.year === viewYear && parsedValue?.month === monthNum;
          const isThisMonth = currentYear === viewYear && currentMonth === monthNum;

          return (
            <button
              key={name}
              type="button"
              className={`month-year-cell${isSelected ? ' is-selected' : ''}${isThisMonth && !isSelected ? ' is-current' : ''}`}
              aria-pressed={isSelected}
              onClick={() => handleSelectMonth(idx)}
            >
              {name}
            </button>
          );
        })}
      </div>

      {/* Footer Actions: Ghost Buttons */}
      <div className="month-year-footer">
        <button
          type="button"
          className="month-year-action-btn"
          onClick={handleClear}
        >
          Xóa
        </button>
        <button
          type="button"
          className="month-year-action-btn"
          onClick={handleSelectCurrentMonth}
        >
          Tháng này
        </button>
      </div>
    </div>,
    document.body
  );

  return (
    <div className={`month-year-picker ${className}`} style={style}>
      <button
        ref={triggerRef}
        id={id}
        type="button"
        className={`month-year-trigger${open ? ' is-open' : ''}${!displayLabel ? ' is-empty' : ''}`}
        disabled={disabled}
        onClick={() => {
          if (!disabled) {
            setViewYear(parsedValue?.year ?? currentYear);
            setOpen((curr) => !curr);
          }
        }}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <span className="month-year-value">
          {displayLabel || placeholder}
        </span>
        <span className="month-year-trigger-icons">
          {displayLabel && !disabled && (
            <span
              className="month-year-clear-icon"
              role="button"
              tabIndex={0}
              title="Xóa lựa chọn"
              onClick={handleClear}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') handleClear(e);
              }}
            >
              <X size={14} />
            </span>
          )}
          <Calendar size={16} className="month-year-calendar-icon" aria-hidden="true" />
        </span>
      </button>
      {popover}
    </div>
  );
}
