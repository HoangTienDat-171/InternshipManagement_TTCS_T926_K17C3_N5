import React, { useState } from 'react';
import { FolderUp, FileText, UploadCloud, Eye } from 'lucide-react';

export default function DocumentManagementView({ onShowToast }) {
  const [documents, setDocuments] = useState([
    {
      id: 1,
      ten_file: 'CV_LeMinhTuan_Backend.pdf',
      thuc_tap_sinh: 'Lê Minh Tuấn',
      loai_tai_lieu: 'CV',
      dung_luong: '2.4 MB',
      ngay_upload: '24/09/2026 14:30',
      trang_thai: 'DaDuyet'
    },
    {
      id: 2,
      ten_file: 'Don_Xin_Thuc_Tap_LeMinhTuan.docx',
      thuc_tap_sinh: 'Lê Minh Tuấn',
      loai_tai_lieu: 'DonXinThucTap',
      dung_luong: '512 KB',
      ngay_upload: '24/09/2026 14:35',
      trang_thai: 'ChoDuyet'
    },
    {
      id: 3,
      ten_file: 'Giay_Gioi_Thieu_HUST_HoangLanAnh.pdf',
      thuc_tap_sinh: 'Hoàng Lan Anh',
      loai_tai_lieu: 'GiayGioiThieu',
      dung_luong: '1.1 MB',
      ngay_upload: '24/09/2026 16:10',
      trang_thai: 'ChoDuyet'
    }
  ]);

  const [selectedType, setSelectedType] = useState('CV');
  const [selectedIntern, setSelectedIntern] = useState('Lê Minh Tuấn');
  const [fakeFileName, setFakeFileName] = useState('');

  const handleSimulatedUpload = (e) => {
    e.preventDefault();
    const fileName = fakeFileName || (selectedType === 'CV' ? 'CV_Ung_Vien.pdf' : 'Don_Xin_Thuc_Tap.pdf');
    const newDoc = {
      id: Date.now(),
      ten_file: fileName,
      thuc_tap_sinh: selectedIntern,
      loai_tai_lieu: selectedType,
      dung_luong: '1.5 MB',
      ngay_upload: 'Vừa xong',
      trang_thai: 'ChoDuyet'
    };

    setDocuments([newDoc, ...documents]);
    onShowToast(`Đã tải lên tệp: ${fileName}`);
    setFakeFileName('');
  };

  const getDocTypeBadge = (type) => {
    switch (type) {
      case 'CV':
        return <span className="badge badge-info">CV</span>;
      case 'DonXinThucTap':
        return <span className="badge badge-warning">Đơn xin thực tập</span>;
      case 'GiayGioiThieu':
        return <span className="badge badge-success">Giấy giới thiệu</span>;
      default:
        return <span className="badge badge-secondary">{type}</span>;
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'DaDuyet':
        return <span className="badge badge-success"><span className="badge-dot" /> Đã duyệt</span>;
      case 'TuChoi':
        return <span className="badge badge-danger"><span className="badge-dot" /> Từ chối</span>;
      default:
        return <span className="badge badge-warning"><span className="badge-dot" /> Chờ duyệt</span>;
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>Quản lý Tài liệu Hồ sơ</h2>
          <p style={{ fontSize: '13px', color: '#64748b' }}>
            Tiếp nhận và quản lý CV, đơn xin thực tập và giấy giới thiệu từ trường
          </p>
        </div>
      </div>

      {/* Upload Zone Card */}
      <div className="card" style={{ marginBottom: '24px' }}>
        <div className="card-header">
          <div className="card-title-box">
            <h2>Tải lên tài liệu mới</h2>
          </div>
        </div>

        <div className="card-body">
          <div className="form-grid" style={{ marginBottom: '18px' }}>
            <div className="form-group">
              <label className="form-label">Thực tập sinh nộp tài liệu</label>
              <select
                className="form-select"
                value={selectedIntern}
                onChange={(e) => setSelectedIntern(e.target.value)}
              >
                <option value="Lê Minh Tuấn">Lê Minh Tuấn</option>
                <option value="Hoàng Lan Anh">Hoàng Lan Anh</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Loại tài liệu</label>
              <select
                className="form-select"
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value)}
              >
                <option value="CV">CV Ứng tuyển</option>
                <option value="DonXinThucTap">Đơn xin thực tập</option>
                <option value="GiayGioiThieu">Giấy giới thiệu từ Nhà trường</option>
              </select>
            </div>
          </div>

          <div 
            className="upload-dropzone"
            onClick={() => document.getElementById('docUploadInput').click()}
          >
            <div className="upload-icon-circle">
              <UploadCloud size={24} />
            </div>
            <div style={{ fontWeight: 600, fontSize: '14px', marginBottom: '4px', color: '#0f172a' }}>
              {fakeFileName ? `Đã chọn: ${fakeFileName}` : 'Kéo thả tệp vào đây hoặc nhấn để chọn file'}
            </div>
            <p style={{ fontSize: '12px', color: '#64748b' }}>
              Hỗ trợ định dạng PDF, DOCX, PNG (Tối đa 15MB)
            </p>

            <input
              type="file"
              id="docUploadInput"
              style={{ display: 'none' }}
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  setFakeFileName(e.target.files[0].name);
                }
              }}
            />
          </div>

          <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'flex-end' }}>
            <button 
              type="button" 
              className="btn btn-primary btn-sm"
              onClick={handleSimulatedUpload}
            >
              <FolderUp size={15} />
              <span>Tải lên tệp</span>
            </button>
          </div>
        </div>
      </div>

      {/* Danh sách tài liệu */}
      <div className="card">
        <div className="card-header">
          <div className="card-title-box">
            <h2>Tài liệu đã lưu trữ ({documents.length})</h2>
          </div>
        </div>

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Tên tệp</th>
                <th>Thực tập sinh</th>
                <th>Phân loại</th>
                <th>Dung lượng</th>
                <th>Thời gian tải lên</th>
                <th>Trạng thái</th>
                <th style={{ textAlign: 'right' }}>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <FileText size={16} color="var(--primary-600)" />
                      <span style={{ fontWeight: 500, color: '#0f172a' }}>{doc.ten_file}</span>
                    </div>
                  </td>
                  <td>{doc.thuc_tap_sinh}</td>
                  <td>{getDocTypeBadge(doc.loai_tai_lieu)}</td>
                  <td style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{doc.dung_luong}</td>
                  <td style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{doc.ngay_upload}</td>
                  <td>{getStatusBadge(doc.trang_thai)}</td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      className="btn btn-secondary btn-sm"
                      title="Xem trước tài liệu"
                      onClick={() => onShowToast(`Mở tệp: ${doc.ten_file}`)}
                    >
                      <Eye size={13} />
                      <span>Xem</span>
                    </button>
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
