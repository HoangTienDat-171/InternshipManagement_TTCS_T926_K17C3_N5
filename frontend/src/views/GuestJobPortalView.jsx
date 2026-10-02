import React, { useState, useEffect } from 'react';
import { Search, Briefcase, Calendar, MapPin, ChevronRight, LogIn, X } from 'lucide-react';
import GuestApplyModal from '../components/GuestApplyModal';

export default function GuestJobPortalView({ onOpenTracking, onGoToLogin }) {
  const [jobs, setJobs] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [keyword, setKeyword] = useState('');
  const [selectedDept, setSelectedDept] = useState('');
  const [applyingJob, setApplyingJob] = useState(null);
  const [viewingDetailJob, setViewingDetailJob] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    const loadJobs = async () => {
      try {
        const params = new URLSearchParams();
        if (keyword.trim()) params.append('keyword', keyword.trim());
        if (selectedDept) params.append('department_id', selectedDept);

        const res = await fetch('/api/guest/programs?' + params.toString(), {
          signal: controller.signal
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Kh?ng th? t?i danh s?ch v? tr?.');
        setJobs(data.items || []);

        // Extract unique departments for filter
        const depts = [];
        const seen = new Set();
        (data.items || []).forEach(j => {
          if (j.department_id && !seen.has(j.department_id)) {
            seen.add(j.department_id);
            depts.push({ id: j.department_id, name: j.department_name });
          }
        });
        if (depts.length > 0) {
          setDepartments(previous => previous.length === 0 ? depts : previous);
        }
      } catch (err) {
        if (!controller.signal.aborted) console.error('L?i t?i danh s?ch v? tr?:', err);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };

    void loadJobs();
    return () => controller.abort();
  }, [keyword, selectedDept]);

  return (
    <div style={{ minHeight: '100vh', background: 'var(--app-bg, #f8fafc)', display: 'flex', flexDirection: 'column' }}>
      {/* Top Header Navbar */}
      <header style={{
        background: '#fff',
        borderBottom: '1px solid #e2e8f0',
        padding: '14px 28px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        position: 'sticky',
        top: 0,
        zIndex: 40,
        boxShadow: '0 1px 3px rgba(0,0,0,0.02)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 38,
            height: 38,
            borderRadius: 10,
            background: 'linear-gradient(135deg, #2563eb, #1d4ed8)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            boxShadow: '0 4px 10px rgba(37,99,235,0.3)'
          }}>
            <Briefcase size={20} />
          </div>
          <div>
            <div style={{ fontSize: 17, fontWeight: 800, color: '#0f172a', lineHeight: 1.2 }}>
              IMS Career Portal
            </div>
            <div style={{ fontSize: 11, color: '#64748b' }}>
              Cổng Tuyển Dụng Thực Tập Sinh Toàn Diện
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => onOpenTracking()}
            style={{ fontSize: 13, gap: 6 }}
          >
            <Search size={15} />
            Tra cứu hồ sơ
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onGoToLogin}
            style={{ fontSize: 13, gap: 6 }}
          >
            <LogIn size={15} />
            Đăng nhập nội bộ
          </button>
        </div>
      </header>

      {/* Hero Banner Section */}
      <section style={{
        background: 'linear-gradient(135deg, #1e3a8a 0%, #2563eb 50%, #3b82f6 100%)',
        color: '#fff',
        padding: '52px 24px',
        textAlign: 'center',
        position: 'relative',
        overflow: 'hidden'
      }}>
        <div style={{ maxWidth: 800, margin: '0 auto', position: 'relative', zIndex: 1 }}>
          <span style={{
            background: 'rgba(255,255,255,0.15)',
            backdropFilter: 'blur(8px)',
            color: '#fff',
            fontSize: 12,
            fontWeight: 700,
            padding: '4px 14px',
            borderRadius: 20,
            display: 'inline-block',
            marginBottom: 16
          }}>
            ✦ CƠ HỘI THỰC TẬP KHÓA MỚI 2026
          </span>
          <h1 style={{ fontSize: 34, fontWeight: 900, marginBottom: 12, letterSpacing: '-0.5px' }}>
            Khởi Đầu Sự Nghiệp Cùng Đội Ngũ Chuyên Gia
          </h1>
          <p style={{ fontSize: 15, opacity: 0.92, maxWidth: 640, margin: '0 auto 32px', lineHeight: 1.6 }}>
            Ứng tuyển nhanh chóng không cần đăng ký tài khoản. Nhận hướng dẫn trực tiếp 1-1 từ các Senior Mentor hàng đầu và tham gia dự án thực tế.
          </p>

          {/* Search Bar & Filter */}
          <div style={{
            maxWidth: 680,
            margin: '0 auto',
            display: 'flex',
            background: '#fff',
            borderRadius: 14,
            padding: 6,
            boxShadow: '0 12px 36px rgba(0,0,0,0.18)',
            gap: 8,
            alignItems: 'center'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', padding: '0 12px', color: '#64748b', flex: 1 }}>
              <Search size={18} />
              <input
                type="text"
                placeholder="Tìm vị trí, kỹ năng (Python, React, AI, Bảo mật)..."
                value={keyword}
                onChange={e => { setLoading(true); setKeyword(e.target.value); }}
                style={{
                  border: 'none',
                  outline: 'none',
                  padding: '12px 10px',
                  width: '100%',
                  fontSize: 14,
                  color: '#0f172a'
                }}
              />
            </div>
            {departments.length > 0 && (
              <select
                value={selectedDept}
                onChange={e => { setLoading(true); setSelectedDept(e.target.value); }}
                style={{
                  border: '1px solid #e2e8f0',
                  borderRadius: 8,
                  padding: '10px 12px',
                  fontSize: 13,
                  outline: 'none',
                  color: '#334155',
                  background: '#f8fafc',
                  maxWidth: 180
                }}
              >
                <option value="">Tất cả phòng ban</option>
                {departments.map(d => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
            )}
          </div>
        </div>
      </section>

      {/* Main Content Area */}
      <main style={{ maxWidth: 1160, width: '100%', margin: '36px auto', padding: '0 20px', flex: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div>
            <h2 style={{ fontSize: 20, fontWeight: 800, color: '#0f172a' }}>
              Vị Trí Đang Mở Đơn Tuyển ({jobs.length})
            </h2>
            <p style={{ fontSize: 13, color: '#64748b', marginTop: 2 }}>
              Chọn vị trí phù hợp với năng lực của bạn để xem chi tiết và nộp hồ sơ trực tuyến.
            </p>
          </div>
        </div>

        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: '#64748b' }}>
            <p>Đang tìm kiếm các vị trí thực tập phù hợp...</p>
          </div>
        ) : jobs.length === 0 ? (
          <div style={{
            textAlign: 'center',
            background: '#fff',
            padding: '56px 20px',
            borderRadius: 16,
            border: '1px solid #e2e8f0'
          }}>
            <Briefcase size={44} color="#94a3b8" style={{ marginBottom: 12 }} />
            <h3 style={{ fontSize: 18, fontWeight: 700, color: '#334155', marginBottom: 6 }}>
              Không tìm thấy vị trí tuyển dụng phù hợp
            </h3>
            <p style={{ color: '#64748b', fontSize: 14 }}>
              Hãy thử tìm kiếm với từ khóa khác hoặc bỏ chọn bộ lọc phòng ban.
            </p>
          </div>
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
            gap: 24
          }}>
            {jobs.map(job => (
              <div
                key={job.id}
                style={{
                  background: '#fff',
                  borderRadius: 14,
                  border: '1px solid #e2e8f0',
                  padding: 24,
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  boxShadow: '0 2px 10px rgba(0,0,0,0.03)',
                  transition: 'all 0.2s ease'
                }}
              >
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                    <span style={{
                      fontSize: 12,
                      fontWeight: 700,
                      color: '#2563eb',
                      background: '#eff6ff',
                      padding: '4px 10px',
                      borderRadius: 16
                    }}>
                      {job.department_name}
                    </span>
                    <span style={{ fontSize: 12, color: '#64748b', display: 'flex', alignItems: 'center', gap: 4 }}>
                      <MapPin size={13} /> {job.location}
                    </span>
                  </div>

                  <h3 style={{ fontSize: 18, fontWeight: 800, color: '#0f172a', marginBottom: 8, lineHeight: 1.4 }}>
                    {job.title}
                  </h3>

                  <p style={{
                    fontSize: 13,
                    color: '#475569',
                    lineHeight: 1.6,
                    marginBottom: 16,
                    display: '-webkit-box',
                    WebkitLineClamp: 3,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden'
                  }}>
                    {job.description}
                  </p>

                  {/* Skills tags */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 20 }}>
                    {job.skills.map(s => (
                      <span
                        key={s}
                        style={{
                          fontSize: 11,
                          fontWeight: 600,
                          background: '#f1f5f9',
                          color: '#334155',
                          padding: '3px 8px',
                          borderRadius: 6
                        }}
                      >
                        {s}
                      </span>
                    ))}
                    <span style={{
                      fontSize: 11,
                      fontWeight: 600,
                      background: '#f0fdf4',
                      color: '#166534',
                      padding: '3px 8px',
                      borderRadius: 6
                    }}>
                      Chỉ tiêu: {job.vacancies}
                    </span>
                  </div>
                </div>

                <div style={{
                  borderTop: '1px solid #f1f5f9',
                  paddingTop: 16,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between'
                }}>
                  <div style={{ fontSize: 12, color: '#64748b', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Calendar size={13} />
                    Hạn nộp: {job.deadline || 'Tuyển liên tục'}
                  </div>

                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      style={{ padding: '7px 12px', fontSize: 12 }}
                      onClick={() => setViewingDetailJob(job)}
                    >
                      Chi tiết
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary"
                      style={{ padding: '7px 14px', fontSize: 12 }}
                      onClick={() => setApplyingJob(job)}
                    >
                      Ứng tuyển <ChevronRight size={14} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* Footer */}
      <footer style={{
        background: '#fff',
        borderTop: '1px solid #e2e8f0',
        padding: '24px 20px',
        textAlign: 'center',
        color: '#64748b',
        fontSize: 13,
        marginTop: 40
      }}>
        © 2026 Hệ Thống Quản Lý & Tuyển Dụng Thực Tập Sinh IMS. Bảo mật thông tin đa tầng.
      </footer>

      {/* Job Details Modal */}
      {viewingDetailJob && (
        <div style={{
          position: 'fixed',
          inset: 0,
          zIndex: 1000,
          background: 'rgba(15,23,42,0.65)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 20
        }}>
          <div style={{
            background: '#fff',
            borderRadius: 16,
            maxWidth: 620,
            width: '100%',
            maxHeight: '90vh',
            overflowY: 'auto',
            padding: 32,
            position: 'relative',
            boxShadow: '0 20px 40px rgba(0,0,0,0.2)'
          }}>
            <button
              type="button"
              onClick={() => setViewingDetailJob(null)}
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

            <span style={{ fontSize: 12, fontWeight: 700, color: '#2563eb', background: '#eff6ff', padding: '4px 10px', borderRadius: 16 }}>
              {viewingDetailJob.department_name}
            </span>
            <h2 style={{ fontSize: 22, fontWeight: 800, color: '#0f172a', marginTop: 10, marginBottom: 8 }}>
              {viewingDetailJob.title}
            </h2>
            <div style={{ fontSize: 13, color: '#64748b', display: 'flex', gap: 16, marginBottom: 20 }}>
              <span>📍 {viewingDetailJob.location}</span>
              <span>📅 Hạn ứng tuyển: {viewingDetailJob.deadline || 'Tuyển liên tục'}</span>
              <span>👥 Chỉ tiêu: {viewingDetailJob.vacancies}</span>
            </div>

            <div style={{ display: 'grid', gap: 18 }}>
              <div>
                <h4 style={{ fontSize: 14, fontWeight: 700, color: '#0f172a', marginBottom: 6 }}>
                  Mô tả công việc:
                </h4>
                <p style={{ fontSize: 13, color: '#475569', lineHeight: 1.6, whiteSpace: 'pre-line' }}>
                  {viewingDetailJob.description}
                </p>
              </div>

              <div>
                <h4 style={{ fontSize: 14, fontWeight: 700, color: '#0f172a', marginBottom: 6 }}>
                  Yêu cầu ứng viên:
                </h4>
                <p style={{ fontSize: 13, color: '#475569', lineHeight: 1.6, whiteSpace: 'pre-line' }}>
                  {viewingDetailJob.requirements}
                </p>
              </div>

              {viewingDetailJob.benefits && (
                <div>
                  <h4 style={{ fontSize: 14, fontWeight: 700, color: '#0f172a', marginBottom: 6 }}>
                    Quyền lợi thực tập:
                  </h4>
                  <p style={{ fontSize: 13, color: '#475569', lineHeight: 1.6, whiteSpace: 'pre-line' }}>
                    {viewingDetailJob.benefits}
                  </p>
                </div>
              )}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 28, borderTop: '1px solid #f1f5f9', paddingTop: 16 }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setViewingDetailJob(null)}
              >
                Đóng
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => {
                  const targetJob = viewingDetailJob;
                  setViewingDetailJob(null);
                  setApplyingJob(targetJob);
                }}
              >
                Nộp đơn ứng tuyển ngay
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Apply Modal */}
      {applyingJob && (
        <GuestApplyModal
          job={applyingJob}
          onClose={() => setApplyingJob(null)}
          onSuccess={(trackingCode, applicantEmail) => {
            setApplyingJob(null);
            onOpenTracking(trackingCode, applicantEmail);
          }}
        />
      )}
    </div>
  );
}
