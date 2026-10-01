import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, Building2, BriefcaseBusiness, CircleCheck, Clock3, GraduationCap, ShieldCheck, Users, UserRoundCheck } from 'lucide-react';
import { apiFetch, readJsonResponse } from '../utils/api';

const number = (value) => Number(value || 0).toLocaleString('vi-VN');
const REQUIRED_METRIC_FIELDS = {
  interns: ['total', 'approved', 'pending', 'rejected', 'in_progress', 'completed', 'withdrawn', 'assigned', 'unassigned', 'universities'],
  programs: ['total', 'open', 'quota', 'applicants', 'pending_applicants', 'breakdown'],
  mentors: ['total', 'assigned_mentors', 'assigned_interns', 'average_interns', 'departments', 'expertise'],
  accounts: ['total', 'managers', 'mentors', 'interns', 'active', 'locked', 'pending'],
};

function readSectionMetrics(data, section) {
  const sectionMetrics = data?.[section];
  const requiredFields = REQUIRED_METRIC_FIELDS[section];
  if (!sectionMetrics || typeof sectionMetrics !== 'object' || !requiredFields
    || requiredFields.some((field) => sectionMetrics[field] === undefined || sectionMetrics[field] === null)) {
    throw new Error('Máy chủ trả về dữ liệu chỉ số không đầy đủ. Vui lòng thử tải lại.');
  }
  if ((section === 'programs' && !Array.isArray(sectionMetrics.breakdown))
    || (section === 'mentors' && (!Array.isArray(sectionMetrics.departments) || !Array.isArray(sectionMetrics.expertise)))) {
    throw new Error('Danh sách thống kê không đúng định dạng. Vui lòng thử tải lại.');
  }
  return sectionMetrics;
}

function describeMetrics(section, metrics) {
  if (section === 'interns') {
    const assignedRate = metrics.approved ? Math.round((metrics.assigned / metrics.approved) * 100) : 0;
    return {
      cards: [
        { label: 'TỔNG SỐ TTS', value: metrics.total, detail: 'Hồ sơ thực tập sinh đang được quản lý', icon: GraduationCap, tone: 'violet' },
        { label: 'ĐÃ GHÉP MENTOR', value: metrics.assigned, detail: `${assignedRate}% hồ sơ đã được phân công`, icon: UserRoundCheck, tone: 'green', progress: assignedRate },
        { label: 'CHỜ GHÉP MENTOR', value: metrics.unassigned, detail: 'Thực tập sinh chưa có người hướng dẫn', icon: Clock3, tone: 'amber' },
        { label: 'TRƯỜNG ĐẠI HỌC', value: metrics.universities, detail: 'Số trường có hồ sơ trong kết quả lọc', icon: Building2, tone: 'blue' },
      ],
      footer: `Trạng thái thực tập: ${number(metrics.in_progress)} đang thực tập · ${number(metrics.completed)} hoàn thành · ${number(metrics.withdrawn)} thôi học`,
    };
  }

  if (section === 'programs') {
    return {
      cards: [
        { label: 'TỔNG CHƯƠNG TRÌNH', value: metrics.total, detail: 'Các đợt thực tập hiện có', icon: BriefcaseBusiness, tone: 'violet' },
        { label: 'ĐANG NHẬN HỒ SƠ', value: metrics.open, detail: 'Chương trình đang mở đăng ký', icon: Activity, tone: 'green' },
        { label: 'TỔNG CHỈ TIÊU', value: metrics.quota, detail: 'Vị trí tuyển trên các chương trình', icon: Users, tone: 'blue' },
        { label: 'HỒ SƠ ỨNG TUYỂN', value: metrics.applicants, detail: `${number(metrics.pending_applicants)} hồ sơ đang chờ xử lý`, icon: CircleCheck, tone: 'amber' },
      ],
      breakdown: metrics.breakdown,
    };
  }

  if (section === 'mentors') {
    return {
      cards: [
        { label: 'TỔNG SỐ MENTOR', value: metrics.total, detail: 'Người hướng dẫn trong hệ thống', icon: Users, tone: 'violet' },
        { label: 'MENTOR ĐANG PHỤ TRÁCH', value: metrics.assigned_mentors, detail: `${number(metrics.total - metrics.assigned_mentors)} mentor chưa có TTS`, icon: UserRoundCheck, tone: 'green' },
        { label: 'TTS ĐANG ĐƯỢC QUẢN LÝ', value: metrics.assigned_interns, detail: 'Tổng lượt phân công mentor – TTS', icon: GraduationCap, tone: 'blue' },
        { label: 'TRUNG BÌNH TTS / MENTOR', value: number(metrics.average_interns), detail: 'Tính trên toàn bộ mentor', icon: Activity, tone: 'amber' },
      ],
      breakdown: metrics.departments,
      expertise: metrics.expertise,
    };
  }

  return {
    cards: [
      { label: 'TỔNG TÀI KHOẢN', value: metrics.total, detail: `${number(metrics.active)} đang hoạt động · ${number(metrics.locked)} bị khóa`, icon: Users, tone: 'violet' },
      { label: 'ADMIN & QUẢN LÝ', value: metrics.managers, detail: 'Tài khoản có quyền quản trị/điều phối', icon: ShieldCheck, tone: 'amber' },
      { label: 'MENTOR', value: metrics.mentors, detail: 'Tài khoản người hướng dẫn', icon: UserRoundCheck, tone: 'green' },
      { label: 'THỰC TẬP SINH', value: metrics.interns, detail: `${number(metrics.pending)} tài khoản chờ duyệt`, icon: GraduationCap, tone: 'blue' },
    ],
    footer: `Trạng thái tài khoản: ${number(metrics.active)} đang hoạt động · ${number(metrics.locked)} bị khóa · ${number(metrics.pending)} chờ duyệt`,
  };
}

export default function DashboardMetrics({ section, filters = null }) {
  const filtersKey = useMemo(() => {
    const params = new URLSearchParams();
    Object.entries(filters || {}).forEach(([key, value]) => {
      if (value !== '' && value !== null && value !== undefined) params.set(key, value);
    });
    return params.toString();
  }, [filters]);
  const requestKey = `${section}?${filtersKey}`;
  const [result, setResult] = useState(null);
  const [requestingKey, setRequestingKey] = useState('');
  const requestSequenceRef = useRef(0);
  const activeRequestRef = useRef(null);
  const currentResult = result?.key === requestKey ? result : null;
  const metrics = currentResult?.metrics || null;
  const error = currentResult?.error || '';
  const loading = requestingKey === requestKey || !currentResult;

  const loadMetrics = useCallback(async () => {
    const requestId = ++requestSequenceRef.current;
    activeRequestRef.current?.controller.abort();
    const controller = new AbortController();
    const activeRequest = { controller };
    activeRequestRef.current = activeRequest;
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, 15_000);

    setRequestingKey(requestKey);
    try {
      const query = filtersKey ? `?${filtersKey}` : '';
      const response = await apiFetch(`/api/dashboard/metrics${query}`, { cache: 'no-store', signal: controller.signal });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data?.detail || 'Không thể tải chỉ số tổng hợp.');
      const sectionMetrics = readSectionMetrics(data, section);
      if (requestId !== requestSequenceRef.current || controller.signal.aborted) return;
      setResult({ key: requestKey, metrics: sectionMetrics, error: '' });
    } catch (loadError) {
      if (requestId !== requestSequenceRef.current || (controller.signal.aborted && !timedOut)) return;
      const message = timedOut
        ? 'Máy chủ không phản hồi trong 15 giây. Vui lòng kiểm tra kết nối rồi thử lại.'
        : loadError.message || 'Không thể tải chỉ số tổng hợp.';
      setResult((previous) => ({
        key: requestKey,
        metrics: previous?.key === requestKey ? previous.metrics : null,
        error: message,
      }));
    } finally {
      window.clearTimeout(timeoutId);
      if (requestId === requestSequenceRef.current) {
        setRequestingKey((key) => key === requestKey ? '' : key);
        if (activeRequestRef.current === activeRequest) activeRequestRef.current = null;
      }
    }
  }, [filtersKey, requestKey, section]);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => void loadMetrics(), 0);
    window.addEventListener('ims-dashboard-metrics-updated', loadMetrics);
    const interval = window.setInterval(loadMetrics, 30_000);
    return () => {
      window.clearTimeout(initialLoad);
      window.removeEventListener('ims-dashboard-metrics-updated', loadMetrics);
      window.clearInterval(interval);
      requestSequenceRef.current += 1;
      activeRequestRef.current?.controller.abort();
      activeRequestRef.current = null;
    };
  }, [loadMetrics]);

  const presentation = metrics ? describeMetrics(section, metrics) : null;
  const cards = presentation?.cards || (loading ? Array.from({ length: 4 }, (_, index) => ({ label: 'ĐANG TẢI CHỈ SỐ', value: '—', detail: ' ', tone: 'violet', key: index })) : []);

  return <section className="dashboard-metrics" aria-label="Chỉ số tổng hợp" aria-busy={loading && !metrics}>
    {error && <div className="dashboard-metrics-error" role="status">
      <span>Chỉ số tổng hợp chưa tải được: {error}</span>
      <button type="button" onClick={() => void loadMetrics()} disabled={loading}>Thử lại</button>
    </div>}
    {cards.length > 0 && <div className="dashboard-metrics-grid">
      {cards.map((card, index) => {
        const Icon = card.icon;
        return <article className={`dashboard-metric-card tone-${card.tone}`} key={card.key ?? card.label ?? index}>
          <span className="dashboard-metric-icon">{Icon && <Icon size={18} />}</span>
          <div className="dashboard-metric-content">
            <span className="dashboard-metric-label">{card.label}</span>
            <strong>{typeof card.value === 'number' ? number(card.value) : card.value}</strong>
            <small>{card.detail}</small>
            {card.progress !== undefined && <span className="dashboard-metric-progress"><i style={{ width: `${card.progress}%` }} /></span>}
          </div>
        </article>;
      })}
    </div>}
    {presentation?.footer && <p className="dashboard-metrics-footer">{presentation.footer}</p>}
    {presentation?.breakdown?.length > 0 && <div className="dashboard-metrics-breakdown">
      <span>{section === 'programs' ? 'Ứng viên theo chương trình:' : 'Mentor theo phòng ban:'}</span>
      {presentation.breakdown.slice(0, 4).map((item) => <small key={item.ma_ct || item.name}>
        {item.ten_ct || item.name}: {section === 'programs'
          ? `${number(item.applicants)} hồ sơ · ${number(item.pending_applicants)} chờ`
          : `${number(item.mentors)} mentor`}
      </small>)}
    </div>}
    {section === 'mentors' && presentation?.expertise?.length > 0 && <div className="dashboard-metrics-breakdown">
      <span>Chuyên môn:</span>
      {presentation.expertise.slice(0, 4).map((item) => <small key={item.name}>{item.name}: {number(item.mentors)}</small>)}
    </div>}
  </section>;
}
