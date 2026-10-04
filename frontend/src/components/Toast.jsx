import React from 'react';
import { AlertCircle, CheckCircle2, X } from 'lucide-react';

export default function Toast({ message, type = 'success', onClose }) {
  const success = type === 'success';
  return <div className={`app-toast is-${success ? 'success' : 'error'}`} role={success ? 'status' : 'alert'} aria-live={success ? 'polite' : 'assertive'}>
    <span className="app-toast-icon">{success ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}</span>
    <span className="app-toast-copy"><strong>{success ? 'Thao tác thành công' : 'Không thể hoàn tất'}</strong><span>{message}</span></span>
    <button type="button" aria-label="Đóng thông báo" onClick={onClose}><X size={15} /></button>
  </div>;
}
