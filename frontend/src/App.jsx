import React, { useState, useEffect, useRef } from 'react';
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';
import LoginView from './views/LoginView';
import InternManagementView from './views/InternManagementView';
import MentorManagementView from './views/MentorManagementView';
import ProgramManagementView from './views/ProgramManagementView';
import DocumentManagementView from './views/DocumentManagementView';
import AccountManagementView from './views/AccountManagementView';
import AccountProfileView from './views/AccountProfileView';
import InternWorkspaceView from './views/InternWorkspaceView';
import MentorWorkspaceView from './views/MentorWorkspaceView';
import { CheckCircle2, AlertCircle } from 'lucide-react';
import { apiFetch } from './utils/api';

function clearSavedSession() {
  try {
    localStorage.removeItem('ims_token');
    localStorage.removeItem('ims_user');
  } catch {
    // The login screen must remain usable when browser storage is unavailable.
  }
}

export default function App() {
  const [activeTab, setActiveTab] = useState('interns');
  
  // Authentication State
  const [currentUser, setCurrentUser] = useState(() => {
    if (window.location.pathname === '/login') {
      clearSavedSession();
      return null;
    }
    try {
      const savedUser = localStorage.getItem('ims_user');
      return savedUser && localStorage.getItem('ims_token') ? JSON.parse(savedUser) : null;
    } catch {
      return null;
    }
  });
  const currentUserId = currentUser?.ma_nguoi_dung;
  const canManageRecords = ['Admin', 'HR'].includes(currentUser?.vai_tro);
  const personalWorkspace = currentUser?.vai_tro === 'Mentor'
    ? 'mentor-workspace'
    : currentUser?.vai_tro === 'ThucTapSinh' ? 'intern-dashboard' : 'profile';
  const visibleActiveTab = currentUser && (
    (!canManageRecords && ['interns', 'mentors', 'documents', 'accounts'].includes(activeTab))
    || (activeTab === 'programs' && !['Admin', 'HR', 'ThucTapSinh'].includes(currentUser.vai_tro))
    || (activeTab === 'accounts' && currentUser.vai_tro !== 'Admin')
  )
    ? personalWorkspace
    : activeTab;

  // Master data
  const [departments, setDepartments] = useState([]);
  const [universities, setUniversities] = useState([]);

  // Toast notifications
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);
  const [compactLayout, setCompactLayout] = useState(() => {
    try { return Boolean(JSON.parse(localStorage.getItem('ims_preferences'))?.compact); }
    catch { return false; }
  });
  const [theme, setTheme] = useState(() => {
    let savedTheme = 'light';
    try { savedTheme = localStorage.getItem('ims_theme') === 'dark' ? 'dark' : 'light'; }
    catch { /* Keep the light theme when storage is unavailable. */ }
    document.documentElement.dataset.theme = savedTheme;
    return savedTheme;
  });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [desktopSidebarCollapsed, setDesktopSidebarCollapsed] = useState(false);
  const [accountSection, setAccountSection] = useState('profile');
  const [sessionNotice, setSessionNotice] = useState('');

  const showToast = (message, type = 'success') => {
    try {
      if (JSON.parse(localStorage.getItem('ims_preferences'))?.notifications === false) return;
    } catch { /* Use the default enabled setting when preferences are unreadable. */ }
    setToast({ message, type });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => {
      setToast(null);
    }, 3500);
  };

  useEffect(() => () => window.clearTimeout(toastTimer.current), []);

  useEffect(() => {
    const handleSessionExpired = (event) => {
      const expiredToken = event.detail?.token;
      if (expiredToken && localStorage.getItem('ims_token') !== expiredToken) return;

      localStorage.removeItem('ims_token');
      localStorage.removeItem('ims_user');
      setCurrentUser(null);
      setSessionNotice(event.detail?.message || 'Phiên đăng nhập đã hết hạn hoặc được thay thế trên thiết bị khác.');
    };

    window.addEventListener('ims-session-expired', handleSessionExpired);
    return () => window.removeEventListener('ims-session-expired', handleSessionExpired);
  }, []);

  useEffect(() => {
    const clearSessionOnLoginRoute = () => {
      if (window.location.pathname !== '/login') return;
      clearSavedSession();
      setCurrentUser(null);
      setSessionNotice('');
    };
    window.addEventListener('popstate', clearSessionOnLoginRoute);
    return () => window.removeEventListener('popstate', clearSessionOnLoginRoute);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('ims_theme', theme); }
    catch { /* The active theme still works for this session without storage. */ }
  }, [theme]);

  useEffect(() => {
    if (!sidebarOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setSidebarOpen(false);
    };
    const closeOnDesktop = () => {
      if (window.innerWidth > 1000) setSidebarOpen(false);
    };
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', closeOnEscape);
    window.addEventListener('resize', closeOnDesktop);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', closeOnEscape);
      window.removeEventListener('resize', closeOnDesktop);
    };
  }, [sidebarOpen]);

  useEffect(() => {
    const handlePreferencesChange = (event) => setCompactLayout(Boolean(event.detail?.compact));
    window.addEventListener('ims-preferences-change', handlePreferencesChange);
    return () => window.removeEventListener('ims-preferences-change', handlePreferencesChange);
  }, []);

  useEffect(() => {
    if (!currentUserId) return;
    const token = localStorage.getItem('ims_token');
    if (!token) return;
    apiFetch('/api/auth/me')
      .then(async (response) => {
        if (!response.ok) throw new Error('Phiên đăng nhập không còn hợp lệ.');
        const user = await response.json();
        if (localStorage.getItem('ims_token') !== token) return;
        localStorage.setItem('ims_user', JSON.stringify(user));
        setCurrentUser(user);
      })
      .catch(() => {
        if (localStorage.getItem('ims_token') !== token) return;
        window.dispatchEvent(new CustomEvent('ims-session-expired', {
          detail: {
            token,
            message: 'Phiên đăng nhập đã hết hạn hoặc được thay thế trên thiết bị khác.',
          },
        }));
      });
  }, [currentUserId]);

  // Load master data when authenticated
  useEffect(() => {
    if (currentUser) {
      apiFetch('/api/master/departments')
        .then(async (res) => {
          const data = await res.json();
          if (!res.ok || !Array.isArray(data)) throw new Error(data.detail || 'Không thể tải danh sách phòng ban.');
          return data;
        })
        .then(data => setDepartments(data))
        .catch(err => {
          setDepartments([]);
          console.error('Error fetching departments:', err);
        });

      apiFetch('/api/master/universities')
        .then(async (res) => {
          const data = await res.json();
          if (!res.ok || !Array.isArray(data)) throw new Error(data.detail || 'Không thể tải danh sách trường đại học.');
          return data;
        })
        .then(data => setUniversities(data))
        .catch(err => {
          setUniversities([]);
          console.error('Error fetching universities:', err);
        });
    }
  }, [currentUser]);

  // Keep the current session connected for immediate revocation notices.
  useEffect(() => {
    const token = localStorage.getItem('ims_token');
    if (!currentUserId || !token) return undefined;
    let socket;
    let reconnectTimer;
    let heartbeatTimer;
    let disposed = false;
    const connect = () => {
      if (disposed) return;
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      socket = new WebSocket(`${protocol}//${window.location.host}/api/auth/events?token=${encodeURIComponent(token)}`);
      socket.onopen = () => {
        heartbeatTimer = window.setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) socket.send('ping');
        }, 15000);
      };
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.type === 'FORCE_LOGOUT') {
          disposed = true;
          window.dispatchEvent(new CustomEvent('ims-session-expired', {
            detail: { token, message: message.message },
          }));
        } else if (message.type === 'ACCOUNT_UPDATED' && message.user) {
          setCurrentUser((previous) => {
            const updated = { ...previous, ...message.user };
            localStorage.setItem('ims_user', JSON.stringify(updated));
            return updated;
          });
        } else if (message.type === 'WORKSPACE_UPDATED') {
          window.dispatchEvent(new CustomEvent('ims-workspace-updated'));
        }
      };
      socket.onclose = (event) => {
        window.clearInterval(heartbeatTimer);
        if (event.code === 4401) {
          disposed = true;
          window.dispatchEvent(new CustomEvent('ims-session-expired', {
            detail: { token, message: 'Phiên đăng nhập đã hết hạn hoặc được thay thế trên thiết bị khác.' },
          }));
        } else if (!disposed) {
          reconnectTimer = window.setTimeout(connect, 2000);
        }
      };
    };
    connect();
    return () => {
      disposed = true;
      window.clearTimeout(reconnectTimer);
      window.clearInterval(heartbeatTimer);
      socket?.close();
    };
  }, [currentUserId]);

  const handleLoginSuccess = (user) => {
    if (window.location.pathname === '/login') window.history.replaceState(null, '', '/');
    setSessionNotice('');
    setSidebarOpen(false);
    setCurrentUser(user);
    showToast(`Đăng nhập thành công! Chào mừng ${user.ho_ten}.`);
  };

  const handleLogout = async () => {
    const token = localStorage.getItem('ims_token');
    clearSavedSession();
    setSidebarOpen(false);
    setCurrentUser(null);
    window.history.replaceState(null, '', '/login');
    try {
      await apiFetch('/api/auth/logout', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
    } catch {
      // ignore
    }
    showToast('Đã đăng xuất khỏi hệ thống.');
  };

  const handleNavigationToggle = () => {
    if (window.innerWidth <= 1000) {
      setSidebarOpen((open) => !open);
      return;
    }
    setDesktopSidebarCollapsed((collapsed) => !collapsed);
  };

  // YÊU CẦU: Đăng nhập xong mới được vào trang chủ
  if (!currentUser) {
    return (
      <LoginView
        onLoginSuccess={handleLoginSuccess}
        departments={departments}
        sessionNotice={sessionNotice}
      />
    );
  }

  // TRANG CHỦ HỆ THỐNG
  return (
    <div className={`app-layout${compactLayout ? ' compact' : ''}${desktopSidebarCollapsed ? ' sidebar-collapsed' : ''}`}>
      {/* Toast Notification */}
      {toast && (
        <div style={{
          position: 'fixed',
          top: '20px',
          right: '20px',
          zIndex: 9999,
          background: toast.type === 'success' ? '#0f766e' : '#b91c1c',
          color: 'white',
          padding: '12px 18px',
          borderRadius: '10px',
          boxShadow: '0 8px 20px rgba(0,0,0,0.15)',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          fontSize: '13px',
          fontWeight: 600,
          animation: 'modalIn 0.2s ease-out'
        }}>
          {toast.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          <span>{toast.message}</span>
        </div>
      )}

      {/* Sidebar */}
      <Sidebar 
        activeTab={visibleActiveTab}
        onTabChange={setActiveTab}
        currentUser={currentUser}
        isOpen={sidebarOpen}
        isCollapsed={window.innerWidth > 1000 && desktopSidebarCollapsed}
        onClose={() => setSidebarOpen(false)}
      />
      {sidebarOpen && (
        <button
          type="button"
          className="sidebar-overlay"
          aria-label="Đóng danh mục"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main Content Area */}
      <div className="app-main">
        {/* Top Navbar */}
        <Navbar
          currentUser={currentUser}
          onLogout={handleLogout}
          onOpenAccount={(section) => { setAccountSection(section); setActiveTab('profile'); }}
          onToggleSidebar={handleNavigationToggle}
          sidebarOpen={window.innerWidth <= 1000 ? sidebarOpen : !desktopSidebarCollapsed}
          theme={theme}
          onToggleTheme={() => setTheme((currentTheme) => currentTheme === 'dark' ? 'light' : 'dark')}
        />

        <main className="content-wrapper">
          {canManageRecords && visibleActiveTab === 'interns' && (
            <InternManagementView
              departments={departments}
              universities={universities}
              onShowToast={showToast}
              currentUser={currentUser}
            />
          )}

          {canManageRecords && visibleActiveTab === 'mentors' && (
            <MentorManagementView
              departments={departments}
              onShowToast={showToast}
              currentUser={currentUser}
            />
          )}

          {['Admin', 'HR', 'ThucTapSinh'].includes(currentUser?.vai_tro) && visibleActiveTab === 'programs' && (
            <ProgramManagementView
              departments={departments}
              onShowToast={showToast}
              currentUser={currentUser}
            />
          )}

          {canManageRecords && visibleActiveTab === 'documents' && (
            <DocumentManagementView
              currentUser={currentUser}
              onShowToast={showToast}
            />
          )}

          {visibleActiveTab === 'accounts' && currentUser?.vai_tro === 'Admin' && (
            <AccountManagementView
              departments={departments}
              onShowToast={showToast}
              currentUser={currentUser}
            />
          )}

          {currentUser?.vai_tro === 'ThucTapSinh' && visibleActiveTab === 'intern-dashboard' && (
            <InternWorkspaceView currentUser={currentUser} onNavigatePrograms={() => setActiveTab('programs')} />
          )}

          {currentUser?.vai_tro === 'Mentor' && visibleActiveTab === 'mentor-workspace' && (
            <MentorWorkspaceView currentUser={currentUser} />
          )}

          {visibleActiveTab === 'profile' && (
            <AccountProfileView
              key={accountSection}
              initialSection={accountSection}
              currentUser={currentUser}
              onUserUpdated={setCurrentUser}
              onShowToast={showToast}
            />
          )}
        </main>
      </div>
    </div>
  );
}
