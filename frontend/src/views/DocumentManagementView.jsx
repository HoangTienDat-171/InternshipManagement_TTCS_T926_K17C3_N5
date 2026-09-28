import React, { useCallback, useEffect, useState } from 'react';
import { FolderUp, FileText, UploadCloud, Eye, Check, XCircle, RefreshCw } from 'lucide-react';
import { apiFetch, readJsonResponse } from '../utils/api';
import CustomSelect from '../components/CustomSelect';

const typeLabels = {
  CV: 'CV',
  DonXinThucTap: 'Đơn xin thực tập',
  GiayGioiThieu: 'Giấy giới thiệu',
};

const formatSize = (bytes) => {
  if (bytes == null) return '—';
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const formatDate = (value) => value ? new Date(value.replace(' ', 'T') + (value.endsWith('Z') ? '' : 'Z')).toLocaleString('vi-VN') : '—';

export default function DocumentManagementView({ currentUser, onShowToast }) {
  const canManage = ['Admin', 'HR'].includes(currentUser?.vai_tro);
  const [documents, setDocuments] = useState([]);
  const [interns, setInterns] = useState([]);
  const [selectedType, setSelectedType] = useState('CV');
  const [selectedIntern, setSelectedIntern] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const requestDocuments = useCallback(async () => {
    const response = await apiFetch('/api/documents');
    const data = await readJsonResponse(response);
    if (!response.ok) throw new Error(data.detail || 'Không thể tải danh sách tài liệu.');
    return data;
  }, []);

  const requestInterns = useCallback(async () => {
    const response = await apiFetch('/api/interns');
    const data = await readJsonResponse(response);
    if (!response.ok) throw new Error(data.detail || 'Không thể tải danh sách thực tập sinh.');
    return data;
  }, []);

  const refreshData = async () => {
    setLoading(true);
    try {
      const [documentRows, internRows] = await Promise.all([requestDocuments(), requestInterns()]);
      setDocuments(documentRows);
      setInterns(internRows);
      setSelectedIntern((previous) => previous || (internRows[0] ? String(internRows[0].ma_ho_so) : ''));
      setErrorMsg('');
    } catch (error) {
      setErrorMsg(error.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let current = true;
    Promise.all([requestDocuments(), requestInterns()])
      .then(([documentRows, internRows]) => {
        if (!current) return;
        setDocuments(documentRows);
        setInterns(internRows);
        setSelectedIntern(internRows[0] ? String(internRows[0].ma_ho_so) : '');
      })
      .catch((error) => { if (current) setErrorMsg(error.message); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [requestDocuments, requestInterns]);

  const uploadDocument = async (event) => {
    event.preventDefault();
    if (!selectedIntern || !selectedFile) {
      onShowToast('Hãy chọn hồ sơ thực tập sinh và tệp cần tải lên.', 'error');
      return;
    }
    if (selectedFile.size > 15 * 1024 * 1024) {
      onShowToast('Tệp không được vượt quá 15 MB.', 'error');
      return;
    }

    const payload = new FormData();
    payload.append('ma_ho_so', selectedIntern);
    payload.append('loai_tai_lieu', selectedType);
    payload.append('file', selectedFile);
    setUploading(true);
    try {
      const response = await apiFetch('/api/documents', { method: 'POST', body: payload });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể tải tài liệu lên.');
      onShowToast(`Đã lưu tài liệu: ${data.ten_file}`);
      setSelectedFile(null);
      document.getElementById('docUploadInput').value = '';
      await refreshData();
    } catch (error) {
      onShowToast(error.message, 'error');
    } finally {
      setUploading(false);
    }
  };

  const reviewDocument = async (item, reviewStatus) => {
    try {
      const response = await apiFetch(`/api/documents/${item.ma_tai_lieu}/review`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trang_thai_duyet: reviewStatus }),
      });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể cập nhật trạng thái tài liệu.');
      onShowToast(reviewStatus === 'DaDuyet' ? 'Đã duyệt tài liệu.' : 'Đã từ chối tài liệu.');
      setDocuments((previous) => previous.map((documentItem) => documentItem.ma_tai_lieu === item.ma_tai_lieu ? data : documentItem));
    } catch (error) {
      onShowToast(error.message, 'error');
    }
  };

  const openDocument = async (item) => {
    const preview = window.open('about:blank', '_blank');
    if (!preview) {
      onShowToast('Trình duyệt đã chặn cửa sổ xem tài liệu.', 'error');
      return;
    }
    preview.opener = null;
    try {
      const response = await apiFetch(`/api/documents/${item.ma_tai_lieu}/file`);
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Không thể mở tài liệu.');
      }
      const url = URL.createObjectURL(await response.blob());
      preview.location.href = url;
      window.setTimeout(() => URL.revokeObjectURL(url), 5 * 60 * 1000);
    } catch (error) {
      preview.close();
      onShowToast(error.message, 'error');
    }
  };

  const statusBadge = (value) => {
    const options = {
      DaDuyet: ['badge-success', 'Đã duyệt'],
      TuChoi: ['badge-danger', 'Từ chối'],
      ChoDuyet: ['badge-warning', 'Chờ duyệt'],
    };
    const [badge, label] = options[value] || ['badge-secondary', value];
    return <span className={`badge ${badge}`}><span className="badge-dot" /> {label}</span>;
  };

  if (!canManage) {
    return <div className="card" style={{ padding: '36px', textAlign: 'center' }}>Chức năng quản lý tài liệu chỉ dành cho Admin và Quản lý thực tập sinh.</div>;
  }

  return (
    <div className="document-management-page">
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>Quản lý Tài liệu Hồ sơ</h2>
        <p style={{ fontSize: '13px', color: '#64748b' }}>Tài liệu được lưu cùng hồ sơ thực tập sinh và có thể xem lại sau khi tải lên.</p>
      </div>

      {errorMsg && <div className="alert-banner error" role="alert" style={{ marginBottom: '16px' }}>{errorMsg}</div>}

      <form className="card document-upload-card" style={{ marginBottom: '24px' }} onSubmit={uploadDocument}>
        <div className="card-header"><div className="card-title-box"><h2>Tải lên tài liệu mới</h2></div></div>
        <div className="card-body document-upload-body">
          <div className="form-grid document-upload-fields">
            <div className="form-group">
              <label className="form-label" htmlFor="document-intern">Thực tập sinh nộp tài liệu</label>
              <CustomSelect id="document-intern" className="form-select" value={selectedIntern} required onChange={(event) => setSelectedIntern(event.target.value)}>
                <option value="">-- Chọn hồ sơ --</option>
                {interns.map((intern) => <option key={intern.ma_ho_so} value={intern.ma_ho_so}>{intern.ho_ten} · #{intern.ma_ho_so}</option>)}
              </CustomSelect>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="document-type">Loại tài liệu</label>
              <CustomSelect id="document-type" className="form-select" value={selectedType} onChange={(event) => setSelectedType(event.target.value)}>
                <option value="CV">CV ứng tuyển</option>
                <option value="DonXinThucTap">Đơn xin thực tập</option>
                <option value="GiayGioiThieu">Giấy giới thiệu từ nhà trường</option>
              </CustomSelect>
            </div>
          </div>

          <label className="upload-dropzone document-upload-dropzone" htmlFor="docUploadInput" onDragOver={(event) => event.preventDefault()} onDrop={(event) => {
            event.preventDefault();
            const droppedFile = event.dataTransfer.files?.[0];
            if (droppedFile) setSelectedFile(droppedFile);
          }}>
            <span className="upload-icon-circle"><UploadCloud size={24} /></span>
            <span style={{ fontWeight: 600, fontSize: '14px', marginBottom: '4px', color: '#0f172a' }}>
              {selectedFile ? `Đã chọn: ${selectedFile.name}` : 'Kéo thả tệp vào đây hoặc nhấn để chọn file'}
            </span>
            <span style={{ fontSize: '12px', color: '#64748b' }}>Hỗ trợ PDF, DOCX, PNG · Tối đa 15 MB</span>
          </label>
          <input id="docUploadInput" type="file" accept=".pdf,.docx,.png" hidden onChange={(event) => setSelectedFile(event.target.files?.[0] || null)} />

          <div className="document-upload-actions">
            <button type="submit" className="btn btn-primary btn-sm" disabled={uploading || interns.length === 0}>
              <FolderUp size={15} /><span>{uploading ? 'Đang tải lên...' : 'Tải lên tệp'}</span>
            </button>
          </div>
        </div>
      </form>

      <div className="card">
        <div className="card-header">
          <div className="card-title-box"><h2>Tài liệu đã lưu trữ{loading || errorMsg ? '' : ` (${documents.length})`}</h2></div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={refreshData} disabled={loading}>
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /><span>Làm mới</span>
          </button>
        </div>
        <div className="table-responsive document-table-scroll">
          <table className="data-table document-data-table">
            <thead><tr>
              <th>Tên tệp</th><th>Thực tập sinh</th><th>Phân loại</th><th>Dung lượng</th>
              <th>Thời gian tải lên</th><th>Trạng thái</th><th style={{ textAlign: 'right' }}>Thao tác</th>
            </tr></thead>
            <tbody>
              {loading ? <tr><td colSpan="7" style={{ textAlign: 'center', padding: '30px' }}>Đang tải dữ liệu...</td></tr>
                : errorMsg ? <tr><td colSpan="7" style={{ textAlign: 'center', padding: '30px', color: '#b91c1c' }}>Không thể xác nhận danh sách tài liệu. Hãy thử làm mới.</td></tr>
                  : documents.length === 0 ? <tr><td colSpan="7" style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>Chưa có tài liệu được lưu trữ.</td></tr>
                    : documents.map((item) => <tr key={item.ma_tai_lieu}>
                    <td><div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><FileText size={16} color="var(--primary-600)" /><span style={{ fontWeight: 500, color: '#0f172a' }}>{item.ten_file}</span></div></td>
                    <td>{item.thuc_tap_sinh}</td>
                    <td><span className="badge badge-info">{typeLabels[item.loai_tai_lieu] || item.loai_tai_lieu}</span></td>
                    <td style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{formatSize(item.kich_thuoc)}</td>
                    <td style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{formatDate(item.ngay_tai_len)}</td>
                    <td>{statusBadge(item.trang_thai_duyet)}</td>
                    <td style={{ textAlign: 'right' }}><div style={{ display: 'inline-flex', gap: '6px' }}>
                      <button type="button" className="btn btn-secondary btn-sm" title="Xem tài liệu" onClick={() => openDocument(item)}><Eye size={13} /><span>Xem</span></button>
                      {item.trang_thai_duyet === 'ChoDuyet' && <>
                        <button type="button" className="btn btn-primary btn-sm" title="Duyệt tài liệu" onClick={() => reviewDocument(item, 'DaDuyet')}><Check size={13} /><span>Duyệt</span></button>
                        <button type="button" className="btn btn-danger btn-sm" title="Từ chối tài liệu" onClick={() => reviewDocument(item, 'TuChoi')}><XCircle size={13} /><span>Từ chối</span></button>
                      </>}
                    </div></td>
                  </tr>)}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
