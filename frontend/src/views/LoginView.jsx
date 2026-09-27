import React, { useState } from 'react';
import { Lock, Mail, Eye, EyeOff, Building2, AlertCircle, CheckCircle2, ArrowRight, UploadCloud, FileText } from 'lucide-react';
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
    if (response.status >= 500) {
      throw new Error('Máy chủ đăng nhập không khả dụng. Hãy kiểm tra backend FastAPI tại cổng 8000.');
    }
    throw new Error(data.detail || 'Không thể xử lý yêu cầu. Vui lòng thử lại.');
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

  // Register Form State
  const [regForm, setRegForm] = useState({
    ho_ten: '',
    email: '',
    mat_khau: '',
    so_dien_thoai: ''
  });
  const [regLoading, setRegLoading] = useState(false);
  const [regSuccessMsg, setRegSuccessMsg] = useState('');
  const [regCv, setRegCv] = useState(null);

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
    if (regCv && (regCv.size > 15 * 1024 * 1024 || !['pdf', 'docx', 'png'].includes(regCv.name.split('.').pop()?.toLowerCase()))) {
      setErrorMsg('CV phải có định dạng PDF, DOCX hoặc PNG và dung lượng tối đa 15 MB.');
      setRegLoading(false);
      return;
    }

    try {
      const payload = new FormData();
      payload.append('ho_ten', regForm.ho_ten.trim());
      payload.append('email', regForm.email.trim());
      payload.append('mat_khau', regForm.mat_khau);
      payload.append('so_dien_thoai', regForm.so_dien_thoai.trim());
      if (regCv) payload.append('cv', regCv);

      const res = await apiFetch('/api/auth/register-with-cv', {
        method: 'POST',
        body: payload
      });

      const data = await readApiResponse(res);

      setRegSuccessMsg(data.message || 'Đăng ký thành công. Tài khoản đang chờ Admin/HR xét duyệt.');
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

  const toggleAuthMode = () => {
    setIsRegisterMode((mode) => !mode);
    setErrorMsg('');
    setRegSuccessMsg('');
  };

  return (
    <main className="auth-page">
      <div className={`auth-card ${isRegisterMode ? 'register-mode' : ''}`}>
        <section className="auth-form-panel">
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
            {isRegisterMode ? 'Đăng ký tài khoản Thực tập sinh' : 'Đăng nhập để vào hệ thống làm việc'}
          </p>
        </div>

        {/* Thông báo lỗi / thành công */}
        {sessionNotice && (
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

        {/* Chọn nhanh tài khoản test mẫu */}
        {!isRegisterMode && (
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
        </section>

        <aside className={`auth-welcome-panel ${isRegisterMode ? 'is-register-mode' : ''}`}>
          <div className="auth-welcome-brand"><Building2 size={18} /> IMS PORTAL</div>
          <div className="auth-welcome-copy">
            <span className="auth-welcome-kicker">HỆ THỐNG QUẢN LÝ THỰC TẬP</span>
            <h2>{isRegisterMode ? 'Bắt đầu hành trình của bạn' : 'Chào mừng trở lại!'}</h2>
            <p>{isRegisterMode
              ? 'Tạo tài khoản để theo dõi hồ sơ và cập nhật quá trình thực tập của bạn.'
              : 'Quản lý hồ sơ, chương trình và tiến độ thực tập trên cùng một nền tảng.'}</p>
            <div className="auth-feature-list">
              <span><CheckCircle2 size={17} /> Theo dõi tiến độ rõ ràng</span>
              <span><CheckCircle2 size={17} /> Cập nhật thông tin tập trung</span>
              <span><CheckCircle2 size={17} /> Kết nối thực tập sinh và mentor</span>
            </div>
          </div>
          <div className="auth-welcome-action">
            <p>{isRegisterMode ? 'Đã có tài khoản IMS Portal?' : 'Bạn chưa có tài khoản?'}</p>
            <button type="button" className="auth-switch-button" onClick={toggleAuthMode}>
              {isRegisterMode ? 'Đăng nhập' : 'Đăng ký ngay'} <ArrowRight size={16} />
            </button>
          </div>
        </aside>
      </div>
      <div className="auth-mobile-switch">
        <span>{isRegisterMode ? 'Đã có tài khoản?' : 'Bạn chưa có tài khoản?'}</span>
        <button type="button" onClick={toggleAuthMode}>{isRegisterMode ? 'Đăng nhập' : 'Đăng ký ngay'}</button>
      </div>
    </main>
  );
}
