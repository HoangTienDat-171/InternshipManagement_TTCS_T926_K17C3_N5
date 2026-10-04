import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowRight, BriefcaseBusiness, Building2, CalendarDays, CircleCheck, Clock3, Download, Eye, FileText, FileType2, GraduationCap, Mail, Phone, Trash2, UploadCloud, UserRound, X } from 'lucide-react';
import ConfirmDialog from '../components/ConfirmDialog';
import ContractDetailView from './ContractDetailView';
import CustomSelect from '../components/CustomSelect';
import { apiFetch, apiUploadWithProgress, downloadProtectedFile, readJsonResponse } from '../utils/api';

const documentStatus = { ChoDuyet: 'Chờ duyệt', DaDuyet: 'Đã duyệt', TuChoi: 'Bị từ chối' };
const applicationStatus = { ChoDuyet: 'Chờ duyệt', DaDuyet: 'Đã duyệt', TuChoi: 'Từ chối' };
const MAX_DOCUMENT_FILE_SIZE = 5 * 1024 * 1024;
const DOCUMENT_ACCEPT = '.pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const documentTypeLabels = { CV: 'CV', DonXinThucTap: 'Đơn xin thực tập' };

function documentExtension(fileName = '') {
  return fileName.split('.').pop()?.toLowerCase() || '';
}

function validateDocumentFile(file) {
  const extension = documentExtension(file.name);
  if (!['pdf', 'doc', 'docx'].includes(extension)) return 'Chỉ nhận tệp PDF, DOC hoặc DOCX.';
  if (!file.size) return 'Tệp không được để trống.';
  if (file.size > MAX_DOCUMENT_FILE_SIZE) return 'Dung lượng tệp tối đa là 5 MB.';
  return '';
}

function formatDocumentSize(bytes) {
  const size = Number(bytes);
  if (!Number.isFinite(size) || size <= 0) return '';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

const contractStatus = {
  PENDING_CONFIRMATION: { label: 'Chờ xác nhận', tone: 'warning' },
  CONFIRMED: { label: 'Đã xác nhận', tone: 'success' },
  REJECTED: { label: 'Đã từ chối', tone: 'danger' },
};

function StatusPill({ status, map = documentStatus }) {
  const tone = status === 'DaDuyet' ? 'success' : status === 'ChoDuyet' ? 'warning' : 'danger';
  return <span className={`workspace-status is-${tone}`}><i />{map[status] || status || 'Chưa cập nhật'}</span>;
}

export default function InternWorkspaceView({ currentUser, onNavigatePrograms, requestedContractId, onShowToast }) {
  const [workspace, setWorkspace] = useState(null);
  const [contracts, setContracts] = useState([]);
  const [selectedContractId, setSelectedContractId] = useState(requestedContractId || null);
  const [loading, setLoading] = useState(true);
  const [contractLoading, setContractLoading] = useState(true);
  const [error, setError] = useState('');
  const [contractError, setContractError] = useState('');
  const [contractPreviewUrl, setContractPreviewUrl] = useState('');
  const [previewingContractId, setPreviewingContractId] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState('');
  const [documentFilter, setDocumentFilter] = useState('all');
  const [uploadType, setUploadType] = useState('CV');
  const [documentDialog, setDocumentDialog] = useState(null);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState('');
  const [dragActive, setDragActive] = useState(false);
  const [previewDocument, setPreviewDocument] = useState(null);
  const [documentPreviewUrl, setDocumentPreviewUrl] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');
  const [documentToDelete, setDocumentToDelete] = useState(null);
  const [deletingDocumentId, setDeletingDocumentId] = useState(null);
  const [documentActionError, setDocumentActionError] = useState('');
  const fileInput = useRef(null);
  const documentPreviewController = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const [workspaceResponse, contractResponse] = await Promise.all([
        apiFetch('/api/interns/me/workspace'),
        apiFetch('/api/contracts/mine/all'),
      ]);
      const [data, contractData] = await Promise.all([
        readJsonResponse(workspaceResponse),
        readJsonResponse(contractResponse),
      ]);
      if (!workspaceResponse.ok) throw new Error(data.detail || 'Không thể tải hồ sơ thực tập.');
      if (!contractResponse.ok) throw new Error(contractData.detail || 'Không thể tải hợp đồng của bạn.');
      setWorkspace(data);
      setContracts(Array.isArray(contractData) ? contractData : contractData ? [contractData] : []);
      setContractError('');
      setError('');
    } catch (err) { setError(err.message); }
    finally { setLoading(false); setContractLoading(false); }
  }, []);

  const previewContract = useCallback(async (contractId) => {
    if (!contractId) return;
    if (Number(previewingContractId) === Number(contractId)) {
      setPreviewingContractId(null);
      setContractPreviewUrl('');
      return;
    }
    try {
      const response = await apiFetch(`/api/contracts/${contractId}/preview`);
      if (!response.ok) {
        const data = await readJsonResponse(response);
        throw new Error(data.detail || 'Không thể xem trước hợp đồng.');
      }
      const nextUrl = URL.createObjectURL(await response.blob());
      setContractError('');
      setPreviewingContractId(contractId);
      setContractPreviewUrl(nextUrl);
    } catch (previewError) {
      setContractError(previewError.message);
    }
  }, [previewingContractId]);

  useEffect(() => () => {
    if (contractPreviewUrl) URL.revokeObjectURL(contractPreviewUrl);
  }, [contractPreviewUrl]);

  useEffect(() => () => documentPreviewController.current?.abort(), []);

  useEffect(() => () => {
    if (documentPreviewUrl) URL.revokeObjectURL(documentPreviewUrl);
  }, [documentPreviewUrl]);

  useEffect(() => {
    if (!selectedContractId) void Promise.resolve().then(refresh);
    const updateWorkspace = () => { if (!selectedContractId) void refresh(); };
    window.addEventListener('ims-workspace-updated', updateWorkspace);
    return () => window.removeEventListener('ims-workspace-updated', updateWorkspace);
  }, [refresh, selectedContractId]);

  const download = async (document) => {
    try { await downloadProtectedFile(document.ma_tai_lieu, document.ten_file); }
    catch (err) { setError(err.message); }
  };

  const openUploadDialog = () => {
    setUploadFile(null);
    setUploadError('');
    setUploadProgress(0);
    setDragActive(false);
    setUploadMessage('');
    setUploadType(documentFilter === 'all' ? 'CV' : documentFilter);
    setDocumentDialog('upload');
  };

  const closeDocumentDialog = useCallback(() => {
    if (uploading) return;
    documentPreviewController.current?.abort();
    documentPreviewController.current = null;
    setDocumentDialog(null);
    setDragActive(false);
    setPreviewDocument(null);
    setDocumentPreviewUrl('');
    setPreviewError('');
    setPreviewLoading(false);
    setDocumentToDelete(null);
    setDocumentActionError('');
  }, [uploading]);

  useEffect(() => {
    if (!['upload', 'preview'].includes(documentDialog) || uploading) return undefined;
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') closeDocumentDialog();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [closeDocumentDialog, documentDialog, uploading]);

  const chooseUploadFile = (file) => {
    if (!file) return;
    const validationError = validateDocumentFile(file);
    setUploadFile(validationError ? null : file);
    setUploadError(validationError);
    setUploadProgress(0);
  };

  const previewDocumentFile = async (item) => {
    documentPreviewController.current?.abort();
    setPreviewDocument(item);
    setDocumentPreviewUrl('');
    setPreviewError('');
    setPreviewLoading(false);
    setDocumentDialog('preview');
    const extension = documentExtension(item.ten_file || '');
    if (!['pdf', 'png'].includes(extension)) return;

    const controller = new AbortController();
    documentPreviewController.current = controller;
    setPreviewLoading(true);
    try {
      const response = await apiFetch(`/api/documents/${item.ma_tai_lieu}/file`, { signal: controller.signal });
      if (!response.ok) {
        const data = await readJsonResponse(response);
        throw new Error(data.detail || 'Không thể xem trước tài liệu.');
      }
      setDocumentPreviewUrl(URL.createObjectURL(await response.blob()));
    } catch (previewError) {
      if (previewError.name !== 'AbortError') setPreviewError(previewError.message);
    } finally {
      if (documentPreviewController.current === controller) setPreviewLoading(false);
    }
  };

  const deleteDocument = async () => {
    if (!documentToDelete) return;
    setDeletingDocumentId(documentToDelete.ma_tai_lieu);
    setDocumentActionError('');
    try {
      const response = await apiFetch(`/api/documents/${documentToDelete.ma_tai_lieu}`, { method: 'DELETE' });
      if (!response.ok) {
        const data = await readJsonResponse(response);
        throw new Error(data.detail || 'Không thể xóa tài liệu.');
      }
      setDocumentDialog(null);
      setDocumentToDelete(null);
      setUploadMessage('Đã xóa tài liệu khỏi hồ sơ.');
      await refresh();
    } catch (deleteError) {
      setDocumentActionError(deleteError.message);
    } finally {
      setDeletingDocumentId(null);
    }
  };

  const downloadContract = async (contractItem) => {
    try {
      const response = await apiFetch(`/api/contracts/${contractItem.ma_hop_dong}/download`);
      if (!response.ok) {
        const data = await readJsonResponse(response);
        throw new Error(data.detail || 'Không thể tải hợp đồng.');
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = contractItem.original_file_name || 'hop-dong.pdf';
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
    } catch (downloadError) {
      setContractError(downloadError.message);
    }
  };

  const uploadDocument = async () => {
    if (!uploadFile) return;
    const validationError = validateDocumentFile(uploadFile);
    if (validationError) {
      setUploadError(validationError);
      return;
    }
    setUploading(true);
    setError('');
    setUploadError('');
    setUploadMessage('');
    setUploadProgress(0);
    try {
      const formData = new FormData();
      formData.append('loai_tai_lieu', uploadType);
      formData.append('file', uploadFile);
      const response = await apiUploadWithProgress('/api/documents', formData, setUploadProgress);
      if (!response.ok) throw new Error(response.data.detail || 'Không thể nộp tài liệu.');
      setUploadMessage(`Đã nộp ${documentTypeLabels[uploadType]} thành công. Hồ sơ đang chờ duyệt.`);
      setUploadFile(null);
      setDocumentDialog(null);
      await refresh();
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
    }
  };

  if (selectedContractId) return <ContractDetailView
    contractId={selectedContractId}
    currentUser={currentUser}
    onBack={() => {
      setSelectedContractId(null);
      setLoading(true);
      setContractLoading(true);
      setContractPreviewUrl('');
      setPreviewingContractId(null);
    }}
    onShowToast={onShowToast}
  />;

  if (loading && !workspace) return <div className="workspace-page"><div className="workspace-loading">Đang tải hồ sơ của bạn…</div></div>;
  if (error && !workspace) return <div className="workspace-page"><div className="workspace-error">{error}<button className="btn btn-secondary btn-sm" onClick={() => { setLoading(true); refresh(); }}>Thử lại</button></div></div>;
  if (!workspace) return null;

  const { profile, mentor, documents: workspaceDocuments, applications, current_program: currentProgram, progress_percent: progress } = workspace;
  const documents = Array.isArray(workspaceDocuments) ? workspaceDocuments : [];
  const visibleDocuments = documents.filter((item) => documentFilter === 'all' || item.loai_tai_lieu === documentFilter);
  const pendingApplications = applications.filter((application) => application.trang_thai_ung_tuyen === 'ChoDuyet').length;
  return <div className="workspace-page">
    <header className="workspace-heading"><div><span className="workspace-eyebrow">KHÔNG GIAN THỰC TẬP</span><h2>Xin chào, {profile.ho_ten || currentUser.ho_ten}</h2><p>Theo dõi người hướng dẫn, hồ sơ và chương trình thực tập của bạn.</p></div><div className="intern-workspace-actions"><button type="button" className="btn btn-secondary" onClick={onNavigatePrograms}><CalendarDays size={15} />Chương trình đang mở<ArrowRight size={14} /></button><button type="button" className="btn btn-secondary" disabled={loading} onClick={() => { setLoading(true); refresh(); }}><Clock3 size={15} />Làm mới</button></div></header>
    {error && <div className="workspace-error compact">{error}</div>}
    <div className="workspace-summary-grid">
      <article className="workspace-card intern-identity-card"><div className="workspace-card-icon"><GraduationCap size={19} /></div><div><span>MÃ HỒ SƠ</span><strong>#{profile.ma_ho_so}</strong><small>{profile.ten_truong || 'Chưa cập nhật trường'} · {profile.chuyen_nganh || 'Chưa cập nhật ngành'}</small></div><StatusPill status={profile.trang_thai_xet_duyet} map={applicationStatus} /></article>
      <article className="workspace-card workspace-mentor-card"><div className="workspace-section-heading"><div><span className="workspace-eyebrow">NGƯỜI HƯỚNG DẪN</span><h3>{mentor?.ho_ten || 'Chưa được phân công'}</h3></div><span className="workspace-card-icon"><UserRound size={18} /></span></div>
        {mentor ? <div className="workspace-contact-grid"><span><Mail size={14} />{mentor.email}</span><span><Phone size={14} />{mentor.so_dien_thoai || 'Chưa cập nhật SĐT'}</span><span><Building2 size={14} />{mentor.phong_ban || 'Chưa phân phòng'}</span><span><BriefcaseBusiness size={14} />{mentor.chuyen_mon || 'Chưa cập nhật chuyên môn'} · {mentor.kinh_nghiem == null ? 'Chưa cập nhật kinh nghiệm' : `${mentor.kinh_nghiem} năm kinh nghiệm`}</span></div> : <p className="workspace-muted">{profile.trang_thai_xet_duyet === 'DaDuyet' ? 'Hồ sơ đã được duyệt. Quản trị viên sẽ sớm phân công người hướng dẫn.' : 'Người hướng dẫn sẽ được phân công sau khi hồ sơ của bạn được duyệt.'}</p>}
      </article>
    </div>

    <article className="workspace-card workspace-program-card"><div className="workspace-section-heading"><div><span className="workspace-eyebrow">CHƯƠNG TRÌNH HIỆN TẠI</span><h3>{currentProgram?.ten_ct || 'Chưa tham gia chương trình nào'}</h3></div>{currentProgram && <StatusPill status={currentProgram.trang_thai_ung_tuyen} map={applicationStatus} />}</div>
      {currentProgram ? <><div className="workspace-program-meta"><span><CalendarDays size={15} />{currentProgram.ngay_bat_dau} – {currentProgram.ngay_ket_thuc}</span><span>{currentProgram.ma_ct}</span></div><div className="workspace-progress"><div><strong>Tiến độ thực tập</strong><b>{progress ?? 0}%</b></div><span className="workspace-progress-track"><i style={{ width: `${progress ?? 0}%` }} /></span></div></> : <div className="intern-program-empty"><p className="workspace-muted">{pendingApplications ? `Bạn đang có ${pendingApplications} hồ sơ chờ xét duyệt. Kết quả sẽ được cập nhật trong mục theo dõi đăng ký.` : 'Chưa có chương trình nào được duyệt. Khám phá các đợt đang mở để gửi hồ sơ.'}</p><button type="button" className="btn btn-secondary btn-sm" onClick={onNavigatePrograms}>Xem chương trình đang mở<ArrowRight size={14} /></button></div>}
    </article>

    <div className="workspace-lower-grid">
      <article className="workspace-card intern-submitted-documents">
        <div className="workspace-section-heading intern-documents-heading">
          <div><span className="workspace-eyebrow">HỒ SƠ ĐÃ NỘP</span><h3>Tài liệu & CV <small>{documents.length}</small></h3></div>
          <label className="intern-document-filter"><span>Lọc loại tài liệu</span>
            <CustomSelect className="form-select" aria-label="Lọc tài liệu đã nộp" value={documentFilter} onChange={(event) => setDocumentFilter(event.target.value)}>
              <option value="all">Tất cả tài liệu</option><option value="CV">CV</option><option value="DonXinThucTap">Đơn xin thực tập</option>
            </CustomSelect>
          </label>
        </div>
        <button type="button" className="intern-document-upload-trigger" onClick={openUploadDialog}>
          <span className="intern-document-upload-icon"><UploadCloud size={19} /></span>
          <span className="intern-document-upload-copy"><strong>Nộp CV</strong><small>PDF, DOC hoặc DOCX · Tối đa 5 MB</small></span>
          <span className="intern-document-upload-action">Chọn tệp <ArrowRight size={15} /></span>
        </button>
        {uploadMessage && <p className="intern-document-feedback is-success" role="status"><CircleCheck size={15} />{uploadMessage}</p>}
        {visibleDocuments.length ? <div className="intern-document-list">{visibleDocuments.map((item) => {
          const extension = documentExtension(item.ten_file || '');
          const extensionLabel = extension ? extension.toUpperCase() : 'FILE';
          const fileSize = formatDocumentSize(item.kich_thuoc);
          return <div className="intern-document-row" key={item.ma_tai_lieu}>
            <span className={`intern-document-file-icon is-${['pdf', 'doc', 'docx', 'png'].includes(extension) ? extension : 'other'}`} aria-label={`Tệp ${extensionLabel}`}>
              <FileType2 size={18} /><small>{extensionLabel}</small>
            </span>
            <div className="intern-document-details">
              <strong title={item.ten_file || item.loai_tai_lieu}>{item.ten_file || item.loai_tai_lieu}</strong>
              <small>{documentTypeLabels[item.loai_tai_lieu] || item.loai_tai_lieu} · {item.ngay_tai_len || 'Ngày tải chưa rõ'}{fileSize ? ` · ${fileSize}` : ''}</small>
            </div>
            <StatusPill status={item.trang_thai_duyet} />
            <div className="intern-document-actions">
              <button type="button" className="intern-document-action" aria-label={`Xem trước ${item.ten_file || 'tài liệu'}`} title="Xem trước" onClick={() => previewDocumentFile(item)}><Eye size={15} /><span>Xem trước</span></button>
              <button type="button" className="intern-document-action" aria-label={`Tải về ${item.ten_file || 'tài liệu'}`} title="Tải về" onClick={() => download(item)}><Download size={15} /><span>Tải về</span></button>
              <button type="button" className="intern-document-action is-danger" aria-label={`Xóa ${item.ten_file || 'tài liệu'}`} title="Xóa" onClick={() => { setDocumentToDelete(item); setDocumentActionError(''); setDocumentDialog('delete'); }}><Trash2 size={15} /><span>Xóa</span></button>
            </div>
          </div>;
        })}</div> : <div className="intern-document-empty"><span><FileText size={20} /></span><strong>{documents.length ? 'Không có tài liệu phù hợp bộ lọc.' : 'Bạn chưa nộp tài liệu nào.'}</strong><small>{documents.length ? 'Hãy chọn loại tài liệu khác để xem danh sách.' : 'Chọn Nộp CV để tải hồ sơ PDF, DOC hoặc DOCX lên.'}</small></div>}
      </article>
      <article className="workspace-card"><div className="workspace-section-heading"><div><span className="workspace-eyebrow">THEO DÕI ĐĂNG KÝ</span><h3>Chương trình đã ứng tuyển <small>{applications.length}</small></h3></div><CircleCheck size={19} /></div>
        {applications.length ? <div className="workspace-application-list">{applications.map((application) => <div className="workspace-application-row" key={application.ma_chuong_trinh}><div><strong>{application.ten_ct}</strong><small>{application.ma_ct} · Nộp {application.ngay_ung_tuyen || '—'}</small></div><StatusPill status={application.trang_thai_ung_tuyen} map={applicationStatus} /></div>)}</div> : <div className="workspace-empty"><CalendarDays size={22} /><span>Bạn chưa ứng tuyển chương trình nào.</span></div>}
      </article>
    </div>
    <article className="workspace-card workspace-contract-card">
      <div className="workspace-section-heading">
        <div><span className="workspace-eyebrow">TÀI LIỆU CỦA BẠN</span><h3>Hợp đồng thực tập <small>{contracts.length}</small></h3></div>
      </div>
      {contractLoading ? <div className="workspace-empty"><span>Đang tải hợp đồng…</span></div>
        : contracts.length ? <div className="workspace-contract-list">
          {contracts.map((contract) => {
            const presentation = contractStatus[contract.trang_thai] || { label: 'Chưa cập nhật', tone: 'warning' };
            const isPreviewing = Number(previewingContractId) === Number(contract.ma_hop_dong);
            return <div className="workspace-contract-item" id={`internship-contract-${contract.ma_hop_dong}`} key={contract.ma_hop_dong}>
              <div className="workspace-contract-item-main">
              <div className="workspace-contract-details">
                  <span className="workspace-file-icon"><FileText size={17} /></span>
                  <div><strong>{contract.original_file_name}</strong><small>{contract.ten_chuong_trinh || contract.ten_phong_ban || 'Chưa có chương trình'} · Tải lên {contract.uploaded_at || '—'}</small></div>
                  <span className={`workspace-status is-${presentation.tone}`} aria-live="polite"><i />{presentation.label}</span>
                </div>
                <div className="workspace-contract-actions">
                  <button type="button" className="btn btn-secondary btn-sm" aria-expanded={isPreviewing} onClick={() => previewContract(contract.ma_hop_dong)}>
                    <Eye size={14} />{isPreviewing ? 'Ẩn xem trước' : 'Xem trước'}
                  </button>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => downloadContract(contract)}>
                    <Download size={14} />Tải xuống
                  </button>
                  <button type="button" className="btn btn-primary btn-sm" onClick={() => {
                    setContractPreviewUrl('');
                    setPreviewingContractId(null);
                    setSelectedContractId(contract.ma_hop_dong);
                  }}>
                    Chi tiết hợp đồng <ArrowRight size={14} />
                  </button>
                </div>
              </div>
              {isPreviewing && contractPreviewUrl && <iframe className="workspace-contract-preview" src={contractPreviewUrl} title={`Xem trước ${contract.original_file_name}`} />}
            </div>;
          })}
        </div> : <div className="workspace-empty"><FileText size={22} /><span>HR chưa tải hợp đồng lên. Hợp đồng sẽ xuất hiện tại đây sau khi được cập nhật.</span></div>}
      {contractError && <p className="contract-error" role="alert">{contractError}</p>}
    </article>
    {documentDialog === 'upload' && <div className="modal-overlay intern-document-modal-overlay" onMouseDown={(event) => event.target === event.currentTarget && closeDocumentDialog()}>
      <section className="modal-container intern-document-modal" role="dialog" aria-modal="true" aria-labelledby="intern-document-upload-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="modal-header intern-document-modal-header">
          <div><span className="workspace-eyebrow">HỒ SƠ THỰC TẬP</span><h3 id="intern-document-upload-title">Nộp CV hoặc đơn xin thực tập</h3><p>Chọn loại hồ sơ, sau đó kéo thả hoặc chọn tệp từ thiết bị.</p></div>
          <button type="button" className="modal-close-btn" aria-label="Đóng hộp thoại" disabled={uploading} onClick={closeDocumentDialog}><X size={18} /></button>
        </header>
        <div className="modal-body intern-document-upload-body">
          <label className="intern-document-upload-type"><span>Loại tài liệu</span>
            <CustomSelect className="form-select" aria-label="Loại tài liệu cần nộp" value={uploadType} onChange={(event) => setUploadType(event.target.value)} disabled={uploading}>
              <option value="CV">CV</option><option value="DonXinThucTap">Đơn xin thực tập</option>
            </CustomSelect>
          </label>
          <input ref={fileInput} type="file" accept={DOCUMENT_ACCEPT} hidden onChange={(event) => { chooseUploadFile(event.target.files?.[0]); event.target.value = ''; }} />
          <div className={`intern-document-dropzone${dragActive ? ' is-dragging' : ''}${uploading ? ' is-disabled' : ''}`}
            role="button" tabIndex={uploading ? -1 : 0} aria-disabled={uploading}
            onClick={() => !uploading && fileInput.current?.click()}
            onKeyDown={(event) => { if (!uploading && ['Enter', ' '].includes(event.key)) { event.preventDefault(); fileInput.current?.click(); } }}
            onDragEnter={(event) => { event.preventDefault(); if (!uploading) setDragActive(true); }}
            onDragOver={(event) => { event.preventDefault(); if (!uploading) setDragActive(true); }}
            onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setDragActive(false); }}
            onDrop={(event) => { event.preventDefault(); setDragActive(false); if (!uploading) chooseUploadFile(event.dataTransfer.files?.[0]); }}>
            <span className="intern-document-dropzone-icon"><UploadCloud size={25} /></span>
            <strong>{dragActive ? 'Thả tệp để đính kèm' : uploadFile ? 'Tệp đã sẵn sàng' : 'Kéo thả tệp vào đây'}</strong>
            <small>hoặc</small>
            <span className="intern-document-dropzone-action">{uploadFile ? 'Chọn tệp khác' : 'Chọn tệp từ thiết bị'}</span>
            <small>PDF, DOC, DOCX · tối đa 5 MB</small>
          </div>
          {uploadFile && <div className="intern-document-selected-file">
            <span><FileType2 size={17} /></span><div><strong>{uploadFile.name}</strong><small>{formatDocumentSize(uploadFile.size)}</small></div>
            <button type="button" aria-label="Bỏ tệp đã chọn" disabled={uploading} onClick={() => { setUploadFile(null); setUploadProgress(0); setUploadError(''); }}><X size={16} /></button>
          </div>}
          {uploadError && <p className="intern-document-feedback is-error" role="alert">{uploadError}</p>}
          {uploading && <div className="intern-document-progress">
            <div><span>{uploadProgress >= 100 ? 'Đang hoàn tất tải lên…' : 'Đang tải tệp lên…'}</span><strong>{uploadProgress}%</strong></div>
            <span className="intern-document-progress-track" role="progressbar" aria-label="Tiến độ tải tệp" aria-valuemin="0" aria-valuemax="100" aria-valuenow={uploadProgress}><i style={{ width: `${uploadProgress}%` }} /></span>
          </div>}
        </div>
        <footer className="modal-footer intern-document-modal-footer">
          <button type="button" className="btn btn-secondary" disabled={uploading} onClick={closeDocumentDialog}>Hủy</button>
          <button type="button" className="btn btn-primary" disabled={!uploadFile || uploading} aria-busy={uploading} onClick={uploadDocument}>
            {uploading ? <><span className="contract-spinner" aria-hidden="true" />Đang tải lên…</> : <><UploadCloud size={16} />Nộp {uploadType === 'CV' ? 'CV' : 'đơn'}</>}
          </button>
        </footer>
      </section>
    </div>}

    {documentDialog === 'preview' && previewDocument && <div className="modal-overlay intern-document-modal-overlay" onMouseDown={(event) => event.target === event.currentTarget && closeDocumentDialog()}>
      <section className="modal-container intern-document-modal intern-document-preview-modal" role="dialog" aria-modal="true" aria-labelledby="intern-document-preview-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="modal-header intern-document-modal-header">
          <div><span className="workspace-eyebrow">XEM TRƯỚC TÀI LIỆU</span><h3 id="intern-document-preview-title">{previewDocument.ten_file || 'Tài liệu'}</h3><p>{documentTypeLabels[previewDocument.loai_tai_lieu] || previewDocument.loai_tai_lieu}</p></div>
          <button type="button" className="modal-close-btn" aria-label="Đóng hộp thoại" onClick={closeDocumentDialog}><X size={18} /></button>
        </header>
        <div className="modal-body intern-document-preview-body">
          {previewLoading && <div className="workspace-loading"><span className="contract-spinner" />Đang tải bản xem trước…</div>}
          {previewError && <p className="intern-document-feedback is-error" role="alert">{previewError}</p>}
          {!previewLoading && !previewError && documentExtension(previewDocument.ten_file || '') === 'pdf' && documentPreviewUrl && <iframe src={documentPreviewUrl} title={`Xem trước ${previewDocument.ten_file}`} />}
          {!previewLoading && !previewError && documentExtension(previewDocument.ten_file || '') === 'png' && documentPreviewUrl && <img src={documentPreviewUrl} alt={`Xem trước ${previewDocument.ten_file}`} />}
          {!previewLoading && !previewError && ['doc', 'docx'].includes(documentExtension(previewDocument.ten_file || '')) && <div className="intern-document-preview-fallback"><span><FileType2 size={26} /></span><strong>Không thể hiển thị trực tiếp định dạng Word trong trình duyệt.</strong><p>Tải tệp xuống để mở bằng Microsoft Word hoặc ứng dụng tương thích.</p></div>}
        </div>
        <footer className="modal-footer intern-document-modal-footer">
          <button type="button" className="btn btn-secondary" onClick={closeDocumentDialog}>Đóng</button>
          <button type="button" className="btn btn-primary" onClick={() => download(previewDocument)}><Download size={15} />Tải về</button>
        </footer>
      </section>
    </div>}

    <ConfirmDialog
      open={documentDialog === 'delete' && Boolean(documentToDelete)}
      title="Xóa tài liệu này?"
      message={`“${documentToDelete?.ten_file || 'Tài liệu'}” sẽ bị xóa khỏi hồ sơ của bạn và không thể khôi phục.`}
      confirmLabel="Xóa tài liệu"
      cancelLabel="Giữ lại"
      danger
      busy={deletingDocumentId === documentToDelete?.ma_tai_lieu}
      onCancel={() => { if (!deletingDocumentId) { setDocumentDialog(null); setDocumentToDelete(null); setDocumentActionError(''); } }}
      onConfirm={deleteDocument}
    >{documentActionError && <p className="intern-document-feedback is-error" role="alert">{documentActionError}</p>}</ConfirmDialog>
  </div>;
}
