import React, { useState, useEffect } from 'react';
import { X, Save, AlertCircle } from 'lucide-react';

export default function InternModal({ 
  isOpen, 
  onClose, 
  internId,
  departments, 
  universities, 
  onSuccess 
}) {
  const isEdit = Boolean(internId);

  const [formData, setFormData] = useState({
    ho_ten: '',
    email: '',
    so_dien_thoai: '',
    ma_phong_ban: '',
    ma_truong: '',
    chuyen_nganh: '',
    trang_thai_xet_duyet: 'ChoDuyet',
    trang_thai_thuc_tap: 'DangThucTap'
  });

  const [loading, setLoading] = useState(false);
  const [loadingInitial, setLoadingInitial] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (isOpen && isEdit && internId) {
      setLoadingInitial(true);
      setErrorMsg('');
      fetch(`/api/interns/${internId}`)
        .then(async (res) => {
          if (!res.ok) throw new Error('Không thể tải thông tin thực tập sinh');
          return res.json();
        })
        .then((data) => {
          setFormData({
            ho_ten: data.ho_ten || '',
            email: data.email || '',
            so_dien_thoai: data.so_dien_thoai || '',
            ma_phong_ban: data.ma_phong_ban ? String(data.ma_phong_ban) : '',
            ma_truong: data.ma_truong ? String(data.ma_truong) : '',
            chuyen_nganh: data.chuyen_nganh || '',
            trang_thai_xet_duyet: data.trang_thai_xet_duyet || 'ChoDuyet',
            trang_thai_thuc_tap: data.trang_thai_thuc_tap || 'DangThucTap'
          });
        })
        .catch((err) => {
          setErrorMsg(err.message);
        })
        .finally(() => {
          setLoadingInitial(false);
        });
    } else if (isOpen && !isEdit) {
      setFormData({
        ho_ten: '',
        email: '',
        so_dien_thoai: '',
        ma_phong_ban: departments.length > 0 ? String(departments[0].ma_phong_ban) : '',
        ma_truong: universities.length > 0 ? String(universities[0].ma_truong) : '',
        chuyen_nganh: '',
        trang_thai_xet_duyet: 'ChoDuyet',
        trang_thai_thuc_tap: 'DangThucTap'
      });
      setErrorMsg('');
    }
  }, [isOpen, internId, isEdit]);

  if (!isOpen) return null;

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErrorMsg('');

    try {
      const payload = {
        ho_ten: formData.ho_ten.trim(),
        email: formData.email.trim(),
        so_dien_thoai: formData.so_dien_thoai.trim(),
        ma_phong_ban: formData.ma_phong_ban ? parseInt(formData.ma_phong_ban, 10) : null,
        ma_truong: formData.ma_truong ? parseInt(formData.ma_truong, 10) : null,
        chuyen_nganh: formData.chuyen_nganh.trim(),
        trang_thai_xet_duyet: formData.trang_thai_xet_duyet,
        trang_thai_thuc_tap: formData.trang_thai_thuc_tap
      };

      let url = '/api/interns';
      let method = 'POST';

      if (isEdit) {
        url = `/api/interns/${internId}`;
        method = 'PUT';
      }

      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const resData = await res.json();
      if (!res.ok) {
        throw new Error(resData.detail || 'Thao tác không thành công');
      }

      onSuccess(isEdit ? 'Cập nhật thông tin thành công!' : 'Thêm thực tập sinh thành công!');
      onClose();
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-container" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h3>{isEdit ? 'Chỉnh sửa thông tin thực tập sinh' : 'Thêm thực tập sinh mới'}</h3>
          </div>
          <button className="modal-close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          {errorMsg && (
            <div className="alert-banner error" style={{ padding: '10px 14px', marginBottom: '16px' }}>
              <AlertCircle size={16} />
              <span>{errorMsg}</span>
            </div>
          )}

          {loadingInitial ? (
            <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>
              Đang tải dữ liệu...
            </div>
          ) : (
            <form id="internForm" onSubmit={handleSubmit} className="form-grid">
              <div className="form-group">
                <label className="form-label">
                  Họ và tên <span className="required">*</span>
                </label>
                <input
                  type="text"
                  name="ho_ten"
                  className="form-control"
                  placeholder="Ví dụ: Nguyễn Văn An"
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
                  placeholder="an.nguyen@example.com"
                  required
                  value={formData.email}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Số điện thoại</label>
                <input
                  type="text"
                  name="so_dien_thoai"
                  className="form-control"
                  placeholder="0912345678"
                  value={formData.so_dien_thoai}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Trường Đại học</label>
                <select
                  name="ma_truong"
                  className="form-select"
                  value={formData.ma_truong}
                  onChange={handleChange}
                >
                  <option value="">-- Chọn trường đại học --</option>
                  {universities.map((u) => (
                    <option key={u.ma_truong} value={u.ma_truong}>
                      {u.ten_truong}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Chuyên ngành</label>
                <input
                  type="text"
                  name="chuyen_nganh"
                  className="form-control"
                  placeholder="Công nghệ Thông tin"
                  value={formData.chuyen_nganh}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Phòng ban</label>
                <select
                  name="ma_phong_ban"
                  className="form-select"
                  value={formData.ma_phong_ban}
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
                <label className="form-label">Xét duyệt</label>
                <select
                  name="trang_thai_xet_duyet"
                  className="form-select"
                  value={formData.trang_thai_xet_duyet}
                  onChange={handleChange}
                >
                  <option value="ChoDuyet">Chờ duyệt</option>
                  <option value="DaDuyet">Đã duyệt</option>
                  <option value="TuChoi">Từ chối</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Trạng thái</label>
                <select
                  name="trang_thai_thuc_tap"
                  className="form-select"
                  value={formData.trang_thai_thuc_tap}
                  onChange={handleChange}
                >
                  <option value="DangThucTap">Đang thực tập</option>
                  <option value="HoanThanh">Hoàn thành</option>
                  <option value="ThoiHoc">Thôi học</option>
                </select>
              </div>
            </form>
          )}
        </div>

        <div className="modal-footer">
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose} disabled={loading}>
            Hủy
          </button>
          <button 
            type="submit" 
            form="internForm" 
            className="btn btn-primary btn-sm" 
            disabled={loading || loadingInitial}
          >
            <Save size={14} />
            <span>{loading ? 'Đang lưu...' : isEdit ? 'Lưu thay đổi' : 'Thêm mới'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
