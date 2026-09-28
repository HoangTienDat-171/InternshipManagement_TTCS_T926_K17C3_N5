import React, { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown } from 'lucide-react';

export default function CustomSelect({
  id,
  name,
  className = '',
  style,
  value = '',
  onChange,
  children,
  required = false,
  disabled = false,
  title,
  'aria-label': ariaLabel,
}) {
  const generatedId = useId();
  const listboxId = `${id || generatedId}-options`;
  const triggerRef = useRef(null);
  const menuRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [placement, setPlacement] = useState({ top: 0, left: 0, width: 0, maxHeight: 260 });

  const options = useMemo(() => React.Children.toArray(children)
    .filter((child) => React.isValidElement(child) && child.type === 'option')
    .map((option) => ({
      value: String(option.props.value ?? option.props.children ?? ''),
      label: option.props.children,
      disabled: Boolean(option.props.disabled),
    })), [children]);
  const selectedIndex = options.findIndex((option) => option.value === String(value ?? ''));
  const selectedOption = options[selectedIndex];
  const compact = style?.width === 'auto';

  const updatePlacement = () => {
    const trigger = triggerRef.current;
    const menu = menuRef.current;
    if (!trigger || !menu) return;
    const bounds = trigger.getBoundingClientRect();
    const menuHeight = Math.min(menu.scrollHeight, 260);
    const roomBelow = window.innerHeight - bounds.bottom - 12;
    const roomAbove = bounds.top - 12;
    const showAbove = roomBelow < menuHeight && roomAbove > roomBelow;
    const maxHeight = Math.max(100, Math.min(260, showAbove ? roomAbove : roomBelow));
    setPlacement({
      top: showAbove ? Math.max(8, bounds.top - Math.min(menuHeight, maxHeight) - 6) : bounds.bottom + 6,
      left: Math.max(8, Math.min(bounds.left, window.innerWidth - bounds.width - 8)),
      width: bounds.width,
      maxHeight,
    });
  };

  useLayoutEffect(() => {
    if (open) updatePlacement();
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const closeIfOutside = (event) => {
      if (!triggerRef.current?.contains(event.target) && !menuRef.current?.contains(event.target)) setOpen(false);
    };
    const reposition = () => updatePlacement();
    document.addEventListener('pointerdown', closeIfOutside, true);
    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', reposition, true);
    return () => {
      document.removeEventListener('pointerdown', closeIfOutside, true);
      window.removeEventListener('resize', reposition);
      window.removeEventListener('scroll', reposition, true);
    };
  }, [open]);

  const emitChange = (nextValue) => {
    onChange?.({ target: { name, value: nextValue } });
    setOpen(false);
    triggerRef.current?.focus();
  };

  const handleKeyDown = (event) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!open) {
        const firstEnabled = options.findIndex((option) => !option.disabled);
        setActiveIndex(selectedIndex >= 0 ? selectedIndex : Math.max(0, firstEnabled));
        setOpen(true);
        return;
      }
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      let next = activeIndex;
      for (let count = 0; count < options.length; count += 1) {
        next = (next + direction + options.length) % options.length;
        if (!options[next].disabled) break;
      }
      setActiveIndex(next);
    } else if ((event.key === 'Enter' || event.key === ' ') && open) {
      event.preventDefault();
      const activeOption = options[activeIndex];
      if (activeOption && !activeOption.disabled) emitChange(activeOption.value);
    } else if (event.key === 'Escape' && open) {
      event.preventDefault();
      setOpen(false);
    } else if (event.key === 'Home' && open) {
      event.preventDefault();
      const firstEnabled = options.findIndex((option) => !option.disabled);
      if (firstEnabled >= 0) setActiveIndex(firstEnabled);
    } else if (event.key === 'End' && open) {
      event.preventDefault();
      const lastEnabled = options.findLastIndex((option) => !option.disabled);
      if (lastEnabled >= 0) setActiveIndex(lastEnabled);
    }
  };

  const dropdown = open && createPortal(
    <div
      ref={menuRef}
      id={listboxId}
      className="custom-select-menu"
      role="listbox"
      style={{ ...placement, visibility: placement.width ? 'visible' : 'hidden' }}
    >
      {options.map((option, index) => (
        <div
          key={`${option.value}-${index}`}
          id={`${listboxId}-option-${index}`}
          className={`custom-select-option${index === activeIndex ? ' is-active' : ''}${option.value === String(value ?? '') ? ' is-selected' : ''}${option.disabled ? ' is-disabled' : ''}`}
          role="option"
          aria-selected={option.value === String(value ?? '')}
          aria-disabled={option.disabled || undefined}
          onMouseEnter={() => !option.disabled && setActiveIndex(index)}
          onClick={() => !option.disabled && emitChange(option.value)}
        >
          <span>{option.label}</span>
          {option.value === String(value ?? '') && <Check size={16} aria-hidden="true" />}
        </div>
      ))}
    </div>,
    document.body,
  );

  return (
    <div className={`custom-select${compact ? ' custom-select-compact' : ''} ${className}`} style={style}>
      <button
        ref={triggerRef}
        id={id}
        type="button"
        className={`custom-select-trigger${open ? ' is-open' : ''}`}
        disabled={disabled}
        title={title}
        style={compact ? style : undefined}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        aria-activedescendant={open ? `${listboxId}-option-${activeIndex}` : undefined}
        aria-required={required || undefined}
        onClick={() => {
          if (disabled) return;
          setActiveIndex(selectedIndex >= 0 ? selectedIndex : Math.max(0, options.findIndex((option) => !option.disabled)));
          setOpen((current) => !current);
        }}
        onKeyDown={handleKeyDown}
      >
        <span className="custom-select-value">{selectedOption?.label ?? options[0]?.label ?? ''}</span>
        <ChevronDown className={`custom-select-chevron${open ? ' is-open' : ''}`} size={16} aria-hidden="true" />
      </button>
      {name && (
        <input
          className="custom-select-form-value"
          type="text"
          name={name}
          value={value ?? ''}
          required={required}
          disabled={disabled}
          tabIndex={-1}
          aria-hidden="true"
          onChange={() => {}}
          onInvalid={(event) => {
            event.preventDefault();
            triggerRef.current?.focus();
            setOpen(true);
          }}
        />
      )}
      {dropdown}
    </div>
  );
}
