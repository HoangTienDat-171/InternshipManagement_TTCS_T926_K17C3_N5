import React, { useState } from 'react';
import { Lock, Mail, Eye, EyeOff, Building2, AlertCircle, CheckCircle2, ArrowRight, ArrowLeft, KeyRound, UploadCloud, FileText } from 'lucide-react';
import PhoneField from '../components/PhoneField';
import { isValidVietnamPhone } from '../utils/phone';
import { apiFetch } from '../utils/api';

async function readApiResponse(response) {
  const responseText = await response.text();
  let data = {};

  if (responseText) {
    try {
      data = JSON.parse(responseText);
    } catch {
      if (response.status >= 500) {
        throw new Error('Máy chủ đăng nhập không khả dụng. Hãy kiểm tra backend FastAPI tại cổng 8000.');
      }
      throw new Error('Máy chủ trả về dữ liệu không hợp lệ. Vui lòng thử lại.');
    }
  }

  if (!response.ok) {
    const message = typeof data.detail === 'string'
      ? data.detail
      : Array.isArray(data.detail)
        ? data.detail.map((e) => e.msg || e.detail).join('; ')
        : (data.detail?.message || null);
    if (message) {
      throw new Error(message);
    }
    if (response.status >= 500) {
      throw new Error('Máy chủ đăng nhập không khả dụng. Hãy kiểm tra backend FastAPI tại cổng 8000.');
    }
    throw new Error('Không thể xử lý yêu cầu. Vui lòng thử lại.');
  }

  return data;
}

function getRequestError(error) {
  if (error instanceof TypeError || /failed to fetch|networkerror/i.test(error.message || '')) {
    return 'Không thể kết nối máy chủ. Hãy kiểm tra backend FastAPI tại cổng 8000 rồi thử lại.';
  }
  return error.message || 'Đã xảy ra lỗi. Vui lòng thử lại.';
}

export default function LoginView({ onLoginSuccess, sessionNotice }) {
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  
  // Login Form State
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  // Forgot Password State
  const [isForgotMode, setIsForgotMode] = useState(false);
  const [forgotEmail, setForgotEmail] = useState('');
  const [forgotLoading, setForgotLoading] = useState(false);
  const [forgotSuccessMsg, setForgotSuccessMsg] = useState('');

  // Register Form State
  const [regForm, setRegForm] = useState({
    ho_ten: '',
    email: '',
    so_dien_thoai: ''
  });
  const [regLoading, setRegLoading] = useState(false);
  const [regSuccessMsg, setRegSuccessMsg] = useState('');
  const [regCv, setRegCv] = useState(null);

  const handleLoginSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      setErrorMsg('Vui lòng nhập địa chỉ email hợp lệ.');
      return;
    }
    if (!password) {
      setErrorMsg('Vui lòng nhập mật khẩu.');
      return;
    }
    setLoading(true);

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

      const data = await readApiResponse(res);

      localStorage.setItem('ims_token', data.token);
      localStorage.setItem('ims_user', JSON.stringify(data.user));

      onLoginSuccess(data.user, data.token);
    } catch (err) {
      setErrorMsg(getRequestError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setRegSuccessMsg('');

    if (!regForm.ho_ten.trim()) {
      setErrorMsg('Vui lòng nhập họ và tên.');
      return;
    }
    if (!/^\S+@\S+\.\S+$/.test(regForm.email.trim())) {
      setErrorMsg('Vui lòng nhập email sinh viên hợp lệ.');
      return;
    }
    setRegLoading(true);

    if (regForm.so_dien_thoai && !isValidVietnamPhone(regForm.so_dien_thoai)) {
      setErrorMsg('Số điện thoại phải gồm 10 chữ số và bắt đầu bằng 03, 05, 07, 08 hoặc 09.');
      setRegLoading(false);
      return;
    }
    if (regCv && (regCv.size > 15 * 1024 * 1024 || !['pdf', 'docx', 'png'].includes(regCv.name.split('.').pop()?.toLowerCase()))) {
      setErrorMsg('CV phải có định dạng PDF, DOCX hoặc PNG và dung lượng tối đa 15 MB.');
      setRegLoading(false);
      return;
    }

    try {
      const payload = new FormData();
      payload.append('ho_ten', regForm.ho_ten.trim());
      payload.append('email', regForm.email.trim());
      payload.append('so_dien_thoai', regForm.so_dien_thoai.trim());
      if (regCv) payload.append('cv', regCv);

      const res = await apiFetch('/api/auth/register-with-cv', {
        method: 'POST',
        body: payload
      });

      const data = await readApiResponse(res);

      setRegSuccessMsg(data.message || 'Đăng ký thành công! Hồ sơ đang chờ xét duyệt. Mật khẩu đăng nhập sẽ được gửi qua email sau khi hồ sơ được duyệt.');
      setEmail(regForm.email);
      setPassword('');
      setRegCv(null);
      setIsRegisterMode(false);
    } catch (err) {
      setErrorMsg(getRequestError(err));
    } finally {
      setRegLoading(false);
    }
  };

  const handleQuickLogin = (quickEmail, quickPassword) => {
    setEmail(quickEmail);
    setPassword(quickPassword);
    setErrorMsg('');
  };

  const openForgotMode = () => {
    setIsForgotMode(true);
    setIsRegisterMode(false);
    setForgotEmail(email);
    setErrorMsg('');
    setRegSuccessMsg('');
    setForgotSuccessMsg('');
  };

  const backToLogin = () => {
    setIsForgotMode(false);
    setIsRegisterMode(false);
    setErrorMsg('');
    setRegSuccessMsg('');
    setForgotSuccessMsg('');
  };

  const handleForgotSubmit = async (e) => {
    e.preventDefault();
    setForgotLoading(true);
    setErrorMsg('');
    setForgotSuccessMsg('');

    const targetEmail = (forgotEmail || email).trim();
    if (!targetEmail) {
      setErrorMsg('Vui lòng nhập địa chỉ email.');
      setForgotLoading(false);
      return;
    }
    if (!/^\S+@\S+\.\S+$/.test(targetEmail)) {
      setErrorMsg('Vui lòng nhập địa chỉ email hợp lệ.');
      setForgotLoading(false);
      return;
    }

    try {
      const res = await apiFetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({ email: targetEmail }),
      });

      const data = await readApiResponse(res);
      setForgotSuccessMsg(data.message || 'Mật khẩu tạm thời mới đã được gửi về email của bạn.');
      setEmail(targetEmail);
    } catch (err) {
      setErrorMsg(getRequestError(err));
    } finally {
      setForgotLoading(false);
    }
  };

  const toggleAuthMode = () => {
    setIsRegisterMode((mode) => !mode);
    setIsForgotMode(false);
    setErrorMsg('');
    setRegSuccessMsg('');
    setForgotSuccessMsg('');
  };

  return (
    <main className="auth-page">
      <div className={`auth-card ${isRegisterMode ? 'register-mode' : ''}`}>
        <section className="auth-form-panel">
        <div className="auth-form-content">
        {/* Brand Header */}
        <div className="auth-brand-header">
          <div style={{
            width: '46px',
            height: '46px',
            borderRadius: '12px',
            background: 'linear-gradient(135deg, #6b63ee, #4f46d8)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white',
            marginBottom: '14px',
            boxShadow: '0 4px 10px rgba(79, 70, 216, 0.2)'
          }}>
            <Building2 size={24} />
          </div>
          <div className="auth-brand-name">IMS PORTAL</div>
          <h1>Hệ thống Quản lý Thực tập sinh</h1>
          <p style={{ fontSize: '13px', color: '#64748b', marginTop: '4px' }}>
            {isForgotMode
              ? 'Khôi phục quyền truy cập vào tài khoản của bạn'
              : isRegisterMode
                ? 'Đăng ký tài khoản Thực tập sinh'
                : 'Đăng nhập để vào hệ thống làm việc'}
          </p>
        </div>

        {/* Thông báo lỗi / thành công */}
        {!isForgotMode && !isRegisterMode && sessionNotice && (
          <div className="alert-banner error auth-alert" role="alert">
            <AlertCircle size={16} style={{ flexShrink: 0 }} />
            <span style={{ fontSize: '13px' }}>{sessionNotice}</span>
          </div>
        )}
        {errorMsg && (
          <div className="alert-banner error auth-alert" role="alert">
            <AlertCircle size={16} style={{ flexShrink: 0 }} />
            <span style={{ fontSize: '13px' }}>{errorMsg}</span>
          </div>
        )}

        {regSuccessMsg && (
          <div className="alert-banner success auth-alert" role="status">
            <CheckCircle2 size={16} style={{ flexShrink: 0 }} />
            <span style={{ fontSize: '13px' }}>{regSuccessMsg}</span>
          </div>
        )}

        {forgotSuccessMsg && (
          <div className="alert-banner success auth-alert" role="status">
            <CheckCircle2 size={16} style={{ flexShrink: 0 }} />
            <span style={{ fontSize: '13px' }}>{forgotSuccessMsg}</span>
          </div>
        )}

        {/* Form Đăng nhập & Quên mật khẩu */}
        {isForgotMode ? (
          <form noValidate onSubmit={handleForgotSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{
              background: '#eff6ff',
              padding: '12px 14px',
              borderRadius: '10px',
              border: '1px solid #bfdbfe',
              fontSize: '13px',
              color: '#1e40af',
              lineHeight: 1.5
            }}>
              Nhập địa chỉ email của bạn. Hệ thống sẽ tạo mật khẩu tạm thời 8 ký tự và gửi qua email để bạn đăng nhập và đổi mật khẩu mới.
            </div>

            <div className="form-group">
              <label className="form-label" style={{ fontSize: '13px' }}>
                Địa chỉ Email
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  type="email"
                  className="form-control"
                  placeholder="admin@internship.vn"
                  required
                  value={forgotEmail || email}
                  onChange={(e) => {
                    setForgotEmail(e.target.value);
                    setEmail(e.target.value);
                  }}
                  autoComplete="email"
                  style={{ paddingRight: '38px' }}
                />
                <Mail size={16} color="#94a3b8" style={{ position: 'absolute', right: '12px', top: '12px' }} />
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              style={{ width: '100%', padding: '11px', fontSize: '14px', marginTop: '4px' }}
              disabled={forgotLoading}
            >
              <KeyRound size={15} />
              <span>{forgotLoading ? 'Đang gửi yêu cầu...' : 'Gửi mật khẩu mới'}</span>
            </button>

            <button
              type="button"
              className="btn btn-secondary"
              style={{ width: '100%', padding: '10px', fontSize: '13px' }}
              onClick={backToLogin}
            >
              <ArrowLeft size={15} />
              <span>Quay lại đăng nhập</span>
            </button>
          </form>
        ) : !isRegisterMode ? (
          <form noValidate onSubmit={handleLoginSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
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
                <button
                  type="button"
                  onClick={openForgotMode}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: '#4f46d8',
                    fontSize: '12px',
                    cursor: 'pointer',
                    padding: 0,
                    fontWeight: 600,
                  }}
                >
                  Quên mật khẩu?
                </button>
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
          <form noValidate onSubmit={handleRegisterSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
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

            <PhoneField id="register-phone" value={regForm.so_dien_thoai} onChange={(value) => setRegForm((prev) => ({ ...prev, so_dien_thoai: value }))} />

            <div className="form-group">
              <label className="form-label" style={{ fontSize: '13px' }}>CV (không bắt buộc)</label>
              <label htmlFor="register-cv" className="btn btn-secondary" style={{ minHeight: 44, justifyContent: 'flex-start', gap: 10, overflow: 'hidden' }}>
                {regCv ? <FileText size={16} /> : <UploadCloud size={16} />}
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{regCv?.name || 'Chọn CV PDF, DOCX hoặc PNG'}</span>
              </label>
              <input id="register-cv" type="file" accept=".pdf,.docx,.png,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png" style={{ display: 'none' }} onChange={(event) => setRegCv(event.target.files?.[0] || null)} />
              <small style={{ color: '#64748b', fontSize: 11 }}>Tối đa 15 MB. Có thể nộp sau khi tài khoản được duyệt.</small>
            </div>

            <div style={{
              background: '#f8fafc',
              padding: '10px 12px',
              borderRadius: '8px',
              border: '1px solid #e2e8f0',
              fontSize: '12px',
              color: '#475569'
            }} className="auth-account-note">
              <div><strong>Vai trò:</strong> Thực tập sinh (Mặc định)</div>
              <div style={{ marginTop: '2px', color: '#64748b' }}>
                Hồ sơ sẽ được gửi duyệt. Sau khi được duyệt, mật khẩu đăng nhập sẽ được gửi về email để bạn đăng nhập và đổi mật khẩu mới.
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

        {/* Chọn nhanh tài khoản test mẫu */}
        {!isRegisterMode && !isForgotMode && (
          <div className="auth-demo-accounts" style={{ marginTop: '20px', paddingTop: '14px', borderTop: '1px solid #f1f5f9' }}>
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
        </section>

        <aside className={`auth-welcome-panel ${isRegisterMode ? 'is-register-mode' : ''}`}>
          <div className="auth-welcome-brand"><Building2 size={18} /> IMS PORTAL</div>
          <div className="auth-welcome-copy">
            <span className="auth-welcome-kicker">HỆ THỐNG QUẢN LÝ THỰC TẬP</span>
            <h2>{isForgotMode ? 'Khôi phục mật khẩu' : isRegisterMode ? 'Bắt đầu hành trình của bạn' : 'Chào mừng trở lại!'}</h2>
            <p>{isForgotMode
              ? 'Hệ thống sẽ cấp lại mật khẩu tạm thời 8 ký tự và gửi qua email để bạn đăng nhập an toàn.'
              : isRegisterMode
                ? 'Tạo tài khoản để theo dõi hồ sơ và cập nhật quá trình thực tập của bạn.'
                : 'Quản lý hồ sơ, chương trình và tiến độ thực tập trên cùng một nền tảng.'}</p>
            <div className="auth-feature-list">
              <span><CheckCircle2 size={17} /> Cấp lại mật khẩu an toàn qua email</span>
              <span><CheckCircle2 size={17} /> Mật khẩu tạm thời rút gọn 8 ký tự</span>
              <span><CheckCircle2 size={17} /> Đổi mật khẩu ngay sau khi đăng nhập</span>
            </div>
          </div>
          <div className="auth-welcome-action">
            <p>{isForgotMode ? 'Đã nhớ lại mật khẩu?' : isRegisterMode ? 'Đã có tài khoản IMS Portal?' : 'Bạn chưa có tài khoản?'}</p>
            <button type="button" className="auth-switch-button" onClick={isForgotMode ? backToLogin : toggleAuthMode}>
              {isForgotMode ? 'Đăng nhập ngay' : isRegisterMode ? 'Đăng nhập' : 'Đăng ký ngay'} <ArrowRight size={16} />
            </button>
          </div>
        </aside>
      </div>
      <div className="auth-mobile-switch">
        <span>{isForgotMode ? 'Đã nhớ lại mật khẩu?' : isRegisterMode ? 'Đã có tài khoản?' : 'Bạn chưa có tài khoản?'}</span>
        <button type="button" onClick={isForgotMode ? backToLogin : toggleAuthMode}>
          {isForgotMode ? 'Đăng nhập' : isRegisterMode ? 'Đăng nhập' : 'Đăng ký ngay'}
        </button>
      </div>
    </main>
  );
}
