import React, { useState } from 'react';
import { X, Lock, Mail, UserCheck, AlertCircle, ArrowRight } from 'lucide-react';

export default function LoginModal({ isOpen, onClose, onLoginSuccess, onSwitchToRegister }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErrorMsg('');

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, mat_khau: password }),
      });
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || 'Đăng nhập không thành công');
      }

      onLoginSuccess(data.user, data.token);
      onClose();
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleQuickLogin = (quickEmail, quickPassword) => {
    setEmail(quickEmail);
    setPassword(quickPassword);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-container" style={{ maxWidth: '440px' }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h3>Đăng nhập Hệ thống (US39)</h3>
            <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              Nhập email và mật khẩu tài khoản
            </p>
          </div>
          <button className="modal-close-btn" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        <div className="modal-body">
          {errorMsg && (
            <div className="alert-banner error" style={{ marginBottom: '16px' }}>
              <AlertCircle size={18} />
              <span>{errorMsg}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div className="form-group">
              <label className="form-label">Email tài khoản</label>
              <div style={{ position: 'relative' }}>
                <input
                  type="email"
                  className="form-control"
                  placeholder="admin@internship.vn"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Mật khẩu</label>
              <input
                type="password"
                className="form-control"
                placeholder="Nhập mật khẩu"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: '8px' }} disabled={loading}>
              <Lock size={16} />
              <span>{loading ? 'Đang xác thực...' : 'Đăng nhập'}</span>
            </button>
          </form>

          {/* Quick Login for 4 Roles */}
          <div style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-subtle)', textTransform: 'uppercase' }}>
              Chọn nhanh tài khoản mẫu theo vai trò:
            </span>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px', marginTop: '8px' }}>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => handleQuickLogin('admin@internship.vn', '123456')}
              >
                Admin (Quản trị)
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => handleQuickLogin('hr@internship.vn', '123456')}
              >
                Quản lý TTS (HR)
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => handleQuickLogin('mentor@internship.vn', '123456')}
              >
                Mentor
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => handleQuickLogin('tuan.lm@internship.vn', '123456')}
              >
                Thực tập sinh
              </button>
            </div>
          </div>

          <div style={{ textAlign: 'center', marginTop: '20px' }}>
            <button
              type="button"
              onClick={() => {
                onClose();
                onSwitchToRegister();
              }}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--primary-600)',
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px'
              }}
            >
              <span>Chưa có tài khoản? Tạo mới tài khoản (US39)</span>
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
