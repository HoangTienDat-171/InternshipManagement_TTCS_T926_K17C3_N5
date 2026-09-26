import React from 'react';
import { 
  UserCheck, 
  Calendar, 
  FolderUp, 
  ShieldCheck, 
  Building2,
  GraduationCap
} from 'lucide-react';

export default function Sidebar({ activeTab, onTabChange, currentUser }) {
  const isAdmin = currentUser?.vai_tro === 'Admin';

  const navItems = [
    {
      id: 'interns',
      label: 'Quản lý Thực tập sinh',
      icon: <GraduationCap size={18} />
    },
    {
      id: 'mentors',
      label: 'Quản lý Mentor',
      icon: <UserCheck size={18} />
    },
    {
      id: 'programs',
      label: 'Chương trình thực tập',
      icon: <Calendar size={18} />
    },
    {
      id: 'documents',
      label: 'Quản lý Tài liệu',
      icon: <FolderUp size={18} />
    },
    // Yêu cầu: Chức năng quản trị người dùng chỉ Admin mới được dùng
    ...(isAdmin ? [{
      id: 'accounts',
      label: 'Quản trị Người dùng',
      icon: <ShieldCheck size={18} />
    }] : [])
  ];

  return (
    <aside className="app-sidebar">
      <div className="sidebar-header">
        <div className="brand-icon">
          <Building2 size={22} />
        </div>
        <div className="brand-info">
          <h1>IMS PORTAL</h1>
          <span>Quản lý thực tập sinh</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section-title">Danh mục quản lý</div>
        {navItems.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
            onClick={() => onTabChange(item.id)}
          >
            {item.icon}
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        {currentUser && (
          <div className="user-profile-badge">
            <div className="user-avatar">
              {currentUser.ho_ten ? currentUser.ho_ten.charAt(0).toUpperCase() : 'U'}
            </div>
            <div className="user-details">
              <div className="user-name" title={currentUser.ho_ten}>{currentUser.ho_ten}</div>
              <div className="user-role-label">
                {currentUser.vai_tro === 'HR' ? 'Quản lý TTS' : currentUser.vai_tro}
              </div>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
