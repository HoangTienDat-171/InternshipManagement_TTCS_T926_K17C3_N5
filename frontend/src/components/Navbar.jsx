import React, { useCallback, useEffect, useState } from 'react';
import { User, LogOut, Shield, Briefcase, FileText, GraduationCap, Users, KeyRound, ChevronDown, Bell, BellRing, Check, ExternalLink, Inbox, Menu, Moon, RefreshCw, Sun, Wallet } from 'lucide-react';
import { apiFetch } from '../utils/api';

export default function Navbar({
  currentUser,
  activeTab,
  onLogout,
  onOpenAccount,
  onToggleSidebar,
  sidebarOpen = false,
  theme = 'light',
  onToggleTheme,
  onOpenNotificationReference
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

  const openNotification = async (item) => {
    if (!item.da_doc) await markNotificationRead(item.ma_thong_bao);
    if (item.reference_type && item.reference_id) onOpenNotificationReference?.(item);
    setNotificationsOpen(false);
  };

  const notificationMeta = (item) => {
    if (item.loai === 'TASK_ASSIGNED') return { label: 'Nhiệm vụ', icon: <Briefcase size={15} /> };
    if (item.loai === 'WEEKLY_REPORT_SUBMITTED') return { label: 'Báo cáo tuần', icon: <FileText size={15} /> };
    if (item.loai === 'WEEKLY_REPORT_REVIEWED') return { label: 'Nhận xét', icon: <FileText size={15} /> };
    if (item.loai === 'internship_review_result') return { label: 'Hồ sơ', icon: <GraduationCap size={15} /> };
    if (item.loai === 'allowance_unreceived_report') return { label: 'Phụ cấp', icon: <Wallet size={15} /> };
    return { label: 'Hệ thống', icon: <BellRing size={15} /> };
  };

  const formatNotificationDate = (value) => {
    if (!value) return '';
    const normalized = value.includes('T') ? value : value.replace(' ', 'T');
    // MySQL DATETIME values have no timezone; parse them as local wall-clock time.
    // Appending Z here incorrectly shifted local database timestamps by UTC+7.
    const date = new Date(normalized);
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

  const getTabLabel = (tab, role) => {
    const isIntern = role === 'ThucTapSinh';
    const canManage = ['Admin', 'HR'].includes(role);
    switch (tab) {
      case 'allowances': return isIntern ? 'Lịch sử phụ cấp' : 'Quản lý phụ cấp';
      case 'interns': return 'Quản lý Thực tập sinh';
      case 'mentors': return 'Quản lý Mentor';
      case 'programs': return canManage ? 'Chương trình thực tập' : 'Chương trình đang mở';
      case 'documents': return 'Quản lý Tài liệu';
      case 'work-shifts': return 'Quản lý ca làm việc';
      case 'leave-requests': return isIntern ? 'Đăng ký nghỉ phép' : 'Quản lý nghỉ phép';
      case 'intern-dashboard': return 'Tổng quan thực tập';
      case 'intern-schedule': return 'Lịch thực tập';
      case 'intern-attendance': return 'Chấm công hôm nay';
      case 'mentor-workspace': return 'Nhóm thực tập sinh';
      case 'tasks': return isIntern ? 'Nhiệm vụ của tôi' : 'Nhiệm vụ thực tập';
      case 'weekly-reports': return 'Báo cáo tuần';
      case 'evaluations': return 'Đánh giá thực tập sinh';
      case 'my-evaluations': return 'Đánh giá của tôi';
      case 'accounts': return 'Quản trị Người dùng';
      case 'profile': return 'Tài khoản cá nhân';
      default: return 'Quản lý phụ cấp';
    }
  };

  const roleInfo = currentUser ? getRoleBadge(currentUser.vai_tro) : null;
  const currentTabLabel = getTabLabel(activeTab, currentUser?.vai_tro);

  return (
    <header className="top-navbar">
      <div className="navbar-title-group">
        <button
          type="button"
          className="navigation-toggle"
          aria-label={sidebarOpen ? 'Thu gọn danh mục' : 'Mở danh mục'}
          aria-expanded={sidebarOpen}
          aria-controls="app-navigation"
          onClick={onToggleSidebar}
        >
          <Menu size={20} />
        </button>
        <div className="navbar-heading-container">
          <nav className="navbar-breadcrumb" aria-label="Đường dẫn nhanh">
            <span className="breadcrumb-root">Trang chủ</span>
            <span className="breadcrumb-separator" aria-hidden="true">/</span>
            <span className="breadcrumb-current">{currentTabLabel}</span>
          </nav>
          <h2 className="navbar-title">
            Hệ thống Quản lý Thực tập sinh
          </h2>
        </div>
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
                <div className="notification-panel-heading">
                  <div><span className="notification-panel-icon"><BellRing size={18} /></span><div><strong>Thông báo</strong><small>{unreadCount ? `${unreadCount} thông báo chưa đọc` : 'Bạn đã xem tất cả thông báo'}</small></div></div>
                  <button type="button" className="notification-refresh" onClick={loadNotifications} disabled={notificationsLoading}><RefreshCw size={14} className={notificationsLoading ? 'animate-spin' : ''} />Làm mới</button>
                </div>
                {notificationsError && <p className="notification-message notification-error">{notificationsError}</p>}
                {notificationsLoading && notifications.length === 0 ? <p className="notification-message">Đang tải thông báo…</p> : notifications.length === 0 ? <div className="notification-empty"><span><Inbox size={22} /></span><strong>Chưa có thông báo</strong><small>Các cập nhật mới sẽ xuất hiện tại đây.</small></div> : (
                  <div className="notification-list">
                    {notifications.map((item) => {
                      const meta = notificationMeta(item);
                      const navigable = ['internship_task', 'weekly_report', 'allowance'].includes(item.reference_type) && item.reference_id;
                      return <article key={item.ma_thong_bao} className={`notification-item${item.da_doc ? '' : ' unread'}`}>
                        <button type="button" className="notification-item-main" onClick={() => openNotification(item)}>
                          <span className="notification-type-icon">{meta.icon}</span>
                          <span className="notification-item-copy"><span className="notification-item-topline"><strong>{item.tieu_de}</strong><em>{meta.label}</em></span><span>{item.noi_dung}</span><small>{formatNotificationDate(item.thoi_gian_gui)}</small></span>
                          {navigable && <ExternalLink className="notification-reference-icon" size={14} aria-label="Mở chi tiết" />}
                        </button>
                        {!item.da_doc && <button type="button" className="notification-read-action" onClick={() => markNotificationRead(item.ma_thong_bao)}><Check size={13} />Đánh dấu đã đọc</button>}
                      </article>;
                    })}
                  </div>
                )}
                {notifications.length > 0 && <footer className="notification-panel-footer">Hiển thị {notifications.length} thông báo gần nhất</footer>}
              </section>
            </>}
          </div>
        )}
        <button
          type="button"
          className="theme-toggle"
          aria-label={theme === 'dark' ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối'}
          aria-pressed={theme === 'dark'}
          title={theme === 'dark' ? 'Giao diện tối' : 'Giao diện sáng'}
          onClick={onToggleTheme}
        >
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </button>
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
