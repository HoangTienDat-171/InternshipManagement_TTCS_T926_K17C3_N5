import React, { useState, useEffect } from 'react';
import { Search, ArrowLeft, CheckCircle2, Clock, XCircle, AlertCircle, Calendar, Building, Briefcase, User, ShieldCheck } from 'lucide-react';

const fetchGuestTracking = async (code, email, signal) => {
  const formData = new FormData();
  formData.append('tracking_code', code);
  formData.append('email', email);

  const res = await fetch('/api/guest/track', {
    method: 'POST',
    body: formData,
    signal
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || 'Kh?ng t?m th?y h? s? v?i th?ng tin ?? cung c?p.');
  }
  return data;
};

export default function GuestTrackingView({ initialCode, initialEmail, onBack }) {
  const [trackingCode, setTrackingCode] = useState(initialCode || '');
  const [email, setEmail] = useState(initialEmail || '');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(Boolean(initialCode && initialEmail));
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (!initialCode || !initialEmail) return undefined;
    const controller = new AbortController();

    const loadInitialResult = async () => {
      try {
        const data = await fetchGuestTracking(initialCode, initialEmail, controller.signal);
        setResult(data);
        setErrorMsg('');
      } catch (err) {
        if (!controller.signal.aborted) setErrorMsg(err.message);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };

    void loadInitialResult();
    return () => controller.abort();
  }, [initialCode, initialEmail]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErrorMsg('');
    setResult(null);
    try {
      setResult(await fetchGuestTracking(trackingCode, email));
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  const renderStatusBadge = (status) => {
    switch (status) {
      case 'ACCEPTED':
        return (
          <span style={{
            background: '#dcfce7',
            color: '#15803d',
            padding: '6px 14px',
            borderRadius: 20,
            fontWeight: 700,
            fontSize: 13,
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6
          }}>
            <CheckCircle2 size={16} /> Đã Trúng Tuyển (Accepted)
          </span>
        );
      case 'UNDER_REVIEW':
        return (
          <span style={{
            background: '#e0f2fe',
            color: '#0369a1',
            padding: '6px 14px',
            borderRadius: 20,
            fontWeight: 700,
            fontSize: 13,
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6
          }}>
            <Clock size={16} /> Đang Xét Duyệt (Under Review)
          </span>
        );
      case 'REJECTED':
        return (
          <span style={{
            background: '#fee2e2',
            color: '#b91c1c',
            padding: '6px 14px',
            borderRadius: 20,
            fontWeight: 700,
            fontSize: 13,
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6
          }}>
            <XCircle size={16} /> Chưa Phù Hợp (Rejected)
          </span>
        );
      default:
        return (
          <span style={{
            background: '#fef3c7',
            color: '#b45309',
            padding: '6px 14px',
            borderRadius: 20,
            fontWeight: 700,
            fontSize: 13,
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6
          }}>
            <Clock size={16} /> Chờ Tiếp Nhận (Pending)
          </span>
        );
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--app-bg, #f8fafc)', padding: '40px 20px' }}>
      <div style={{ maxWidth: 720, margin: '0 auto' }}>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={onBack}
          style={{ marginBottom: 24, gap: 6 }}
        >
          <ArrowLeft size={16} /> Quay lại danh sách việc làm
        </button>

        <div style={{
          background: '#fff',
          borderRadius: 16,
          border: '1px solid #e2e8f0',
          padding: '32px',
          boxShadow: '0 4px 20px rgba(0,0,0,0.04)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
            <div style={{
              width: 40,
              height: 40,
              borderRadius: 10,
              background: '#eff6ff',
              color: '#2563eb',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <Search size={20} />
            </div>
            <div>
              <h1 style={{ fontSize: 22, fontWeight: 800, color: '#0f172a' }}>
                Tra Cứu Trạng Thái Hồ Sơ Ứng Tuyển
              </h1>
              <p style={{ fontSize: 13, color: '#64748b' }}>
                Cổng công khai dành cho ứng viên kiểm tra tiến độ xét duyệt trực tiếp.
              </p>
            </div>
          </div>

          <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 14, marginTop: 24, marginBottom: 24 }}>
            <div>
              <label style={{ fontSize: 13, fontWeight: 600, color: '#334155', display: 'block', marginBottom: 4 }}>
                Mã tra cứu hồ sơ (Tracking Code) *
              </label>
              <input
                required
                type="text"
                className="form-control"
                placeholder="VD: APP-9F2B81C4"
                value={trackingCode}
                onChange={e => setTrackingCode(e.target.value)}
              />
            </div>
            <div>
              <label style={{ fontSize: 13, fontWeight: 600, color: '#334155', display: 'block', marginBottom: 4 }}>
                Địa chỉ Email đã dùng khi nộp đơn *
              </label>
              <input
                required
                type="email"
                className="form-control"
                placeholder="email.ungvien@example.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading}
              style={{ justifyContent: 'center', padding: '12px' }}
            >
              <Search size={16} />
              {loading ? 'Đang tra cứu dữ liệu...' : 'Tra Cứu Trạng Thái'}
            </button>
          </form>

          {errorMsg && (
            <div style={{
              background: '#fef2f2',
              border: '1px solid #fecaca',
              color: '#b91c1c',
              padding: '12px 16px',
              borderRadius: 8,
              fontSize: 13,
              display: 'flex',
              alignItems: 'center',
              gap: 8
            }}>
              <AlertCircle size={16} />
              <span>{errorMsg}</span>
            </div>
          )}

          {result && (
            <div style={{
              borderTop: '1px solid #e2e8f0',
              paddingTop: 24,
              animation: 'modalIn 0.25s ease-out'
            }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 12,
                marginBottom: 20
              }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#64748b' }}>MÃ TRA CỨU HỢP LỆ</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: '#2563eb' }}>{result.tracking_code}</div>
                </div>
                {renderStatusBadge(result.status)}
              </div>

              {/* Application Details Grid */}
              <div style={{
                background: '#f8fafc',
                border: '1px solid #f1f5f9',
                borderRadius: 12,
                padding: '20px',
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
                gap: 16
              }}>
                <div>
                  <div style={{ fontSize: 12, color: '#64748b', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <User size={14} /> Ứng viên
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>{result.candidate_name}</div>
                </div>

                <div>
                  <div style={{ fontSize: 12, color: '#64748b', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <Briefcase size={14} /> Vị trí ứng tuyển
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>{result.position_title}</div>
                </div>

                <div>
                  <div style={{ fontSize: 12, color: '#64748b', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <Building size={14} /> Phòng ban
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#334155' }}>{result.department_name}</div>
                </div>

                <div>
                  <div style={{ fontSize: 12, color: '#64748b', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <Calendar size={14} /> Thời gian nộp đơn
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#334155' }}>{result.submission_date}</div>
                </div>
              </div>

              {/* Status Pipeline description */}
              <div style={{ marginTop: 24, padding: '16px', background: '#f0fdf4', borderRadius: 10, border: '1px solid #dcfce7' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#166534', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                  <ShieldCheck size={16} /> Lưu ý bảo mật thông tin
                </div>
                <div style={{ fontSize: 12, color: '#15803d', lineHeight: 1.5 }}>
                  Hệ thống bảo vệ quyền riêng tư tuyệt đối cho ứng viên: Mọi thông tin chi tiết về nhận xét chuyên môn, lịch phỏng vấn và phản hồi tuyển dụng sẽ được phòng nhân sự gửi trực tiếp tới email của bạn.
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
