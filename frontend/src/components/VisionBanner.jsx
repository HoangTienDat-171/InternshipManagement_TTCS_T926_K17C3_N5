import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Sparkles } from 'lucide-react';

export default function VisionBanner() {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="vision-banner">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <Sparkles size={18} color="#fde047" />
            <span style={{ fontSize: '12px', textTransform: 'uppercase', letterSpacing: '1px', fontWeight: 700, color: '#fde047' }}>
              Tầm nhìn & Mục tiêu dự án
            </span>
          </div>
          <h2>Hệ thống Số hóa Toàn diện Quản lý Thực tập sinh</h2>
          <p>
            Tối ưu quy trình tuyển chọn, quản lý và đánh giá; mang đến cho thực tập sinh trải nghiệm minh bạch, chuyên nghiệp và hiệu quả; củng cố hợp tác giữa doanh nghiệp và các trường đại học.
          </p>
        </div>

        <button 
          onClick={() => setExpanded(!expanded)}
          style={{
            background: 'rgba(255, 255, 255, 0.2)',
            border: 'none',
            color: 'white',
            borderRadius: '8px',
            padding: '8px 12px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '13px',
            fontWeight: 600
          }}
        >
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          <span>{expanded ? 'Thu gọn' : 'Xem 5 mục tiêu'}</span>
        </button>
      </div>

      <div className="vision-badges">
        <span className="vision-pill">1. Chuẩn hóa quy trình</span>
        <span className="vision-pill">2. Tăng hiệu quả & Giảm chi phí</span>
        <span className="vision-pill">3. Nâng cao trải nghiệm TTS</span>
        <span className="vision-pill">4. Củng cố hợp tác Nhà trường</span>
        <span className="vision-pill">5. Phân tích nhân sự chiến lược</span>
      </div>

      {expanded && (
        <div style={{ 
          marginTop: '18px', 
          paddingTop: '16px', 
          borderTop: '1px solid rgba(255, 255, 255, 0.2)',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '12px',
          fontSize: '13px'
        }}>
          <div>
            <strong>1. Chuẩn hóa & Số hóa:</strong> Tự động hóa tiếp nhận, phân công, chấm công, giảm thiểu thao tác thủ công (Excel rời rạc).
          </div>
          <div>
            <strong>2. Giảm chi phí nhân sự:</strong> Giúp HR và Mentor dễ dàng theo dõi số lượng lớn thực tập sinh cùng lúc.
          </div>
          <div>
            <strong>3. Trải nghiệm thực tập sinh:</strong> Cổng thông tin xem lịch, tiến độ công việc, chấm công và kết quả đánh giá minh bạch.
          </div>
          <div>
            <strong>4. Hợp tác Trường Đại học:</strong> Xuất báo cáo chi tiết gửi nhà trường, xây dựng thương hiệu tuyển dụng sinh viên.
          </div>
          <div>
            <strong>5. Dữ liệu phân tích chiến lược:</strong> Thống kê theo trường/ngành, tỷ lệ hoàn thành, làm cơ sở dự báo nhân lực trẻ.
          </div>
        </div>
      )}
    </div>
  );
}
