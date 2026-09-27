import React, { useCallback, useEffect, useState } from 'react';
import { User, LogOut, Shield, Briefcase, GraduationCap, Users, Settings, KeyRound, ChevronDown, Bell } from 'lucide-react';
import { apiFetch } from '../utils/api';

export default function Navbar({ 
  currentUser, 
  onLogout, 
  onOpenAccount
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [notificationsError, setNotificationsError] = useState('');
  const userId = currentUser?.ma_nguoi_dung;

  const loadNotifications = useCallback(async () => {
    if (!userId) return;
    setNotificationsLoading(true);
    setNotificationsError('');
    try {
      const response = await apiFetch('/api/notifications');
      if (!response.ok) throw new Error('Không tải được thông báo.');
      setNotifications(await response.json());
    } catch (error) {
      setNotificationsError(error.message || 'Không tải được thông báo.');
    } finally {
      setNotificationsLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => loadNotifications(), 0);
    const refreshTimer = window.setInterval(loadNotifications, 60000);
    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(refreshTimer);
    };
  }, [loadNotifications]);

  const markNotificationRead = async (notificationId) => {
    try {
      const response = await apiFetch(`/api/notifications/${notificationId}/read`, { method: 'PUT' });
      if (!response.ok) throw new Error('Không thể cập nhật thông báo.');
      setNotifications((items) => items.map((item) => item.ma_thong_bao === notificationId ? { ...item, da_doc: 1 } : item));
    } catch (error) {
      setNotificationsError(error.message || 'Không thể cập nhật thông báo.');
    }
  };

  const formatNotificationDate = (value) => {
    if (!value) return '';
    const normalized = value.includes('T') ? value : value.replace(' ', 'T');
    const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(normalized) ? normalized : `${normalized}Z`);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString('vi-VN');
  };

  const unreadCount = notifications.filter((item) => !item.da_doc).length;
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
        {currentUser && (
          <div className="notification-menu-wrap">
            <button type="button" className="notification-trigger" aria-label="Thông báo" aria-expanded={notificationsOpen} onClick={() => { setNotificationsOpen((open) => !open); setMenuOpen(false); if (!notificationsOpen) loadNotifications(); }}>
              <Bell size={19} />
              {unreadCount > 0 && <span className="notification-count">{unreadCount > 99 ? '99+' : unreadCount}</span>}
            </button>
            {notificationsOpen && <>
              <button className="notification-dismiss" aria-label="Đóng thông báo" onClick={() => setNotificationsOpen(false)} />
              <section className="notification-panel" aria-label="Danh sách thông báo">
                <div className="notification-panel-heading"><strong>Thông báo</strong><button type="button" onClick={loadNotifications}>Làm mới</button></div>
                {notificationsError && <p className="notification-message notification-error">{notificationsError}</p>}
                {notificationsLoading && notifications.length === 0 ? <p className="notification-message">Đang tải thông báo…</p> : notifications.length === 0 ? <p className="notification-message">Bạn chưa có thông báo.</p> : (
                  <div className="notification-list">
                    {notifications.map((item) => (
                      <button type="button" key={item.ma_thong_bao} className={`notification-item${item.da_doc ? '' : ' unread'}`} onClick={() => item.da_doc ? null : markNotificationRead(item.ma_thong_bao)}>
                        <span className="notification-item-title">{item.tieu_de}</span>
                        <span>{item.noi_dung}</span>
                        <small>{formatNotificationDate(item.thoi_gian_gui)}</small>
                      </button>
                    ))}
                  </div>
                )}
              </section>
            </>}
          </div>
        )}
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
