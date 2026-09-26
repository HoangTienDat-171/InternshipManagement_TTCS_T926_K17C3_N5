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
import { CheckCircle2, AlertCircle } from 'lucide-react';
import { apiFetch } from './utils/api';

export default function App() {
  const [activeTab, setActiveTab] = useState('interns');
  
  // Authentication State
  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const savedUser = localStorage.getItem('ims_user');
      return savedUser && localStorage.getItem('ims_token') ? JSON.parse(savedUser) : null;
    } catch {
      return null;
    }
  });
  const currentUserId = currentUser?.ma_nguoi_dung;

  // Master data
  const [departments, setDepartments] = useState([]);
  const [universities, setUniversities] = useState([]);

  // Toast notifications
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);
  const [accountSection, setAccountSection] = useState('profile');
  const [sessionNotice, setSessionNotice] = useState('');

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => {
      setToast(null);
    }, 3500);
  };

  useEffect(() => () => window.clearTimeout(toastTimer.current), []);

  useEffect(() => {
    if (!currentUserId) return;
    apiFetch('/api/auth/me')
      .then(async (response) => {
        if (!response.ok) throw new Error('Phiên đăng nhập không còn hợp lệ.');
        const user = await response.json();
        localStorage.setItem('ims_user', JSON.stringify(user));
        setCurrentUser(user);
      })
      .catch(() => {
        localStorage.removeItem('ims_token');
        localStorage.removeItem('ims_user');
        setCurrentUser(null);
        setSessionNotice('Phiên đăng nhập đã hết hạn hoặc được thay thế trên thiết bị khác.');
      });
  }, [currentUserId]);

  // Load master data when authenticated
  useEffect(() => {
    if (currentUser) {
      apiFetch('/api/master/departments')
        .then(res => res.json())
        .then(data => setDepartments(data))
        .catch(err => console.error('Error fetching departments:', err));

      apiFetch('/api/master/universities')
        .then(res => res.json())
        .then(data => setUniversities(data))
        .catch(err => console.error('Error fetching universities:', err));
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
          localStorage.removeItem('ims_token');
          localStorage.removeItem('ims_user');
          setCurrentUser(null);
          setSessionNotice(message.message || 'Phiên đăng nhập đã bị kết thúc.');
        } else if (message.type === 'ACCOUNT_UPDATED' && message.user) {
          setCurrentUser((previous) => {
            const updated = { ...previous, ...message.user };
            localStorage.setItem('ims_user', JSON.stringify(updated));
            return updated;
          });
        }
      };
      socket.onclose = (event) => {
        window.clearInterval(heartbeatTimer);
        if (event.code === 4401) {
          disposed = true;
          localStorage.removeItem('ims_token');
          localStorage.removeItem('ims_user');
          setCurrentUser(null);
          setSessionNotice('Phiên đăng nhập đã hết hạn hoặc được thay thế trên thiết bị khác.');
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
    setSessionNotice('');
    setCurrentUser(user);
    showToast(`Đăng nhập thành công! Chào mừng ${user.ho_ten}.`);
  };

  const handleLogout = async () => {
    try {
      await apiFetch('/api/auth/logout', { method: 'POST' });
    } catch {
      // ignore
    }
    localStorage.removeItem('ims_token');
    localStorage.removeItem('ims_user');
    setCurrentUser(null);
    showToast('Đã đăng xuất khỏi hệ thống.');
  };

  const handleSwitchRole = (newRole) => {
    const roleProfiles = {
      Admin: { ma_nguoi_dung: 1, ho_ten: 'Quản Trị Viên Hệ Thống', email: 'admin@internship.vn', vai_tro: 'Admin', ten_phong_ban: 'Trung tâm CNTT' },
      HR: { ma_nguoi_dung: 2, ho_ten: 'Trần Thu Hà', email: 'hr@internship.vn', vai_tro: 'HR', ten_phong_ban: 'Trung tâm CNTT' },
      Mentor: { ma_nguoi_dung: 3, ho_ten: 'Nguyễn Văn Hướng', email: 'mentor@internship.vn', vai_tro: 'Mentor', ten_phong_ban: 'Trung tâm CNTT' },
      ThucTapSinh: { ma_nguoi_dung: 4, ho_ten: 'Lê Minh Tuấn', email: 'tuan.lm@internship.vn', vai_tro: 'ThucTapSinh', ten_phong_ban: 'Trung tâm CNTT' }
    };

    const targetUser = roleProfiles[newRole] || { ...currentUser, vai_tro: newRole };
    setCurrentUser(targetUser);
    if (newRole !== 'Admin' && activeTab === 'accounts') setActiveTab('interns');
    localStorage.setItem('ims_user', JSON.stringify(targetUser));
    showToast(`Đã chuyển vai trò: ${targetUser.ho_ten} (${newRole})`);
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
    <div className="app-layout">
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
        activeTab={activeTab} 
        onTabChange={setActiveTab}
        currentUser={currentUser}
      />

      {/* Main Content Area */}
      <div className="app-main">
        {/* Top Navbar */}
        <Navbar
          currentUser={currentUser}
          onLogout={handleLogout}
          onSwitchRole={handleSwitchRole}
          onOpenAccount={(section) => { setAccountSection(section); setActiveTab('profile'); }}
        />

        <main className="content-wrapper">
          {activeTab === 'interns' && (
            <InternManagementView
              departments={departments}
              universities={universities}
              onShowToast={showToast}
              currentUser={currentUser}
            />
          )}

          {activeTab === 'mentors' && (
            <MentorManagementView
              departments={departments}
              onShowToast={showToast}
            />
          )}

          {activeTab === 'programs' && (
            <ProgramManagementView
              departments={departments}
              onShowToast={showToast}
            />
          )}

          {activeTab === 'documents' && (
            <DocumentManagementView
              onShowToast={showToast}
            />
          )}

          {activeTab === 'accounts' && currentUser?.vai_tro === 'Admin' && (
            <AccountManagementView
              departments={departments}
              onShowToast={showToast}
              currentUser={currentUser}
            />
          )}

          {activeTab === 'profile' && (
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
