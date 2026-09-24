import React, { useState } from 'react';
import { Calendar, PlusCircle, Clock } from 'lucide-react';

export default function ProgramManagementView({ departments, onShowToast }) {
  const [showAddForm, setShowAddForm] = useState(false);

  const [programs, setPrograms] = useState([
    {
      id: 1,
      ma_ct: 'CT-2026-SUMMER',
      ten_ct: 'Chương trình Thực tập sinh Công nghệ Mùa Hè 2026',
      phong_ban: 'Trung tâm Công nghệ Thông tin',
      thoi_gian: '01/06/2026 - 31/08/2026',
      chi_tieu: 20,
      so_luong_hien_tai: 8,
      trang_thai: 'DangMo'
    },
    {
      id: 2,
      ma_ct: 'CT-2026-AI',
      ten_ct: 'Tài năng Trí tuệ Nhân tạo & Kỹ thuật Dữ liệu',
      phong_ban: 'Phòng Dữ liệu & Trí tuệ nhân tạo (AI/Data)',
      thoi_gian: '15/07/2026 - 15/10/2026',
      chi_tieu: 10,
      so_luong_hien_tai: 4,
      trang_thai: 'DangMo'
    }
  ]);

  const [form, setForm] = useState({
    ten_ct: '',
    ma_ct: '',
    ma_phong_ban: '',
    ngay_bat_dau: '',
    ngay_ket_thuc: '',
    chi_tieu: 10,
    yeu_cau: '',
    quyen_loi: ''
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm(prev => ({ ...prev, [name]: value }));
  };

  const handleCreateProgram = (e) => {
    e.preventDefault();
    const deptObj = departments.find(d => String(d.ma_phong_ban) === String(form.ma_phong_ban));
    const newProg = {
      id: Date.now(),
      ma_ct: form.ma_ct || `CT-${Date.now().toString().slice(-4)}`,
      ten_ct: form.ten_ct,
      phong_ban: deptObj ? deptObj.ten_phong_ban : 'Trung tâm CNTT',
      thoi_gian: `${form.ngay_bat_dau || '01/07/2026'} - ${form.ngay_ket_thuc || '30/09/2026'}`,
      chi_tieu: parseInt(form.chi_tieu, 10) || 10,
      so_luong_hien_tai: 0,
      trang_thai: 'DangMo'
    };

    setPrograms([newProg, ...programs]);
    onShowToast(`Đã tạo chương trình: ${newProg.ten_ct}`);
    setForm({
      ten_ct: '',
      ma_ct: '',
      ma_phong_ban: '',
      ngay_bat_dau: '',
      ngay_ket_thuc: '',
      chi_tieu: 10,
      yeu_cau: '',
      quyen_loi: ''
    });
    setShowAddForm(false);
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>Chương trình Thực tập</h2>
          <p style={{ fontSize: '13px', color: '#64748b' }}>
            Thiết lập và quản lý các đợt thực tập và kế hoạch tiếp nhận sinh viên
          </p>
        </div>

        <button 
          className="btn btn-primary"
          onClick={() => setShowAddForm(!showAddForm)}
        >
          <PlusCircle size={16} />
          <span>{showAddForm ? 'Đóng biểu mẫu' : 'Tạo chương trình'}</span>
        </button>
      </div>

      {showAddForm && (
        <div className="card" style={{ marginBottom: '24px' }}>
          <div className="card-header">
            <div className="card-title-box">
              <h2>Tạo mới chương trình thực tập</h2>
            </div>
          </div>
          <div className="card-body">
            <form onSubmit={handleCreateProgram} className="form-grid">
              <div className="form-group">
                <label className="form-label">
                  Tên chương trình <span className="required">*</span>
                </label>
                <input
                  type="text"
                  name="ten_ct"
                  className="form-control"
                  placeholder="Ví dụ: Thực tập sinh Công nghệ Mùa Hè 2026"
                  required
                  value={form.ten_ct}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Mã chương trình</label>
                <input
                  type="text"
                  name="ma_ct"
                  className="form-control"
                  placeholder="CT-2026-01"
                  value={form.ma_ct}
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
                <label className="form-label">Chỉ tiêu tiếp nhận</label>
                <input
                  type="number"
                  name="chi_tieu"
                  className="form-control"
                  min="1"
                  value={form.chi_tieu}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Ngày bắt đầu</label>
                <input
                  type="date"
                  name="ngay_bat_dau"
                  className="form-control"
                  value={form.ngay_bat_dau}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Ngày kết thúc</label>
                <input
                  type="date"
                  name="ngay_ket_thuc"
                  className="form-control"
                  value={form.ngay_ket_thuc}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group form-full">
                <label className="form-label">Yêu cầu tuyển chọn</label>
                <textarea
                  name="yeu_cau"
                  className="form-textarea"
                  placeholder="Sinh viên năm 3, 4 có kiến thức cơ bản về lập trình..."
                  value={form.yeu_cau}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group form-full">
                <label className="form-label">Quyền lợi & Phụ cấp</label>
                <textarea
                  name="quyen_loi"
                  className="form-textarea"
                  placeholder="Phụ cấp hàng tháng, có mentor hướng dẫn..."
                  value={form.quyen_loi}
                  onChange={handleChange}
                />
              </div>

              <div className="form-full" style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowAddForm(false)}>
                  Hủy
                </button>
                <button type="submit" className="btn btn-primary btn-sm">
                  <PlusCircle size={15} />
                  <span>Xác nhận tạo</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Danh sách chương trình */}
      <div className="card">
        <div className="card-header">
          <div className="card-title-box">
            <h2>Các chương trình đào tạo ({programs.length})</h2>
          </div>
        </div>

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Mã CT</th>
                <th>Tên chương trình</th>
                <th>Phòng ban</th>
                <th>Thời gian</th>
                <th>Chỉ tiêu & Hiện tại</th>
                <th>Trạng thái</th>
              </tr>
            </thead>
            <tbody>
              {programs.map((p) => (
                <tr key={p.id}>
                  <td style={{ fontWeight: 600, color: 'var(--text-muted)' }}>{p.ma_ct}</td>
                  <td>
                    <div style={{ fontWeight: 600, color: '#0f172a' }}>{p.ten_ct}</div>
                  </td>
                  <td>{p.phong_ban}</td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}>
                      <Clock size={13} color="var(--text-subtle)" />
                      <span>{p.thoi_gian}</span>
                    </div>
                  </td>
                  <td>
                    <div style={{ fontWeight: 600 }}>
                      {p.so_luong_hien_tai} / {p.chi_tieu} ứng viên
                    </div>
                  </td>
                  <td>
                    <span className="badge badge-success">
                      <span className="badge-dot" /> Đang nhận hồ sơ
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
