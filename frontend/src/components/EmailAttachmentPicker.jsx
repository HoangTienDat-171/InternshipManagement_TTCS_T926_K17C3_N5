import React, { useState } from 'react';
import { Paperclip, FileText, Image as ImageIcon, X, AlertTriangle } from 'lucide-react';

const MAX_FILE_SIZE = 10 * 1024 * 1024;    // 10MB
const MAX_TOTAL_SIZE = 20 * 1024 * 1024;   // 20MB warning threshold
const ALLOWED_EXTS = ['.pdf', '.docx', '.png', '.jpg', '.jpeg'];

export default function EmailAttachmentPicker({ attachments, setAttachments }) {
  const [errorMsg, setErrorMsg] = useState('');

  const handleFiles = (newFiles) => {
    setErrorMsg('');
    const validBatch = [];
    let currentTotal = attachments.reduce((acc, f) => acc + f.size, 0);

    for (const file of newFiles) {
      const ext = '.' + file.name.split('.').pop().toLowerCase();
      if (!ALLOWED_EXTS.includes(ext)) {
        setErrorMsg(`Tệp "${file.name}" không hợp lệ. Chỉ chấp nhận PDF, DOCX, PNG, JPG.`);
        return;
      }
      if (file.size > MAX_FILE_SIZE) {
        setErrorMsg(`Tệp "${file.name}" vượt quá kích thước tối đa 10MB.`);
        return;
      }
      if (currentTotal + file.size > MAX_TOTAL_SIZE) {
        setErrorMsg('Tổng kích thước tất cả các tệp đính kèm vượt quá 20MB.');
        return;
      }
      currentTotal += file.size;
      validBatch.push(file);
    }
    setAttachments([...attachments, ...validBatch]);
  };

  const removeFile = (index) => {
    setAttachments(attachments.filter((_, i) => i !== index));
  };

  const totalSizeMB = (attachments.reduce((acc, f) => acc + f.size, 0) / 1024 / 1024).toFixed(2);

  return (
    <div style={{ marginTop: 12 }}>
      <label style={{ fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6, color: '#334155' }}>
        <Paperclip size={15} /> Tệp đính kèm ({attachments.length} tệp - {totalSizeMB} MB)
      </label>

      {/* Drag & Drop Area */}
      <div
        style={{
          border: '2px dashed #cbd5e1',
          borderRadius: 8,
          padding: '14px',
          textAlign: 'center',
          background: '#f8fafc',
          cursor: 'pointer',
          marginTop: 6
        }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          handleFiles(Array.from(e.dataTransfer.files));
        }}
        onClick={() => document.getElementById('file-picker-input').click()}
      >
        <input
          id="file-picker-input"
          type="file"
          multiple
          accept=".pdf,.docx,image/png,image/jpeg"
          style={{ display: 'none' }}
          onChange={(e) => handleFiles(Array.from(e.target.files))}
        />
        <div style={{ fontSize: 13, color: '#475569' }}>
          Nhấp hoặc kéo thả hợp đồng, tài liệu, ảnh vào đây (Tối đa 10MB/tệp)
        </div>
      </div>

      {errorMsg && (
        <div style={{ color: '#b91c1c', fontSize: 12, marginTop: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
          <AlertTriangle size={14} /> {errorMsg}
        </div>
      )}

      {/* Attached Files List */}
      {attachments.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
          {attachments.map((file, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                background: '#fff',
                border: '1px solid #e2e8f0',
                padding: '4px 10px',
                borderRadius: 6,
                fontSize: 12,
                boxShadow: '0 1px 3px rgba(0,0,0,0.04)'
              }}
            >
              {file.type.startsWith('image/') ? <ImageIcon size={14} color="#0284c7" /> : <FileText size={14} color="#d97706" />}
              <span style={{ maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {file.name}
              </span>
              <span style={{ color: '#94a3b8' }}>({(file.size / 1024).toFixed(0)} KB)</span>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  removeFile(idx);
                }}
                style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#ef4444', padding: 2 }}
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
