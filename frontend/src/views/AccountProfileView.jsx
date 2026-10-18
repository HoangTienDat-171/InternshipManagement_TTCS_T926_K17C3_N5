import React, { useState } from 'react';
import { UserRound, KeyRound, Save, ShieldCheck, Mail, Building2, Eye, EyeOff } from 'lucide-react';
import PhoneField from '../components/PhoneField';
import { isValidVietnamPhone } from '../utils/phone';
import { apiFetch } from '../utils/api';

export default function AccountProfileView({ currentUser, initialSection = 'profile', forcePasswordChange = false, onUserUpdated, onShowToast }) {
  const [section, setSection] = useState(forcePasswordChange || initialSection === 'password' ? 'password' : 'profile');
  const [profile, setProfile] = useState({ ho_ten: currentUser.ho_ten || '', so_dien_thoai: currentUser.so_dien_thoai || '' });
  const [saving, setSaving] = useState(false);
  const [password, setPassword] = useState({ mat_khau_hien_tai: '', mat_khau_moi: '', xac_nhan: '' });
  const [showPassword, setShowPassword] = useState({ current: false, next: false, confirm: false });
  const allSections = [
    { id: 'profile', label: 'Tài khoản', icon: <UserRound size={17} /> },
    { id: 'password', label: 'Cập nhật mật khẩu', icon: <KeyRound size={17} /> }
  ];
  const sections = forcePasswordChange ? allSections.filter((item) => item.id === 'password') : allSections;

  const saveProfile = async (event) => {
    event.preventDefault();
    if (!profile.ho_ten.trim()) return onShowToast('Vui lòng nhập họ và tên.', 'error');
    if (profile.so_dien_thoai && !isValidVietnamPhone(profile.so_dien_thoai)) return onShowToast('Số điện thoại chưa đúng định dạng Việt Nam.', 'error');
    setSaving(true);
    try {
      const response = await apiFetch(`/api/auth/users/${currentUser.ma_nguoi_dung}/profile`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profile)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Không thể cập nhật thông tin.');
      const updatedUser = { ...currentUser, ...profile };
      localStorage.setItem('ims_user', JSON.stringify(updatedUser));
      onUserUpdated(updatedUser);
      onShowToast(data.message || 'Đã cập nhật thông tin tài khoản.');
    } catch (error) { onShowToast(error.message, 'error'); }
    finally { setSaving(false); }
  };

  const changePassword = async (event) => {
    event.preventDefault();
    if (!password.mat_khau_hien_tai) return onShowToast('Vui lòng nhập mật khẩu hiện tại.', 'error');
    if (password.mat_khau_moi.length < 6) return onShowToast('Mật khẩu mới cần ít nhất 6 ký tự.', 'error');
    if (password.mat_khau_moi !== password.xac_nhan) return onShowToast('Mật khẩu xác nhận không khớp.', 'error');
    setSaving(true);
    try {
      const response = await apiFetch(`/api/auth/users/${currentUser.ma_nguoi_dung}/password`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mat_khau_hien_tai: password.mat_khau_hien_tai, mat_khau_moi: password.mat_khau_moi })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Không thể đổi mật khẩu.');
      setPassword({ mat_khau_hien_tai: '', mat_khau_moi: '', xac_nhan: '' });
      onUserUpdated({ ...currentUser, must_change_password: false });
      onShowToast(data.message || 'Đã đổi mật khẩu.');
    } catch (error) { onShowToast(error.message, 'error'); }
    finally { setSaving(false); }
  };

  return (
    <div className="account-page">
      <div className="page-heading"><div><h2>{forcePasswordChange ? 'Đổi mật khẩu lần đầu' : 'Thông tin tài khoản'}</h2><p>{forcePasswordChange ? 'Bạn đang dùng mật khẩu tạm. Hãy đặt mật khẩu mới để tiếp tục sử dụng hệ thống.' : 'Quản lý thông tin cá nhân và mật khẩu.'}</p></div></div>
      <div className="account-layout">
        <aside className="account-nav-card">
          <div className="account-identity"><span className="user-avatar">{currentUser.ho_ten?.charAt(0)?.toUpperCase() || 'U'}</span><div><strong>{currentUser.ho_ten}</strong><small>{currentUser.email}</small></div></div>
          <nav aria-label="Quản lý tài khoản">{sections.map((item) => <button key={item.id} className={section === item.id ? 'active' : ''} onClick={() => setSection(item.id)}>{item.icon}{item.label}</button>)}</nav>
        </aside>
        <section className="account-content-card">
          <header className="account-content-header"><div><h3>{sections.find((item) => item.id === section)?.label}</h3><p>{section === 'profile' ? 'Thông tin được dùng trong hồ sơ của bạn.' : 'Đặt mật khẩu mới để bảo vệ tài khoản.'}</p></div></header>
          {forcePasswordChange && <div className="password-reset-notice"><KeyRound size={17} /><span>Hãy đặt mật khẩu mới trước khi tiếp tục. Nếu bạn đang dùng mật khẩu tạm do Admin cấp, mật khẩu này chỉ đăng nhập được một lần và hết hạn sau 30 phút; hãy liên hệ Admin nếu mật khẩu đã hết hạn.</span></div>}
          {!forcePasswordChange && section === 'profile' && <form className="account-profile-form" noValidate onSubmit={saveProfile}>
            <div className="account-avatar-large">{currentUser.ho_ten?.charAt(0)?.toUpperCase() || 'U'}</div>
            <div className="account-profile-grid">
              <label className="form-group"><span className="form-label">Tên tài khoản</span><input className="form-control is-readonly" value={currentUser.email?.split('@')[0] || ''} readOnly /></label>
              <label className="form-group"><span className="form-label">Tên hiển thị <span className="required">*</span></span><input className="form-control" value={profile.ho_ten} required onChange={(event) => setProfile((old) => ({ ...old, ho_ten: event.target.value }))} /></label>
              <label className="form-group"><span className="form-label">Email</span><span className="account-readonly-value"><Mail size={15} />{currentUser.email}</span></label>
              <PhoneField id="profile-phone" value={profile.so_dien_thoai} onChange={(value) => setProfile((old) => ({ ...old, so_dien_thoai: value }))} required />
              <div className="account-meta"><ShieldCheck size={16} /><span>Vai trò: <strong>{currentUser.vai_tro === 'HR' ? 'Quản lý thực tập sinh' : currentUser.vai_tro}</strong></span></div>
              <div className="account-meta"><Building2 size={16} /><span>Phòng ban: <strong>{currentUser.ten_phong_ban || 'Chưa phân phòng ban'}</strong></span></div>
            </div>
            <footer className="account-form-footer"><button className="btn btn-primary" disabled={saving}><Save size={16} />{saving ? 'Đang lưu...' : 'Lưu thay đổi'}</button></footer>
          </form>}
          {section === 'password' && <form className="password-form" noValidate onSubmit={changePassword}>
            <div className="form-group">
              <label className="form-label" htmlFor="current-password">Mật khẩu hiện tại <span className="required">*</span></label>
              <div className="password-input-control">
                <input id="current-password" className="form-control" type={showPassword.current ? 'text' : 'password'} autoComplete="current-password" required value={password.mat_khau_hien_tai} onChange={(event) => setPassword((old) => ({ ...old, mat_khau_hien_tai: event.target.value }))} />
                <button type="button" className="password-visibility-toggle" aria-label={showPassword.current ? 'Ẩn mật khẩu hiện tại' : 'Hiện mật khẩu hiện tại'} aria-pressed={showPassword.current} onClick={() => setShowPassword((old) => ({ ...old, current: !old.current }))}>{showPassword.current ? <EyeOff size={17} /> : <Eye size={17} />}</button>
              </div>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="new-password">Mật khẩu mới <span className="required">*</span></label>
              <div className="password-input-control">
                <input id="new-password" className="form-control" type={showPassword.next ? 'text' : 'password'} autoComplete="new-password" minLength={6} required value={password.mat_khau_moi} onChange={(event) => setPassword((old) => ({ ...old, mat_khau_moi: event.target.value }))} />
                <button type="button" className="password-visibility-toggle" aria-label={showPassword.next ? 'Ẩn mật khẩu mới' : 'Hiện mật khẩu mới'} aria-pressed={showPassword.next} onClick={() => setShowPassword((old) => ({ ...old, next: !old.next }))}>{showPassword.next ? <EyeOff size={17} /> : <Eye size={17} />}</button>
              </div>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="confirm-password">Xác nhận mật khẩu mới <span className="required">*</span></label>
              <div className="password-input-control">
                <input id="confirm-password" className="form-control" type={showPassword.confirm ? 'text' : 'password'} autoComplete="new-password" minLength={6} required value={password.xac_nhan} onChange={(event) => setPassword((old) => ({ ...old, xac_nhan: event.target.value }))} />
                <button type="button" className="password-visibility-toggle" aria-label={showPassword.confirm ? 'Ẩn xác nhận mật khẩu' : 'Hiện xác nhận mật khẩu'} aria-pressed={showPassword.confirm} onClick={() => setShowPassword((old) => ({ ...old, confirm: !old.confirm }))}>{showPassword.confirm ? <EyeOff size={17} /> : <Eye size={17} />}</button>
              </div>
            </div>
            <footer className="account-form-footer"><button className="btn btn-primary" disabled={saving}><KeyRound size={16} />{saving ? 'Đang cập nhật...' : 'Cập nhật mật khẩu'}</button></footer>
          </form>}
        </section>
      </div>
    </div>
  );
}
