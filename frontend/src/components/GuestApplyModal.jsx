import React, { useState, useEffect } from 'react';
import { X, Upload, CheckCircle2, AlertCircle, RefreshCw, Copy, Check, FileCheck, ArrowRight } from 'lucide-react';

export default function GuestApplyModal({ job, onClose, onSuccess }) {
  const [formData, setFormData] = useState({
    full_name: '',
    email: '',
    phone: '',
    university: '',
    major: '',
    year_of_study: 'Năm 3',
    expected_duration: '3 tháng',
    portfolio_link: '',
    captcha_answer: ''
  });
  const [cvFile, setCvFile] = useState(null);
  const [captcha, setCaptcha] = useState({ question: '', token: '' });
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [submittedResult, setSubmittedResult] = useState(null);
  const [copied, setCopied] = useState(false);

  const loadCaptcha = async () => {
    try {
      const res = await fetch('/api/guest/captcha');
      const data = await res.json();
      setCaptcha({ question: data.question, token: data.captcha_token });
    } catch (err) {
      console.error('Không thể tải mã bảo vệ:', err);
    }
  };

  useEffect(() => {
    loadCaptcha();
  }, []);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const validExts = ['.pdf', '.docx'];
    const lowerName = file.name.toLowerCase();
    const hasValidExt = validExts.some(ext => lowerName.endsWith(ext));

    if (!hasValidExt) {
      setErrorMsg('Hệ thống chỉ chấp nhận định dạng tệp PDF hoặc DOCX.');
      e.target.value = '';
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      setErrorMsg('Dung lượng tệp CV vượt quá giới hạn tối đa 5MB.');
      e.target.value = '';
      return;
    }

    setErrorMsg('');
    setCvFile(file);
  };

  const handleCopyCode = (code) => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!cvFile) {
      setErrorMsg('Vui lòng đính kèm tệp tin CV (PDF hoặc DOCX).');
      return;
    }
    if (!formData.captcha_answer.trim()) {
      setErrorMsg('Vui lòng nhập câu trả lời cho mã bảo vệ.');
      return;
    }

    setSubmitting(true);
    setErrorMsg('');

    const body = new FormData();
    body.append('program_id', job.id);
    body.append('full_name', formData.full_name);
    body.append('email', formData.email);
    body.append('phone', formData.phone);
    body.append('university', formData.university);
    body.append('major', formData.major);
    body.append('year_of_study', formData.year_of_study);
    body.append('expected_duration', formData.expected_duration);
    if (formData.portfolio_link) {
      body.append('portfolio_link', formData.portfolio_link);
    }
    body.append('captcha_token', captcha.token);
    body.append('captcha_answer', formData.captcha_answer);
    body.append('cv_file', cvFile);

    try {
      const res = await fetch('/api/guest/apply', {
        method: 'POST',
        body
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Có lỗi xảy ra khi nộp hồ sơ.');
      }
      setSubmittedResult(data);
    } catch (err) {
      setErrorMsg(err.message);
      loadCaptcha();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 1000,
      background: 'rgba(15, 23, 42, 0.65)',
      backdropFilter: 'blur(4px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px'
    }}>
      <div style={{
        background: '#fff',
        borderRadius: 16,
        width: '100%',
        maxWidth: 640,
        maxHeight: '92vh',
        overflowY: 'auto',
        padding: '32px',
        position: 'relative',
        boxShadow: '0 20px 40px rgba(0,0,0,0.2)',
        animation: 'modalIn 0.25s ease-out'
      }}>
        <button
          type="button"
          onClick={onClose}
          style={{
            position: 'absolute',
            top: 20,
            right: 20,
            border: 'none',
            background: '#f1f5f9',
            borderRadius: '50%',
            width: 32,
            height: 32,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            color: '#64748b'
          }}
        >
          <X size={18} />
        </button>

        {submittedResult ? (
          <div style={{ textAlign: 'center', padding: '16px 8px' }}>
            <div style={{
              width: 64,
              height: 64,
              borderRadius: '50%',
              background: '#dcfce7',
              color: '#15803d',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px'
            }}>
              <CheckCircle2 size={36} />
            </div>

            <h2 style={{ fontSize: 24, fontWeight: 800, color: '#0f172a', marginBottom: 8 }}>
              Nộp Hồ Sơ Thành Công!
            </h2>
            <p style={{ color: '#475569', fontSize: 14, marginBottom: 24, lineHeight: 1.6 }}>
              Hồ sơ ứng tuyển vị trí <strong>{submittedResult.position_title}</strong> của bạn đã được chuyển tới phòng tuyển dụng.
            </p>

            <div style={{
              background: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: 12,
              padding: '20px',
              marginBottom: 24,
              textAlign: 'left'
            }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: 6 }}>
                Mã Tra Cứu Hồ Sơ (Tracking Code)
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <span style={{ fontSize: 22, fontWeight: 800, letterSpacing: '1px', color: '#2563eb' }}>
                  {submittedResult.tracking_code}
                </span>
                <button
                  type="button"
                  onClick={() => handleCopyCode(submittedResult.tracking_code)}
                  className="btn btn-secondary"
                  style={{ padding: '6px 14px', fontSize: 13, gap: 6 }}
                >
                  {copied ? <Check size={15} color="#15803d" /> : <Copy size={15} />}
                  {copied ? 'Đã sao chép' : 'Sao chép mã'}
                </button>
              </div>
              <div style={{ fontSize: 12, color: '#64748b', marginTop: 10 }}>
                * Email xác nhận kèm mã tra cứu và đường dẫn theo dõi đã được gửi tới <strong>{submittedResult.email}</strong>.
              </div>
            </div>

            <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onClose}
              >
                Đóng
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => onSuccess(submittedResult.tracking_code, submittedResult.email)}
              >
                Tra cứu tiến độ ngay <ArrowRight size={16} />
              </button>
            </div>
          </div>
        ) : (
          <>
            <div style={{ marginBottom: 20 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: '#2563eb', background: '#eff6ff', padding: '4px 10px', borderRadius: 20 }}>
                {job.department_name || 'Khối Kỹ Thuật'}
              </span>
              <h2 style={{ fontSize: 22, fontWeight: 800, color: '#0f172a', marginTop: 8, marginBottom: 4 }}>
                Ứng tuyển: {job.title}
              </h2>
              <p style={{ fontSize: 13, color: '#64748b' }}>
                Vui lòng điền thông tin bên dưới và đính kèm CV để ứng tuyển trực tiếp không cần đăng nhập.
              </p>
            </div>

            {errorMsg && (
              <div style={{
                background: '#fef2f2',
                border: '1px solid #fecaca',
                color: '#b91c1c',
                padding: '12px 16px',
                borderRadius: 8,
                fontSize: 13,
                marginBottom: 16,
                display: 'flex',
                alignItems: 'center',
                gap: 8
              }}>
                <AlertCircle size={16} />
                <span>{errorMsg}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 14 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 13, fontWeight: 600, color: '#334155', display: 'block', marginBottom: 4 }}>
                    Họ và tên *
                  </label>
                  <input
                    required
                    type="text"
                    className="form-control"
                    placeholder="Nguyễn Văn A"
                    value={formData.full_name}
                    onChange={e => setFormData({ ...formData, full_name: e.target.value })}
                  />
                </div>
                <div>
                  <label style={{ fontSize: 13, fontWeight: 600, color: '#334155', display: 'block', marginBottom: 4 }}>
                    Số điện thoại *
                  </label>
                  <input
                    required
                    type="tel"
                    className="form-control"
                    placeholder="0912345678"
                    value={formData.phone}
                    onChange={e => setFormData({ ...formData, phone: e.target.value })}
                  />
                </div>
              </div>

              <div>
                <label style={{ fontSize: 13, fontWeight: 600, color: '#334155', display: 'block', marginBottom: 4 }}>
                  Địa chỉ Email (Nhận mã tra cứu & kết quả) *
                </label>
                <input
                  required
                  type="email"
                  className="form-control"
                  placeholder="nguyenvana@gmail.com"
                  value={formData.email}
                  onChange={e => setFormData({ ...formData, email: e.target.value })}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 13, fontWeight: 600, color: '#334155', display: 'block', marginBottom: 4 }}>
                    Trường Đại học *
                  </label>
                  <input
                    required
                    type="text"
                    className="form-control"
                    placeholder="Đại học Bách Khoa Hà Nội"
                    value={formData.university}
                    onChange={e => setFormData({ ...formData, university: e.target.value })}
                  />
                </div>
                <div>
                  <label style={{ fontSize: 13, fontWeight: 600, color: '#334155', display: 'block', marginBottom: 4 }}>
                    Chuyên ngành *
                  </label>
                  <input
                    required
                    type="text"
                    className="form-control"
                    placeholder="Kỹ thuật phần mềm"
                    value={formData.major}
                    onChange={e => setFormData({ ...formData, major: e.target.value })}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 13, fontWeight: 600, color: '#334155', display: 'block', marginBottom: 4 }}>
                    Năm học hiện tại *
                  </label>
                  <select
                    className="form-control"
                    value={formData.year_of_study}
                    onChange={e => setFormData({ ...formData, year_of_study: e.target.value })}
                  >
                    <option value="Năm 2">Năm 2</option>
                    <option value="Năm 3">Năm 3</option>
                    <option value="Năm 4">Năm 4</option>
                    <option value="Mới tốt nghiệp">Mới tốt nghiệp</option>
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: 13, fontWeight: 600, color: '#334155', display: 'block', marginBottom: 4 }}>
                    Thời gian thực tập dự kiến *
                  </label>
                  <select
                    className="form-control"
                    value={formData.expected_duration}
                    onChange={e => setFormData({ ...formData, expected_duration: e.target.value })}
                  >
                    <option value="3 tháng">3 tháng (Toàn thời gian)</option>
                    <option value="6 tháng">6 tháng (Toàn thời gian)</option>
                    <option value="Part-time linh hoạt">Bán thời gian linh hoạt</option>
                  </select>
                </div>
              </div>

              <div>
                <label style={{ fontSize: 13, fontWeight: 600, color: '#334155', display: 'block', marginBottom: 4 }}>
                  Liên kết Portfolio / GitHub / LinkedIn (không bắt buộc)
                </label>
                <input
                  type="url"
                  className="form-control"
                  placeholder="https://github.com/username hoặc https://portfolio.dev"
                  value={formData.portfolio_link}
                  onChange={e => setFormData({ ...formData, portfolio_link: e.target.value })}
                />
              </div>

              {/* CV File Upload */}
              <div>
                <label style={{ fontSize: 13, fontWeight: 600, color: '#334155', display: 'block', marginBottom: 4 }}>
                  Tải lên tệp CV (Chỉ chấp nhận PDF hoặc DOCX, tối đa 5MB) *
                </label>
                <div style={{
                  border: '2px dashed #cbd5e1',
                  borderRadius: 10,
                  padding: '16px',
                  textAlign: 'center',
                  background: cvFile ? '#f0fdf4' : '#f8fafc',
                  borderColor: cvFile ? '#86efac' : '#cbd5e1',
                  position: 'relative'
                }}>
                  <input
                    required
                    type="file"
                    accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    onChange={handleFileChange}
                    style={{
                      position: 'absolute',
                      inset: 0,
                      opacity: 0,
                      cursor: 'pointer',
                      width: '100%',
                      height: '100%'
                    }}
                  />
                  {cvFile ? (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, color: '#166534' }}>
                      <FileCheck size={20} />
                      <span style={{ fontWeight: 600, fontSize: 14 }}>{cvFile.name}</span>
                      <span style={{ fontSize: 12, color: '#64748b' }}>({(cvFile.size / 1024 / 1024).toFixed(2)} MB)</span>
                    </div>
                  ) : (
                    <div>
                      <Upload size={24} color="#64748b" style={{ marginBottom: 6 }} />
                      <div style={{ fontSize: 13, color: '#475569', fontWeight: 500 }}>
                        Nhấp hoặc kéo thả tệp CV vào đây
                      </div>
                      <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>
                        PDF, DOCX (Dung lượng tối đa: 5MB)
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Anti-bot Captcha */}
              <div style={{
                background: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: 10,
                padding: '12px 16px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 12
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: '#1e293b' }}>
                    Mã xác thực: {captcha.question || '...'}
                  </span>
                  <button
                    type="button"
                    onClick={loadCaptcha}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      cursor: 'pointer',
                      color: '#64748b',
                      padding: 4
                    }}
                    title="Đổi câu hỏi khác"
                  >
                    <RefreshCw size={15} />
                  </button>
                </div>
                <input
                  required
                  type="text"
                  className="form-control"
                  style={{ width: 110, textAlign: 'center' }}
                  placeholder="Đáp án"
                  value={formData.captcha_answer}
                  onChange={e => setFormData({ ...formData, captcha_answer: e.target.value })}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={onClose}
                  disabled={submitting}
                >
                  Hủy bỏ
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={submitting}
                  style={{ minWidth: 140 }}
                >
                  {submitting ? 'Đang gửi hồ sơ...' : 'Nộp Đơn Ứng Tuyển'}
                </button>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
