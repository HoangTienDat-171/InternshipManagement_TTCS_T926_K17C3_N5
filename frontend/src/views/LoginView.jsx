import React, { useState } from 'react';
import { Lock, Mail, Eye, EyeOff, Building2, AlertCircle, CheckCircle2, ArrowRight } from 'lucide-react';
import PhoneField from '../components/PhoneField';
import { isValidVietnamPhone } from '../utils/phone';
import { apiFetch } from '../utils/api';

export default function LoginView({ onLoginSuccess, sessionNotice }) {
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  
  // Login Form State
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  // Register Form State
  const [regForm, setRegForm] = useState({
    ho_ten: '',
    email: '',
    mat_khau: '',
    so_dien_thoai: ''
  });
  const [regLoading, setRegLoading] = useState(false);
  const [regSuccessMsg, setRegSuccessMsg] = useState('');

  const handleLoginSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErrorMsg('');

    try {
      const res = await apiFetch('/api/auth/login', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify({ 
          email: email.trim(), 
          mat_khau: password 
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || 'Email hoặc mật khẩu không chính xác');
      }

      localStorage.setItem('ims_token', data.token);
      localStorage.setItem('ims_user', JSON.stringify(data.user));

      onLoginSuccess(data.user, data.token);
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterSubmit = async (e) => {
    e.preventDefault();
    setRegLoading(true);
    setErrorMsg('');
    setRegSuccessMsg('');

    if (regForm.mat_khau.length < 6) {
      setErrorMsg('Mật khẩu phải có tối thiểu 6 ký tự');
      setRegLoading(false);
      return;
    }
    if (regForm.so_dien_thoai && !isValidVietnamPhone(regForm.so_dien_thoai)) {
      setErrorMsg('Số điện thoại phải gồm 10 chữ số và bắt đầu bằng 03, 05, 07, 08 hoặc 09.');
      setRegLoading(false);
      return;
    }

    try {
      // Mặc định là Thực tập sinh và chờ Quản lý thực tập sinh xét duyệt
      const payload = {
        ho_ten: regForm.ho_ten.trim(),
        email: regForm.email.trim(),
        mat_khau: regForm.mat_khau,
        so_dien_thoai: regForm.so_dien_thoai.trim(),
        vai_tro: 'ThucTapSinh'
      };

      const res = await apiFetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Không thể tạo tài khoản');
      }

      setRegSuccessMsg('Đăng ký thành công! Tài khoản đang chờ Quản lý thực tập sinh xét duyệt trước khi có thể đăng nhập.');
      setEmail(regForm.email);
      setPassword('');
      setIsRegisterMode(false);
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setRegLoading(false);
    }
  };

  const handleQuickLogin = (quickEmail, quickPassword) => {
    setEmail(quickEmail);
    setPassword(quickPassword);
    setErrorMsg('');
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: '#f8fafc',
      padding: '24px',
      fontFamily: 'var(--font-family)'
    }}>
      <div style={{
        width: '100%',
        maxWidth: '440px',
        background: '#ffffff',
        borderRadius: '16px',
        boxShadow: '0 4px 20px -2px rgba(15, 23, 42, 0.08), 0 2px 6px -1px rgba(15, 23, 42, 0.04)',
        border: '1px solid #e2e8f0',
        padding: '36px 32px'
      }}>
        {/* Brand Header */}
        <div style={{ textAlign: 'center', marginBottom: '28px' }}>
          <div style={{
            width: '46px',
            height: '46px',
            borderRadius: '12px',
            background: 'linear-gradient(135deg, #2563eb, #1d4ed8)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white',
            marginBottom: '14px',
            boxShadow: '0 4px 10px rgba(37, 99, 235, 0.2)'
          }}>
            <Building2 size={24} />
          </div>
          <h1 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a', letterSpacing: '-0.3px' }}>
            Hệ thống Quản lý Thực tập sinh
          </h1>
          <p style={{ fontSize: '13px', color: '#64748b', marginTop: '4px' }}>
            {isRegisterMode ? 'Đăng ký tài khoản Thực tập sinh' : 'Đăng nhập để vào hệ thống làm việc'}
          </p>
        </div>

        {/* Thông báo lỗi / thành công */}
        {sessionNotice && (
          <div className="alert-banner error" style={{ marginBottom: '18px', padding: '10px 14px' }}>
            <AlertCircle size={16} style={{ flexShrink: 0 }} />
            <span style={{ fontSize: '13px' }}>{sessionNotice}</span>
          </div>
        )}
        {errorMsg && (
          <div className="alert-banner error" style={{ marginBottom: '18px', padding: '10px 14px' }}>
            <AlertCircle size={16} style={{ flexShrink: 0 }} />
            <span style={{ fontSize: '13px' }}>{errorMsg}</span>
          </div>
        )}

        {regSuccessMsg && (
          <div className="alert-banner success" style={{ marginBottom: '18px', padding: '10px 14px' }}>
            <CheckCircle2 size={16} style={{ flexShrink: 0 }} />
            <span style={{ fontSize: '13px' }}>{regSuccessMsg}</span>
          </div>
        )}

        {/* Form Đăng nhập */}
        {!isRegisterMode ? (
          <form onSubmit={handleLoginSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div className="form-group">
              <label className="form-label" style={{ fontSize: '13px' }}>
                Email
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  type="email"
                  className="form-control"
                  placeholder="admin@internship.vn"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="username"
                  style={{ paddingRight: '38px' }}
                />
                <Mail size={16} color="#94a3b8" style={{ position: 'absolute', right: '12px', top: '12px' }} />
              </div>
            </div>

            <div className="form-group">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <label className="form-label" style={{ fontSize: '13px' }}>
                  Mật khẩu
                </label>
              </div>
              <div style={{ position: 'relative' }}>
                <input
                  type={showPassword ? 'text' : 'password'}
                  className="form-control"
                  placeholder="••••••••"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  style={{ paddingRight: '38px' }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  style={{
                    position: 'absolute',
                    right: '12px',
                    top: '10px',
                    background: 'none',
                    border: 'none',
                    color: '#94a3b8',
                    cursor: 'pointer',
                    padding: '2px'
                  }}
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              style={{ width: '100%', padding: '11px', fontSize: '14px', marginTop: '4px' }}
              disabled={loading}
            >
              <Lock size={15} />
              <span>{loading ? 'Đang xử lý...' : 'Đăng nhập'}</span>
            </button>
          </form>
        ) : (
          /* Form Đăng ký tài khoản (Mặc định là Thực tập sinh) */
          <form onSubmit={handleRegisterSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div className="form-group">
              <label className="form-label" style={{ fontSize: '13px' }}>Họ và tên</label>
              <input
                type="text"
                className="form-control"
                placeholder="Nguyễn Văn A"
                required
                value={regForm.ho_ten}
                onChange={(e) => setRegForm({ ...regForm, ho_ten: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label className="form-label" style={{ fontSize: '13px' }}>Email sinh viên</label>
              <input
                type="email"
                className="form-control"
                placeholder="sinhvien@example.com"
                required
                value={regForm.email}
                onChange={(e) => setRegForm({ ...regForm, email: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label className="form-label" style={{ fontSize: '13px' }}>Mật khẩu (Tối thiểu 6 ký tự)</label>
              <input
                type="password"
                className="form-control"
                placeholder="Nhập mật khẩu an toàn"
                required
                value={regForm.mat_khau}
                onChange={(e) => setRegForm({ ...regForm, mat_khau: e.target.value })}
              />
            </div>

            <PhoneField id="register-phone" value={regForm.so_dien_thoai} onChange={(value) => setRegForm((prev) => ({ ...prev, so_dien_thoai: value }))} />

            <div style={{
              background: '#f8fafc',
              padding: '10px 12px',
              borderRadius: '8px',
              border: '1px solid #e2e8f0',
              fontSize: '12px',
              color: '#475569'
            }}>
              <div><strong>Vai trò:</strong> Thực tập sinh (Mặc định)</div>
              <div style={{ marginTop: '2px', color: '#64748b' }}>
                Sau khi đăng ký, tài khoản sẽ chuyển tới <strong>Quản lý thực tập sinh</strong> xét duyệt kích hoạt.
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              style={{ width: '100%', padding: '11px', marginTop: '6px' }}
              disabled={regLoading}
            >
              <span>{regLoading ? 'Đang gửi thông tin...' : 'Đăng ký tài khoản'}</span>
            </button>
          </form>
        )}

        {/* Chuyển đổi Đăng nhập / Đăng ký */}
        <div style={{ textAlign: 'center', marginTop: '18px', paddingTop: '16px', borderTop: '1px solid #f1f5f9' }}>
          <button
            type="button"
            onClick={() => {
              setIsRegisterMode(!isRegisterMode);
              setErrorMsg('');
              setRegSuccessMsg('');
            }}
            style={{
              background: 'none',
              border: 'none',
              color: '#2563eb',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px'
            }}
          >
            <span>{isRegisterMode ? 'Đã có tài khoản? Đăng nhập' : 'Chưa có tài khoản? Đăng ký Thực tập sinh'}</span>
            <ArrowRight size={13} />
          </button>
        </div>

        {/* Chọn nhanh tài khoản test mẫu */}
        {!isRegisterMode && (
          <div style={{ marginTop: '20px', paddingTop: '14px', borderTop: '1px solid #f1f5f9' }}>
            <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 600, marginBottom: '8px', textAlign: 'center' }}>
              Tài khoản mẫu:
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '6px' }}>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                style={{ fontSize: '11px', padding: '5px 4px' }}
                onClick={() => handleQuickLogin('admin@internship.vn', '123456')}
              >
                Admin
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                style={{ fontSize: '11px', padding: '5px 4px' }}
                onClick={() => handleQuickLogin('hr@internship.vn', '123456')}
              >
                Quản lý
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                style={{ fontSize: '11px', padding: '5px 4px' }}
                onClick={() => handleQuickLogin('mentor@internship.vn', '123456')}
              >
                Mentor
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                style={{ fontSize: '11px', padding: '5px 4px' }}
                onClick={() => handleQuickLogin('tuan.lm@internship.vn', '123456')}
              >
                TTS
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
