import React, { useState } from 'react';
import { User, LogOut, Shield, Briefcase, GraduationCap, Users, Settings, KeyRound, ChevronDown } from 'lucide-react';

export default function Navbar({ 
  currentUser, 
  onLogout, 
  onSwitchRole,
  onOpenAccount
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const getRoleBadge = (role) => {
    switch (role) {
      case 'Admin':
        return { label: 'Admin', icon: <Shield size={13} />, class: 'badge-danger' };
      case 'HR':
        return { label: 'Quản lý TTS', icon: <Briefcase size={13} />, class: 'badge-info' };
      case 'Mentor':
        return { label: 'Mentor', icon: <Users size={13} />, class: 'badge-warning' };
      case 'ThucTapSinh':
        return { label: 'Thực tập sinh', icon: <GraduationCap size={13} />, class: 'badge-success' };
      default:
        return { label: role, icon: <User size={13} />, class: 'badge-info' };
    }
  };

  const roleInfo = currentUser ? getRoleBadge(currentUser.vai_tro) : null;

  return (
    <header className="top-navbar">
      <div className="navbar-title-group">
        <h2 className="navbar-title" style={{ fontSize: '17px', fontWeight: 700 }}>
          Hệ thống Quản lý Thực tập sinh
        </h2>
      </div>

      <div className="navbar-actions">
        {/* Vai trò */}
        <div className="role-switcher" title="Chuyển đổi góc nhìn vai trò">
          <span className="role-switcher-label">Vai trò:</span>
          <select 
            className="role-select"
            value={currentUser?.vai_tro || 'HR'}
            onChange={(e) => onSwitchRole(e.target.value)}
          >
            <option value="Admin">Admin</option>
            <option value="HR">Quản lý thực tập sinh</option>
            <option value="Mentor">Mentor</option>
            <option value="ThucTapSinh">Thực tập sinh</option>
          </select>
        </div>

        {currentUser && (
          <div className="account-menu-wrap">
            <button type="button" className="account-menu-trigger" aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}>
              <span className="user-avatar account-menu-avatar">{currentUser.ho_ten?.charAt(0)?.toUpperCase() || 'U'}</span>
              <span className="account-menu-copy"><strong>{currentUser.ho_ten}</strong><small>{roleInfo?.label}</small></span>
              <ChevronDown size={15} />
            </button>
            {menuOpen && <>
              <button className="account-menu-dismiss" aria-label="Đóng menu" onClick={() => setMenuOpen(false)} />
              <div className="account-menu-panel">
                <div className="account-menu-heading"><strong>{currentUser.ho_ten}</strong><span>{currentUser.email}</span></div>
                <button type="button" onClick={() => { onOpenAccount('profile'); setMenuOpen(false); }}><User size={16} /> Tài khoản</button>
                <button type="button" onClick={() => { onOpenAccount('settings'); setMenuOpen(false); }}><Settings size={16} /> Cài đặt</button>
                <button type="button" onClick={() => { onOpenAccount('password'); setMenuOpen(false); }}><KeyRound size={16} /> Cập nhật mật khẩu</button>
                <div className="account-menu-divider" />
                <button type="button" className="account-menu-logout" onClick={onLogout}><LogOut size={16} /> Đăng xuất</button>
              </div>
            </>}
          </div>
        )}
      </div>
    </header>
  );
}
