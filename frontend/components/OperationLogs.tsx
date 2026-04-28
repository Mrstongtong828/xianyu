import React, { useEffect, useState } from 'react';
import { OperationLog } from '../types';
import { getOperationLogs, getAccountDetails } from '../services/api';
import { ScrollText, ChevronLeft, ChevronRight, Loader2, Filter, X, Check, AlertTriangle, Clock } from 'lucide-react';

const EVENT_TYPES = [
  { value: '', label: '全部类型' },
  { value: 'slider_captcha', label: '滑块验证' },
  { value: 'token_refresh', label: 'Token刷新' },
  { value: 'cookie_refresh', label: 'Cookie刷新' },
  { value: 'auto_delivery', label: '自动发货' },
  { value: 'auto_reply', label: '自动回复' },
  { value: 'auto_confirm', label: '自动确认' },
  { value: 'item_sync', label: '商品同步' },
  { value: 'error', label: '错误' },
];

const eventLabelMap: Record<string, string> = {};
EVENT_TYPES.forEach(e => { eventLabelMap[e.value] = e.label; });

const OperationLogs: React.FC = () => {
  const [logs, setLogs] = useState<OperationLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [cookieIdFilter, setCookieIdFilter] = useState('');
  const [logTypeFilter, setLogTypeFilter] = useState('');
  const [accounts, setAccounts] = useState<{ id: string; nickname?: string }[]>([]);
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    getAccountDetails().then(data => setAccounts(data)).catch(console.error);
  }, []);

  useEffect(() => {
    loadLogs();
  }, [page, cookieIdFilter, logTypeFilter]);

  const loadLogs = async () => {
    setLoading(true);
    try {
      const res = await getOperationLogs({
        cookie_id: cookieIdFilter || undefined,
        log_type: logTypeFilter || undefined,
        page,
        page_size: pageSize,
      });
      setLogs(res.data || []);
      setTotal(res.total || 0);
    } catch (e) {
      console.error('加载操作日志失败', e);
    } finally {
      setLoading(false);
    }
  };

  const clearFilters = () => {
    setCookieIdFilter('');
    setLogTypeFilter('');
    setPage(1);
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const getEventBadge = (eventType: string) => {
    const colorMap: Record<string, string> = {
      slider_captcha: 'bg-orange-100 text-orange-700',
      token_refresh: 'bg-blue-100 text-blue-700',
      cookie_refresh: 'bg-indigo-100 text-indigo-700',
      auto_delivery: 'bg-green-100 text-green-700',
      auto_reply: 'bg-cyan-100 text-cyan-700',
      auto_confirm: 'bg-purple-100 text-purple-700',
      item_sync: 'bg-teal-100 text-teal-700',
      error: 'bg-red-100 text-red-700',
    };
    return colorMap[eventType] || 'bg-gray-100 text-gray-600';
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success':
      case 'resolved':
        return <Check className="w-4 h-4 text-green-500" />;
      case 'failed':
        return <AlertTriangle className="w-4 h-4 text-red-500" />;
      default:
        return <Clock className="w-4 h-4 text-yellow-500" />;
    }
  };

  return (
    <div className="space-y-8 animate-fade-in">
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-4xl font-extrabold text-gray-900 tracking-tight">操作日志</h2>
          <p className="text-gray-500 mt-2 font-medium">查看系统操作记录和风控日志</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-2 px-5 py-3 rounded-2xl font-bold transition-all shadow-lg ${
              showFilters || cookieIdFilter || logTypeFilter
                ? 'bg-[#FFE815] text-black'
                : 'bg-gradient-to-br from-gray-100 to-gray-200 hover:from-gray-200 hover:to-gray-300'
            }`}
          >
            <Filter className="w-5 h-5" />
            筛选
          </button>
          <button
            onClick={loadLogs}
            className="flex items-center gap-2 px-6 py-3 rounded-2xl font-bold bg-gradient-to-br from-gray-100 to-gray-200 hover:from-gray-200 hover:to-gray-300 transition-all shadow-lg"
          >
            <Loader2 className="w-5 h-5" />
            刷新
          </button>
        </div>
      </div>

      {showFilters && (
        <div className="ios-card p-6 rounded-[2rem] flex flex-wrap gap-4 items-end">
          <div className="flex-1 min-w-[200px]">
            <label className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2 block">账号</label>
            <select
              value={cookieIdFilter}
              onChange={e => { setCookieIdFilter(e.target.value); setPage(1); }}
              className="w-full px-4 py-3 rounded-2xl border border-gray-200 bg-white text-sm font-medium focus:outline-none focus:border-[#FFE815] focus:ring-2 focus:ring-yellow-100"
            >
              <option value="">全部账号</option>
              {accounts.map(a => (
                <option key={a.id} value={a.id}>{a.nickname || a.id}</option>
              ))}
            </select>
          </div>
          <div className="flex-1 min-w-[200px]">
            <label className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2 block">事件类型</label>
            <select
              value={logTypeFilter}
              onChange={e => { setLogTypeFilter(e.target.value); setPage(1); }}
              className="w-full px-4 py-3 rounded-2xl border border-gray-200 bg-white text-sm font-medium focus:outline-none focus:border-[#FFE815] focus:ring-2 focus:ring-yellow-100"
            >
              {EVENT_TYPES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          <button
            onClick={clearFilters}
            className="px-5 py-3 rounded-2xl font-bold text-gray-500 hover:text-red-500 hover:bg-red-50 transition-all flex items-center gap-2"
          >
            <X className="w-4 h-4" />
            清除
          </button>
        </div>
      )}

      <div className="ios-card rounded-[2rem] p-6 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="text-gray-400 text-xs font-bold uppercase tracking-wider border-b border-gray-50">
                <th className="px-6 py-4 whitespace-nowrap">时间</th>
                <th className="px-6 py-4 whitespace-nowrap">账号ID</th>
                <th className="px-6 py-4 whitespace-nowrap">事件类型</th>
                <th className="px-6 py-4 whitespace-nowrap">事件详情</th>
                <th className="px-6 py-4 whitespace-nowrap text-center">结果</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-6 py-20 text-center text-gray-400">
                    <Loader2 className="w-8 h-8 animate-spin mx-auto" />
                  </td>
                </tr>
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-20 text-center text-gray-400">
                    <ScrollText className="w-12 h-12 mx-auto mb-3 opacity-20" />
                    <p className="text-lg font-medium">暂无操作日志</p>
                    <p className="text-sm mt-1">系统操作记录将显示在这里</p>
                  </td>
                </tr>
              ) : (
                logs.map(log => (
                  <tr key={log.id} className="hover:bg-[#FFFDE7]/50 transition-colors group">
                    <td className="px-6 py-4 text-sm text-gray-500 font-mono whitespace-nowrap">
                      {log.created_at || '-'}
                    </td>
                    <td className="px-6 py-4">
                      <span className="text-sm font-bold text-gray-800">
                        {log.cookie_id?.substring(0, 12)}...
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-3 py-1.5 rounded-lg text-xs font-bold ${getEventBadge(log.event_type)}`}>
                        {eventLabelMap[log.event_type] || log.event_type}
                      </span>
                    </td>
                    <td className="px-6 py-4 max-w-[300px]">
                      <div className="text-sm text-gray-700 truncate" title={log.event_description || log.error_message || ''}>
                        {log.event_description || log.error_message || log.processing_result || '-'}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-center">
                      <div className="flex items-center justify-center gap-1.5">
                        {getStatusIcon(log.processing_status)}
                        <span className={`text-xs font-bold ${
                          log.processing_status === 'success' || log.processing_status === 'resolved'
                            ? 'text-green-600'
                            : log.processing_status === 'failed'
                            ? 'text-red-600'
                            : 'text-yellow-600'
                        }`}>
                          {log.processing_status === 'success' || log.processing_status === 'resolved'
                            ? '成功'
                            : log.processing_status === 'failed'
                            ? '失败'
                            : '处理中'}
                        </span>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="mt-6 flex items-center justify-between border-t border-gray-50 pt-4">
            <span className="text-sm text-gray-500 font-medium">
              共 {total} 条记录，第 {page}/{totalPages} 页
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-2.5 rounded-xl border border-gray-200 bg-white disabled:opacity-40 hover:bg-gray-50 transition-all"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                let pageNum: number;
                if (totalPages <= 5) {
                  pageNum = i + 1;
                } else if (page <= 3) {
                  pageNum = i + 1;
                } else if (page >= totalPages - 2) {
                  pageNum = totalPages - 4 + i;
                } else {
                  pageNum = page - 2 + i;
                }
                return (
                  <button
                    key={pageNum}
                    onClick={() => setPage(pageNum)}
                    className={`w-10 h-10 rounded-xl text-sm font-bold transition-all ${
                      pageNum === page
                        ? 'bg-[#FFE815] text-black shadow-md'
                        : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    {pageNum}
                  </button>
                );
              })}
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-2.5 rounded-xl border border-gray-200 bg-white disabled:opacity-40 hover:bg-gray-50 transition-all"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default OperationLogs;
