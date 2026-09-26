import React from 'react';
import { isValidVietnamPhone, sanitizePhone } from '../utils/phone';

export default function PhoneField({ value, onChange, required = false, label = 'Số điện thoại', placeholder = '0912345678', id = 'phone', name = 'so_dien_thoai' }) {
  const invalid = value && !isValidVietnamPhone(value);
  return (
    <div className="form-group">
      <label className="form-label" htmlFor={id}>{label}{required && <> <span className="required">*</span></>}</label>
      <input
        id={id}
        name={name}
        type="tel"
        inputMode="numeric"
        autoComplete="tel"
        className={`form-control${invalid ? ' is-invalid' : ''}`}
        placeholder={placeholder}
        value={value || ''}
        required={required}
        maxLength={10}
        aria-invalid={Boolean(invalid)}
        aria-describedby={invalid ? `${id}-error` : undefined}
        onChange={(event) => onChange(sanitizePhone(event.target.value))}
      />
      {invalid && <small className="field-error" id={`${id}-error`}>Số điện thoại phải gồm 10 chữ số và bắt đầu bằng 03, 05, 07, 08 hoặc 09.</small>}
    </div>
  );
}
