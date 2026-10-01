import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Download, Eye, FileText, UploadCloud } from 'lucide-react';
import { apiFetch, readJsonResponse } from '../utils/api';

const MAX_CONTRACT_SIZE = 15 * 1024 * 1024;

function formatDate(value) {
  if (!value) return '—';
  const parsed = new Date(value.replace(' ', 'T') + (value.endsWith('Z') ? '' : 'Z'));
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('vi-VN');
}

export default function ContractManagementPanel({ interns, onShowToast }) {
  const [contracts, setContracts] = useState([]);
  const [selectedProfile, setSelectedProfile] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const requestContracts = useCallback(async () => {
    const rows = [];
    let page = 1;
    let totalPages = 1;
    do {
      const response = await apiFetch(`/api/contracts?page=${page}&pageSize=100`);
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể tải danh sách hợp đồng.');
      rows.push(...(Array.isArray(data.items) ? data.items : []));
      totalPages = Number(data.totalPages) || 0;
      page += 1;
    } while (page <= totalPages);
    return rows;
  }, []);

  useEffect(() => {
    let active = true;
    requestContracts()
      .then((rows) => { if (active) { setContracts(rows); setError(''); } })
      .catch((requestError) => { if (active) setError(requestError.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [requestContracts]);

  const refreshContracts = async () => {
    setLoading(true);
    try {
      setContracts(await requestContracts());
      setError('');
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };

  const uploadedProfiles = useMemo(
    () => new Set(contracts.map((contract) => String(contract.ma_ho_so))),
    [contracts],
  );
  const approvedInterns = useMemo(
    () => interns.filter((intern) => intern.trang_thai_xet_duyet === 'DaDuyet'),
    [interns],
  );
  const eligibleInterns = useMemo(
    () => approvedInterns.filter((intern) => !uploadedProfiles.has(String(intern.ma_ho_so))),
    [approvedInterns, uploadedProfiles],
  );

  const uploadContract = async (event) => {
    event.preventDefault();
    if (!selectedProfile || !selectedFile) {
      setError('Chọn hồ sơ đã duyệt và tệp hợp đồng PDF.');
      return;
    }
    if (!selectedFile.name.toLowerCase().endsWith('.pdf')
      || selectedFile.size === 0 || selectedFile.size > MAX_CONTRACT_SIZE) {
      setError('Hợp đồng phải là PDF có dung lượng từ 1 byte đến 15 MB.');
      return;
    }

    setUploading(true);
    setError('');
    try {
      const payload = new FormData();
      payload.append('ma_ho_so', selectedProfile);
      payload.append('file', selectedFile);
      const response = await apiFetch('/api/contracts', { method: 'POST', body: payload });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể tải hợp đồng lên.');
      onShowToast(`Đã tải hợp đồng của ${data.ho_ten} lên. Email thông báo đang được xử lý.`);
      setSelectedProfile('');
      setSelectedFile(null);
      await refreshContracts();
    } catch (uploadError) {
      setError(uploadError.message);
    } finally {
      setUploading(false);
    }
  };

  const openContract = async (contract) => {
    const preview = window.open('about:blank', '_blank');
    if (!preview) {
      onShowToast('Trình duyệt đã chặn cửa sổ xem hợp đồng.', 'error');
      return;
    }
    preview.opener = null;
    try {
      const response = await apiFetch(`/api/contracts/${contract.ma_hop_dong}/preview`);
      if (!response.ok) {
        const data = await readJsonResponse(response);
        throw new Error(data.detail || 'Không thể mở hợp đồng.');
      }
      const url = URL.createObjectURL(await response.blob());
      preview.location.replace(url);
      window.setTimeout(() => URL.revokeObjectURL(url), 5 * 60 * 1000);
    } catch (openError) {
      preview.close();
      onShowToast(openError.message, 'error');
    }
  };

  const downloadContract = async (contract) => {
    try {
      const response = await apiFetch(`/api/contracts/${contract.ma_hop_dong}/download`);
      if (!response.ok) {
        const data = await readJsonResponse(response);
        throw new Error(data.detail || 'Không thể tải hợp đồng.');
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = contract.original_file_name || 'hop-dong.pdf';
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
    } catch (downloadError) {
      onShowToast(downloadError.message, 'error');
    }
  };

  return (
    <section className="card contract-management-card" aria-labelledby="contract-management-title">
      <div className="card-header">
        <div className="card-title-box">
          <h2 id="contract-management-title">Hợp đồng thực tập</h2>
          <p>Tải PDF lên cho hồ sơ đã được duyệt. TTS nhận thông báo trong hệ thống và email.</p>
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={refreshContracts} disabled={loading}>
          Làm mới
        </button>
      </div>

      <form className="contract-upload-form" onSubmit={uploadContract}>
        <label className="form-group">
          <span className="form-label">Hồ sơ đã duyệt</span>
          <select className="form-select" value={selectedProfile} onChange={(event) => setSelectedProfile(event.target.value)} disabled={uploading} required>
            <option value="">-- Chọn thực tập sinh --</option>
            {eligibleInterns.map((intern) => (
              <option key={intern.ma_ho_so} value={intern.ma_ho_so}>{intern.ho_ten} · #{intern.ma_ho_so}</option>
            ))}
          </select>
        </label>
        <label className="contract-file-picker">
          <FileText size={18} />
          <span>{selectedFile?.name || 'Chọn hợp đồng PDF · tối đa 15 MB'}</span>
          <input type="file" accept=".pdf,application/pdf" disabled={uploading} onChange={(event) => { setSelectedFile(event.target.files?.[0] || null); event.target.value = ''; }} />
        </label>
        <button type="submit" className="btn btn-primary btn-sm" disabled={uploading || eligibleInterns.length === 0}>
          <UploadCloud size={15} />{uploading ? 'Đang tải lên…' : 'Tải hợp đồng'}
        </button>
      </form>
      {!eligibleInterns.length && !loading && <p className="contract-hint">Không có hồ sơ đã duyệt đang chờ hợp đồng.</p>}
      {error && <p className="contract-error" role="alert">{error}</p>}

      <div className="table-responsive contract-table-scroll">
        <table className="data-table contract-data-table">
          <thead><tr><th>Thực tập sinh</th><th>Tên tệp</th><th>Chương trình</th><th>Ngày tải</th><th>Trạng thái</th><th>Thao tác</th></tr></thead>
          <tbody>
            {loading ? <tr><td colSpan="6" className="contract-table-empty">Đang tải danh sách hợp đồng…</td></tr>
              : contracts.length === 0 ? <tr><td colSpan="6" className="contract-table-empty">Chưa có hợp đồng được tải lên.</td></tr>
                : contracts.map((contract) => (
                  <tr key={contract.ma_hop_dong}>
                    <td>{contract.ho_ten} · #{contract.ma_ho_so}</td>
                    <td>{contract.original_file_name}</td>
                    <td>{contract.ten_chuong_trinh || contract.ten_phong_ban || '—'}</td>
                    <td>{formatDate(contract.uploaded_at)}</td>
                    <td><span className="badge badge-warning"><span className="badge-dot" />Chờ xác nhận</span></td>
                    <td><div className="contract-row-actions">
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => openContract(contract)} title="Xem hợp đồng"><Eye size={14} /><span>Xem</span></button>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => downloadContract(contract)} title="Tải hợp đồng"><Download size={14} /><span>Tải</span></button>
                    </div></td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
