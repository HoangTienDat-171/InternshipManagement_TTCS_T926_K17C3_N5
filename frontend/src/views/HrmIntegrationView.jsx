import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  Database,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
  UsersRound,
} from 'lucide-react';
import { apiFetch } from '../utils/api';
import './HrmIntegrationView.css';

const EMPTY_STATUS = {
  state: 'NOT_CONFIGURED',
  configured: false,
  can_test_connection: false,
  can_preview: false,
  can_sync: false,
  sync_history_available: false,
  missing_requirements: [],
  sync_scope: [],
  excluded_scope: [],
  message: '',
};

export default function HrmIntegrationView() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const requestStatus = async (signal) => {
    const response = await apiFetch('/api/integrations/hrm/status', { signal });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || 'Không tải được trạng thái tích hợp HRM.');
    return payload;
  };

  const loadStatus = async (signal) => {
    try {
      const payload = await requestStatus(signal);
      if (!signal?.aborted) setStatus(payload);
    } catch (cause) {
      if (cause.name !== 'AbortError') setError(cause.message || 'Không tải được trạng thái tích hợp HRM.');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  };

  const refreshStatus = () => {
    setLoading(true);
    setError('');
    loadStatus();
  };

  useEffect(() => {
    const controller = new AbortController();
    requestStatus(controller.signal)
      .then((payload) => { if (!controller.signal.aborted) setStatus(payload); })
      .catch((cause) => { if (!controller.signal.aborted && cause.name !== 'AbortError') setError(cause.message || 'Không tải được trạng thái tích hợp HRM.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  const current = status || EMPTY_STATUS;

  return (
    <section className="hrm-integration-page">
      <header className="hrm-page-header">
        <div>
          <span className="hrm-eyebrow">TÍCH HỢP HỆ THỐNG</span>
          <h1>Đồng bộ dữ liệu HRM</h1>
          <p>Theo dõi cấu hình và chuẩn bị đồng bộ hồ sơ nhân sự vào IMS.</p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={refreshStatus} disabled={loading}>
          <RefreshCw size={16} aria-hidden="true" /> Làm mới
        </button>
      </header>

      {error && <div className="hrm-error" role="alert"><AlertTriangle size={18} />{error}</div>}

      <section className={`hrm-status-card${current.configured ? ' is-ready' : ' is-blocked'}`} aria-live="polite">
        <div className="hrm-status-icon">
          {current.configured ? <CheckCircle2 size={24} /> : <CircleHelp size={24} />}
        </div>
        <div className="hrm-status-copy">
          <span className="hrm-status-label">{loading ? 'ĐANG KIỂM TRA' : current.configured ? 'SẴN SÀNG KIỂM TRA' : 'CHƯA CẤU HÌNH HRM'}</span>
          <h2>{current.provider_name || 'Chưa có nhà cung cấp HRM được cấu hình'}</h2>
          <p>{current.message || (loading ? 'Đang đọc trạng thái từ backend.' : 'Không có adapter hoặc cấu hình HRM trong source hiện tại.')}</p>
        </div>
        <span className="hrm-status-badge">{current.configured ? 'Chờ kiểm tra' : 'Bị chặn bởi cấu hình'}</span>
      </section>

      <div className="hrm-summary-grid">
        <article className="hrm-summary-card">
          <span className="hrm-summary-icon"><Database size={18} /></span>
          <div><span>Nhà cung cấp</span><strong>{current.provider_name || 'Chưa xác định'}</strong></div>
        </article>
        <article className="hrm-summary-card">
          <span className="hrm-summary-icon"><UsersRound size={18} /></span>
          <div><span>Bản ghi xem trước</span><strong>Chưa có</strong></div>
        </article>
        <article className="hrm-summary-card">
          <span className="hrm-summary-icon"><ShieldCheck size={18} /></span>
          <div><span>Lần đồng bộ gần nhất</span><strong>Chưa có</strong></div>
        </article>
      </div>

      <div className="hrm-content-grid">
        <section className="hrm-panel">
          <div className="hrm-panel-heading">
            <div><h2>Điều kiện cần để kết nối</h2><p>Chưa có thông tin nhà cung cấp/API trong backlog hoặc source hiện tại.</p></div>
            <LockKeyhole size={19} aria-hidden="true" />
          </div>
          {loading ? <p className="hrm-empty" role="status">Đang tải trạng thái cấu hình…</p> : (
            <ol className="hrm-requirements">
              {current.missing_requirements.map((item) => <li key={item}>{item}</li>)}
            </ol>
          )}
        </section>

        <section className="hrm-panel">
          <div className="hrm-panel-heading">
            <div><h2>Phạm vi dữ liệu</h2><p>Quy tắc giới hạn tác động của tích hợp.</p></div>
            <ShieldCheck size={19} aria-hidden="true" />
          </div>
          <h3>Dữ liệu dự kiến đối chiếu</h3>
          <ul className="hrm-scope-list is-included">
            {current.sync_scope.map((item) => <li key={item}>{item}</li>)}
          </ul>
          <h3>Không đồng bộ</h3>
          <ul className="hrm-scope-list is-excluded">
            {current.excluded_scope.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </section>
      </div>

      <section className="hrm-panel hrm-actions-panel">
        <div className="hrm-panel-heading">
          <div><h2>Kiểm tra và đồng bộ</h2><p>Thao tác bị khóa cho đến khi có adapter HRM thật và được kiểm tra.</p></div>
          <AlertTriangle size={19} aria-hidden="true" />
        </div>
        <div className="hrm-action-row">
          <button type="button" className="btn btn-secondary" disabled={!current.can_test_connection} title="Cần provider adapter và cấu hình được duyệt.">Kiểm tra kết nối</button>
          <button type="button" className="btn btn-secondary" disabled={!current.can_preview} title="Cần kết nối HRM thật để tạo bản xem trước.">Tạo bản xem trước</button>
          <button type="button" className="btn btn-primary" disabled={!current.can_sync} title="Đồng bộ chỉ bật sau khi xem trước và xác nhận.">Đồng bộ sau khi xác nhận</button>
        </div>
        <p className="hrm-action-note">Không gửi request đến máy chủ HRM, không tạo dữ liệu thử và không sửa tài khoản IMS ở trạng thái hiện tại.</p>
      </section>

      <section className="hrm-history-panel" aria-label="Lịch sử đồng bộ">
        <div><h2>Lịch sử đồng bộ</h2><p>{current.sync_history_available ? 'Các lần đồng bộ sẽ được ghi lại.' : 'Chưa có lịch sử: chưa có provider thật hoặc lần đồng bộ nào được thực hiện.'}</p></div>
        <span>0 lần</span>
      </section>
    </section>
  );
}
