import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle, ArrowLeft, ChevronLeft, ChevronRight, Clock3,
  FileCheck2, Inbox, LifeBuoy, Loader2, Mail, MailOpen, Plus, RefreshCw,
  Reply, Search, Send, X,
} from 'lucide-react';
import { apiFetch, readJsonResponse } from '../utils/api';
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

function RichTextEditor({ editorRef, value, onChange, label }) {
  const runCommand = (command, argument) => {
    editorRef.current?.focus();
    document.execCommand(command, false, argument);
    onChange(editorRef.current?.innerHTML || '');
  };
  const addLink = () => {
    const url = window.prompt('Nhập liên kết bắt đầu bằng https://');
    if (url) runCommand('createLink', url);
  };
  return <div className="mailbox-editor-wrap">
    <div className="mailbox-editor-toolbar" aria-label="Định dạng nội dung">
      <button type="button" onClick={() => runCommand('bold')} aria-label="In đậm"><strong>B</strong></button>
      <button type="button" onClick={() => runCommand('italic')} aria-label="In nghiêng"><em>I</em></button>
      <button type="button" onClick={() => runCommand('underline')} aria-label="Gạch chân"><u>U</u></button>
      <button type="button" onClick={() => runCommand('insertUnorderedList')} aria-label="Danh sách chấm">• List</button>
      <button type="button" onClick={() => runCommand('insertOrderedList')} aria-label="Danh sách số">1. List</button>
      <button type="button" onClick={addLink} aria-label="Thêm liên kết">Link</button>
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
      data-placeholder="Nhập nội dung thư…"
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
      const result = await fetchJson('/api/mailbox/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          receiverIds: selectedRecipients.map((item) => item.ma_nguoi_dung),
          groupKeys: groupKey ? [groupKey] : [], category,
          subject: subject.trim(), contentHtml, sendEmail,
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
          <label className="mailbox-field"><span>Nội dung *</span><RichTextEditor editorRef={editorRef} value={contentHtml} onChange={setContentHtml} label="Nội dung thư" /></label>
          <label className="mailbox-email-check"><input type="checkbox" checked={sendEmail} onChange={(event) => setSendEmail(event.target.checked)} /><span><strong>Gửi thêm email</strong><small>Thư nội bộ vẫn xuất hiện ngay; email được xử lý ở hàng đợi.</small></span></label>
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
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState('');
  const [composeOpen, setComposeOpen] = useState(false);
  const [replyOpen, setReplyOpen] = useState(false);
  const [replyHtml, setReplyHtml] = useState('');
  const [replying, setReplying] = useState(false);
  const replyEditorRef = useRef(null);

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
      setMailbox(await fetchJson(`/api/mailbox/messages?${params}`));
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
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setReplying(false);
    }
  };

  const folderItems = [
    { label: 'Hộp thư đến', icon: Inbox, action: () => chooseFolder('inbox'), active: folder === 'inbox' && statusFilter === 'all' && !category, count: mailbox.totalItems },
    { label: 'Đã gửi', icon: Send, action: () => chooseFolder('sent'), active: folder === 'sent' },
    { label: 'Chưa đọc', icon: MailOpen, action: () => chooseFolder('inbox', 'unread'), active: folder === 'inbox' && statusFilter === 'unread' },
    { label: 'Cần xử lý', icon: Clock3, action: () => chooseFolder('inbox', 'all', 'XIN_XET_DUYET'), active: category === 'XIN_XET_DUYET' },
  ];

  return <div className="mailbox-page">
    <div className="mailbox-page-heading"><div><span>Hộp thư & tương tác nội bộ</span><h1>Hộp thư</h1><p>Trao đổi, gửi yêu cầu và theo dõi thông báo ngay trong IMS Portal.</p></div><button type="button" className="mailbox-button primary mobile-compose" onClick={() => setComposeOpen(true)}><Plus size={17} /> Soạn thư</button></div>
    {error && <div className="mailbox-page-error"><AlertCircle size={18} /><span>{error}</span><button type="button" onClick={loadMessages}>Thử lại</button></div>}
    <div className={`mailbox-shell${selectedId ? ' has-selection' : ''}`}>
      <aside className="mailbox-folders">
        <button type="button" className="mailbox-button primary compose-button" onClick={() => setComposeOpen(true)}><Plus size={17} /> Soạn thư mới</button>
        <nav>{folderItems.map(({ label, icon: Icon, action, active, count }) => <button type="button" key={label} className={active ? 'active' : ''} onClick={action}><Icon size={18} /><span>{label}</span>{label === 'Hộp thư đến' && count > 0 && <b>{count}</b>}</button>)}</nav>
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
          <div className="mailbox-thread">
            {detail.thread?.map((message) => <article key={message.id} className={message.sender_id === currentUser.ma_nguoi_dung ? 'from-me' : ''}><header><span className="mailbox-avatar small">{initials(message.sender_name)}</span><div><strong>{message.sender_id === currentUser.ma_nguoi_dung ? 'Bạn' : message.sender_name || 'Tài khoản đã xóa'}</strong><time>{formatDate(message.created_at)}</time></div></header><div className="mailbox-rich-content" dangerouslySetInnerHTML={{ __html: message.content_html }} />{message.recipients?.some((recipient) => recipient.email_status) && <div className="mailbox-email-status">Email: {message.recipients.map((recipient) => recipient.email_status).filter(Boolean).join(', ')}</div>}</article>)}
          </div>
          <footer className="mailbox-detail-actions">{replyOpen ? <div className="mailbox-reply-box"><RichTextEditor editorRef={replyEditorRef} value={replyHtml} onChange={setReplyHtml} label="Nội dung trả lời" /><div><button type="button" className="mailbox-button secondary" onClick={() => setReplyOpen(false)}>Hủy</button><button type="button" className="mailbox-button primary" disabled={replying} onClick={submitReply}>{replying ? <Loader2 className="spin" size={16} /> : <Send size={16} />} Gửi trả lời</button></div></div> : <button type="button" className="mailbox-button primary" onClick={() => setReplyOpen(true)}><Reply size={16} /> Trả lời</button>}</footer>
        </>}
      </section>
    </div>
    {composeOpen && <ComposeModal currentUser={currentUser} onClose={() => setComposeOpen(false)} onSent={(count) => { setComposeOpen(false); chooseFolder('sent'); onShowToast(`Đã gửi thư tới ${count} người nhận.`); }} />}
  </div>;
}
