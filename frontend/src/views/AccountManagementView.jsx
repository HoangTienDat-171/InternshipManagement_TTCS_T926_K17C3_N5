import React, { useState, useEffect } from 'react';
import { UserPlus, RefreshCw, Mail, Phone, Shield, Briefcase, Users, GraduationCap, AlertCircle, Check, XCircle, Trash2 } from 'lucide-react';

export default function AccountManagementView({ departments, onShowToast, currentUser }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const isAdmin = currentUser?.vai_tro === 'Admin';

  const [formData, setFormData] = useState({
    ho_ten: '',
    email: '',
    mat_khau: '',
    so_dien_thoai: '',
    vai_tro: 'ThucTapSinh',
    ma_phong_ban: ''
  });

  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  const fetchUsers = async () => {
    if (!isAdmin) return;
    setLoading(true);
    setErrorMsg('');
    try {
      const res = await fetch('/api/auth/users', {
        headers: {
          'x-user-role': currentUser?.vai_tro || ''
        }
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Không thể tải danh sách tài khoản');
      }
      const data = await res.json();
      setUsers(data);
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAdmin) {
      fetchUsers();
    }
  }, [isAdmin]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleCreateAccount = async (e) => {
    e.preventDefault();
    if (!isAdmin) {
      onShowToast('Chỉ Quản trị viên (Admin) mới có quyền tạo người dùng!', 'error');
      return;
    }
    setFormSubmitting(true);
    setFormError('');

    try {
      const payload = {
        ho_ten: formData.ho_ten.trim(),
        email: formData.email.trim(),
        mat_khau: formData.mat_khau,
        so_dien_thoai: formData.so_dien_thoai.trim(),
        vai_tro: formData.vai_tro,
        ma_phong_ban: formData.ma_phong_ban ? parseInt(formData.ma_phong_ban, 10) : null
      };

      const res = await fetch('/api/auth/users', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'x-user-role': currentUser?.vai_tro || ''
        },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Không thể tạo tài khoản');
      }

      onShowToast(data.message || `Đã tạo tài khoản: ${formData.email}`);
      setFormData({
        ho_ten: '',
        email: '',
        mat_khau: '',
        so_dien_thoai: '',
        vai_tro: 'ThucTapSinh',
        ma_phong_ban: ''
      });
      fetchUsers();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setFormSubmitting(false);
    }
  };

  // Yêu cầu: Admin có thể phân quyền cho các role dưới
  const handleRoleChange = async (userId, newRole) => {
    try {
      const res = await fetch(`/api/auth/users/${userId}/role`, {
        method: 'PUT',
        headers: { 
          'Content-Type': 'application/json',
          'x-user-role': currentUser?.vai_tro || ''
        },
        body: JSON.stringify({ vai_tro: newRole })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Không thể đổi vai trò');
      onShowToast(data.message);
      fetchUsers();
    } catch (err) {
      onShowToast(err.message, 'error');
    }
  };

  const handleStatusChange = async (userId, newStatus) => {
    try {
      const endpoint = `/api/auth/users/${userId}/status`;
      const res = await fetch(endpoint, { 
        method: 'PUT',
        headers: { 
          'Content-Type': 'application/json',
          'x-user-role': currentUser?.vai_tro || '' 
        },
        body: JSON.stringify({ trang_thai: newStatus })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Không thể cập nhật trạng thái');
      onShowToast(data.message);
      fetchUsers();
    } catch (err) {
      onShowToast(err.message, 'error');
    }
  };

  const handleDeleteUser = async (userId, userName) => {
    if (userId === 1) {
      onShowToast('Không thể xóa tài khoản Quản trị viên mặc định!', 'error');
      return;
    }
    if (currentUser?.ma_nguoi_dung === userId) {
      onShowToast('Bạn không thể xóa tài khoản đang đăng nhập!', 'error');
      return;
    }
    if (!window.confirm(`Xác nhận xóa người dùng "${userName}"? Thao tác này không thể hoàn tác.`)) {
      return;
    }

    try {
      const res = await fetch(`/api/auth/users/${userId}`, {
        method: 'DELETE',
        headers: { 'x-user-role': currentUser?.vai_tro || '' }
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Không thể xóa người dùng');
      onShowToast(data.message);
      fetchUsers();
    } catch (err) {
      onShowToast(err.message, 'error');
    }
  };

  const getRoleBadge = (role) => {
    switch (role) {
      case 'Admin':
        return (
          <span className="badge badge-danger">
            <Shield size={12} />
            <span>Admin</span>
          </span>
        );
      case 'HR':
        return (
          <span className="badge badge-info">
            <Briefcase size={12} />
            <span>Quản lý TTS</span>
          </span>
        );
      case 'Mentor':
        return (
          <span className="badge badge-warning">
            <Users size={12} />
            <span>Mentor</span>
          </span>
        );
      case 'ThucTapSinh':
        return (
          <span className="badge badge-success">
            <GraduationCap size={12} />
            <span>Thực tập sinh</span>
          </span>
        );
      default:
        return <span className="badge badge-secondary">{role}</span>;
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'HoatDong':
        return <span className="badge badge-success"><span className="badge-dot" /> Đang hoạt động</span>;
      case 'Khoa':
        return <span className="badge badge-danger"><span className="badge-dot" /> Bị khóa</span>;
      case 'ChoDuyet':
      default:
        return <span className="badge badge-warning"><span className="badge-dot" /> Chờ xét duyệt</span>;
    }
  };

  // Yêu cầu: Chức năng quản trị người dùng chỉ Admin mới được dùng
  if (!isAdmin) {
    return (
      <div className="card" style={{ padding: '48px 24px', textAlign: 'center' }}>
        <div style={{
          width: '52px',
          height: '52px',
          borderRadius: '50%',
          background: '#fee2e2',
          color: '#dc2626',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          margin: '0 auto 16px'
        }}>
          <Shield size={26} />
        </div>
        <h3 style={{ fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
          Quyền truy cập bị từ chối
        </h3>
        <p style={{ color: '#64748b', marginTop: '6px', fontSize: '14px' }}>
          Chức năng Quản trị Người dùng chỉ dành riêng cho tài khoản Quản trị viên (Admin).
        </p>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>Quản trị Người dùng & Phân quyền</h2>
          <p style={{ fontSize: '13px', color: '#64748b' }}>
            {isAdmin 
              ? 'Tài khoản Admin: Bạn có toàn quyền phân quyền các vai trò và kích hoạt tài khoản bên dưới'
              : 'Danh sách tài khoản người dùng và trạng thái xét duyệt'}
          </p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '360px 1fr', gap: '24px', alignItems: 'start' }}>
        {/* Form Tạo mới tài khoản */}
        <div className="card">
          <div className="card-header">
            <div className="card-title-box">
              <h2>Thêm tài khoản mới</h2>
            </div>
          </div>
          <div className="card-body">
            {formError && (
              <div className="alert-banner error" style={{ padding: '8px 12px', marginBottom: '14px' }}>
                <AlertCircle size={15} />
                <span style={{ fontSize: '13px' }}>{formError}</span>
              </div>
            )}

            <form onSubmit={handleCreateAccount} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div className="form-group">
                <label className="form-label">
                  Họ và tên <span className="required">*</span>
                </label>
                <input
                  type="text"
                  name="ho_ten"
                  className="form-control"
                  placeholder="Ví dụ: Hoàng Tuấn Anh"
                  required
                  value={formData.ho_ten}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Email <span className="required">*</span>
                </label>
                <input
                  type="email"
                  name="email"
                  className="form-control"
                  placeholder="user@internship.vn"
                  required
                  value={formData.email}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Mật khẩu khởi tạo <span className="required">*</span>
                </label>
                <input
                  type="password"
                  name="mat_khau"
                  className="form-control"
                  placeholder="Tối thiểu 6 ký tự"
                  required
                  value={formData.mat_khau}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Số điện thoại</label>
                <input
                  type="text"
                  name="so_dien_thoai"
                  className="form-control"
                  placeholder="0988776655"
                  value={formData.so_dien_thoai}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Vai trò ban đầu
                </label>
                <select
                  name="vai_tro"
                  className="form-select"
                  value={formData.vai_tro}
                  onChange={handleChange}
                >
                  <option value="ThucTapSinh">Thực tập sinh (Mặc định)</option>
                  <option value="Mentor">Mentor (Người hướng dẫn)</option>
                  <option value="HR">Quản lý thực tập sinh</option>
                  <option value="Admin">Admin (Quản trị viên)</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Phòng ban</label>
                <select
                  name="ma_phong_ban"
                  className="form-select"
                  value={formData.ma_phong_ban}
                  onChange={handleChange}
                >
                  <option value="">-- Không chỉ định --</option>
                  {departments.map((d) => (
                    <option key={d.ma_phong_ban} value={d.ma_phong_ban}>
                      {d.ten_phong_ban}
                    </option>
                  ))}
                </select>
              </div>

              <button
                type="submit"
                className="btn btn-primary btn-sm"
                style={{ width: '100%', padding: '10px', marginTop: '6px' }}
                disabled={formSubmitting}
              >
                <UserPlus size={15} />
                <span>{formSubmitting ? 'Đang tạo...' : 'Tạo tài khoản'}</span>
              </button>
            </form>
          </div>
        </div>

        {/* Bảng Danh sách Tài khoản & Phân quyền */}
        <div className="card">
          <div className="card-header">
            <div className="card-title-box">
              <h2>Danh sách người dùng ({users.length})</h2>
            </div>
            <button className="btn btn-secondary btn-sm" onClick={fetchUsers} disabled={loading}>
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
              <span>Làm mới</span>
            </button>
          </div>

          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Họ và tên</th>
                  <th>Email & SĐT</th>
                  <th>Phân quyền Vai trò</th>
                  <th>Trạng thái</th>
                  <th style={{ textAlign: 'right' }}>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan="6" style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>
                      Đang tải dữ liệu...
                    </td>
                  </tr>
                ) : (
                  users.map((u) => (
                    <tr key={u.ma_nguoi_dung}>
                      <td style={{ fontWeight: 600, color: 'var(--text-muted)' }}>#{u.ma_nguoi_dung}</td>
                      <td>
                        <div style={{ fontWeight: 600, color: '#0f172a' }}>{u.ho_ten}</div>
                        <div style={{ fontSize: '11px', color: '#64748b' }}>{u.ten_phong_ban || 'Chưa phân phòng'}</div>
                      </td>
                      <td>
                        <div style={{ fontSize: '13px' }}>{u.email}</div>
                        {u.so_dien_thoai && (
                          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{u.so_dien_thoai}</div>
                        )}
                      </td>

                      {/* Phân quyền Vai trò */}
                      <td>
                        {isAdmin ? (
                          <select
                            className="form-select"
                            style={{ padding: '4px 8px', fontSize: '12px', width: 'auto', fontWeight: 600 }}
                            value={u.vai_tro}
                            onChange={(e) => handleRoleChange(u.ma_nguoi_dung, e.target.value)}
                            title="Admin phân quyền vai trò cho tài khoản"
                          >
                            <option value="Admin">Admin</option>
                            <option value="HR">Quản lý thực tập sinh</option>
                            <option value="Mentor">Mentor</option>
                            <option value="ThucTapSinh">Thực tập sinh</option>
                          </select>
                        ) : (
                          getRoleBadge(u.vai_tro)
                        )}
                      </td>

                      <td>{getStatusBadge(u.trang_thai)}</td>

                      <td style={{ textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', gap: '6px' }}>
                          {u.trang_thai === 'ChoDuyet' && (
                            <button
                              className="btn btn-sm"
                              style={{ backgroundColor: '#10b981', color: 'white', padding: '4px 8px', fontSize: '11px' }}
                              onClick={() => handleStatusChange(u.ma_nguoi_dung, 'HoatDong')}
                              title="Duyệt kích hoạt tài khoản"
                            >
                              <Check size={12} />
                              <span>Duyệt</span>
                            </button>
                          )}

                          {u.trang_thai === 'HoatDong' && u.vai_tro !== 'Admin' && (
                            <button
                              className="btn btn-secondary btn-sm"
                              style={{ padding: '4px 8px', fontSize: '11px', color: '#dc2626' }}
                              onClick={() => handleStatusChange(u.ma_nguoi_dung, 'Khoa')}
                              title="Khóa tài khoản"
                            >
                              <span>Khóa</span>
                            </button>
                          )}

                          {u.trang_thai === 'Khoa' && (
                            <button
                              className="btn btn-secondary btn-sm"
                              style={{ padding: '4px 8px', fontSize: '11px', color: '#059669' }}
                              onClick={() => handleStatusChange(u.ma_nguoi_dung, 'HoatDong')}
                              title="Kích hoạt lại"
                            >
                              <span>Mở khóa</span>
                            </button>
                          )}

                          {isAdmin && u.ma_nguoi_dung !== 1 && u.ma_nguoi_dung !== currentUser?.ma_nguoi_dung && (
                            <button
                              className="btn btn-secondary btn-sm"
                              style={{ padding: '4px 8px', fontSize: '11px', color: '#dc2626', borderColor: '#fca5a5' }}
                              onClick={() => handleDeleteUser(u.ma_nguoi_dung, u.ho_ten)}
                              title="Xóa tài khoản"
                            >
                              <Trash2 size={12} />
                              <span>Xóa</span>
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
