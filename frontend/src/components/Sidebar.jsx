import React from 'react';
import { 
  UserCheck, 
  Calendar, 
  CalendarDays,
  Award,
  FolderUp, 
  ShieldCheck, 
  Building2,
  GraduationCap,
  LayoutDashboard,
  UsersRound,
  ClipboardList,
  FileText,
  Clock3,
  ClipboardCheck,
  LogOut,
  X,
  Wallet
} from 'lucide-react';

export default function Sidebar({ activeTab, onTabChange, currentUser, onLogout, isOpen = false, isCollapsed = false, onClose }) {
  const isAdmin = currentUser?.vai_tro === 'Admin';
  const canManage = isAdmin || currentUser?.vai_tro === 'HR';
  const canViewPrograms = canManage || currentUser?.vai_tro === 'ThucTapSinh';
  const isIntern = currentUser?.vai_tro === 'ThucTapSinh';
  const isMentor = currentUser?.vai_tro === 'Mentor';

  const navItems = [
    ...(isIntern ? [{ id: 'intern-dashboard', label: 'Tổng quan thực tập', icon: <LayoutDashboard size={18} /> }] : []),
    ...(isIntern ? [{ id: 'intern-schedule', label: 'Lịch thực tập', icon: <CalendarDays size={18} /> }] : []),
    ...(isIntern ? [{ id: 'intern-attendance', label: 'Chấm công hôm nay', icon: <ClipboardCheck size={18} /> }] : []),
    ...(isMentor ? [{ id: 'mentor-workspace', label: 'Nhóm thực tập sinh', icon: <UsersRound size={18} /> }] : []),
    ...((isMentor || isIntern) ? [{ id: 'tasks', label: isIntern ? 'Nhiệm vụ của tôi' : 'Nhiệm vụ thực tập', icon: <ClipboardList size={18} /> }] : []),
    ...((isIntern || isMentor) ? [{ id: 'weekly-reports', label: 'Báo cáo tuần', icon: <FileText size={18} /> }] : []),
    ...(isMentor ? [{ id: 'evaluations', label: 'Đánh giá thực tập sinh', icon: <ClipboardList size={18} /> }] : []),
    ...(isIntern ? [{ id: 'my-evaluations', label: 'Đánh giá của tôi', icon: <Award size={18} /> }] : []),
    ...(canManage ? [
    {
      id: 'interns',
      label: 'Quản lý Thực tập sinh',
      icon: <GraduationCap size={18} />
    },
    {
      id: 'mentors',
      label: 'Quản lý Mentor',
      icon: <UserCheck size={18} />
    }] : []),
    ...(canViewPrograms ? [{
      id: 'programs',
      label: canManage ? 'Chương trình thực tập' : 'Chương trình đang mở',
      icon: <Calendar size={18} />
    }] : []),
    ...(canManage ? [{
      id: 'documents',
      label: 'Quản lý Tài liệu',
      icon: <FolderUp size={18} />
    }] : []),
    ...(canManage ? [{
      id: 'work-shifts',
      label: 'Quản lý ca làm việc',
      icon: <Clock3 size={18} />
    }] : []),
    ...(canManage ? [{
      id: 'leave-requests',
      label: 'Quản lý nghỉ phép',
      icon: <Calendar size={18} />
    }] : []),
    ...(isIntern ? [{
      id: 'leave-requests',
      label: 'Đăng ký nghỉ phép',
      icon: <Calendar size={18} />
    }] : []),
    ...((canManage || isIntern) ? [{
      id: 'allowances',
      label: canManage ? 'Quản lý phụ cấp' : 'Lịch sử phụ cấp',
      icon: <Wallet size={18} />
    }] : []),
    // Yêu cầu: Chức năng quản trị người dùng chỉ Admin mới được dùng
    ...(isAdmin ? [{
      id: 'accounts',
      label: 'Quản trị Người dùng',
      icon: <ShieldCheck size={18} />
    }] : [])
  ];

  return (
    <aside id="app-navigation" className={`app-sidebar${isOpen ? ' is-open' : ''}`} aria-hidden={isCollapsed ? 'true' : undefined}>
      <div className="sidebar-header">
        <div className="brand-icon">
          <Building2 size={22} />
        </div>
        <div className="brand-info">
          <h1>IMS PORTAL</h1>
          <span>Quản lý thực tập sinh</span>
        </div>
        <button type="button" className="sidebar-close" aria-label="Đóng danh mục" onClick={onClose}>
          <X size={20} />
        </button>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section-title">Danh mục quản lý</div>
        {navItems.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
            onClick={() => { onTabChange(item.id); onClose?.(); }}
          >
            {item.icon}
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <button type="button" className="sidebar-logout-button" onClick={onLogout}>
          <LogOut size={18} aria-hidden="true" />
          <span>Đăng xuất</span>
        </button>
      </div>
    </aside>
  );
}
