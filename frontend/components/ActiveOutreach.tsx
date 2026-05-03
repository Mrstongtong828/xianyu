import React, { useEffect, useState } from 'react';
import { ActiveOutreachRecord, AccountDetail } from '../types';
import { getAccountDetails, initiateActiveOutreach, getActiveOutreachHistory } from '../services/api';
import { Send, ExternalLink, RefreshCw, Loader2, User, Bot, AlertCircle, CheckCircle2, Clock, XCircle, ChevronLeft, ChevronRight } from 'lucide-react';

const statusConfig: Record<string, { bg: string; text: string; icon: React.ReactNode }> = {
  pending: { bg: 'bg-gray-100', text: 'text-gray-600', icon: <Clock className="w-3 h-3" /> },
  sending: { bg: 'bg-yellow-100', text: 'text-yellow-700', icon: <Loader2 className="w-3 h-3 animate-spin" /> },
  sent: { bg: 'bg-blue-100', text: 'text-blue-700', icon: <Send className="w-3 h-3" /> },
  replied: { bg: 'bg-green-100', text: 'text-green-700', icon: <CheckCircle2 className="w-3 h-3" /> },
  failed: { bg: 'bg-red-100', text: 'text-red-600', icon: <XCircle className="w-3 h-3" /> },
};

const ActiveOutreach: React.FC = () => {
  const STORAGE_KEY = 'active_outreach_form';
  const savedForm = (() => { try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); } catch { return {}; } })();

  const [accounts, setAccounts] = useState<AccountDetail[]>([]);
  const [selectedAccount, setSelectedAccount] = useState(savedForm.selectedAccount || '');
  const [itemUrl, setItemUrl] = useState(savedForm.itemUrl || '');
  const [customMessage, setCustomMessage] = useState(savedForm.customMessage || '');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [records, setRecords] = useState<ActiveOutreachRecord[]>([]);
  const [loadingRecords, setLoadingRecords] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    getAccountDetails().then(accs => {
      const enabled = accs.filter(a => a.enabled);
      setAccounts(enabled);
      if (!selectedAccount || !enabled.find(a => a.id === selectedAccount)) {
        if (enabled.length > 0) setSelectedAccount(enabled[0].id);
      }
    }).catch(console.error);
    loadRecords(1);
  }, []);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ selectedAccount, itemUrl, customMessage }));
  }, [selectedAccount, itemUrl, customMessage]);

  const loadRecords = async (p: number = 1) => {
    setLoadingRecords(true);
    try {
      const res = await getActiveOutreachHistory({ page: p, page_size: pageSize });
      if (res.success) {
        setRecords(res.data || []);
        setTotal(res.total || 0);
      }
    } catch (e) {
      console.error('加载主动询价记录失败:', e);
    } finally {
      setLoadingRecords(false);
    }
  };

  const handleSubmit = async () => {
    if (!selectedAccount) { setError('请选择账号'); return; }
    if (!itemUrl.trim()) { setError('请输入闲鱼商品链接'); return; }
    setError(null);
    setResult(null);
    setSubmitting(true);
    try {
      const res = await initiateActiveOutreach({
        cookie_id: selectedAccount,
        item_url: itemUrl.trim(),
        custom_message: customMessage.trim() || undefined,
      });
      if (res.success) {
        setResult(res.message);
        setItemUrl('');
        setCustomMessage('');
        loadRecords(1);
      } else {
        setError(res.message || '发起询价失败');
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || '请求失败，请检查网络连接');
    } finally {
      setSubmitting(false);
    }
  };

  const formatTime = (ts: string) => {
    if (!ts) return '';
    try {
      return new Date(ts).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
    } catch { return ts; }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="text-4xl font-extrabold text-gray-900 dark:text-gray-100 tracking-tight">主动询价</h2>
        <p className="text-gray-500 dark:text-gray-400 mt-2 font-medium">输入闲鱼商品链接，AI 自动向卖家发起询价对话。</p>
      </div>

      {/* 发起询价卡片 */}
      <div className="ios-card rounded-[2rem] p-6 bg-white dark:bg-gray-900 shadow-lg border-0">
        <div className="flex items-center gap-3 mb-5">
          <div className="p-2.5 rounded-xl bg-green-100">
            <Send className="w-5 h-5 text-green-600" />
          </div>
          <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">发起主动询价</h3>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-bold text-gray-700 dark:text-gray-300 mb-2">选择账号</label>
            <select
              value={selectedAccount}
              onChange={e => setSelectedAccount(e.target.value)}
              className="ios-input w-full px-4 py-3 rounded-xl bg-gray-50 dark:bg-gray-800 border-none text-sm"
            >
              {accounts.length === 0 && <option value="">暂无可用账号</option>}
              {accounts.map(a => (
                <option key={a.id} value={a.id}>{a.remark || a.id}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-bold text-gray-700 dark:text-gray-300 mb-2">商品链接</label>
            <div className="relative group">
              <ExternalLink className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 group-focus-within:text-green-500 transition-colors" />
              <input
                type="text"
                placeholder="粘贴闲鱼商品链接，例如 https://www.goofish.com/item?id=..."
                value={itemUrl}
                onChange={e => setItemUrl(e.target.value)}
                className="ios-input pl-10 pr-4 py-3 rounded-xl w-full bg-gray-50 dark:bg-gray-800 border-none text-sm"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-bold text-gray-700 dark:text-gray-300 mb-2">
              自定义消息 <span className="text-gray-400 font-normal">(选填，AI 将基于此生成询价内容)</span>
            </label>
            <textarea
              placeholder="例如：帮我问问这个最低多少钱，包邮吗？"
              value={customMessage}
              onChange={e => setCustomMessage(e.target.value)}
              rows={3}
              className="ios-input w-full px-4 py-3 rounded-xl bg-gray-50 dark:bg-gray-800 border-none text-sm resize-none"
            />
          </div>

          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="w-full py-3.5 rounded-xl bg-green-500 hover:bg-green-600 text-white font-bold text-base flex items-center justify-center gap-2 transition-all active:scale-95 disabled:opacity-50 shadow-lg shadow-green-200"
          >
            {submitting ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
            {submitting ? 'AI 正在生成询价...' : '发起询价'}
          </button>
        </div>

        {result && (
          <div className="mt-4 p-4 rounded-xl bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="w-5 h-5 text-green-500 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm font-bold text-green-700 dark:text-green-400 mb-1">询价已发送</p>
                <p className="text-sm text-green-600 dark:text-green-500">{result}</p>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mt-4 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-500 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            </div>
          </div>
        )}
      </div>

      {/* 询价历史记录 */}
      <div className="ios-card rounded-[2rem] p-6 bg-white dark:bg-gray-900 shadow-lg border-0">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">询价记录</h3>
          <button
            onClick={() => loadRecords(page)}
            className="p-2.5 rounded-xl bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loadingRecords ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {loadingRecords ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw className="w-6 h-6 text-[#FFE815] animate-spin" />
          </div>
        ) : records.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-400">
            <Send className="w-10 h-10 mb-3" />
            <p className="text-sm font-medium">暂无主动询价记录</p>
          </div>
        ) : (
          <>
            <div className="space-y-3">
              {records.map(record => {
                const status = statusConfig[record.status] || statusConfig.pending;
                return (
                  <div key={record.id} className="p-4 rounded-xl bg-gray-50 dark:bg-gray-800 border border-gray-100 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-750 transition-colors">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <a
                            href={record.item_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm font-bold text-gray-900 dark:text-gray-100 hover:text-green-500 transition-colors truncate flex items-center gap-1"
                          >
                            {record.item_title || record.item_url.substring(0, 50) + '...'}
                            <ExternalLink className="w-3 h-3 flex-shrink-0" />
                          </a>
                        </div>
                        <div className="text-xs text-gray-400 mb-2">
                          {record.seller_name && <span>卖家: {record.seller_name} · </span>}
                          {formatTime(record.created_at)}
                        </div>
                        <div className="space-y-2">
                          <div className="flex items-start gap-2">
                            <Send className="w-3.5 h-3.5 text-green-500 mt-0.5 flex-shrink-0" />
                            <p className="text-sm text-gray-700 dark:text-gray-300">{record.message}</p>
                          </div>
                          {record.reply && (
                            <div className="flex items-start gap-2">
                              <User className="w-3.5 h-3.5 text-blue-500 mt-0.5 flex-shrink-0" />
                              <p className="text-sm text-gray-500 dark:text-gray-400">{record.reply}</p>
                            </div>
                          )}
                          {record.error_message && (
                            <div className="flex items-start gap-2">
                              <AlertCircle className="w-3.5 h-3.5 text-red-500 mt-0.5 flex-shrink-0" />
                              <p className="text-xs text-red-500">{record.error_message}</p>
                            </div>
                          )}
                        </div>
                      </div>
                      <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-bold flex-shrink-0 ${status.bg} ${status.text}`}>
                        {status.icon}
                        {record.status === 'pending' && '等待中'}
                        {record.status === 'sending' && '发送中'}
                        {record.status === 'sent' && '已发送'}
                        {record.status === 'replied' && '已回复'}
                        {record.status === 'failed' && '失败'}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="mt-4 flex items-center justify-between">
              <span className="text-sm text-gray-400">第 {page} 页 / 共 {totalPages} 页 (共 {total} 条)</span>
              <div className="flex gap-2">
                <button
                  disabled={page <= 1}
                  onClick={() => { setPage(p => p - 1); loadRecords(page - 1); }}
                  className="p-2 rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  disabled={page >= totalPages}
                  onClick={() => { setPage(p => p + 1); loadRecords(page + 1); }}
                  className="p-2 rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default ActiveOutreach;
