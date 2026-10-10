import React from 'react';
import {
  Award,
  BadgeDollarSign,
  Briefcase,
  Calendar,
  CalendarDays,
  CalendarOff,
  ClipboardCheck,
  FileCheck,
  FileSpreadsheet,
  FileText,
  FolderKanban,
  FolderOpen,
  GraduationCap,
  HelpCircle,
  LayoutDashboard,
  LifeBuoy,
  LogOut,
  ShieldCheck,
  SquareCheck,
  UserCheck,
  Users,
  Wallet,
  X,
  Clock,
} from 'lucide-react';

const MENU_CONFIG = [
  // Intern / TTS
  { id: 'intern-dashboard', label: 'Tổng quan thực tập', icon: LayoutDashboard, roles: ['intern'] },
  { id: 'intern-schedule', label: 'Lịch thực tập', icon: Calendar, roles: ['intern'] },
  { id: 'intern-attendance', label: 'Chấm công hôm nay', icon: Clock, roles: ['intern'] },
  { id: 'tasks', label: 'Nhiệm vụ của tôi', icon: SquareCheck, roles: ['intern'] },
  { id: 'weekly-reports', label: 'Báo cáo tuần', icon: FileText, roles: ['intern'] },
  { id: 'my-evaluations', label: 'Đánh giá của tôi', icon: Award, roles: ['intern'] },
  { id: 'programs', label: 'Chương trình đang mở', icon: FolderOpen, roles: ['intern'] },
  { id: 'leave-requests', label: 'Đăng ký nghỉ phép', icon: CalendarOff, roles: ['intern'] },
  { id: 'allowances', label: 'Lịch sử phụ cấp', icon: Wallet, roles: ['intern'] },
  { id: 'support-requests', label: 'Yêu cầu hỗ trợ', icon: LifeBuoy, roles: ['intern'] },

  // HR / Admin / Manager
  { id: 'interns', label: 'Quản lý Thực tập sinh', icon: Users, roles: ['manager'] },
  { id: 'mentors', label: 'Quản lý Mentor', icon: UserCheck, roles: ['manager'] },
  { id: 'programs', label: 'Chương trình thực tập', icon: Briefcase, roles: ['manager'] },
  { id: 'documents', label: 'Quản lý Tài liệu', icon: FolderKanban, roles: ['manager'] },
  { id: 'work-shifts', label: 'Quản lý ca làm việc', icon: CalendarDays, roles: ['manager'] },
  { id: 'leave-requests', label: 'Quản lý nghỉ phép', icon: FileSpreadsheet, roles: ['manager'] },
  { id: 'allowances', label: 'Quản lý phụ cấp', icon: BadgeDollarSign, roles: ['manager'] },
  { id: 'support-requests', label: 'Xử lý Yêu cầu hỗ trợ', icon: HelpCircle, roles: ['manager'] },
  { id: 'accounts', label: 'Quản trị Người dùng', icon: ShieldCheck, roles: ['manager'], adminOnly: true },

  // Mentor
  { id: 'mentor-workspace', label: 'Danh sách TTS hướng dẫn', icon: Users, roles: ['mentor'] },
  { id: 'evaluations', label: 'Đánh giá TTS', icon: ClipboardCheck, roles: ['mentor'] },
  { id: 'tasks', label: 'Giao nhiệm vụ / Task', icon: SquareCheck, roles: ['mentor'] },
  { id: 'weekly-reports', label: 'Duyệt báo cáo', icon: FileCheck, roles: ['mentor'] },
];

function getRoleFamily(role) {
  const normalizedRole = String(role || '').trim().toUpperCase();

  if (['THUCTAPSINH', 'INTERN', 'TTS'].includes(normalizedRole)) return 'intern';
  if (['ADMIN', 'HR', 'MANAGER'].includes(normalizedRole)) return 'manager';
  if (normalizedRole === 'MENTOR') return 'mentor';
  return null;
}

export default function Sidebar({ activeTab, onTabChange, currentUser, onLogout, isOpen = false, isCollapsed = false, onClose }) {
  const role = String(currentUser?.vai_tro || '').trim().toUpperCase();
  const roleFamily = getRoleFamily(role);
  const navItems = MENU_CONFIG.filter((item) => (
    item.roles.includes(roleFamily) && (!item.adminOnly || role === 'ADMIN')
  ));

  return (
    <aside
      id="app-navigation"
      className={`app-sidebar${isOpen ? ' is-open' : ''}${isCollapsed ? ' is-collapsed' : ''}`}
    >
      <div className="sidebar-header">
        <div className="brand-icon">
          <GraduationCap size={22} strokeWidth={2} />
        </div>
        <div className="brand-info">
          <h1>IMS PORTAL</h1>
          <span>Quản lý thực tập sinh</span>
        </div>
        <button type="button" className="sidebar-close" aria-label="Đóng danh mục" onClick={onClose}>
          <X size={20} />
        </button>
      </div>

      <nav className="sidebar-nav" aria-label="Danh mục chức năng">
        <div className="nav-section-title">Danh mục quản lý</div>
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;

          return (
            <button
              key={`${item.id}-${item.label}`}
              type="button"
              className={`nav-item${isActive ? ' active' : ''}`}
              title={isCollapsed ? item.label : undefined}
              aria-label={isCollapsed ? item.label : undefined}
              aria-current={isActive ? 'page' : undefined}
              onClick={() => { onTabChange(item.id); onClose?.(); }}
            >
              <Icon size={20} strokeWidth={1.9} aria-hidden="true" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <button
          type="button"
          className="sidebar-logout-button"
          onClick={onLogout}
          title={isCollapsed ? 'Đăng xuất' : undefined}
          aria-label={isCollapsed ? 'Đăng xuất' : undefined}
        >
          <LogOut size={20} aria-hidden="true" />
          <span>Đăng xuất</span>
        </button>
      </div>
    </aside>
  );
}
