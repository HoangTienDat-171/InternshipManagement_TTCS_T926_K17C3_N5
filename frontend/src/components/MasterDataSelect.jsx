import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
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
  itemName = 'danh mục',
  maxNameLength = 255,
  confirmCreate = false,
  disabled = false,
  required = false,
}) {
  const inputRef = useRef(null);
  const menuRef = useRef(null);
  const createNameRef = useRef(null);
  const optionRefs = useRef([]);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [placement, setPlacement] = useState({ top: 0, left: 0, width: 0, height: 280, showAbove: false });
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createName, setCreateName] = useState('');
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
    const gap = 6;
    const viewportPadding = 8;
    const below = Math.max(0, window.innerHeight - bounds.bottom - viewportPadding - gap);
    const above = Math.max(0, bounds.top - viewportPadding - gap);
    const showAbove = below < 160 && above > below;
    const available = showAbove ? above : below;
    const height = Math.min(280, available);
    const width = Math.min(bounds.width, window.innerWidth - viewportPadding * 2);
    const left = Math.max(viewportPadding, Math.min(bounds.left, window.innerWidth - width - viewportPadding));
    const top = showAbove
      ? Math.max(viewportPadding, bounds.top - height - gap)
      : Math.min(bounds.bottom + gap, window.innerHeight - height - viewportPadding);

    setPlacement({ top, left, width, height, showAbove });
  };

  useLayoutEffect(() => {
    if (!open) return undefined;
    updatePlacement();
    const closeOutside = (event) => {
      if (!inputRef.current?.parentElement?.contains(event.target) && !menuRef.current?.contains(event.target)) {
        setOpen(false);
        setQuery('');
        setShowCreateForm(false);
        setCreateName('');
        setError('');
      }
    };
    const handleEscape = (event) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopPropagation();
      if (showCreateForm) {
        setShowCreateForm(false);
        setCreateName('');
        setError('');
        inputRef.current?.focus();
      } else {
        setOpen(false);
        setQuery('');
        setError('');
      }
    };
    window.addEventListener('resize', updatePlacement);
    window.addEventListener('scroll', updatePlacement, true);
    document.addEventListener('pointerdown', closeOutside, true);
    document.addEventListener('keydown', handleEscape, true);
    return () => {
      window.removeEventListener('resize', updatePlacement);
      window.removeEventListener('scroll', updatePlacement, true);
      document.removeEventListener('pointerdown', closeOutside, true);
      document.removeEventListener('keydown', handleEscape, true);
    };
  }, [open, showCreateForm]);

  useEffect(() => {
    if (showCreateForm) createNameRef.current?.focus();
  }, [showCreateForm]);

  const emitChange = (nextValue) => {
    onChange?.({ target: { name, value: String(nextValue ?? '') } });
    setOpen(false);
    setQuery('');
    setShowCreateForm(false);
    setCreateName('');
    setError('');
  };

  const createItem = async (normalizedName) => {
    setCreating(true);
    setError('');
    try {
      const created = await onCreateNew(normalizedName);
      if (!created || created[idKey] == null) throw new Error('Không nhận được dữ liệu danh mục vừa tạo.');
      emitChange(created[idKey]);
    } catch (createError) {
      setError(createError.message || 'Không thể thêm danh mục.');
      createNameRef.current?.focus();
    } finally {
      setCreating(false);
    }
  };

  const submitCreate = async (event) => {
    event?.preventDefault();
    const normalizedName = String(createName || '').trim().replace(/\s+/g, ' ');
    if (!normalizedName) {
      setError(`Vui lòng nhập tên ${itemName}.`);
      createNameRef.current?.focus();
      return;
    }
    if (normalizedName.length > maxNameLength) {
      setError(`Tên ${itemName} không được vượt quá ${maxNameLength} ký tự.`);
      createNameRef.current?.focus();
      return;
    }
    if (items.some((item) => normalize(item[labelKey]) === normalize(normalizedName))) {
      setError(`${itemName[0].toLocaleUpperCase()}${itemName.slice(1)} này đã tồn tại.`);
      createNameRef.current?.focus();
      return;
    }

    await createItem(normalizedName);
  };

  const openCreateForm = () => {
    setCreateName(String(query || '').trim().replace(/\s+/g, ' '));
    setError('');
    setShowCreateForm(true);
  };

  const handleAdd = () => {
    if (confirmCreate) {
      openCreateForm();
      return;
    }
    void createItem(String(query || '').trim().replace(/\s+/g, ' '));
  };

  const focusOption = (index) => {
    const option = optionRefs.current[index];
    option?.focus();
  };

  const handleOptionKeyDown = (event, index) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (index + 1 < filteredItems.length) focusOption(index + 1);
      else if (canAdd) menuRef.current?.querySelector('.master-data-add')?.focus();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (index > 0) focusOption(index - 1);
      else inputRef.current?.focus();
    }
  };

  const menu = open && createPortal(
    <div
      ref={menuRef}
      className={`master-data-menu${placement.showAbove ? ' opens-above' : ''}`}
      style={{
        top: placement.top,
        left: placement.left,
        width: placement.width,
        height: placement.height,
        visibility: placement.width ? 'visible' : 'hidden',
      }}
    >
      {!showCreateForm && <>
        <div className="master-data-search"><Search size={15} aria-hidden="true" /><span>{query ? `Kết quả cho “${query}”` : 'Tìm trong danh mục'}</span></div>
        <div id={`${id || name}-master-data-options`} className="master-data-options" role="listbox" aria-label={placeholder}>
          {filteredItems.map((item, index) => (
            <button
              type="button"
              role="option"
              aria-selected={String(item[idKey]) === String(value)}
              className="master-data-option"
              key={item[idKey]}
              ref={(element) => { optionRefs.current[index] = element; }}
              onKeyDown={(event) => handleOptionKeyDown(event, index)}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => emitChange(item[idKey])}
            >
              <span>{item[labelKey]}</span>
              {String(item[idKey]) === String(value) && <Check size={16} aria-hidden="true" />}
            </button>
          ))}
          {!filteredItems.length && <div className="master-data-empty">Không tìm thấy {itemName} phù hợp.</div>}
        </div>
      </>}
      {canAdd && !showCreateForm && (
        <button
          type="button"
          className="master-data-add"
          onMouseDown={(event) => event.preventDefault()}
          onClick={handleAdd}
          disabled={creating}
        >
          <Plus size={16} aria-hidden="true" />
          <span>{creating ? 'Đang thêm…' : `Thêm ${itemName} “${query.trim().replace(/\s+/g, ' ')}”`}</span>
        </button>
      )}
      {showCreateForm && (
        <div className="master-data-create" aria-label={`Thêm ${itemName} mới`}>
          <label htmlFor={`${id || name}-new-master-item`}>Tên {itemName} mới</label>
          <input
            ref={createNameRef}
            id={`${id || name}-new-master-item`}
            type="text"
            maxLength={maxNameLength}
            value={createName}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? `${id || name}-master-data-error` : undefined}
            placeholder={`Nhập tên ${itemName}`}
            onChange={(event) => { setCreateName(event.target.value); setError(''); }}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void submitCreate(event);
            }}
            disabled={creating}
          />
          {error && <div id={`${id || name}-master-data-error`} className="master-data-error" role="alert">{error}</div>}
          <div className="master-data-create-actions">
            <button type="button" className="master-data-cancel" onClick={() => { setShowCreateForm(false); setCreateName(''); setError(''); inputRef.current?.focus(); }} disabled={creating}>Hủy</button>
            <button type="button" className="master-data-save" onClick={() => void submitCreate()} disabled={creating}>
              {creating ? 'Đang lưu…' : `Lưu ${itemName}`}
            </button>
          </div>
        </div>
      )}
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
        onFocus={() => {
          setError('');
          if (!open) {
            setQuery('');
            setOpen(true);
          }
        }}
        onChange={(event) => { setQuery(event.target.value); setOpen(true); setError(''); }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' && open && filteredItems.length) {
            event.preventDefault();
            focusOption(0);
          } else if (event.key === 'Enter' && open) {
            event.preventDefault();
            if (filteredItems.length === 1) emitChange(filteredItems[0][idKey]);
            else if (!filteredItems.length && canAdd) openCreateForm();
          }
        }}
      />
      <ChevronDown className={open ? 'is-open' : ''} size={16} aria-hidden="true" />
    </div>
    <input type="hidden" name={name} value={value ?? ''} readOnly />
    {menu}
  </div>;
}
