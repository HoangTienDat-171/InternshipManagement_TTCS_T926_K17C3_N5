import React, { useState, useEffect, useCallback } from 'react';
import { UserPlus, RefreshCw, Shield, Briefcase, Users, GraduationCap, AlertCircle, Check, Trash2, Download, X } from 'lucide-react';
import PhoneField from '../components/PhoneField';
import ConfirmDialog from '../components/ConfirmDialog';
import { isValidVietnamPhone } from '../utils/phone';

export default function AccountManagementView({ departments, onShowToast, currentUser }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');

  const currentRole = currentUser?.vai_tro || '';
  const isAdmin = currentRole === 'Admin';

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
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);

  const requestUsers = useCallback(async () => {
    if (!isAdmin) return [];
    const res = await fetch('/api/auth/users', { headers: { 'x-user-role': currentRole } });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || 'Không thể tải danh sách tài khoản');
    }
    return res.json();
  }, [isAdmin, currentRole]);

  const fetchUsers = async () => {
    try {
      setUsers(await requestUsers());
      setErrorMsg('');
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  const refreshUsers = () => {
    setLoading(true);
    fetchUsers();
  };

  useEffect(() => {
    let current = true;
    requestUsers()
      .then((data) => {
        if (current) {
          setUsers(data);
          setErrorMsg('');
        }
      })
      .catch((err) => {
        if (current) setErrorMsg(err.message);
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => { current = false; };
  }, [requestUsers]);

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

    if (formData.so_dien_thoai && !isValidVietnamPhone(formData.so_dien_thoai)) {
      setFormError('Số điện thoại phải gồm 10 chữ số và bắt đầu bằng 03, 05, 07, 08 hoặc 09.');
      setFormSubmitting(false);
      return;
    }

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
      setShowCreateModal(false);
      refreshUsers();
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
      refreshUsers();
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
      refreshUsers();
    } catch (err) {
      onShowToast(err.message, 'error');
    }
  };

  const handleDeleteUser = async (userId) => {
    if (userId === 1) {
      onShowToast('Không thể xóa tài khoản Quản trị viên mặc định!', 'error');
      return;
    }
    if (currentUser?.ma_nguoi_dung === userId) {
      onShowToast('Bạn không thể xóa tài khoản đang đăng nhập!', 'error');
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
      setPendingDelete(null);
      refreshUsers();
    } catch (err) {
      onShowToast(err.message, 'error');
    }
  };

  const exportUsers = () => {
    const columns = ['ID', 'Họ và tên', 'Email', 'Số điện thoại', 'Vai trò', 'Trạng thái', 'Phòng ban'];
    const rows = users.map((user) => [user.ma_nguoi_dung, user.ho_ten, user.email, user.so_dien_thoai || '', user.vai_tro, user.trang_thai, user.ten_phong_ban || '']);
    const csv = [columns, ...rows].map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(',')).join('\r\n');
    const url = URL.createObjectURL(new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'danh-sach-nguoi-dung.csv';
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
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

      <div className="card account-management-card">
          <div className="card-header">
            <div className="card-title-box">
              <div>
                <h2>Danh sách người dùng ({users.length})</h2>
                <p className="account-list-description">Quản lý vai trò, trạng thái và thông tin tài khoản</p>
              </div>
            </div>
            <div className="account-list-actions">
              <button className="btn btn-primary btn-sm" onClick={() => { setFormError(''); setShowCreateModal(true); }}>
                <UserPlus size={15} /><span>Thêm tài khoản</span>
              </button>
              <button className="btn btn-secondary btn-sm" onClick={exportUsers} disabled={!users.length}>
                <Download size={13} /><span>Xuất danh sách</span>
              </button>
              <button className="btn btn-secondary btn-sm" onClick={refreshUsers} disabled={loading}>
                <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /><span>Làm mới</span>
              </button>
            </div>
          </div>

          {errorMsg && <div className="alert-banner error account-list-error" role="alert"><AlertCircle size={16} /><span>{errorMsg}</span></div>}
          <div className="table-responsive account-table-scroll">
            <table className="data-table account-data-table">
              <colgroup>
                <col className="account-col-id" />
                <col className="account-col-name" />
                <col className="account-col-contact" />
                <col className="account-col-role" />
                <col className="account-col-status" />
                <col className="account-col-actions" />
              </colgroup>
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
                            onClick={() => setPendingDelete({ id: u.ma_nguoi_dung, name: u.ho_ten })}
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
      {showCreateModal && (
        <div className="modal-overlay" onMouseDown={(event) => event.target === event.currentTarget && !formSubmitting && setShowCreateModal(false)}>
          <section className="modal-container create-account-dialog" role="dialog" aria-modal="true" aria-labelledby="create-account-title">
            <div className="modal-header">
              <div>
                <h3 id="create-account-title">Thêm tài khoản mới</h3>
                <p className="create-account-subtitle">Nhập thông tin để tạo tài khoản cho thành viên.</p>
              </div>
              <button className="modal-close-btn" type="button" aria-label="Đóng" onClick={() => !formSubmitting && setShowCreateModal(false)}><X size={20} /></button>
            </div>
            <div className="modal-body">
              {formError && (
                <div className="alert-banner error create-account-error" role="alert">
                  <AlertCircle size={15} /><span>{formError}</span>
                </div>
              )}
              <form id="create-account-form" onSubmit={handleCreateAccount} className="create-account-form">
                <div className="form-group">
                  <label className="form-label" htmlFor="new-user-name">Họ và tên <span className="required">*</span></label>
                  <input id="new-user-name" type="text" name="ho_ten" className="form-control" placeholder="Ví dụ: Hoàng Tuấn Anh" required value={formData.ho_ten} onChange={handleChange} />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="new-user-email">Email <span className="required">*</span></label>
                  <input id="new-user-email" type="email" name="email" className="form-control" placeholder="user@internship.vn" required value={formData.email} onChange={handleChange} />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="new-user-password">Mật khẩu khởi tạo <span className="required">*</span></label>
                  <input id="new-user-password" type="password" name="mat_khau" className="form-control" placeholder="Tối thiểu 6 ký tự" minLength={6} required value={formData.mat_khau} onChange={handleChange} />
                </div>
                <PhoneField value={formData.so_dien_thoai} onChange={(value) => setFormData((prev) => ({ ...prev, so_dien_thoai: value }))} placeholder="0988776655" />
                <div className="form-group">
                  <label className="form-label" htmlFor="new-user-role">Vai trò ban đầu</label>
                  <select id="new-user-role" name="vai_tro" className="form-select" value={formData.vai_tro} onChange={handleChange}>
                    <option value="ThucTapSinh">Thực tập sinh (Mặc định)</option>
                    <option value="Mentor">Mentor (Người hướng dẫn)</option>
                    <option value="HR">Quản lý thực tập sinh</option>
                    <option value="Admin">Admin (Quản trị viên)</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="new-user-department">Phòng ban</label>
                  <select id="new-user-department" name="ma_phong_ban" className="form-select" value={formData.ma_phong_ban} onChange={handleChange}>
                    <option value="">-- Không chỉ định --</option>
                    {departments.map((d) => <option key={d.ma_phong_ban} value={d.ma_phong_ban}>{d.ten_phong_ban}</option>)}
                  </select>
                </div>
              </form>
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-secondary" onClick={() => setShowCreateModal(false)} disabled={formSubmitting}>Hủy</button>
              <button type="submit" form="create-account-form" className="btn btn-primary" disabled={formSubmitting}>
                <UserPlus size={15} /><span>{formSubmitting ? 'Đang tạo...' : 'Tạo tài khoản'}</span>
              </button>
            </div>
          </section>
        </div>
      )}
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Xóa tài khoản người dùng?"
        message={pendingDelete ? `Bạn có chắc muốn xóa “${pendingDelete.name}”? Thao tác này không thể hoàn tác.` : ''}
        confirmLabel="Xóa tài khoản"
        danger
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => pendingDelete && handleDeleteUser(pendingDelete.id)}
      />
    </div>
  );
}
