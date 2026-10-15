import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Check, CheckCircle2, Clock3, History, LoaderCircle, RefreshCw, Send, UsersRound } from 'lucide-react';
import { apiFetch } from '../utils/api';
import './HrmIntegrationView.css';

async function requestJson(path, options) {
  const response = await apiFetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status}).`);
  return payload;
}

function dateLabel(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('vi-VN');
}

export default function HrmOutboundPanel({ currentUser }) {
  const canApprove = currentUser?.vai_tro === 'HR';
  const [status, setStatus] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [inbox, setInbox] = useState([]);
  const [history, setHistory] = useState([]);
  const [preview, setPreview] = useState(null);
  const [decisionReason, setDecisionReason] = useState('');
  const [rejectReasons, setRejectReasons] = useState({});
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const refresh = useCallback(async () => {
    try {
      const current = await requestJson('/api/integrations/hrm/outbound/status');
      setError('');
      setStatus(current);
      if (!current.enabled) {
        setCandidates([]);
        setInbox([]);
        setHistory([]);
        return;
      }
      const [candidateData, inboxData, historyData] = await Promise.all([
        requestJson('/api/integrations/hrm/outbound/candidates?page=1&page_size=50'),
        requestJson('/api/integrations/hrm/outbound/sandbox-inbox'),
        requestJson('/api/integrations/hrm/outbound/history?page=1&page_size=20'),
      ]);
      setCandidates(candidateData.items || []);
      setInbox(inboxData.items || []);
      setHistory(historyData.items || []);
    } catch (cause) {
      setError(cause.message || 'Could not load HRM Sandbox outbound status.');
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  const createPreview = async (profileId) => {
    setBusy(`preview:${profileId}`);
    setError('');
    setNotice('');
    try {
      const result = await requestJson('/api/integrations/hrm/outbound/preview', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile_id: profileId }),
      });
      setPreview({ ...result, approved: false });
      setDecisionReason('');
    } catch (cause) {
      setError(cause.message || 'Could not create candidate preview.');
    } finally { setBusy(''); }
  };

  const approve = async () => {
    if (!preview?.preview_id || !canApprove) return;
    const confirmed = window.confirm('Xác nhận quyết định tuyển dụng của HR và cho phép gửi đúng snapshot này sang HRM Sandbox?');
    if (!confirmed) return;
    setBusy('approve');
    setError('');
    try {
      await requestJson('/api/integrations/hrm/outbound/approve', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preview_id: preview.preview_id, reason: decisionReason.trim() || null }),
      });
      setPreview((current) => ({ ...current, approved: true }));
      setNotice('HR đã lưu quyết định tuyển dụng và phê duyệt gửi snapshot này.');
      await refresh();
    } catch (cause) { setError(cause.message || 'Could not save HR approval.'); }
    finally { setBusy(''); }
  };

  const send = async () => {
    if (!preview?.preview_id || !preview.approved || !canApprove) return;
    setBusy('send');
    setError('');
    try {
      const result = await requestJson('/api/integrations/hrm/outbound/send', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preview_id: preview.preview_id }),
      });
      setNotice(result.message || `Candidate request status: ${result.status}.`);
      setPreview(null);
      await refresh();
    } catch (cause) { setError(cause.message || 'Could not send candidate request.'); }
    finally { setBusy(''); }
  };

  const decide = async (item, decision) => {
    const reason = String(rejectReasons[item.external_reference] || '').trim();
    if (decision === 'REJECT' && !reason) {
      setError('Nhập lý do từ chối trước khi lưu quyết định.');
      return;
    }
    if (decision === 'ACCEPT' && !window.confirm('HRM Sandbox chấp nhận hồ sơ nháp và tạo mã nhân viên thử nghiệm?')) return;
    setBusy(`decision:${item.external_reference}`);
    setError('');
    try {
      const result = await requestJson(`/api/integrations/hrm/outbound/sandbox-inbox/${encodeURIComponent(item.external_reference)}/decision`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, reason: reason || null }),
      });
      setNotice(result.status === 'ACCEPTED'
        ? `Sandbox đã chấp nhận và tạo nhân viên ${result.external_employee_id}.`
        : 'Sandbox đã từ chối; lịch sử TTS trong IMS vẫn được giữ nguyên.');
      await refresh();
    } catch (cause) { setError(cause.message || 'Could not save Sandbox decision.'); }
    finally { setBusy(''); }
  };

  const reconcile = async (profileId) => {
    setBusy(`reconcile:${profileId}`);
    setError('');
    try {
      const result = await requestJson(`/api/integrations/hrm/outbound/reconcile/${profileId}`, { method: 'POST' });
      setNotice(result.message || `Reconciliation status: ${result.status}.`);
      await refresh();
    } catch (cause) { setError(cause.message || 'Could not reconcile this request.'); }
    finally { setBusy(''); }
  };

  return (
    <section className="hrm-panel hrm-outbound-panel">
      <div className="hrm-panel-heading">
        <div>
          <h2>IMS → HRM Sandbox · Đề xuất ứng viên</h2>
          <p>HR xác nhận quyết định tuyển dụng và snapshot dữ liệu. Sandbox chỉ tạo nhân viên sau khi HRM chấp nhận.</p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={refresh} disabled={Boolean(busy)}>
          {busy ? <LoaderCircle className="hrm-spin" size={16} /> : <RefreshCw size={16} />} Làm mới
        </button>
      </div>
      {error && <div className="hrm-message is-error" role="alert"><AlertTriangle size={18} />{error}</div>}
      {notice && <div className="hrm-message is-success" role="status"><CheckCircle2 size={18} />{notice}</div>}
      <div className={`hrm-status-card ${status?.enabled ? 'is-connected' : 'is-waiting'}`}>
        <div className="hrm-status-icon">{status?.enabled ? <CheckCircle2 size={22} /> : <Clock3 size={22} />}</div>
        <div className="hrm-status-copy"><span className="hrm-status-label">SANDBOX MODE</span><h3>{status?.enabled ? 'Outbound UAT enabled' : 'Outbound disabled'}</h3><p>{status?.message || 'Checking configuration…'}</p></div>
        <span className={`hrm-status-badge ${status?.enabled ? 'is-connected' : ''}`}>{status?.environment || 'checking'}</span>
      </div>
      <div className="hrm-outbound-scope">
        <strong>Gói dữ liệu gửi</strong>
        <span>IMS profile reference, họ tên và các chương trình đã được duyệt và xác nhận hoàn thành.</span>
        <small>Email, số điện thoại, CV, chi tiết đánh giá, mật khẩu, phòng ban và quyền IMS không được gửi.</small>
      </div>

      <section className="hrm-outbound-section">
        <div className="hrm-panel-heading"><div><h3><UsersRound size={18} /> Ứng viên đủ điều kiện ({candidates.length})</h3><p>Cần hồ sơ TTS được duyệt và ít nhất một lượt tham gia được duyệt có trạng thái hoàn thành do nghiệp vụ xác nhận.</p></div></div>
        {candidates.length === 0 ? <p className="hrm-empty">Chưa có hồ sơ đủ điều kiện; không suy luận hoàn thành từ ngày kết thúc hoặc điểm đánh giá.</p> : (
          <div className="hrm-table-wrap"><table className="hrm-table">
            <thead><tr><th>Hồ sơ</th><th>Chương trình đã hoàn thành</th><th>Quyết định HR</th><th>Trạng thái HRM</th><th>Thao tác</th></tr></thead>
            <tbody>{candidates.map((item) => (
              <tr key={item.profile_id}>
                <td><strong>#{item.profile_id} · {item.full_name}</strong></td>
                <td>{item.completed_programs.map((program) => <small key={program.program_reference}>{program.program_name} · {program.completion_date || 'Ngày hoàn thành chưa ghi'}</small>)}</td>
                <td>{item.hiring_decision === 'APPROVED' ? `Đã duyệt · ${dateLabel(item.decision_at)}` : item.hiring_decision === 'REVOKED' ? 'Đã thu hồi' : 'Chưa ghi nhận'}</td>
                <td><span className={`hrm-action-badge tone-${item.status === 'ACCEPTED' ? 'new' : item.status === 'REJECTED' ? 'conflict' : 'unchanged'}`}>{item.status}</span>{item.external_employee_id && <small>Mã NV HRM: {item.external_employee_id}</small>}</td>
                <td className="hrm-outbound-actions">
                  {canApprove && ['AVAILABLE', 'REJECTED', 'FAILED'].includes(item.status) && <button type="button" className="btn btn-secondary" onClick={() => createPreview(item.profile_id)} disabled={Boolean(busy)}>{busy === `preview:${item.profile_id}` ? <LoaderCircle className="hrm-spin" size={15} /> : <Check size={15} />} Xem trước</button>}
                  {['PENDING', 'PENDING_RECONCILIATION'].includes(item.status) && <button type="button" className="btn btn-secondary" onClick={() => reconcile(item.profile_id)} disabled={Boolean(busy)}>{busy === `reconcile:${item.profile_id}` ? <LoaderCircle className="hrm-spin" size={15} /> : <RefreshCw size={15} />} {item.status === 'PENDING' ? 'Lấy quyết định HRM' : 'Đối soát'}</button>}
                </td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </section>

      {preview && (
        <section className="hrm-outbound-preview" aria-labelledby="outbound-preview-title">
          <div className="hrm-panel-heading"><div><h3 id="outbound-preview-title">Xem trước đề xuất tuyển dụng #{preview.profile_id}</h3><p>Preview có thời hạn đến {dateLabel(preview.expires_at)}. Kiểm tra toàn bộ dữ liệu trước khi xác nhận.</p></div></div>
          <dl className="hrm-outbound-payload">
            <div><dt>Tham chiếu IMS</dt><dd>{preview.payload.external_reference}</dd></div>
            <div><dt>Họ tên</dt><dd>{preview.payload.full_name}</dd></div>
            <div><dt>Trạng thái nguồn</dt><dd>{preview.payload.source_status}</dd></div>
            <div><dt>Chương trình hoàn thành</dt><dd>{preview.payload.completed_programs.map((program) => `${program.program_name} (${program.start_date || '—'} → ${program.completion_date || '—'})`).join('; ')}</dd></div>
          </dl>
          <ul className="hrm-scope-list is-included">{preview.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
          {canApprove && <label className="hrm-outbound-reason">Ghi chú quyết định HR (không bắt buộc)<input maxLength={500} value={decisionReason} onChange={(event) => setDecisionReason(event.target.value)} placeholder="Ví dụ: HR đã phỏng vấn và duyệt tuyển dụng" disabled={preview.approved} /></label>}
          <div className="hrm-action-row">
            {!preview.approved && canApprove && <button type="button" className="btn btn-primary" onClick={approve} disabled={Boolean(busy)}>{busy === 'approve' ? <LoaderCircle className="hrm-spin" size={16} /> : <Check size={16} />} HR xác nhận tuyển dụng & duyệt gửi</button>}
            {preview.approved && canApprove && <button type="button" className="btn btn-primary" onClick={send} disabled={Boolean(busy)}>{busy === 'send' ? <LoaderCircle className="hrm-spin" size={16} /> : <Send size={16} />} Gửi bản nháp PENDING</button>}
            <button type="button" className="btn btn-secondary" onClick={() => setPreview(null)} disabled={Boolean(busy)}>Đóng preview</button>
          </div>
        </section>
      )}

      <section className="hrm-outbound-section">
        <div className="hrm-panel-heading"><div><h3><Clock3 size={18} /> Hộp tiếp nhận HRM Sandbox ({inbox.length})</h3><p>Đây là đề xuất nháp. Chấp nhận tạo nhân viên thử nghiệm và mã HRM; từ chối cần lý do.</p></div></div>
        {inbox.length === 0 ? <p className="hrm-empty">Không có đề xuất đang chờ quyết định HRM.</p> : inbox.map((item) => (
          <article className="hrm-candidate-card" key={item.candidate_request_id}>
            <div><strong>{item.payload.full_name}</strong><span>{item.external_reference} · revision {item.revision}</span>
              <small>{item.payload.completed_programs.map((program) => program.program_name).join(', ')}</small>
            </div>
            {canApprove ? <div className="hrm-candidate-decision">
              <input aria-label={`Lý do từ chối ${item.payload.full_name}`} maxLength={500} value={rejectReasons[item.external_reference] || ''} onChange={(event) => setRejectReasons((current) => ({ ...current, [item.external_reference]: event.target.value }))} placeholder="Lý do từ chối (bắt buộc nếu từ chối)" />
              <button type="button" className="btn btn-primary" onClick={() => decide(item, 'ACCEPT')} disabled={Boolean(busy)}>{busy === `decision:${item.external_reference}` ? <LoaderCircle className="hrm-spin" size={15} /> : <Check size={15} />} Chấp nhận</button>
              <button type="button" className="btn btn-secondary" onClick={() => decide(item, 'REJECT')} disabled={Boolean(busy)}>Từ chối</button>
            </div> : <span className="hrm-action-badge tone-unchanged">Read only</span>}
          </article>
        ))}
      </section>

      <section className="hrm-outbound-section">
        <div className="hrm-panel-heading"><div><h3><History size={18} /> Lịch sử outbound</h3><p>Lưu trạng thái gửi, tiếp nhận, quyết định HRM và mã nhân viên ngoài.</p></div></div>
        {history.length === 0 ? <p className="hrm-empty">Chưa có lịch sử đề xuất.</p> : <div className="hrm-table-wrap"><table className="hrm-table"><thead><tr><th>Thời gian</th><th>Hồ sơ</th><th>Người thao tác</th><th>Trạng thái</th><th>Request ID</th><th>Ghi chú</th></tr></thead><tbody>
          {history.map((item) => <tr key={item.id}><td>{dateLabel(item.created_at)}</td><td>#{item.ma_ho_so}</td><td>{item.actor_name || 'HR'}</td><td>{item.event_status}</td><td>{item.candidate_request_id || '—'}</td><td>{item.reason || '—'}</td></tr>)}
        </tbody></table></div>}
      </section>
    </section>
  );
}
