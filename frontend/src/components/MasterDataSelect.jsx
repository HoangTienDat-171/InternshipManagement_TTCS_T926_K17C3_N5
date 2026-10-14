import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, Plus, Search } from 'lucide-react';
import './MasterDataSelect.css';

const normalize = (value) => String(value || '').trim().replace(/\s+/g, ' ').toLocaleLowerCase();

export default function MasterDataSelect({
  id,
  name,
  value = '',
  items = [],
  idKey,
  labelKey,
  onChange,
  onCreateNew,
  placeholder = 'Chọn danh mục',
  disabled = false,
  required = false,
}) {
  const inputRef = useRef(null);
  const menuRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [placement, setPlacement] = useState({ top: 0, left: 0, width: 0, maxHeight: 280 });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  const selected = items.find((item) => String(item[idKey]) === String(value));
  const filteredItems = useMemo(() => {
    const needle = normalize(query);
    return items.filter((item) => !needle || normalize(item[labelKey]).includes(needle));
  }, [items, labelKey, query]);
  const canAdd = Boolean(onCreateNew && normalize(query)
    && !items.some((item) => normalize(item[labelKey]) === normalize(query)));

  const updatePlacement = () => {
    const input = inputRef.current;
    if (!input) return;
    const bounds = input.getBoundingClientRect();
    const below = window.innerHeight - bounds.bottom - 12;
    const above = bounds.top - 12;
    const showAbove = below < 220 && above > below;
    const maxHeight = Math.max(110, Math.min(280, showAbove ? above : below));
    setPlacement({
      top: showAbove ? Math.max(8, bounds.top - Math.min(280, maxHeight) - 6) : bounds.bottom + 6,
      left: Math.max(8, Math.min(bounds.left, window.innerWidth - bounds.width - 8)),
      width: bounds.width,
      maxHeight,
    });
  };

  useEffect(() => {
    if (!open) return undefined;
    updatePlacement();
    const closeOutside = (event) => {
      if (!inputRef.current?.parentElement?.contains(event.target) && !menuRef.current?.contains(event.target)) {
        setOpen(false);
        setQuery('');
        setError('');
      }
    };
    window.addEventListener('resize', updatePlacement);
    window.addEventListener('scroll', updatePlacement, true);
    document.addEventListener('pointerdown', closeOutside, true);
    return () => {
      window.removeEventListener('resize', updatePlacement);
      window.removeEventListener('scroll', updatePlacement, true);
      document.removeEventListener('pointerdown', closeOutside, true);
    };
  }, [open]);

  const emitChange = (nextValue) => {
    onChange?.({ target: { name, value: String(nextValue ?? '') } });
    setOpen(false);
    setQuery('');
    setError('');
  };

  const createOption = async () => {
    if (!canAdd || creating) return;
    setCreating(true);
    setError('');
    try {
      const created = await onCreateNew(query.trim().replace(/\s+/g, ' '));
      if (!created) throw new Error('Không nhận được dữ liệu danh mục vừa tạo.');
      emitChange(created[idKey]);
    } catch (createError) {
      setError(createError.message || 'Không thể thêm danh mục.');
    } finally {
      setCreating(false);
    }
  };

  const menu = open && createPortal(
    <div ref={menuRef} className="master-data-menu" style={{ ...placement, visibility: placement.width ? 'visible' : 'hidden' }}>
      <div className="master-data-search"><Search size={15} aria-hidden="true" /><span>{query ? `Kết quả cho “${query}”` : 'Tìm trong danh mục'}</span></div>
      <div id={`${id || name}-master-data-options`} className="master-data-options" role="listbox" aria-label={placeholder}>
        {filteredItems.map((item) => (
          <button
            type="button"
            role="option"
            aria-selected={String(item[idKey]) === String(value)}
            className="master-data-option"
            key={item[idKey]}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => emitChange(item[idKey])}
          >
            <span>{item[labelKey]}</span>
            {String(item[idKey]) === String(value) && <Check size={16} aria-hidden="true" />}
          </button>
        ))}
        {!filteredItems.length && !canAdd && <div className="master-data-empty">Không tìm thấy danh mục phù hợp.</div>}
      </div>
      {canAdd && <button type="button" className="master-data-add" onMouseDown={(event) => event.preventDefault()} onClick={createOption} disabled={creating}>
        <Plus size={16} aria-hidden="true" />
        <span>{creating ? 'Đang thêm…' : `Thêm “${query.trim().replace(/\s+/g, ' ')}”`}</span>
      </button>}
      {error && <div className="master-data-error" role="alert">{error}</div>}
    </div>,
    document.body,
  );

  return <div className="master-data-select">
    <div className="master-data-control">
      <input
        ref={inputRef}
        id={id}
        type="text"
        className="form-control"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-required={required || undefined}
        required={required}
        aria-controls={open ? `${id || name}-master-data-options` : undefined}
        autoComplete="off"
        value={open ? query : (selected?.[labelKey] || '')}
        placeholder={placeholder}
        disabled={disabled}
        onFocus={() => { setQuery(''); setError(''); setOpen(true); }}
        onChange={(event) => { setQuery(event.target.value); setOpen(true); setError(''); }}
        onKeyDown={(event) => {
          if (event.key === 'Escape') { setOpen(false); setQuery(''); }
          if (event.key === 'Enter' && open) {
            event.preventDefault();
            if (canAdd) void createOption();
            else if (filteredItems[0]) emitChange(filteredItems[0][idKey]);
          }
        }}
      />
      <ChevronDown className={open ? 'is-open' : ''} size={16} aria-hidden="true" />
    </div>
    <input type="hidden" name={name} value={value ?? ''} readOnly />
    {open && menu}
  </div>;
}
