import React, { useState } from 'react';
import { UserRound, Settings, KeyRound, Save, Bell, ShieldCheck, Mail, Building2 } from 'lucide-react';
import PhoneField from '../components/PhoneField';
import { isValidVietnamPhone } from '../utils/phone';

export default function AccountProfileView({ currentUser, initialSection = 'profile', onUserUpdated, onShowToast }) {
  const [section, setSection] = useState(initialSection);
  const [profile, setProfile] = useState({ ho_ten: currentUser.ho_ten || '', so_dien_thoai: currentUser.so_dien_thoai || '' });
  const [saving, setSaving] = useState(false);
  const [password, setPassword] = useState({ mat_khau_hien_tai: '', mat_khau_moi: '', xac_nhan: '' });
  const [preferences, setPreferences] = useState(() => {
    try { return JSON.parse(localStorage.getItem('ims_preferences')) || { notifications: true, compact: false }; }
    catch { return { notifications: true, compact: false }; }
  });
  const sections = [
    { id: 'profile', label: 'Tài khoản', icon: <UserRound size={17} /> },
    { id: 'settings', label: 'Cài đặt', icon: <Settings size={17} /> },
    { id: 'password', label: 'Cập nhật mật khẩu', icon: <KeyRound size={17} /> }
  ];

  const saveProfile = async (event) => {
    event.preventDefault();
    if (!profile.ho_ten.trim()) return onShowToast('Vui lòng nhập họ và tên.', 'error');
    if (profile.so_dien_thoai && !isValidVietnamPhone(profile.so_dien_thoai)) return onShowToast('Số điện thoại chưa đúng định dạng Việt Nam.', 'error');
    setSaving(true);
    try {
      const response = await fetch(`/api/auth/users/${currentUser.ma_nguoi_dung}/profile`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json', 'x-user-id': String(currentUser.ma_nguoi_dung) },
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
    if (password.mat_khau_moi.length < 6) return onShowToast('Mật khẩu mới cần ít nhất 6 ký tự.', 'error');
    if (password.mat_khau_moi !== password.xac_nhan) return onShowToast('Mật khẩu xác nhận không khớp.', 'error');
    setSaving(true);
    try {
      const response = await fetch(`/api/auth/users/${currentUser.ma_nguoi_dung}/password`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json', 'x-user-id': String(currentUser.ma_nguoi_dung) },
        body: JSON.stringify({ mat_khau_hien_tai: password.mat_khau_hien_tai, mat_khau_moi: password.mat_khau_moi })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Không thể đổi mật khẩu.');
      setPassword({ mat_khau_hien_tai: '', mat_khau_moi: '', xac_nhan: '' });
      onShowToast(data.message || 'Đã đổi mật khẩu.');
    } catch (error) { onShowToast(error.message, 'error'); }
    finally { setSaving(false); }
  };

  const updatePreference = (key) => setPreferences((previous) => {
    const next = { ...previous, [key]: !previous[key] };
    localStorage.setItem('ims_preferences', JSON.stringify(next));
    return next;
  });

  return (
    <div className="account-page">
      <div className="page-heading"><div><h2>Thông tin tài khoản</h2><p>Quản lý thông tin cá nhân và tùy chọn sử dụng hệ thống.</p></div></div>
      <div className="account-layout">
        <aside className="account-nav-card">
          <div className="account-identity"><span className="user-avatar">{currentUser.ho_ten?.charAt(0)?.toUpperCase() || 'U'}</span><div><strong>{currentUser.ho_ten}</strong><small>{currentUser.email}</small></div></div>
          <nav aria-label="Cài đặt tài khoản">{sections.map((item) => <button key={item.id} className={section === item.id ? 'active' : ''} onClick={() => setSection(item.id)}>{item.icon}{item.label}</button>)}</nav>
        </aside>
        <section className="account-content-card">
          <header className="account-content-header"><div><h3>{sections.find((item) => item.id === section)?.label}</h3><p>{section === 'profile' ? 'Thông tin được dùng trong hồ sơ của bạn.' : section === 'settings' ? 'Tùy chỉnh trải nghiệm sử dụng IMS Portal.' : 'Đặt mật khẩu mới để bảo vệ tài khoản.'}</p></div></header>
          {section === 'profile' && <form className="account-profile-form" onSubmit={saveProfile}>
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
          {section === 'settings' && <div className="account-settings-list">
            <button className="setting-row" onClick={() => updatePreference('notifications')}><span className="setting-icon"><Bell size={17} /></span><span><strong>Thông báo trong hệ thống</strong><small>Hiển thị thông báo khi có cập nhật mới.</small></span><span className={`toggle-switch${preferences.notifications ? ' checked' : ''}`} aria-label={preferences.notifications ? 'Đang bật' : 'Đang tắt'} /></button>
            <button className="setting-row" onClick={() => updatePreference('compact')}><span className="setting-icon"><Settings size={17} /></span><span><strong>Giao diện gọn</strong><small>Giảm khoảng cách giữa các mục trong danh sách.</small></span><span className={`toggle-switch${preferences.compact ? ' checked' : ''}`} aria-label={preferences.compact ? 'Đang bật' : 'Đang tắt'} /></button>
            <p className="settings-note">Tùy chọn được lưu trên thiết bị này.</p>
          </div>}
          {section === 'password' && <form className="password-form" onSubmit={changePassword}>
            <label className="form-group"><span className="form-label">Mật khẩu hiện tại <span className="required">*</span></span><input className="form-control" type="password" autoComplete="current-password" required value={password.mat_khau_hien_tai} onChange={(event) => setPassword((old) => ({ ...old, mat_khau_hien_tai: event.target.value }))} /></label>
            <label className="form-group"><span className="form-label">Mật khẩu mới <span className="required">*</span></span><input className="form-control" type="password" autoComplete="new-password" minLength={6} required value={password.mat_khau_moi} onChange={(event) => setPassword((old) => ({ ...old, mat_khau_moi: event.target.value }))} /></label>
            <label className="form-group"><span className="form-label">Xác nhận mật khẩu mới <span className="required">*</span></span><input className="form-control" type="password" autoComplete="new-password" minLength={6} required value={password.xac_nhan} onChange={(event) => setPassword((old) => ({ ...old, xac_nhan: event.target.value }))} /></label>
            <footer className="account-form-footer"><button className="btn btn-primary" disabled={saving}><KeyRound size={16} />{saving ? 'Đang cập nhật...' : 'Cập nhật mật khẩu'}</button></footer>
          </form>}
        </section>
      </div>
    </div>
  );
}
