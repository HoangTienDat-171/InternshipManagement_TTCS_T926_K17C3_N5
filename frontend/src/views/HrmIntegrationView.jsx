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
  ShieldCheck,
  UsersRound,
  XCircle,
} from 'lucide-react';
import { apiFetch } from '../utils/api';
import './HrmIntegrationView.css';

const ACTIONS = [
  { key: 'NEW', label: 'Mới', tone: 'new' },
  { key: 'UPDATE', label: 'Cập nhật', tone: 'update' },
  { key: 'UNCHANGED', label: 'Không đổi', tone: 'unchanged' },
  { key: 'CONFLICT', label: 'Xung đột', tone: 'conflict' },
  { key: 'INVALID', label: 'Không hợp lệ', tone: 'invalid' },
];

const ACTION_LABELS = Object.fromEntries(ACTIONS.map(({ key, label }) => [key, label]));

async function apiJson(path, options) {
  const response = await apiFetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Yêu cầu thất bại (${response.status}).`);
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

export default function HrmIntegrationView() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [preview, setPreview] = useState(null);
  const [mappings, setMappings] = useState(null);
  const [mappingSelection, setMappingSelection] = useState({});
  const [history, setHistory] = useState([]);
  const [directory, setDirectory] = useState([]);

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
  const hasApplicableChanges = (previewCounts.NEW || 0) + (previewCounts.UPDATE || 0) > 0;
  const previewRows = preview?.rows || [];
  const previewExpiry = useMemo(() => formatDate(preview?.expires_at), [preview?.expires_at]);

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

  const loadMappings = async () => {
    setBusy('mappings');
    setError('');
    try {
      const result = await apiJson('/api/integrations/hrm/department-mappings');
      setMappings(result);
      setMappingSelection(Object.fromEntries((result.hrm_departments || []).map((item) => [
        item.department_code,
        item.mapped_department_id ? String(item.mapped_department_id) : '',
      ])));
    } catch (cause) {
      setError(cause.message || 'Không tải được danh mục phòng ban.');
    } finally {
      setBusy('');
    }
  };

  const saveMapping = async (departmentCode) => {
    const departmentId = Number(mappingSelection[departmentCode]);
    if (!departmentId) {
      setError('Hãy chọn phòng ban IMS trước khi lưu ánh xạ.');
      return;
    }
    setBusy(`mapping:${departmentCode}`);
    setError('');
    setNotice('');
    try {
      await apiJson('/api/integrations/hrm/department-mappings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ department_code: departmentCode, ma_phong_ban: departmentId }),
      });
      setPreview(null);
      setNotice(`Đã lưu ánh xạ phòng ban ${departmentCode}.`);
      await loadMappings();
    } catch (cause) {
      setError(cause.message || 'Không lưu được ánh xạ phòng ban.');
    } finally {
      setBusy('');
    }
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
      await loadMappings().catch(() => {});
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
    const skipCount = (previewCounts.CONFLICT || 0) + (previewCounts.INVALID || 0);
    const confirmed = window.confirm(
      `Xác nhận áp dụng ${newCount} nhân viên mới và ${updateCount} cập nhật vào danh bạ HRM của IMS? ${skipCount} bản ghi xung đột/không hợp lệ sẽ được bỏ qua. Thao tác không tạo tài khoản, không đổi quyền và không sửa phân công Mentor.`,
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
      await loadMappings().catch(() => {});
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
        <section className="hrm-panel">
          <div className="hrm-panel-heading">
            <div><h2>Ánh xạ phòng ban</h2><p>Ánh xạ mã phòng ban HRM vào danh mục IMS. Không tự tạo phòng ban hoặc thay đổi phân công.</p></div>
            <button type="button" className="btn btn-secondary" onClick={loadMappings} disabled={Boolean(busy)}>
              {busy === 'mappings' ? <LoaderCircle className="hrm-spin" size={15} /> : <RefreshCw size={15} />}
              Tải danh mục
            </button>
          </div>
          {!mappings ? <p className="hrm-empty">Tải mã phòng ban từ Sandbox để cấu hình ánh xạ.</p> : mappings.hrm_departments.length === 0 ? (
            <p className="hrm-empty">HRM Sandbox chưa có mã phòng ban để ánh xạ.</p>
          ) : (
            <div className="hrm-mapping-list">
              {mappings.hrm_departments.map((department) => (
                <div className="hrm-mapping-row" key={department.department_code}>
                  <div className="hrm-mapping-source"><strong>{department.department_code}</strong><span>{department.department_name || 'Chưa có tên'}</span></div>
                  <select
                    aria-label={`Phòng ban IMS cho ${department.department_code}`}
                    value={mappingSelection[department.department_code] || ''}
                    onChange={(event) => setMappingSelection((previous) => ({ ...previous, [department.department_code]: event.target.value }))}
                  >
                    <option value="">Chọn phòng ban IMS</option>
                    {(mappings.ims_departments || []).map((choice) => <option key={choice.ma_phong_ban} value={choice.ma_phong_ban}>{choice.ten_phong_ban}</option>)}
                  </select>
                  <button type="button" className="btn btn-secondary" onClick={() => saveMapping(department.department_code)} disabled={!mappingSelection[department.department_code] || Boolean(busy)}>
                    {busy === `mapping:${department.department_code}` ? <LoaderCircle className="hrm-spin" size={15} /> : <Check size={15} />}
                    Lưu ánh xạ
                  </button>
                </div>
              ))}
            </div>
          )}
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
          <div className="hrm-panel-heading"><div><h2>Bản xem trước ({preview.total})</h2><p>Chỉ các dòng Mới/Cập nhật/Không đổi được áp dụng. Xung đột và dữ liệu sai được giữ lại để rà soát.</p></div></div>
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
    </section>
  );
}
