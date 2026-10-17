import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Camera, CameraOff, CheckCircle2, Clock3, QrCode } from 'lucide-react';
import { apiFetch, readJsonResponse } from '../utils/api';
import './AttendanceQrManagementView.css';

export default function AttendanceQrManagementView({ onShowToast }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const animationRef = useRef(0);
  const busyRef = useRef(false);
  const [methods, setMethods] = useState(null);
  const [loading, setLoading] = useState(true);
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState('');
  const [token, setToken] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    apiFetch('/api/attendance/methods', { signal: controller.signal })
      .then(async (response) => {
        const data = await readJsonResponse(response);
        if (!response.ok) throw new Error(data.detail || 'Không thể tải cấu hình chấm công.');
        setMethods(data);
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setCameraError(error.message || 'Không thể tải cấu hình chấm công.');
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  const stopCamera = useCallback(() => {
    if (animationRef.current) window.cancelAnimationFrame(animationRef.current);
    animationRef.current = 0;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraActive(false);
  }, []);

  useEffect(() => () => stopCamera(), [stopCamera]);

  const submitQr = useCallback(async (value) => {
    const cleanToken = String(value || '').trim();
    if (!cleanToken || busyRef.current) return;
    busyRef.current = true;
    setSubmitting(true);
    setResult(null);
    setCameraError('');
    try {
      const response = await apiFetch('/api/attendance/qr/check-in', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: cleanToken }),
      });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Không thể xác nhận chấm công QR.');
      setResult(data);
      setToken('');
      stopCamera();
      onShowToast?.('Chấm công QR đã được ghi nhận.', 'success');
    } catch (error) {
      setCameraError(error.message || 'Không thể xác nhận chấm công QR. Mã có thể đã hết hạn hoặc đã dùng.');
      stopCamera();
    } finally {
      busyRef.current = false;
      setSubmitting(false);
    }
  }, [onShowToast, stopCamera]);

  const startCamera = async () => {
    setCameraError('');
    setResult(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError('Trình duyệt không hỗ trợ camera. Mở localhost/HTTPS bằng Chrome mới hoặc nhập mã thủ công bên dưới.');
      return;
    }
    if (!('BarcodeDetector' in window)) {
      setCameraError('Trình duyệt này chưa hỗ trợ nhận diện QR bằng camera. Cập nhật Chrome hoặc nhập mã thủ công bên dưới.');
      return;
    }
    try {
      const detector = new window.BarcodeDetector({ formats: ['qr_code'] });
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
      streamRef.current = stream;
      if (!videoRef.current) throw new Error('Không tìm thấy khung camera. Hãy tải lại trang.');
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      setCameraActive(true);
      const scanFrame = async () => {
        if (!streamRef.current || busyRef.current) return;
        try {
          const codes = await detector.detect(videoRef.current);
          const value = codes.find((code) => code.rawValue)?.rawValue;
          if (value) {
            await submitQr(value);
            return;
          }
        } catch {
          setCameraError('Không đọc được mã QR. Hãy đưa mã rõ vào khung hình hoặc nhập mã thủ công.');
          stopCamera();
          return;
        }
        animationRef.current = window.requestAnimationFrame(scanFrame);
      };
      animationRef.current = window.requestAnimationFrame(scanFrame);
    } catch (error) {
      stopCamera();
      if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
        setCameraError('Bạn đã chặn quyền camera. Bấm biểu tượng khóa cạnh địa chỉ trang, cho phép Camera rồi tải lại.');
      } else if (error.name === 'NotFoundError') {
        setCameraError('Thiết bị này không tìm thấy camera. Dùng ô nhập mã thủ công hoặc thử trên thiết bị có camera.');
      } else {
        setCameraError(error.message || 'Không khởi động được camera. Kiểm tra quyền truy cập và thử lại.');
      }
    }
  };

  return <div className="workspace-page attendance-qr-page">
    <header className="workspace-heading">
      <div><span className="workspace-eyebrow">US38 · MỞ RỘNG CHẤM CÔNG US21</span><h2>Quét mã QR chấm công</h2>
        <p>TTS đăng nhập tạo mã một lần; Admin/HR dùng camera này để xác nhận. Ca và quy tắc chấm công vẫn do service US21/US23 xử lý.</p>
      </div>
    </header>

    <section className="workspace-card attendance-qr-instructions">
      <div className="attendance-qr-step"><span>1</span><div><strong>TTS đăng nhập tài khoản của mình</strong><p>Trong Chấm công hôm nay, chọn “Tạo mã QR”. Mã có hạn 120 giây và tự thay thế mã trước.</p></div></div>
      <div className="attendance-qr-step"><span>2</span><div><strong>Admin/HR quét mã bằng camera này</strong><p>Backend xác định TTS từ token ngẫu nhiên do server cấp, không nhận profile ID từ trình duyệt.</p></div></div>
      <div className="attendance-qr-step"><span>3</span><div><strong>Hệ thống ghi vào CHAM_CONG</strong><p>Giờ server, lượt thực tập, ca US23 và quy tắc US21 đều được kiểm tra trước khi xác nhận.</p></div></div>
    </section>

    <section className="workspace-card attendance-qr-scanner-card">
      <div className="attendance-qr-card-heading"><div><span className="workspace-eyebrow">THIẾT BỊ QUÉT</span><h3>Camera QR</h3></div>
        {!cameraActive
          ? <button type="button" className="btn btn-primary" onClick={startCamera} disabled={loading || submitting}><Camera size={16} />Bật camera</button>
          : <button type="button" className="btn btn-secondary" onClick={stopCamera}><CameraOff size={16} />Dừng camera</button>}
      </div>
      {cameraError && <div className="workspace-error attendance-qr-error" role="alert"><AlertTriangle size={17} /><span>{cameraError}</span></div>}
      {result && <div className="attendance-qr-success" role="status"><CheckCircle2 size={18} /><div><strong>Đã ghi nhận check-in qua QR</strong><span>{result.shift?.name || 'Ca làm việc'} · {new Date(result.check_in_at).toLocaleTimeString('vi-VN')}</span></div></div>}
      <div className={`attendance-qr-camera${cameraActive ? ' is-active' : ''}`}>
        <video ref={videoRef} muted autoPlay playsInline aria-label="Camera quét mã QR" />
        {!cameraActive && <div><QrCode size={28} /><span>Bật camera khi TTS đã hiển thị mã QR.</span></div>}
      </div>
      <form className="attendance-qr-manual" onSubmit={(event) => { event.preventDefault(); submitQr(token); }}>
        <label htmlFor="attendance-qr-token">Nhập mã thủ công khi camera không dùng được</label>
        <div><input id="attendance-qr-token" value={token} maxLength={128} autoComplete="off" onChange={(event) => setToken(event.target.value)} placeholder="Dán nội dung mã QR tại đây" />
          <button type="submit" className="btn btn-primary" disabled={!token.trim() || submitting}>{submitting ? 'Đang xác nhận…' : 'Xác nhận QR'}</button></div>
      </form>
    </section>

    <section className="workspace-card attendance-qr-methods-card">
      <h3>Phương thức chấm công</h3>
      {loading ? <div className="attendance-qr-loading" role="status">Đang tải trạng thái…</div> : <div className="attendance-qr-methods">
        <div><CheckCircle2 size={17} /><strong>Thủ công</strong><span>{methods?.manual?.description || 'Chấm công US21 hiện tại'}</span></div>
        <div><CheckCircle2 size={17} /><strong>QR</strong><span>{methods?.qr?.description || 'QR credential dùng một lần'}</span></div>
        <div className="is-unavailable"><Clock3 size={17} /><strong>Thẻ</strong><span>{methods?.card?.description || 'Chưa có đầu đọc phần cứng hoặc giao thức UID được xác nhận. Adapter contract đã sẵn sàng; chưa có tích hợp CARD E2E.'}</span></div>
      </div>}
    </section>
  </div>;
}
