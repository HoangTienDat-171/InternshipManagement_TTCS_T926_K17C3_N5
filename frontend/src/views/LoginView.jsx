import React, { useState } from 'react';
import { Lock, Mail, Eye, EyeOff, Building2, AlertCircle, CheckCircle2, ArrowRight, KeyRound, UploadCloud, FileText, Moon, Sun, LogIn, LoaderCircle } from 'lucide-react';
import PhoneField from '../components/PhoneField';
import { isValidVietnamPhone } from '../utils/phone';
import { apiFetch } from '../utils/api';
import './LoginView.css';

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

export default function LoginView({ onLoginSuccess, sessionNotice, theme = 'light', onToggleTheme = () => {} }) {
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
    if (regLoading) return;
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
    <main className="auth-page ims-login-page">
      <div className="auth-background-grid" aria-hidden="true" />
      <button
        type="button"
        className="auth-theme-toggle"
        onClick={onToggleTheme}
        aria-label={theme === 'dark' ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối'}
        title={theme === 'dark' ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối'}
      >
        {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
      </button>

      <section className={`auth-card ims-login-card ${isRegisterMode ? 'is-register-mode' : ''}`}>
        <header className="auth-brand-header">
          <div className="auth-brand-lockup">
            <span className="auth-brand-mark"><Building2 size={22} strokeWidth={2.1} /></span>
            <span className="auth-brand-name">IMS PORTAL</span>
          </div>
          <h1>{isForgotMode ? 'Khôi phục mật khẩu' : isRegisterMode ? 'Tạo tài khoản thực tập sinh' : 'Hệ thống Quản lý Thực tập sinh'}</h1>
          <p>{isForgotMode
            ? 'Khôi phục quyền truy cập vào tài khoản của bạn.'
            : isRegisterMode
              ? 'Đăng ký để bắt đầu hành trình thực tập của bạn.'
              : 'Đăng nhập để quản lý và theo dõi quá trình thực tập của bạn.'}</p>
        </header>

        <div className="auth-form-content">
          {!isForgotMode && !isRegisterMode && sessionNotice && (
            <div className="alert-banner error auth-alert" role="alert">
              <AlertCircle size={17} aria-hidden="true" />
              <span>{sessionNotice}</span>
            </div>
          )}
          {errorMsg && (
            <div className="alert-banner error auth-alert" role="alert">
              <AlertCircle size={17} aria-hidden="true" />
              <span>{errorMsg}</span>
            </div>
          )}
          {regSuccessMsg && (
            <div className="alert-banner success auth-alert" role="status">
              <CheckCircle2 size={17} aria-hidden="true" />
              <span>{regSuccessMsg}</span>
            </div>
          )}
          {forgotSuccessMsg && (
            <div className="alert-banner success auth-alert" role="status">
              <CheckCircle2 size={17} aria-hidden="true" />
              <span>{forgotSuccessMsg}</span>
            </div>
          )}

          {isForgotMode ? (
            <form noValidate onSubmit={handleForgotSubmit} className="auth-form">
              <div className="auth-info-note">
                Nhập email đã đăng ký. Hệ thống sẽ gửi mật khẩu tạm thời để bạn đăng nhập và đổi mật khẩu mới.
              </div>
              <div className="auth-field">
                <label htmlFor="forgot-email" className="form-label">Địa chỉ email</label>
                <div className="auth-input-wrap">
                  <Mail size={18} aria-hidden="true" />
                  <input
                    id="forgot-email"
                    type="email"
                    className="form-control"
                    placeholder="Nhập địa chỉ email"
                    required
                    value={forgotEmail || email}
                    onChange={(event) => {
                      setForgotEmail(event.target.value);
                      setEmail(event.target.value);
                    }}
                    autoComplete="email"
                  />
                </div>
              </div>
              <button type="submit" className="btn btn-primary auth-submit-button" disabled={forgotLoading}>
                {forgotLoading ? <LoaderCircle className="auth-spinner" size={17} /> : <KeyRound size={17} />}
                <span>{forgotLoading ? 'Đang gửi yêu cầu…' : 'Gửi mật khẩu mới'}</span>
              </button>
            </form>
          ) : !isRegisterMode ? (
            <form noValidate onSubmit={handleLoginSubmit} className="auth-form">
              <div className="auth-field">
                <label htmlFor="login-email" className="form-label">Email</label>
                <div className="auth-input-wrap">
                  <Mail size={18} aria-hidden="true" />
                  <input
                    id="login-email"
                    type="email"
                    className="form-control"
                    placeholder="Nhập địa chỉ email"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    autoComplete="username"
                  />
                </div>
              </div>

              <div className="auth-field">
                <div className="auth-label-row">
                  <label htmlFor="login-password" className="form-label">Mật khẩu</label>
                  <button type="button" className="auth-text-button" onClick={openForgotMode}>Quên mật khẩu?</button>
                </div>
                <div className="auth-input-wrap">
                  <Lock size={18} aria-hidden="true" />
                  <input
                    id="login-password"
                    type={showPassword ? 'text' : 'password'}
                    className="form-control"
                    placeholder="Nhập mật khẩu"
                    required
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    className="auth-password-toggle"
                    onClick={() => setShowPassword((visible) => !visible)}
                    aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                    aria-pressed={showPassword}
                    title={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              <button type="submit" className="btn btn-primary auth-submit-button" disabled={loading}>
                {loading ? <LoaderCircle className="auth-spinner" size={17} /> : <LogIn size={17} />}
                <span>{loading ? 'Đang xử lý…' : 'Đăng nhập'}</span>
                {!loading && <ArrowRight size={17} className="auth-submit-arrow" />}
              </button>
            </form>
          ) : (
            <form noValidate onSubmit={handleRegisterSubmit} className="auth-form auth-register-form">
              <div className="auth-field">
                <label htmlFor="register-name" className="form-label">Họ và tên</label>
                <input
                  id="register-name"
                  type="text"
                  className="form-control"
                  placeholder="Nguyễn Văn A"
                  required
                  value={regForm.ho_ten}
                  onChange={(event) => setRegForm({ ...regForm, ho_ten: event.target.value })}
                />
              </div>
              <div className="auth-field">
                <label htmlFor="register-email" className="form-label">Email sinh viên</label>
                <input
                  id="register-email"
                  type="email"
                  className="form-control"
                  placeholder="sinhvien@example.com"
                  required
                  value={regForm.email}
                  onChange={(event) => setRegForm({ ...regForm, email: event.target.value })}
                />
              </div>
              <div className="auth-field auth-phone-field">
                <PhoneField id="register-phone" value={regForm.so_dien_thoai} onChange={(value) => setRegForm((prev) => ({ ...prev, so_dien_thoai: value }))} />
              </div>
              <div className="auth-field">
                <label htmlFor="register-cv" className="form-label">CV <span>(không bắt buộc)</span></label>
                <input
                  id="register-cv"
                  className="auth-file-input"
                  type="file"
                  accept=".pdf,.docx,.png,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png"
                  onChange={(event) => setRegCv(event.target.files?.[0] || null)}
                />
                <label htmlFor="register-cv" className="auth-file-picker">
                  {regCv ? <FileText size={17} /> : <UploadCloud size={17} />}
                  <span>{regCv?.name || 'Chọn CV PDF, DOCX hoặc PNG'}</span>
                </label>
                <small className="auth-helper-text">Tối đa 15 MB. Có thể nộp sau khi tài khoản được duyệt.</small>
              </div>
              <div className="auth-account-note">
                <strong>Vai trò mặc định: Thực tập sinh</strong>
                <span>Hồ sơ sẽ được gửi duyệt. Sau khi được duyệt, mật khẩu đăng nhập sẽ được gửi về email.</span>
              </div>
              <button type="submit" className="btn btn-primary auth-submit-button" disabled={regLoading}>
                {regLoading ? <LoaderCircle className="auth-spinner" size={17} /> : <ArrowRight size={17} />}
                <span>{regLoading ? 'Đang gửi thông tin…' : 'Đăng ký tài khoản'}</span>
              </button>
            </form>
          )}

          {import.meta.env.DEV && !isRegisterMode && !isForgotMode && (
            <div className="auth-demo-accounts">
              <div className="auth-demo-heading">Tài khoản demo <span>Chọn để điền nhanh</span></div>
              <div className="auth-demo-buttons">
                <button type="button" className="btn btn-secondary" onClick={() => handleQuickLogin('admin@internship.vn', '123456')}>Admin</button>
                <button type="button" className="btn btn-secondary" onClick={() => handleQuickLogin('hr@internship.vn', '123456')}>Quản lý</button>
                <button type="button" className="btn btn-secondary" onClick={() => handleQuickLogin('mentor@internship.vn', '123456')}>Mentor</button>
                <button type="button" className="btn btn-secondary" onClick={() => handleQuickLogin('tuan.lm@internship.vn', '123456')}>TTS</button>
              </div>
            </div>
          )}

          <footer className="auth-form-footer">
            <span>{isForgotMode ? 'Đã nhớ lại mật khẩu?' : isRegisterMode ? 'Đã có tài khoản IMS Portal?' : 'Chưa có tài khoản?'}</span>
            <button type="button" className="auth-text-button" onClick={isForgotMode ? backToLogin : toggleAuthMode}>
              {isForgotMode ? 'Quay lại đăng nhập' : isRegisterMode ? 'Đăng nhập' : 'Đăng ký ngay'}
            </button>
          </footer>
        </div>
      </section>
    </main>
  );
}
