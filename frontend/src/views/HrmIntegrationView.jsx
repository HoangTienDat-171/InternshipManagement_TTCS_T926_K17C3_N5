import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  CircleHelp,
  Database,
  History,
  Link2,
  LoaderCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  UsersRound,
  XCircle,
} from 'lucide-react';
import { apiFetch } from '../utils/api';
import MasterDataSelect from '../components/MasterDataSelect';
import HrmOutboundPanel from './HrmOutboundPanel';
import HrmDepartmentMappingPanel from './HrmDepartmentMappingPanel';
import './HrmIntegrationView.css';

const ACTIONS = [
  { key: 'NEW', label: 'Mới', tone: 'new' },
  { key: 'UPDATE', label: 'Cập nhật', tone: 'update' },
  { key: 'MENTOR_UPDATE', label: 'Mentor linked update', tone: 'update' },
  { key: 'MENTOR_DIRECTORY_UPDATE', label: 'HRM directory only', tone: 'update' },
  { key: 'UNCHANGED', label: 'Không đổi', tone: 'unchanged' },
  { key: 'MENTOR_UNCHANGED', label: 'Mentor unchanged', tone: 'unchanged' },
  { key: 'CONFLICT', label: 'Xung đột', tone: 'conflict' },
  { key: 'INVALID', label: 'Không hợp lệ', tone: 'invalid' },
];

const ACTION_LABELS = Object.fromEntries(ACTIONS.map(({ key, label }) => [key, label]));

async function apiJson(path, options) {
  const response = await apiFetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail || `Yêu cầu thất bại (${response.status}).`;
    if (response.status === 404 && (!payload.detail || payload.detail === 'Not Found')) {
      throw new Error(`Backend trả 404 cho ${path}. Hãy kiểm tra backend có đang chạy từ worktree feature US37 trên cổng 8000 không, rồi tải lại trang.`);
    }
    throw new Error(detail);
  }
  return payload;
}

function formatDate(value) {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('vi-VN');
}

function StatusIcon({ state }) {
  if (state === 'CONNECTED') return <CheckCircle2 size={23} aria-hidden="true" />;
  if (state === 'ERROR') return <XCircle size={23} aria-hidden="true" />;
  if (state === 'NOT_CONFIGURED') return <CircleHelp size={23} aria-hidden="true" />;
  return <AlertTriangle size={23} aria-hidden="true" />;
}

function AdminHrmIntegrationView({ currentUser }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [preview, setPreview] = useState(null);
  const [history, setHistory] = useState([]);
  const [directory, setDirectory] = useState([]);
  const [mentorMappings, setMentorMappings] = useState(null);
  const [mentorMappingSelection, setMentorMappingSelection] = useState({});
  const [mentorQuery, setMentorQuery] = useState('');
  const [mentorLinkFilter, setMentorLinkFilter] = useState('ALL');

  const loadStatus = useCallback(async (signal) => {
    const payload = await apiJson('/api/integrations/hrm/status', { signal });
    if (!signal?.aborted) setStatus(payload);
    return payload;
  }, []);

  const loadHistoryAndDirectory = useCallback(async (signal) => {
    const [historyData, directoryData] = await Promise.all([
      apiJson('/api/integrations/hrm/history?page=1&page_size=10', { signal }),
      apiJson('/api/integrations/hrm/directory?page=1&page_size=10', { signal }),
    ]);
    if (!signal?.aborted) {
      setHistory(historyData.items || []);
      setDirectory(directoryData.items || []);
    }
  }, []);

  const refresh = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    try {
      const current = await loadStatus(signal);
      if (current.sync_history_available) await loadHistoryAndDirectory(signal);
      else if (!signal?.aborted) {
        setHistory([]);
        setDirectory([]);
      }
    } catch (cause) {
      if (!signal?.aborted && cause.name !== 'AbortError') setError(cause.message || 'Không tải được trạng thái HRM.');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [loadHistoryAndDirectory, loadStatus]);

  useEffect(() => {
    const controller = new AbortController();
    Promise.resolve().then(() => {
      if (!controller.signal.aborted) refresh(controller.signal);
    });
    return () => controller.abort();
  }, [refresh]);

  const previewCounts = preview?.counts || {};
  const hasApplicableChanges = (previewCounts.NEW || 0) + (previewCounts.UPDATE || 0) + (previewCounts.MENTOR_UPDATE || 0) + (previewCounts.MENTOR_DIRECTORY_UPDATE || 0) > 0;
  const previewRows = preview?.rows || [];
  const previewExpiry = useMemo(() => formatDate(preview?.expires_at), [preview?.expires_at]);
  const mentorRows = useMemo(() => mentorMappings?.employees || [], [mentorMappings]);
  const mentorUserById = useMemo(() => new Map((mentorMappings?.mentors || []).map((mentor) => [
    Number(mentor.ma_nguoi_dung), mentor,
  ])), [mentorMappings]);
  const mentorOptions = useMemo(() => (mentorMappings?.mentors || [])
    .filter((mentor) => !mentorRows.some((employee) => Number(employee.linked_user_id) === Number(mentor.ma_nguoi_dung)))
    .map((mentor) => ({
      ...mentor,
      option_label: `${mentor.ho_ten || 'Chưa có tên'} · ${mentor.email || `IMS #${mentor.ma_nguoi_dung}`}`,
    })), [mentorMappings, mentorRows]);
  const filteredMentorRows = useMemo(() => {
    const needle = mentorQuery.trim().toLocaleLowerCase();
    return mentorRows.filter((employee) => {
      const isLinked = Boolean(employee.linked_user_id);
      if (mentorLinkFilter === 'LINKED' && !isLinked) return false;
      if (mentorLinkFilter === 'UNLINKED' && isLinked) return false;
      if (!needle) return true;
      const linkedMentor = mentorUserById.get(Number(employee.linked_user_id));
      return [
        employee.external_employee_id, employee.full_name, employee.work_email,
        linkedMentor?.ho_ten, linkedMentor?.email, employee.linked_user_id,
      ].some((value) => String(value || '').toLocaleLowerCase().includes(needle));
    });
  }, [mentorRows, mentorQuery, mentorLinkFilter, mentorUserById]);

  const checkConnection = async () => {
    setBusy('connection');
    setError('');
    setNotice('');
    try {
      const result = await apiJson('/api/integrations/hrm/test-connection', { method: 'POST' });
      setNotice(result.message || 'Đã kết nối HRM Sandbox.');
      await loadStatus();
    } catch (cause) {
      setError(cause.message || 'Không kết nối được HRM Sandbox.');
      await loadStatus().catch(() => {});
    } finally {
      setBusy('');
    }
  };

  const loadMentorMappings = async () => {
    setBusy('mentor-mappings');
    setError('');
    try {
      const result = await apiJson('/api/integrations/hrm/mentor-mappings');
      setMentorMappings(result);
      setMentorMappingSelection(Object.fromEntries((result.employees || []).map((item) => [
        item.external_employee_id,
        item.linked_user_id ? String(item.linked_user_id) : '',
      ])));
    } catch (cause) {
      setError(cause.message || 'Could not load explicit Mentor mappings.');
    } finally { setBusy(''); }
  };

  const saveMentorMapping = async (externalEmployeeId) => {
    const mentorId = Number(mentorMappingSelection[externalEmployeeId]);
    if (!mentorId) return;
    setBusy(`mentor-map:${externalEmployeeId}`);
    setError('');
    setNotice('');
    try {
      await apiJson('/api/integrations/hrm/mentor-mappings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ external_employee_id: externalEmployeeId, ma_nguoi_dung: mentorId }),
      });
      setPreview(null);
      setNotice('Admin đã xác nhận liên kết external ID HRM ↔ Mentor IMS. Tạo preview mới để xem các thay đổi HRM-owned.');
      await loadMentorMappings();
    } catch (cause) { setError(cause.message || 'Could not save the external-ID mapping.'); }
    finally { setBusy(''); }
  };

  const createPreview = async () => {
    setBusy('preview');
    setError('');
    setNotice('');
    setPreview(null);
    try {
      const result = await apiJson('/api/integrations/hrm/preview', { method: 'POST' });
      setPreview(result);
      setNotice(`Đã tải ${result.total} bản ghi từ HRM Sandbox. Bản xem trước hết hạn ${formatDate(result.expires_at)}.`);
    } catch (cause) {
      setError(cause.message || 'Không tạo được bản xem trước.');
    } finally {
      setBusy('');
    }
  };

  const applyPreview = async () => {
    if (!preview?.preview_id) return;
    const newCount = previewCounts.NEW || 0;
    const updateCount = previewCounts.UPDATE || 0;
    const mentorUpdateCount = previewCounts.MENTOR_UPDATE || 0;
    const directoryOnlyCount = previewCounts.MENTOR_DIRECTORY_UPDATE || 0;
    const skipCount = (previewCounts.CONFLICT || 0) + (previewCounts.INVALID || 0);
    const confirmed = window.confirm(
      `Apply ${newCount} new HRM directory records, ${updateCount} HRM directory updates, ${directoryOnlyCount} directory-only changes for linked Mentors, and ${mentorUpdateCount} supported Mentor profile updates? ${skipCount} conflicts/invalid rows will be skipped. Roles, login status, assignments, and history stay unchanged.`,
    );
    if (!confirmed) return;
    setBusy('apply');
    setError('');
    setNotice('');
    try {
      const result = await apiJson('/api/integrations/hrm/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preview_id: preview.preview_id }),
      });
      setPreview(null);
      setNotice(`Đồng bộ ${result.status.toLowerCase()}: tạo ${result.created}, cập nhật ${result.updated}, không đổi ${result.unchanged}, bỏ qua ${result.skipped}, lỗi ${result.errors}.`);
      await refresh();
    } catch (cause) {
      setError(cause.message || 'Không áp dụng được bản xem trước.');
      if (cause.message?.includes('thay đổi') || cause.message?.includes('hết hạn')) setPreview(null);
    } finally {
      setBusy('');
    }
  };

  const current = status || {};
  const connected = current.connection_state === 'CONNECTED' || current.state === 'CONNECTED';

  return (
    <section className="hrm-integration-page">
      <header className="hrm-page-header">
        <div>
          <span className="hrm-eyebrow">TÍCH HỢP NHÂN SỰ</span>
          <h1>Đồng bộ dữ liệu HRM</h1>
          <p>Kiểm tra, đối chiếu và đồng bộ nhân viên từ HRM Sandbox vào danh bạ nhân sự riêng của IMS.</p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={() => refresh()} disabled={loading || Boolean(busy)}>
          {loading ? <LoaderCircle className="hrm-spin" size={16} /> : <RefreshCw size={16} aria-hidden="true" />}
          Làm mới
        </button>
      </header>

      {error && <div className="hrm-message is-error" role="alert"><AlertTriangle size={18} />{error}</div>}
      {notice && <div className="hrm-message is-success" role="status"><CheckCircle2 size={18} />{notice}</div>}

      <section className={`hrm-status-card ${connected ? 'is-connected' : current.state === 'ERROR' ? 'is-error' : 'is-waiting'}`} aria-live="polite">
        <div className="hrm-status-icon"><StatusIcon state={connected ? 'CONNECTED' : current.state} /></div>
        <div className="hrm-status-copy">
          <span className="hrm-status-label">{loading ? 'ĐANG KIỂM TRA' : connected ? 'ĐÃ KẾT NỐI' : current.state === 'SCHEMA_REQUIRED' ? 'CẦN CÀI SCHEMA' : current.state === 'ERROR' ? 'CẤU HÌNH LỖI' : current.configured ? 'CHƯA KIỂM TRA' : 'CHƯA CẤU HÌNH'}</span>
          <h2>{current.provider_name || 'HRM Sandbox'}</h2>
          <p>{current.message || 'Đang tải cấu hình kết nối.'}</p>
          {current.endpoint && <code className="hrm-endpoint">{current.endpoint}</code>}
        </div>
        <span className={`hrm-status-badge ${connected ? 'is-connected' : ''}`}>{connected ? 'CONNECTED' : current.state || 'Đang tải'}</span>
      </section>

      <div className="hrm-summary-grid">
        {ACTIONS.map((item) => (
          <article className={`hrm-summary-card tone-${item.tone}`} key={item.key}>
            <span className="hrm-summary-icon"><UsersRound size={18} aria-hidden="true" /></span>
            <div><span>{item.label}</span><strong>{preview ? previewCounts[item.key] || 0 : '—'}</strong></div>
          </article>
        ))}
      </div>

      <div className="hrm-content-grid">
        <section className="hrm-panel">
          <div className="hrm-panel-heading">
            <div><h2>Kết nối HRM Sandbox</h2><p>Endpoint và credential chỉ lấy từ environment; API key không hiển thị trên giao diện.</p></div>
            <Database size={19} aria-hidden="true" />
          </div>
          <div className="hrm-connection-details">
            <div><span>Provider</span><strong>{current.provider_name || 'HRM Sandbox'}</strong></div>
            <div><span>Endpoint</span><strong>{current.endpoint || 'Chưa cấu hình'}</strong></div>
            <div><span>Xác thực</span><strong>Bearer key · environment</strong></div>
            <div><span>Database HRM</span><strong>SQLite riêng, lưu bền vững</strong></div>
          </div>
          <button type="button" className="btn btn-secondary" onClick={checkConnection} disabled={!current.can_test_connection || Boolean(busy)}>
            {busy === 'connection' ? <LoaderCircle className="hrm-spin" size={16} /> : <Link2 size={16} />}
            Kiểm tra kết nối
          </button>
        </section>

        <section className="hrm-panel">
          <div className="hrm-panel-heading">
            <div><h2>Phạm vi đồng bộ</h2><p>Dữ liệu nguồn nhân sự được lưu trong danh bạ HRM, tách biệt với tài khoản và lịch sử thực tập.</p></div>
            <ShieldCheck size={19} aria-hidden="true" />
          </div>
          <h3>Dữ liệu nhân viên</h3>
          <ul className="hrm-scope-list is-included">{(current.sync_scope || []).map((item) => <li key={item}>{item}</li>)}</ul>
          <h3>Không thay đổi trong IMS</h3>
          <ul className="hrm-scope-list is-excluded">{(current.excluded_scope || []).map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
      </div>

      {current.configured && current.sync_history_available && (
        <HrmDepartmentMappingPanel
          busy={busy}
          onMappingChanged={() => setPreview(null)}
          onNotice={setNotice}
          onError={setError}
        />
      )}

      {current.configured && current.sync_history_available && (
        <section className="hrm-panel">
          <div className="hrm-panel-heading">
            <div><h2>Liên kết Mentor theo external ID</h2><p>Email chỉ là gợi ý. Admin phải chọn đúng tài khoản Mentor và xác nhận; hệ thống không tự ghép, tạo tài khoản hoặc gộp hồ sơ.</p></div>
            <button type="button" className="btn btn-secondary" onClick={loadMentorMappings} disabled={Boolean(busy)}>
              {busy === 'mentor-mappings' ? <LoaderCircle className="hrm-spin" size={15} /> : <RefreshCw size={15} />} Tải nhân viên HRM
            </button>
          </div>
          {!mentorMappings ? <p className="hrm-empty">Tải danh sách để xem mapping hiện có và gợi ý email cần xác nhận.</p> : mentorRows.length === 0 ? (
            <p className="hrm-empty">HRM Sandbox không có hồ sơ nhân viên để liên kết.</p>
          ) : (
            <>
              <div className="hrm-mentor-toolbar">
                <label className="hrm-map-search"><Search size={16} aria-hidden="true" /><input value={mentorQuery} placeholder="Tìm mã HRM, tên, email hoặc Mentor IMS" onChange={(event) => setMentorQuery(event.target.value)} /></label>
                <div className="hrm-mentor-filter">
                  <MasterDataSelect id="hrm-mentor-link-filter" value={mentorLinkFilter}
                    items={[{ value: 'ALL', label: 'Tất cả nhân viên' }, { value: 'LINKED', label: 'Đã liên kết' }, { value: 'UNLINKED', label: 'Chưa liên kết' }]}
                    idKey="value" labelKey="label" placeholder="Lọc liên kết" itemName="trạng thái liên kết"
                    disabled={Boolean(busy)} onChange={(event) => setMentorLinkFilter(event.target.value)} />
                </div>
                <span className="hrm-mentor-count">{mentorRows.filter((employee) => employee.linked_user_id).length} đã liên kết · {mentorRows.filter((employee) => !employee.linked_user_id).length} chưa liên kết</span>
              </div>
              {filteredMentorRows.length === 0 ? <p className="hrm-empty">Không có nhân viên HRM phù hợp với tìm kiếm/bộ lọc.</p> : (
                <div className="hrm-table-wrap"><table className="hrm-table hrm-mentor-table">
                  <thead><tr><th>HRM external ID</th><th>Nhân viên HRM</th><th>Mentor IMS</th><th>Trạng thái</th><th>Thao tác</th></tr></thead>
                  <tbody>{filteredMentorRows.map((employee) => {
                    const linkedMentor = mentorUserById.get(Number(employee.linked_user_id));
                    const suggestion = employee.email_suggestion_user_id ? mentorUserById.get(Number(employee.email_suggestion_user_id)) : null;
                    const selectedMentorId = mentorMappingSelection[employee.external_employee_id] || '';
                    return <tr key={employee.external_employee_id}>
                      <td>{employee.external_employee_id}</td>
                      <td><strong>{employee.full_name || 'Chưa có tên'}</strong><small>{employee.work_email || 'Không có email'}</small></td>
                      <td>
                        {employee.linked_user_id ? <><strong>{linkedMentor?.ho_ten || `Tài khoản IMS #${employee.linked_user_id}`}</strong><small>{linkedMentor?.email || 'Liên kết external ID đã lưu'}</small></> : <>
                          <MasterDataSelect id={`hrm-mentor-${employee.external_employee_id}`} value={selectedMentorId}
                            items={mentorOptions} idKey="ma_nguoi_dung" labelKey="option_label" placeholder="Tìm và chọn Mentor IMS"
                            itemName="Mentor IMS" disabled={Boolean(busy)}
                            onChange={(event) => setMentorMappingSelection((previous) => ({ ...previous, [employee.external_employee_id]: event.target.value }))} />
                          {employee.email_suggestion_count > 1 ? <small className="hrm-map-warning">Email trùng với {employee.email_suggestion_count} tài khoản; không tự chọn.</small>
                            : suggestion ? <small>Gợi ý khớp email: {suggestion.ho_ten} · cần Admin tự chọn và xác nhận.</small>
                              : <small>Chưa có gợi ý email; chỉ liên kết nếu chắc chắn cùng một người.</small>}
                        </>}
                      </td>
                      <td><span className={`hrm-map-badge ${employee.linked_user_id ? 'state-override' : 'state-unmapped'}`}>{employee.linked_user_id ? 'Đã liên kết' : 'Chưa liên kết'}</span></td>
                      <td>{employee.linked_user_id ? <span className="hrm-action-note">Liên kết hiện có được giữ nguyên.</span> : <button type="button" className="btn btn-secondary" onClick={() => saveMentorMapping(employee.external_employee_id)} disabled={!selectedMentorId || Boolean(busy)}>
                        {busy === `mentor-map:${employee.external_employee_id}` ? <LoaderCircle className="hrm-spin" size={15} /> : <Check size={15} />} Xác nhận mapping
                      </button>}</td>
                    </tr>;
                  })}</tbody>
                </table></div>
              )}
            </>
          )}
          <p className="hrm-action-note">Mapping theo provider + external ID không đổi role, mật khẩu, phân công Mentor–TTS hoặc lịch sử. Tạo preview mới sau khi mapping để Admin xem và xác nhận các trường HRM-owned được hỗ trợ.</p>
        </section>
      )}

      <section className="hrm-panel hrm-actions-panel">
        <div className="hrm-panel-heading">
          <div><h2>Xem trước và xác nhận đồng bộ</h2><p>Preview có thời hạn; dữ liệu nguồn và mapping được kiểm tra lại trước khi ghi.</p></div>
          <AlertTriangle size={19} aria-hidden="true" />
        </div>
        <div className="hrm-action-row">
          <button type="button" className="btn btn-secondary" onClick={createPreview} disabled={!current.can_preview || Boolean(busy)}>
            {busy === 'preview' ? <LoaderCircle className="hrm-spin" size={16} /> : <RefreshCw size={16} />}
            Xem trước đồng bộ
          </button>
          <button type="button" className="btn btn-primary" onClick={applyPreview} disabled={!preview || !hasApplicableChanges || Boolean(busy)}>
            {busy === 'apply' ? <LoaderCircle className="hrm-spin" size={16} /> : <Check size={16} />}
            Xác nhận đồng bộ
          </button>
        </div>
        {preview && <p className="hrm-action-note">Preview hết hạn: {previewExpiry}. Bản ghi xung đột/không hợp lệ sẽ được bỏ qua.</p>}
        {!current.can_preview && <p className="hrm-action-note">{current.missing_requirements?.join(' ') || 'Cần cấu hình Sandbox và schema thử nghiệm trước khi xem trước.'}</p>}
      </section>

      {preview && (
        <section className="hrm-panel">
          <div className="hrm-panel-heading"><div><h2>Preview ({preview.total})</h2><p>Apply directory changes and Admin-approved Mentor links according to their separate scopes. Conflicts and invalid records remain for review.</p></div></div>
          <div className="hrm-table-wrap">
            <table className="hrm-table">
              <thead><tr><th>Mã NV</th><th>Nhân viên</th><th>Phòng ban HRM → IMS</th><th>Chức danh</th><th>Trạng thái</th><th>Hành động</th><th>Ghi chú</th></tr></thead>
              <tbody>
                {previewRows.map((row, index) => (
                  <tr key={`${row.external_employee_id || 'invalid'}-${index}`}>
                    <td>{row.external_employee_id || 'Thiếu mã'}</td>
                    <td><strong>{row.full_name || 'Thiếu họ tên'}</strong><small>{row.work_email || 'Không có email'}</small></td>
                    <td>{row.department_code ? <><strong>{row.department_code}</strong><small>{row.mapped_department_name || 'Chưa ánh xạ'}</small></> : '—'}</td>
                    <td>{row.job_title || '—'}</td>
                    <td>{row.employment_status === 'inactive' ? 'Ngừng làm việc' : row.employment_status === 'active' ? 'Đang làm việc' : 'Không hợp lệ'}</td>
                    <td><span className={`hrm-action-badge tone-${(ACTIONS.find((item) => item.key === row.action)?.tone) || 'invalid'}`}>{ACTION_LABELS[row.action] || row.action}</span></td>
                    <td>{row.reason}{row.warnings?.map((warning) => <small key={warning}>{warning}</small>)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="hrm-panel">
        <div className="hrm-panel-heading"><div><h2>Danh bạ HRM đã đồng bộ</h2><p>Đây là hồ sơ nguồn HRM tách biệt; không phải tài khoản IMS.</p></div><UsersRound size={19} /></div>
        {directory.length === 0 ? <p className="hrm-empty">Chưa có nhân viên nào được đồng bộ.</p> : (
          <div className="hrm-table-wrap">
            <table className="hrm-table">
              <thead><tr><th>Mã NV</th><th>Nhân viên</th><th>Phòng ban</th><th>Chức danh</th><th>Trạng thái</th><th>Đồng bộ lúc</th></tr></thead>
              <tbody>{directory.map((row) => (
                <tr key={row.external_employee_id}>
                  <td>{row.external_employee_id}</td>
                  <td><strong>{row.full_name}</strong><small>{row.work_email || 'Không có email'}</small></td>
                  <td>{row.mapped_department_name || row.department || 'Chưa phân phòng ban'}<small>{row.department_code || ''}</small></td>
                  <td>{row.job_title || '—'}</td>
                  <td><span className={`hrm-employment-state ${row.employment_status}`}>{row.employment_status === 'inactive' ? 'Ngừng làm việc' : 'Đang làm việc'}</span></td>
                  <td>{formatDate(row.synced_at)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </section>

      <section className="hrm-panel">
        <div className="hrm-panel-heading"><div><h2>Lịch sử đồng bộ</h2><p>Nhật ký được lưu trong database IMS hiện tại.</p></div><History size={19} /></div>
        {history.length === 0 ? <p className="hrm-empty">Chưa có lần đồng bộ nào.</p> : (
          <div className="hrm-table-wrap">
            <table className="hrm-table">
              <thead><tr><th>Thời gian</th><th>Người thực hiện</th><th>Tổng</th><th>Tạo mới</th><th>Cập nhật</th><th>Không đổi</th><th>Bỏ qua</th><th>Lỗi</th><th>Trạng thái</th></tr></thead>
              <tbody>{history.map((item) => (
                <tr key={item.id}>
                  <td>{formatDate(item.created_at)}</td><td>{item.actor_name || 'Admin'}</td><td>{item.total_count}</td>
                  <td>{item.created_count}</td><td>{item.updated_count}</td><td>{item.unchanged_count}</td>
                  <td>{item.skipped_count}</td><td>{item.error_count}</td><td>{item.status}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </section>

      <HrmOutboundPanel currentUser={currentUser} />
    </section>
  );
}

export default function HrmIntegrationView({ currentUser }) {
  if (currentUser?.vai_tro === 'HR') return <HrmOutboundPanel currentUser={currentUser} />;
  return <AdminHrmIntegrationView currentUser={currentUser} />;
}
