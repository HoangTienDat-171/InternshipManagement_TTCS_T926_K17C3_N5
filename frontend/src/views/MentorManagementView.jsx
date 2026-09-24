import React, { useState } from 'react';
import { UserCheck, UserPlus, Mail, Phone } from 'lucide-react';

export default function MentorManagementView({ departments, onShowToast }) {
  const [showAddForm, setShowAddForm] = useState(false);

  const [mentors, setMentors] = useState([
    {
      id: 1,
      ho_ten: 'Nguyễn Văn Hướng',
      email: 'mentor@internship.vn',
      so_dien_thoai: '0905555666',
      phong_ban: 'Trung tâm Công nghệ Thông tin',
      chuyen_mon: 'Kiến trúc Phần mềm & Python',
      kinh_nghiem: '8 năm',
      so_tts: 3
    },
    {
      id: 2,
      ho_ten: 'Lê Thị Phương Thảo',
      email: 'thao.lp@internship.vn',
      so_dien_thoai: '0912888999',
      phong_ban: 'Phòng Dữ liệu & Trí tuệ nhân tạo (AI/Data)',
      chuyen_mon: 'Machine Learning & Data Engineering',
      kinh_nghiem: '6 năm',
      so_tts: 2
    }
  ]);

  const [form, setForm] = useState({
    ho_ten: '',
    email: '',
    so_dien_thoai: '',
    ma_phong_ban: '',
    chuyen_mon: '',
    kinh_nghiem: '',
    so_tts_toi_da: 3,
    ghi_chu: ''
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleAddMentor = (e) => {
    e.preventDefault();
    const deptObj = departments.find(d => String(d.ma_phong_ban) === String(form.ma_phong_ban));
    const newMentor = {
      id: Date.now(),
      ho_ten: form.ho_ten,
      email: form.email,
      so_dien_thoai: form.so_dien_thoai,
      phong_ban: deptObj ? deptObj.ten_phong_ban : 'Trung tâm CNTT',
      chuyen_mon: form.chuyen_mon || 'Kỹ thuật viên',
      kinh_nghiem: form.kinh_nghiem ? `${form.kinh_nghiem} năm` : '—',
      so_tts: 0
    };

    setMentors([newMentor, ...mentors]);
    onShowToast(`Đã thêm mới Mentor: ${newMentor.ho_ten}`);
    setForm({
      ho_ten: '',
      email: '',
      so_dien_thoai: '',
      ma_phong_ban: '',
      chuyen_mon: '',
      kinh_nghiem: '',
      so_tts_toi_da: 3,
      ghi_chu: ''
    });
    setShowAddForm(false);
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>Quản lý Mentor</h2>
          <p style={{ fontSize: '13px', color: '#64748b' }}>
            Danh sách và quản lý thông tin người hướng dẫn thực tập sinh
          </p>
        </div>

        <button 
          className="btn btn-primary"
          onClick={() => setShowAddForm(!showAddForm)}
        >
          <UserPlus size={16} />
          <span>{showAddForm ? 'Đóng biểu mẫu' : 'Thêm Mentor'}</span>
        </button>
      </div>

      {/* Form Thêm mới Mentor */}
      {showAddForm && (
        <div className="card" style={{ marginBottom: '24px' }}>
          <div className="card-header">
            <div className="card-title-box">
              <h2>Thêm người hướng dẫn mới</h2>
            </div>
          </div>
          <div className="card-body">
            <form onSubmit={handleAddMentor} className="form-grid">
              <div className="form-group">
                <label className="form-label">
                  Họ và tên <span className="required">*</span>
                </label>
                <input
                  type="text"
                  name="ho_ten"
                  className="form-control"
                  placeholder="Ví dụ: Nguyễn Văn Hướng"
                  required
                  value={form.ho_ten}
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
                  placeholder="mentor@internship.vn"
                  required
                  value={form.email}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Số điện thoại</label>
                <input
                  type="text"
                  name="so_dien_thoai"
                  className="form-control"
                  placeholder="0905555666"
                  value={form.so_dien_thoai}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Phòng ban</label>
                <select
                  name="ma_phong_ban"
                  className="form-select"
                  value={form.ma_phong_ban}
                  onChange={handleChange}
                >
                  <option value="">-- Chọn phòng ban --</option>
                  {departments.map((d) => (
                    <option key={d.ma_phong_ban} value={d.ma_phong_ban}>
                      {d.ten_phong_ban}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Chuyên môn</label>
                <input
                  type="text"
                  name="chuyen_mon"
                  className="form-control"
                  placeholder="Frontend / Backend / AI / QA"
                  value={form.chuyen_mon}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Số năm kinh nghiệm</label>
                <input
                  type="number"
                  name="kinh_nghiem"
                  className="form-control"
                  placeholder="5"
                  min="0"
                  value={form.kinh_nghiem}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group form-full">
                <label className="form-label">Ghi chú</label>
                <textarea
                  name="ghi_chu"
                  className="form-textarea"
                  placeholder="Kỹ năng chính hoặc định hướng đào tạo..."
                  value={form.ghi_chu}
                  onChange={handleChange}
                />
              </div>

              <div className="form-full" style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowAddForm(false)}>
                  Hủy
                </button>
                <button type="submit" className="btn btn-primary btn-sm">
                  <UserPlus size={15} />
                  <span>Xác nhận thêm</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Danh sách Mentor */}
      <div className="card">
        <div className="card-header">
          <div className="card-title-box">
            <h2>Danh sách Người hướng dẫn ({mentors.length})</h2>
          </div>
        </div>

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Họ và tên</th>
                <th>Thông tin liên hệ</th>
                <th>Phòng ban</th>
                <th>Chuyên môn</th>
                <th>Kinh nghiệm</th>
                <th>TTS đang phụ trách</th>
              </tr>
            </thead>
            <tbody>
              {mentors.map((m) => (
                <tr key={m.id}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div className="user-avatar" style={{ width: '32px', height: '32px', fontSize: '12px' }}>
                        {m.ho_ten.charAt(0)}
                      </div>
                      <div>
                        <div style={{ fontWeight: 600 }}>{m.ho_ten}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <div style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Mail size={12} color="var(--text-subtle)" />
                      <span>{m.email}</span>
                    </div>
                    {m.so_dien_thoai && (
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Phone size={12} color="var(--text-subtle)" />
                        <span>{m.so_dien_thoai}</span>
                      </div>
                    )}
                  </td>
                  <td>
                    <div style={{ fontSize: '13px' }}>{m.phong_ban}</div>
                  </td>
                  <td>
                    <span className="badge badge-info" style={{ fontSize: '12px' }}>
                      {m.chuyen_mon}
                    </span>
                  </td>
                  <td style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                    {m.kinh_nghiem}
                  </td>
                  <td>
                    <span className="badge badge-success" style={{ fontWeight: 600 }}>
                      {m.so_tts} người
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
