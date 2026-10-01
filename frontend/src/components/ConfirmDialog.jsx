import React, { useEffect } from 'react';
import { AlertTriangle, X } from 'lucide-react';

export default function ConfirmDialog({ open, title = 'Xác nhận thao tác', message, confirmLabel = 'Xác nhận', cancelLabel = 'Hủy', danger = false, className = '', children, busy = false, confirmDisabled = false, onConfirm, onCancel }) {
  useEffect(() => {
    if (!open) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && !busy) onCancel();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, busy, onCancel]);

  if (!open) return null;
  return (
    <div className="modal-overlay confirm-overlay" onMouseDown={(event) => !busy && event.target === event.currentTarget && onCancel()}>
      <section className={'confirm-dialog ' + className} role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-message">
        <div className={`confirm-icon${danger ? ' danger' : ''}`}><AlertTriangle size={22} /></div>
        <button className="modal-close-btn confirm-close" type="button" aria-label="Đóng" disabled={busy} onClick={onCancel}><X size={18} /></button>
        <h3 id="confirm-title">{title}</h3>
        <p id="confirm-message">{message}</p>
        {children}
        <div className="confirm-actions">
          <button type="button" className="btn btn-secondary" disabled={busy} onClick={onCancel}>{cancelLabel}</button>
          <button type="button" className={`btn ${danger ? 'btn-danger-solid' : 'btn-primary'}`} disabled={busy || confirmDisabled} aria-busy={busy} onClick={onConfirm}>
            {busy && <span className="contract-spinner" aria-hidden="true" />}{busy ? 'Đang xử lý…' : confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
