import React from 'react';
import { User, LogIn, LogOut, Shield, Briefcase, GraduationCap, Users } from 'lucide-react';

export default function Navbar({ 
  currentUser, 
  onLogout, 
  onSwitchRole 
}) {
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
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div className={`badge ${roleInfo?.class}`} style={{ gap: '6px' }}>
              {roleInfo?.icon}
              <span>{currentUser.ho_ten}</span>
            </div>
            <button 
              className="btn btn-secondary btn-sm" 
              onClick={onLogout}
              title="Đăng xuất khỏi hệ thống"
            >
              <LogOut size={14} />
              <span>Đăng xuất</span>
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
