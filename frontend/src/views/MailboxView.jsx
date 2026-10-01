import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle, ArrowLeft, ChevronLeft, ChevronRight, Clock3,
  Download, FileCheck2, Inbox, LifeBuoy, Loader2, Mail, MailOpen, Maximize2, Plus, RefreshCw,
  Reply, RotateCcw, Search, Send, X, Image as ImageIcon, Paperclip, ZoomIn, ZoomOut,
} from 'lucide-react';
import { apiFetch, readJsonResponse } from '../utils/api';
import EmailAttachmentPicker from '../components/EmailAttachmentPicker';
import './MailboxView.css';

const CATEGORY_LABELS = {
  XIN_HO_TRO: 'Xin hỗ trợ',
  XIN_XET_DUYET: 'Xin xét duyệt',
  THAC_MAC_LICH_LAM_VIEC: 'Lịch làm việc',
  BO_SUNG_HO_SO: 'Bổ sung hồ sơ',
  THONG_BAO_CHUNG: 'Thông báo chung',
  KET_QUA_XET_DUYET: 'Kết quả xét duyệt',
};

const COMPOSE_CATEGORIES = Object.entries(CATEGORY_LABELS);

function formatDate(value, compact = false) {
  if (!value) return '';
  const normalized = String(value).includes('T') ? value : String(value).replace(' ', 'T');
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;
  return compact
    ? date.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' })
    : date.toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit', year: 'numeric' });
}

function initials(name) {
  return (name || '?').trim().split(/\s+/).slice(-2).map((word) => word[0]).join('').toUpperCase();
}

async function fetchJson(url, options) {
  const response = await apiFetch(url, options);
  const data = await readJsonResponse(response);
  if (!response.ok) throw new Error(data.detail || 'Không thể xử lý yêu cầu.');
  return data;
}

function CategoryBadge({ category }) {
  return <span className={`mailbox-category is-${category?.toLowerCase()}`}>{CATEGORY_LABELS[category] || category}</span>;
}

function MessageSkeleton() {
  return <div className="mailbox-skeleton" aria-label="Đang tải thư">
    {[0, 1, 2, 3, 4].map((item) => <div key={item}><i /><span /><small /></div>)}
  </div>;
}

function RichTextEditor({ editorRef, value, onChange, label, onAttachFile }) {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const imageInputRef = useRef(null);
  const docInputRef = useRef(null);

  const runCommand = (command, argument) => {
    editorRef.current?.focus();
    document.execCommand(command, false, argument);
    onChange(editorRef.current?.innerHTML || '');
  };

  const addLink = () => {
    const url = window.prompt('Nhập liên kết bắt đầu bằng https://');
    if (url) runCommand('createLink', url);
  };

  const insertHtmlAtCursor = (html) => {
    editorRef.current?.focus();
    const selection = window.getSelection();
    if (selection && selection.rangeCount > 0) {
      const range = selection.getRangeAt(0);
      range.deleteContents();
      const tempDiv = document.createElement('div');
      tempDiv.innerHTML = html;
      const frag = document.createDocumentFragment();
      let node;
      let lastNode;
      while ((node = tempDiv.firstChild)) {
        lastNode = frag.appendChild(node);
      }
      range.insertNode(frag);
      if (lastNode) {
        range.setStartAfter(lastNode);
        range.collapse(true);
        selection.removeAllRanges();
        selection.addRange(range);
      }
    } else {
      document.execCommand('insertHTML', false, html);
    }
    onChange(editorRef.current?.innerHTML || '');
  };

  const uploadFile = async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const resp = await apiFetch('/api/mailbox/upload-attachment', {
      method: 'POST',
      body: formData,
    });
    if (!resp.ok) {
      const err = await readJsonResponse(resp);
      throw new Error(err.detail || 'Không thể tải tệp lên.');
    }
    return await readJsonResponse(resp);
  };

  const handleImageFile = async (file) => {
    if (!file) return;
    setUploading(true);
    setUploadError('');
    try {
      const data = await uploadFile(file);
      const imgHtml = `<p><img src="${data.url}" alt="${data.filename}" style="max-width:100%; border-radius:6px; margin:8px 0; display:block;" /></p><p><br></p>`;
      insertHtmlAtCursor(imgHtml);
      onAttachFile?.(file);
    } catch (err) {
      setUploadError(err.message || 'Lỗi tải ảnh lên.');
    } finally {
      setUploading(false);
    }
  };

  const handleDocFile = async (file) => {
    if (!file) return;
    setUploading(true);
    setUploadError('');
    try {
      const data = await uploadFile(file);
      const sizeStr = (data.size / 1024).toFixed(0);
      const fileHtml = `<p><a href="${data.url}" download="${data.filename}" class="mailbox-file-chip" target="_blank" rel="noopener noreferrer">📎 <span>${data.filename}</span> <small>(${sizeStr} KB)</small></a></p><p><br></p>`;
      insertHtmlAtCursor(fileHtml);
      onAttachFile?.(file);
    } catch (err) {
      setUploadError(err.message || 'Lỗi tải tệp lên.');
    } finally {
      setUploading(false);
    }
  };

  const handlePaste = (e) => {
    const items = e.clipboardData?.items;
    if (items) {
      for (const item of items) {
        if (item.type.startsWith('image/')) {
          const file = item.getAsFile();
          if (file) {
            e.preventDefault();
            handleImageFile(file);
            return;
          }
        }
      }
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer?.files?.length) {
      for (const file of e.dataTransfer.files) {
        if (file.type.startsWith('image/')) {
          handleImageFile(file);
        } else {
          handleDocFile(file);
        }
      }
    }
  };

  return <div className="mailbox-editor-wrap">
    <div className="mailbox-editor-toolbar" aria-label="Định dạng nội dung">
      <button type="button" onClick={() => runCommand('bold')} aria-label="In đậm"><strong>B</strong></button>
      <button type="button" onClick={() => runCommand('italic')} aria-label="In nghiêng"><em>I</em></button>
      <button type="button" onClick={() => runCommand('underline')} aria-label="Gạch chân"><u>U</u></button>
      <button type="button" onClick={() => runCommand('insertUnorderedList')} aria-label="Danh sách chấm">• List</button>
      <button type="button" onClick={() => runCommand('insertOrderedList')} aria-label="Danh sách số">1. List</button>
      <button type="button" onClick={addLink} aria-label="Thêm liên kết">Link</button>
      <span className="mailbox-toolbar-divider" />
      <button
        type="button"
        className="media-btn"
        onClick={() => imageInputRef.current?.click()}
        title="Chèn ảnh từ máy (hoặc dán Ctrl+V / kéo thả)"
        aria-label="Chèn ảnh"
      >
        <ImageIcon size={14} /> Ảnh
      </button>
      <button
        type="button"
        className="media-btn"
        onClick={() => docInputRef.current?.click()}
        title="Đính kèm tệp tài liệu (PDF, Word, Ảnh...)"
        aria-label="Đính kèm tệp"
      >
        <Paperclip size={14} /> Đính kèm tệp
      </button>
      {uploading && <span className="mailbox-uploading-tag"><Loader2 className="spin" size={13} /> Đang tải…</span>}
      {uploadError && <span className="mailbox-uploading-err"><AlertCircle size={13} /> {uploadError}</span>}
      <input
        ref={imageInputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        style={{ display: 'none' }}
        onChange={(e) => {
          if (e.target.files?.[0]) handleImageFile(e.target.files[0]);
          e.target.value = '';
        }}
      />
      <input
        ref={docInputRef}
        type="file"
        accept=".pdf,.docx,.doc,.xlsx,.xls,.png,.jpg,.jpeg,.zip"
        style={{ display: 'none' }}
        onChange={(e) => {
          if (e.target.files?.[0]) handleDocFile(e.target.files[0]);
          e.target.value = '';
        }}
      />
    </div>
    <div
      ref={editorRef}
      className="mailbox-editor"
      contentEditable
      suppressContentEditableWarning
      role="textbox"
      aria-label={label}
      aria-multiline="true"
      onInput={(event) => onChange(event.currentTarget.innerHTML)}
      onPaste={handlePaste}
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
      data-placeholder="Nhập nội dung thư… (Có thể dán ảnh Ctrl+V hoặc kéo thả tệp vào đây)"
    />
    <input type="hidden" value={value} readOnly />
  </div>;
}

function ComposeModal({ currentUser, onClose, onSent }) {
  const editorRef = useRef(null);
  const [recipientQuery, setRecipientQuery] = useState('');
  const [recipientResults, setRecipientResults] = useState([]);
  const [selectedRecipients, setSelectedRecipients] = useState([]);
  const [groups, setGroups] = useState([]);
  const [groupKey, setGroupKey] = useState('');
  const [templates, setTemplates] = useState([]);
  const [templateId, setTemplateId] = useState('');
  const [category, setCategory] = useState(currentUser.vai_tro === 'ThucTapSinh' ? 'XIN_HO_TRO' : 'THONG_BAO_CHUNG');
  const [subject, setSubject] = useState('');
  const [contentHtml, setContentHtml] = useState('');
  const [sendEmail, setSendEmail] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const canUseTemplates = ['Admin', 'HR'].includes(currentUser.vai_tro);

  useEffect(() => {
    Promise.all([
      fetchJson('/api/mailbox/recipient-groups'),
      canUseTemplates ? fetchJson('/api/mailbox/templates') : Promise.resolve([]),
    ]).then(([groupData, templateData]) => {
      setGroups(groupData);
      setTemplates(templateData.filter((item) => item.isActive));
    }).catch((requestError) => setError(requestError.message));
  }, [canUseTemplates]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      fetchJson(`/api/mailbox/recipients?q=${encodeURIComponent(recipientQuery.trim())}`)
        .then((data) => setRecipientResults(data.filter((candidate) => !selectedRecipients.some((item) => item.ma_nguoi_dung === candidate.ma_nguoi_dung))))
        .catch((requestError) => setError(requestError.message));
    }, 320);
    return () => window.clearTimeout(timer);
  }, [recipientQuery, selectedRecipients]);

  const chooseTemplate = (id) => {
    setTemplateId(id);
    const template = templates.find((item) => String(item.id) === id);
    if (!template) return;
    setSubject(template.subject);
    setCategory(template.category);
    setContentHtml(template.bodyHtml);
    if (editorRef.current) editorRef.current.innerHTML = template.bodyHtml;
  };

  const submit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    setError('');
    if (!selectedRecipients.length && !groupKey) {
      setError('Vui lòng chọn người nhận hoặc một nhóm người nhận.');
      return;
    }
    if (!subject.trim() || !contentHtml.replace(/<[^>]*>/g, '').trim()) {
      setError('Tiêu đề và nội dung là bắt buộc.');
      return;
    }
    setSubmitting(true);
    try {
      if (sendEmail && attachments.length > 0 && selectedRecipients.length > 0 && ['Admin', 'HR'].includes(currentUser.vai_tro)) {
        for (const r of selectedRecipients) {
          if (r.email) {
            const formData = new FormData();
            formData.append('recipient_email', r.email);
            formData.append('subject', subject.trim());
            formData.append('body_text', contentHtml.replace(/<[^>]*>/g, '').trim());
            formData.append('body_html', contentHtml);
            for (const att of attachments) {
              formData.append('files', att);
            }
            await apiFetch('/api/notifications/send-with-attachments', {
              method: 'POST',
              body: formData,
            });
          }
        }
      }

      const result = await fetchJson('/api/mailbox/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          receiverIds: selectedRecipients.map((item) => item.ma_nguoi_dung),
          groupKeys: groupKey ? [groupKey] : [], category,
          subject: subject.trim(), contentHtml,
          sendEmail: attachments.length > 0 ? false : sendEmail,
          templateId: templateId ? Number(templateId) : null,
        }),
      });
      onSent(result.sentCount);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="mailbox-modal-backdrop" role="presentation">
    <section className="mailbox-compose-modal" role="dialog" aria-modal="true" aria-labelledby="compose-title">
      <header><div><h2 id="compose-title">Soạn thư mới</h2><p>Gửi trao đổi nội bộ an toàn trong IMS Portal</p></div><button type="button" onClick={onClose} aria-label="Đóng"><X size={20} /></button></header>
      <form onSubmit={submit}>
        <div className="mailbox-compose-body">
          {error && <div className="mailbox-inline-error"><AlertCircle size={16} />{error}</div>}
          <label className="mailbox-field"><span>Người nhận *</span>
            <div className="mailbox-recipient-box">
              {selectedRecipients.map((recipient) => <span className="mailbox-recipient-chip" key={recipient.ma_nguoi_dung}>{recipient.ho_ten}<button type="button" onClick={() => setSelectedRecipients((items) => items.filter((item) => item.ma_nguoi_dung !== recipient.ma_nguoi_dung))}><X size={13} /></button></span>)}
              <input value={recipientQuery} onChange={(event) => setRecipientQuery(event.target.value)} placeholder="Tìm theo tên hoặc email…" />
            </div>
            {recipientQuery && recipientResults.length > 0 && <div className="mailbox-recipient-results">
              {recipientResults.map((recipient) => <button type="button" key={recipient.ma_nguoi_dung} onClick={() => { setSelectedRecipients((items) => [...items, recipient]); setRecipientQuery(''); }}><span className="mailbox-avatar small">{initials(recipient.ho_ten)}</span><span><strong>{recipient.ho_ten}</strong><small>{recipient.email} · {recipient.vai_tro}</small></span></button>)}
            </div>}
          </label>
          {groups.length > 0 && <label className="mailbox-field"><span>Hoặc chọn nhóm</span><select value={groupKey} onChange={(event) => setGroupKey(event.target.value)}><option value="">Không chọn nhóm</option>{groups.map((group) => <option key={group.key} value={group.key}>{group.label} ({group.memberCount})</option>)}</select></label>}
          <div className="mailbox-compose-grid">
            {canUseTemplates && <label className="mailbox-field"><span>Mẫu thư</span><select value={templateId} onChange={(event) => chooseTemplate(event.target.value)}><option value="">Không dùng mẫu</option>{templates.map((template) => <option key={template.id} value={template.id}>{template.title}</option>)}</select></label>}
            <label className="mailbox-field"><span>Loại thư *</span><select value={category} onChange={(event) => setCategory(event.target.value)}>{COMPOSE_CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          </div>
          <label className="mailbox-field"><span>Tiêu đề *</span><input maxLength={255} value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="Nhập tiêu đề thư" /></label>
          <label className="mailbox-field"><span>Nội dung *</span><RichTextEditor editorRef={editorRef} value={contentHtml} onChange={setContentHtml} label="Nội dung thư" onAttachFile={(file) => setAttachments((prev) => [...prev, file])} /></label>
          <label className="mailbox-email-check"><input type="checkbox" checked={sendEmail} onChange={(event) => setSendEmail(event.target.checked)} /><span><strong>Gửi thêm email</strong><small>Thư nội bộ vẫn xuất hiện ngay; email được xử lý ở hàng đợi.</small></span></label>
          {sendEmail && ['Admin', 'HR'].includes(currentUser.vai_tro) && (
            <EmailAttachmentPicker attachments={attachments} setAttachments={setAttachments} />
          )}
        </div>
        <footer><button type="button" className="mailbox-button secondary" onClick={onClose}>Hủy</button><button className="mailbox-button primary" disabled={submitting}>{submitting ? <Loader2 className="spin" size={16} /> : <Send size={16} />}{submitting ? 'Đang gửi…' : 'Gửi thư'}</button></footer>
      </form>
    </section>
  </div>;
}

export default function MailboxView({ currentUser, onShowToast }) {
  const [folder, setFolder] = useState('inbox');
  const [statusFilter, setStatusFilter] = useState('all');
  const [category, setCategory] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [mailbox, setMailbox] = useState({ items: [], page: 1, totalPages: 0, totalItems: 0 });
  const [folderCounts, setFolderCounts] = useState({ unreadCount: 0, inboxTotal: 0, sentTotal: 0 });
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState('');
  const [composeOpen, setComposeOpen] = useState(false);
  const [replyOpen, setReplyOpen] = useState(false);
  const [replyHtml, setReplyHtml] = useState('');
  const [replying, setReplying] = useState(false);
  const [zoomedImage, setZoomedImage] = useState(null);
  const [zoomScale, setZoomScale] = useState(1);
  const replyEditorRef = useRef(null);

  const loadFolderCounts = useCallback(async () => {
    try {
      const data = await fetchJson('/api/mailbox/folder-counts');
      setFolderCounts({
        unreadCount: Number(data.unreadCount) || 0,
        inboxTotal: Number(data.inboxTotal) || 0,
        sentTotal: Number(data.sentTotal) || 0,
      });
    } catch {
      // Ignore background badge errors
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(loadFolderCounts, 0);
    return () => window.clearTimeout(timer);
  }, [loadFolderCounts]);

  useEffect(() => {
    const handleRead = () => {
      loadFolderCounts();
    };
    window.addEventListener('ims-mailbox-read', handleRead);
    return () => window.removeEventListener('ims-mailbox-read', handleRead);
  }, [loadFolderCounts]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') setZoomedImage(null);
    };
    if (zoomedImage) {
      window.addEventListener('keydown', handleKeyDown);
      return () => window.removeEventListener('keydown', handleKeyDown);
    }
  }, [zoomedImage]);

  useEffect(() => {
    const timer = window.setTimeout(() => { setQuery(searchInput.trim()); setPage(1); }, 350);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const loadMessages = useCallback(async () => {
    setLoading(true);
    setError('');
    const params = new URLSearchParams({ folder, page: String(page), pageSize: '20', status: statusFilter });
    if (category) params.set('category', category);
    if (query) params.set('q', query);
    try {
      const data = await fetchJson(`/api/mailbox/messages?${params}`);
      setMailbox(data);
      if (folder === 'inbox' && statusFilter === 'all' && !category && !query) {
        setFolderCounts((prev) => ({ ...prev, inboxTotal: data.totalItems }));
      } else if (folder === 'sent' && !query) {
        setFolderCounts((prev) => ({ ...prev, sentTotal: data.totalItems }));
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, [folder, page, statusFilter, category, query]);

  useEffect(() => {
    const timer = window.setTimeout(loadMessages, 0);
    return () => window.clearTimeout(timer);
  }, [loadMessages]);

  const selectMessage = async (messageId) => {
    setSelectedId(messageId);
    setDetailLoading(true);
    setError('');
    try {
      const data = await fetchJson(`/api/mailbox/messages/${messageId}`);
      setDetail(data);
      setMailbox((current) => ({ ...current, items: current.items.map((item) => item.id === messageId ? { ...item, is_read: true } : item) }));
      window.dispatchEvent(new CustomEvent('ims-mailbox-read'));
      loadFolderCounts();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setDetailLoading(false);
    }
  };

  const chooseFolder = (nextFolder, nextStatus = 'all', nextCategory = '') => {
    setFolder(nextFolder); setStatusFilter(nextStatus); setCategory(nextCategory);
    setPage(1); setSelectedId(null); setDetail(null);
  };

  const submitReply = async () => {
    if (replying) return;
    if (!replyHtml.replace(/<[^>]*>/g, '').trim()) return;
    setReplying(true);
    try {
      const result = await fetchJson(`/api/mailbox/messages/${selectedId}/reply`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ contentHtml: replyHtml, sendEmail: false }),
      });
      setReplyHtml('');
      if (replyEditorRef.current) replyEditorRef.current.innerHTML = '';
      setReplyOpen(false);
      await selectMessage(result.messageId);
      onShowToast('Đã gửi trả lời.');
      loadFolderCounts();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setReplying(false);
    }
  };

  const folderItems = [
    {
      label: 'Hộp thư đến',
      icon: Inbox,
      action: () => chooseFolder('inbox'),
      active: folder === 'inbox' && statusFilter === 'all' && !category,
      badge: folderCounts.inboxTotal > 0 ? folderCounts.inboxTotal : null,
    },
    {
      label: 'Đã gửi',
      icon: Send,
      action: () => chooseFolder('sent'),
      active: folder === 'sent',
      badge: folderCounts.sentTotal > 0 ? folderCounts.sentTotal : null,
    },
    {
      label: 'Chưa đọc',
      icon: MailOpen,
      action: () => chooseFolder('inbox', 'unread'),
      active: folder === 'inbox' && statusFilter === 'unread',
      badge: folderCounts.unreadCount > 0 ? folderCounts.unreadCount : null,
    },
    {
      label: 'Cần xử lý',
      icon: Clock3,
      action: () => chooseFolder('inbox', 'all', 'XIN_XET_DUYET'),
      active: category === 'XIN_XET_DUYET',
      badge: null,
    },
  ];

  return <div className="mailbox-page">
    <div className="mailbox-page-heading"><div><span>Hộp thư & tương tác nội bộ</span><h1>Hộp thư</h1><p>Trao đổi, gửi yêu cầu và theo dõi thông báo ngay trong IMS Portal.</p></div><button type="button" className="mailbox-button primary mobile-compose" onClick={() => setComposeOpen(true)}><Plus size={17} /> Soạn thư</button></div>
    {error && <div className="mailbox-page-error"><AlertCircle size={18} /><span>{error}</span><button type="button" onClick={loadMessages}>Thử lại</button></div>}
    <div className={`mailbox-shell${selectedId ? ' has-selection' : ''}`}>
      <aside className="mailbox-folders">
        <button type="button" className="mailbox-button primary compose-button" onClick={() => setComposeOpen(true)}><Plus size={17} /> Soạn thư mới</button>
        <nav>{folderItems.map(({ label, icon: Icon, action, active, badge }) => <button type="button" key={label} className={active ? 'active' : ''} onClick={action}><Icon size={18} /><span>{label}</span>{badge !== null && badge !== undefined && <b>{badge}</b>}</button>)}</nav>
        <div className="mailbox-folder-separator" />
        <button type="button" className={category === 'XIN_HO_TRO' ? 'mailbox-folder-link active' : 'mailbox-folder-link'} onClick={() => chooseFolder('inbox', 'all', 'XIN_HO_TRO')}><LifeBuoy size={18} /><span>Yêu cầu hỗ trợ</span></button>
        <button type="button" className={category === 'XIN_XET_DUYET' ? 'mailbox-folder-link active' : 'mailbox-folder-link'} onClick={() => chooseFolder('inbox', 'all', 'XIN_XET_DUYET')}><FileCheck2 size={18} /><span>Xin xét duyệt</span></button>
      </aside>

      <section className="mailbox-list-panel">
        <header><div><h2>{folder === 'sent' ? 'Đã gửi' : statusFilter === 'unread' ? 'Thư chưa đọc' : category ? CATEGORY_LABELS[category] : 'Hộp thư đến'}</h2><span>{mailbox.totalItems} thư</span></div><button type="button" onClick={loadMessages} aria-label="Làm mới"><RefreshCw size={17} /></button></header>
        <div className="mailbox-list-tools"><label><Search size={16} /><input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Tìm theo tiêu đề hoặc người gửi…" /></label><select value={statusFilter} disabled={folder === 'sent'} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}><option value="all">Tất cả</option><option value="unread">Chưa đọc</option><option value="read">Đã đọc</option></select></div>
        <div className="mailbox-message-list">
          {loading ? <MessageSkeleton /> : mailbox.items.length === 0 ? <div className="mailbox-empty-list"><Mail size={38} /><strong>Bạn chưa có thư nào.</strong><span>Các trao đổi phù hợp bộ lọc sẽ xuất hiện tại đây.</span></div> : mailbox.items.map((message) => <button type="button" key={message.id} className={`mailbox-message-item${message.is_read ? '' : ' unread'}${selectedId === message.id ? ' selected' : ''}`} onClick={() => selectMessage(message.id)}><span className="mailbox-unread-dot" /><span className="mailbox-avatar">{initials(folder === 'sent' ? message.recipient_names : message.sender_name)}</span><span className="mailbox-message-copy"><span className="mailbox-message-meta"><strong>{folder === 'sent' ? message.recipient_names || 'Người nhận' : message.sender_name || 'Tài khoản đã xóa'}</strong><time>{formatDate(message.created_at, true)}</time></span><b>{message.subject}</b><span className="mailbox-preview">{message.preview}</span><CategoryBadge category={message.category} /></span></button>)}
        </div>
        {mailbox.totalPages > 1 && <footer className="mailbox-pagination"><button type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={16} /></button><span>Trang {page}/{mailbox.totalPages}</span><button type="button" disabled={page >= mailbox.totalPages} onClick={() => setPage((value) => value + 1)}><ChevronRight size={16} /></button></footer>}
      </section>

      <section className="mailbox-detail-panel">
        {!selectedId ? <div className="mailbox-detail-empty"><span><Mail size={46} /></span><h2>Chọn một thư để xem nội dung</h2><p>Nội dung hội thoại và trạng thái email sẽ hiển thị tại đây.</p></div> : detailLoading ? <div className="mailbox-detail-loading"><Loader2 className="spin" size={28} /> Đang tải hội thoại…</div> : detail && <>
          <header className="mailbox-detail-header"><button type="button" className="mailbox-back" onClick={() => { setSelectedId(null); setDetail(null); }}><ArrowLeft size={18} /> Quay lại</button><div className="mailbox-detail-person"><span className="mailbox-avatar large">{initials(detail.sender_name)}</span><div><strong>{detail.sender_name || 'Tài khoản đã xóa'}</strong><span>{detail.sender_role} · {detail.sender_email}</span></div><time>{formatDate(detail.created_at)}</time></div><h2>{detail.subject}</h2><CategoryBadge category={detail.category} /></header>
          <div
            className="mailbox-thread"
            onClick={(e) => {
              if (e.target.tagName?.toLowerCase() === 'img') {
                e.preventDefault();
                setZoomScale(1.4);
                setZoomedImage({
                  src: e.target.src,
                  alt: e.target.alt || 'Hình ảnh',
                });
              }
            }}
          >
            {detail.thread?.map((message) => <article key={message.id} className={message.sender_id === currentUser.ma_nguoi_dung ? 'from-me' : ''}><header><span className="mailbox-avatar small">{initials(message.sender_name)}</span><div><strong>{message.sender_id === currentUser.ma_nguoi_dung ? 'Bạn' : message.sender_name || 'Tài khoản đã xóa'}</strong><time>{formatDate(message.created_at)}</time></div></header><div className="mailbox-rich-content" dangerouslySetInnerHTML={{ __html: message.content_html }} />{message.recipients?.some((recipient) => recipient.email_status) && <div className="mailbox-email-status">Email: {message.recipients.map((recipient) => recipient.email_status).filter(Boolean).join(', ')}</div>}</article>)}
          </div>
          <footer className="mailbox-detail-actions">{replyOpen ? <div className="mailbox-reply-box"><RichTextEditor editorRef={replyEditorRef} value={replyHtml} onChange={setReplyHtml} label="Nội dung trả lời" /><div><button type="button" className="mailbox-button secondary" onClick={() => setReplyOpen(false)}>Hủy</button><button type="button" className="mailbox-button primary" disabled={replying} onClick={submitReply}>{replying ? <Loader2 className="spin" size={16} /> : <Send size={16} />} Gửi trả lời</button></div></div> : <button type="button" className="mailbox-button primary" onClick={() => setReplyOpen(true)}><Reply size={16} /> Trả lời</button>}</footer>
        </>}
      </section>
    </div>
    {composeOpen && <ComposeModal currentUser={currentUser} onClose={() => setComposeOpen(false)} onSent={(count) => { setComposeOpen(false); chooseFolder('sent'); loadFolderCounts(); onShowToast(`Đã gửi thư tới ${count} người nhận.`); }} />}

    {zoomedImage && (
      <div
        className="mailbox-lightbox-backdrop"
        onClick={() => setZoomedImage(null)}
        role="dialog"
        aria-modal="true"
        aria-label="Xem ảnh phóng to"
      >
        <div className="mailbox-lightbox-container" onClick={(e) => e.stopPropagation()}>
          <div className="mailbox-lightbox-header">
            <span className="mailbox-lightbox-title">{zoomedImage.alt || 'Xem ảnh phóng to'}</span>
            <div className="mailbox-lightbox-actions">
              <button
                type="button"
                className="mailbox-lightbox-btn"
                onClick={() => setZoomScale((prev) => Math.max(Number((prev - 0.25).toFixed(2)), 0.5))}
                disabled={zoomScale <= 0.5}
                title="Thu nhỏ (-)"
                aria-label="Thu nhỏ"
              >
                <ZoomOut size={17} />
              </button>
              <span className="mailbox-lightbox-zoom-badge">
                {Math.round(zoomScale * 100)}%
              </span>
              <button
                type="button"
                className="mailbox-lightbox-btn"
                onClick={() => setZoomScale((prev) => Math.min(Number((prev + 0.25).toFixed(2)), 4))}
                disabled={zoomScale >= 4}
                title="Phóng to (+)"
                aria-label="Phóng to"
              >
                <ZoomIn size={17} />
              </button>
              <button
                type="button"
                className="mailbox-lightbox-btn"
                onClick={() => setZoomScale(1)}
                title="Kích thước gốc (100%)"
                aria-label="Kích thước gốc"
              >
                <RotateCcw size={16} />
              </button>
              <button
                type="button"
                className="mailbox-lightbox-btn"
                onClick={() => setZoomScale((prev) => (prev >= 2.5 ? 1 : 2.5))}
                title={zoomScale >= 2.5 ? 'Thu về 100%' : 'Phóng to tối đa (250%)'}
                aria-label="Phóng to tối đa"
              >
                <Maximize2 size={16} />
              </button>
              <div className="mailbox-lightbox-divider" />
              <a
                href={zoomedImage.src}
                download={zoomedImage.alt || 'image'}
                target="_blank"
                rel="noopener noreferrer"
                className="mailbox-lightbox-btn"
                title="Tải ảnh gốc về máy"
                onClick={(e) => e.stopPropagation()}
              >
                <Download size={17} />
              </a>
              <button
                type="button"
                className="mailbox-lightbox-btn close"
                onClick={() => setZoomedImage(null)}
                title="Đóng (ESC)"
                aria-label="Đóng"
              >
                <X size={20} />
              </button>
            </div>
          </div>
          <div
            className="mailbox-lightbox-body"
            onWheel={(e) => {
              e.preventDefault();
              const delta = e.deltaY < 0 ? 0.25 : -0.25;
              setZoomScale((prev) => Math.min(Math.max(Number((prev + delta).toFixed(2)), 0.5), 4));
            }}
          >
            <div className="mailbox-lightbox-img-stage">
              <img
                src={zoomedImage.src}
                alt={zoomedImage.alt}
                className="mailbox-lightbox-img"
                style={{
                  transform: `scale(${zoomScale})`,
                  transformOrigin: 'center center',
                  transition: 'transform 0.12s ease-out',
                }}
                onClick={() => {
                  setZoomScale((prev) => (prev > 1.3 ? 1 : 2));
                }}
                title="Click để phóng to / thu nhỏ. Dùng con lăn chuột để zoom tự do."
              />
            </div>
          </div>
        </div>
      </div>
    )}
  </div>;
}
