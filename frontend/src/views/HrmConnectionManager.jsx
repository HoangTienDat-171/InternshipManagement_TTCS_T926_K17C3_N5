import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Check, CirclePause, CirclePlay, Clock3, Link2, LoaderCircle, Plus, RefreshCw, Unplug, X } from 'lucide-react';
import { apiFetch } from '../utils/api';
import './HrmConnectionManager.css';

async function requestJson(path, options) {
  const response = await apiFetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Yêu cầu thất bại (${response.status}).`);
  return payload;
}

const STATE_LABEL = {
  CONNECTED: 'Đã kết nối', NOT_TESTED: 'Chưa kiểm tra', PAUSED: 'Đã tạm dừng',
  DISCONNECTED: 'Đã ngắt kết nối', ERROR: 'Lỗi kết nối',
};

export default function HrmConnectionManager({ onChanged }) {
  const [connections, setConnections] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [dialog, setDialog] = useState('');
  const [target, setTarget] = useState(null);
  const [form, setForm] = useState({ connection_name: '', endpoint: 'http://127.0.0.1:8100', api_key: '' });
  const [tested, setTested] = useState(false);
  const [history, setHistory] = useState(null);

  const load = useCallback(async () => {
    try {
      const result = await requestJson('/api/integrations/hrm/connections');
      setConnections(result.items || []);
      setActiveId(result.active_connection_id || null);
    } catch (cause) { setError(cause.message || 'Không tải được danh sách kết nối.'); }
    finally { setLoading(false); }
  }, []);

  // eslint-disable-next-line react/set-state-in-effect -- Fetches persisted connection state on mount.
  useEffect(() => { void load(); }, [load]);

  const run = async (key, path, options, successText) => {
    setBusy(key); setError(''); setNotice('');
    try {
      const result = await requestJson(path, options);
      setNotice(successText || result.message || 'Đã cập nhật kết nối.');
      await load();
      onChanged?.();
      return result;
    } catch (cause) { setError(cause.message || 'Không thể cập nhật kết nối.'); return null; }
    finally { setBusy(''); }
  };

  const testNew = async (event) => {
    event.preventDefault();
    setBusy('new-test'); setError(''); setNotice(''); setTested(false);
    try {
      await requestJson('/api/integrations/hrm/connections/test', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form),
      });
      setTested(true); setNotice('Kết nối thử thành công. Bạn có thể lưu nguồn này; dữ liệu chưa được đồng bộ vào IMS.');
    } catch (cause) { setError(cause.message || 'Kiểm tra Sandbox thất bại.'); }
    finally { setBusy(''); }
  };

  const saveNew = async () => {
    setBusy('new-save'); setError('');
    try {
      const saved = await requestJson('/api/integrations/hrm/connections', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form),
      });
      setConnections((items) => [...items, saved]);
      setForm({ connection_name: '', endpoint: 'http://127.0.0.1:8100', api_key: '' });
      setTested(false); setDialog(''); setNotice('Đã lưu Sandbox mới. Hãy chọn “Dùng làm nguồn” để chuyển kết nối đang hoạt động.');
      await load(); onChanged?.();
    } catch (cause) { setError(cause.message || 'Không lưu được kết nối.'); }
    finally { setBusy(''); }
  };

  const reconnect = async (event) => {
    event.preventDefault();
    if (!target) return;
    const response = await run('reconnect', `/api/integrations/hrm/connections/${target.connection_id}/reconnect`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ api_key: form.api_key }),
    }, 'Đã kiểm tra và lưu credential mới an toàn trong máy local.');
    if (response) {
      setDialog(''); setForm((value) => ({ ...value, api_key: '' })); setTarget(null);
    }
  };

  const activate = async (item) => {
    if (!window.confirm(`Chuyển nguồn HRM đang dùng sang “${item.connection_name}” (${item.endpoint})? Preview chờ từ mọi nguồn sẽ hết hiệu lực; dữ liệu và lịch sử từng nguồn vẫn được giữ riêng.`)) return;
    await run(`activate:${item.connection_id}`, `/api/integrations/hrm/connections/${item.connection_id}/activate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_active_id: activeId, confirm: true }),
    }, `Đã chuyển nguồn đang dùng sang ${item.connection_name}. Preview cũ đã hết hiệu lực.`);
  };

  const disconnect = async (item) => {
    if (!window.confirm(`Ngắt “${item.connection_name}”? Credential sẽ bị thu hồi khỏi máy local. Danh bạ, mapping và lịch sử sẽ được giữ lại.`)) return;
    await run(`disconnect:${item.connection_id}`, `/api/integrations/hrm/connections/${item.connection_id}/disconnect`, { method: 'POST' }, 'Đã ngắt kết nối; dữ liệu nguồn vẫn được giữ.');
  };

  const showHistory = async (item) => {
    setTarget(item); setHistory(null); setDialog('history'); setBusy(`history:${item.connection_id}`); setError('');
    try { setHistory(await requestJson(`/api/integrations/hrm/connections/${item.connection_id}/history?page=1&page_size=20`)); }
    catch (cause) { setError(cause.message || 'Không tải được lịch sử nguồn.'); }
    finally { setBusy(''); }
  };

  const closeDialog = () => {
    if (busy) return;
    setDialog(''); setTarget(null); setHistory(null); setTested(false);
    setForm((value) => ({ ...value, api_key: '' }));
  };

  return <section className="hrm-connection-manager workspace-card">
    <header className="hrm-connection-manager-heading">
      <div><span className="hrm-eyebrow">NGUỒN DỮ LIỆU HRM</span><h2>Quản lý kết nối</h2><p>Mỗi Sandbox có vùng external ID, mapping, preview và lịch sử riêng. Chỉ nguồn đang hoạt động được dùng để xem trước hoặc đồng bộ.</p></div>
      <div className="hrm-connection-manager-actions">
        <button type="button" className="btn btn-secondary" onClick={() => { setError(''); setLoading(true); void load(); }} disabled={loading || Boolean(busy)}><RefreshCw size={15} /> Làm mới</button>
        <button type="button" className="btn btn-primary" onClick={() => { setError(''); setNotice(''); setTested(false); setTarget(null); setForm({ connection_name: '', endpoint: 'http://127.0.0.1:8100', api_key: '' }); setDialog('add'); }}><Plus size={16} /> Thêm Sandbox</button>
      </div>
    </header>
    {error && <div className="hrm-message is-error" role="alert"><AlertTriangle size={17} />{error}</div>}
    {notice && <div className="hrm-message is-success" role="status">{notice}</div>}
    {loading ? <p className="hrm-empty">Đang tải các kết nối…</p> : connections.length === 0 ? <div className="hrm-connection-empty"><Link2 size={22} /><strong>Chưa có Sandbox được lưu</strong><span>Thêm endpoint localhost, kiểm tra API key rồi lưu để bắt đầu.</span></div> : (
      <div className="hrm-connection-list">{connections.map((item) => {
        const isActive = item.connection_id === activeId;
        const isBusy = busy.endsWith(item.connection_id);
        return <article className={`hrm-connection-item ${isActive ? 'is-current' : ''}`} key={item.connection_id}>
          <div className="hrm-connection-item-main">
            <div className="hrm-connection-item-title"><strong>{item.connection_name}</strong>{isActive && <span className="hrm-connection-active">ĐANG DÙNG</span>}<span className={`hrm-connection-state state-${String(item.state).toLowerCase()}`}>{STATE_LABEL[item.state] || item.state}</span></div>
            <code>{item.endpoint}</code>
            <small>{item.last_sync_at ? `Đồng bộ gần nhất: ${item.last_sync_at}` : 'Chưa có lượt đồng bộ'} · {item.has_credential ? 'Credential local đã lưu' : 'Cần nhập lại credential'}</small>
          </div>
          <div className="hrm-connection-item-controls">
            <button type="button" className="btn btn-secondary btn-sm" disabled={Boolean(busy)} onClick={() => void run(`test:${item.connection_id}`, `/api/integrations/hrm/connections/${item.connection_id}/test`, { method: 'POST' }, 'Kiểm tra kết nối hoàn tất.')}>{isBusy ? <LoaderCircle className="hrm-spin" size={14} /> : <Check size={14} />} Kiểm tra</button>
            {item.state === 'PAUSED'
              ? <button type="button" className="btn btn-secondary btn-sm" disabled={Boolean(busy)} onClick={() => void run(`resume:${item.connection_id}`, `/api/integrations/hrm/connections/${item.connection_id}/resume`, { method: 'POST' }, 'Đã kiểm tra và tiếp tục kết nối.') }><CirclePlay size={14} /> Tiếp tục</button>
              : item.state === 'CONNECTED' && <button type="button" className="btn btn-secondary btn-sm" disabled={Boolean(busy)} onClick={() => void run(`pause:${item.connection_id}`, `/api/integrations/hrm/connections/${item.connection_id}/pause`, { method: 'POST' }, 'Đã tạm dừng; không thể tạo preview hoặc sync mới.') }><CirclePause size={14} /> Tạm dừng</button>}
            {!isActive && item.state === 'CONNECTED' && <button type="button" className="btn btn-primary btn-sm" disabled={Boolean(busy)} onClick={() => void activate(item)}><Check size={14} /> Dùng làm nguồn</button>}
            <button type="button" className="btn btn-secondary btn-sm" disabled={Boolean(busy)} onClick={() => { setTarget(item); setForm((value) => ({ ...value, api_key: '' })); setError(''); setDialog('reconnect'); }}><Link2 size={14} /> Kết nối lại</button>
            <button type="button" className="btn btn-secondary btn-sm" disabled={Boolean(busy)} onClick={() => void showHistory(item)}><Clock3 size={14} /> Lịch sử</button>
            <button type="button" className="btn btn-danger-outline btn-sm" disabled={Boolean(busy)} onClick={() => void disconnect(item)}><Unplug size={14} /> Ngắt</button>
          </div>
        </article>;
      })}</div>
    )}
    {dialog && <div className="hrm-connection-modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && closeDialog()}>
      <section className="hrm-connection-modal" role="dialog" aria-modal="true" aria-labelledby="hrm-connection-modal-title">
        <header><div><span className="hrm-eyebrow">CẤU HÌNH LOCAL</span><h2 id="hrm-connection-modal-title">{dialog === 'add' ? 'Thêm HRM Sandbox' : dialog === 'reconnect' ? `Kết nối lại ${target?.connection_name || ''}` : `Lịch sử · ${target?.connection_name || ''}`}</h2></div><button type="button" className="modal-close-btn" onClick={closeDialog} aria-label="Đóng"><X size={18} /></button></header>
        {(dialog === 'add' || dialog === 'reconnect') && <form onSubmit={dialog === 'add' ? (event) => { event.preventDefault(); void testNew(event); } : reconnect}>
          {dialog === 'add' && <>
            <label className="form-group"><span className="form-label">Tên kết nối <b className="required">*</b></span><input className="form-control" required maxLength={100} value={form.connection_name} onChange={(event) => { setForm((value) => ({ ...value, connection_name: event.target.value })); setTested(false); }} placeholder="Ví dụ: HRM Sandbox B" /></label>
            <label className="form-group"><span className="form-label">Endpoint local <b className="required">*</b></span><input className="form-control" required value={form.endpoint} onChange={(event) => { setForm((value) => ({ ...value, endpoint: event.target.value })); setTested(false); }} placeholder="http://127.0.0.1:8101" /><small className="form-hint">Chỉ chấp nhận loopback HTTP, cổng 8100–8109. Không dùng địa chỉ Internet.</small></label>
          </>}
          <label className="form-group"><span className="form-label">Sandbox service API key <b className="required">*</b></span><input className="form-control" type="password" autoComplete="new-password" required minLength={32} maxLength={256} value={form.api_key} onChange={(event) => { setForm((value) => ({ ...value, api_key: event.target.value })); setTested(false); }} placeholder="Chỉ lưu an toàn trên máy local" /><small className="form-hint">Dùng HRM_SANDBOX_API_KEY dành cho IMS service; không nhập khóa quản trị HRM_SANDBOX_ADMIN_API_KEY. Key chỉ gửi trong local request body, không hiện lại và không ghi vào URL hoặc UI sau khi lưu.</small></label>
          {error && <div className="hrm-message is-error" role="alert"><AlertTriangle size={16} />{error}</div>}
          <footer>
            {dialog === 'add' && <button className="btn btn-secondary" type="submit" disabled={Boolean(busy)}>{busy === 'new-test' ? <LoaderCircle className="hrm-spin" size={15} /> : <Link2 size={15} />} Kiểm tra trước</button>}
            {dialog === 'add' ? <button className="btn btn-primary" type="button" disabled={!tested || Boolean(busy)} onClick={() => void saveNew()}>{busy === 'new-save' ? <LoaderCircle className="hrm-spin" size={15} /> : <Check size={15} />} Lưu kết nối</button> : <button className="btn btn-primary" type="submit" disabled={Boolean(busy)}>{busy === 'reconnect' ? <LoaderCircle className="hrm-spin" size={15} /> : <Link2 size={15} />} Kiểm tra và kết nối lại</button>}
          </footer>
        </form>}
        {dialog === 'history' && <div className="hrm-connection-history">
          {busy ? <p className="hrm-empty"><LoaderCircle className="hrm-spin" size={15} /> Đang tải lịch sử…</p> : history?.items?.length ? history.items.map((item) => <div key={`${item.source}-${item.id}`}><span>{item.source}</span><strong>{item.event}</strong><small>{item.created_at}{item.detail ? ` · ${item.detail}` : ''}</small></div>) : <p className="hrm-empty">Chưa có lịch sử cho nguồn này.</p>}
        </div>}
      </section>
    </div>}
  </section>;
}
