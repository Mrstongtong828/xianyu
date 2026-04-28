import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { DeliveryRetryEntry } from '../types';
import { getDeliveryRetryQueue, retryDelivery, deleteDeliveryRetry } from '../services/api';
import { RotateCw, Trash2, Loader2, Clock, User, AlertTriangle, ShoppingBag } from 'lucide-react';

const statusConfig: Record<string, { label: string; class: string }> = {
  pending: { label: '等待中', class: 'bg-yellow-100 text-yellow-700' },
  retrying: { label: '重试中', class: 'bg-blue-100 text-blue-700' },
  success: { label: '已成功', class: 'bg-green-100 text-green-700' },
  failed: { label: '已失败', class: 'bg-red-100 text-red-700' },
};

const DeliveryRetryQueue: React.FC = () => {
  const [entries, setEntries] = useState<DeliveryRetryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [retrying, setRetrying] = useState<number | null>(null);

  useEffect(() => {
    loadEntries();
  }, []);

  const loadEntries = async () => {
    setLoading(true);
    try {
      const res = await getDeliveryRetryQueue();
      setEntries(res.data || []);
    } catch (e) {
      console.error('加载发货重试队列失败', e);
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = async (id: number) => {
    setRetrying(id);
    try {
      await retryDelivery(id);
      alert('重试已提交！');
      loadEntries();
    } catch (e) {
      alert('重试失败：' + (e as Error).message);
    } finally {
      setRetrying(null);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('确认删除该重试记录吗？')) return;
    try {
      await deleteDeliveryRetry(id);
      loadEntries();
      alert('删除成功！');
    } catch (e) {
      alert('删除失败：' + (e as Error).message);
    }
  };

  const getStatusBadge = (status: string) => {
    const config = statusConfig[status] || { label: status, class: 'bg-gray-100 text-gray-700' };
    return (
      <span className={`px-3 py-1.5 rounded-xl text-xs font-bold shadow-sm ${config.class}`}>
        {config.label}
      </span>
    );
  };

  const truncate = (text: string, maxLen: number = 40) => {
    if (!text) return '-';
    return text.length > maxLen ? text.substring(0, maxLen) + '...' : text;
  };

  return (
    <div className="space-y-8 animate-fade-in">
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-4xl font-extrabold text-gray-900 tracking-tight">发货重试队列</h2>
          <p className="text-gray-500 mt-2 font-medium">管理发货失败的重试记录，支持手动重新发起发货</p>
        </div>
        <button
          onClick={loadEntries}
          className="flex items-center gap-2 px-6 py-3 rounded-2xl font-bold bg-gradient-to-br from-gray-100 to-gray-200 hover:from-gray-200 hover:to-gray-300 transition-all shadow-lg"
        >
          <RotateCw className="w-5 h-5" />
          刷新
        </button>
      </div>

      <div className="ios-card rounded-[2rem] bg-white overflow-hidden shadow-xl">
        {loading ? (
          <div className="py-24 flex justify-center">
            <div className="flex flex-col items-center gap-4">
              <Loader2 className="w-16 h-16 text-[#FFE815] animate-spin" />
              <p className="text-gray-500 font-medium">加载中...</p>
            </div>
          </div>
        ) : entries.length === 0 ? (
          <div className="py-24 text-center">
            <div className="w-24 h-24 bg-gradient-to-br from-[#FFE815]/20 to-[#FFD700]/20 rounded-full flex items-center justify-center mx-auto mb-6 shadow-inner">
              <RotateCw className="w-12 h-12 text-[#FFE815]" />
            </div>
            <h3 className="text-2xl font-bold text-gray-900 mb-2">队列为空</h3>
            <p className="text-gray-500 text-lg">暂无需要重试的发货记录</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  <th className="text-left px-5 py-5 text-sm font-bold text-gray-600">订单ID</th>
                  <th className="text-left px-5 py-5 text-sm font-bold text-gray-600">买家</th>
                  <th className="text-left px-5 py-5 text-sm font-bold text-gray-600">错误类型</th>
                  <th className="text-left px-5 py-5 text-sm font-bold text-gray-600">错误信息</th>
                  <th className="text-center px-5 py-5 text-sm font-bold text-gray-600">重试次数</th>
                  <th className="text-center px-5 py-5 text-sm font-bold text-gray-600">状态</th>
                  <th className="text-left px-5 py-5 text-sm font-bold text-gray-600">创建时间</th>
                  <th className="text-center px-5 py-5 text-sm font-bold text-gray-600">操作</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id} className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-2">
                        <ShoppingBag className="w-4 h-4 text-gray-400" />
                        <span className="font-mono text-sm font-bold text-gray-900">{entry.order_id}</span>
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 bg-gradient-to-br from-gray-100 to-gray-200 rounded-xl flex items-center justify-center flex-shrink-0">
                          <User className="w-3.5 h-3.5 text-gray-500" />
                        </div>
                        <div className="min-w-0">
                          <div className="font-medium text-gray-700 text-sm truncate max-w-[120px]">{entry.buyer_name || entry.buyer_id}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <span className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-700">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                        {entry.error_type || '-'}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <span className="text-sm text-gray-500" title={entry.error_message}>
                        {truncate(entry.error_message)}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-center">
                      <span className={`text-sm font-bold font-mono ${
                        entry.retry_count >= entry.max_retries ? 'text-red-500' : 'text-gray-700'
                      }`}>
                        {entry.retry_count}/{entry.max_retries}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-center">
                      {getStatusBadge(entry.status)}
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-1.5 text-gray-500 text-sm">
                        <Clock className="w-3.5 h-3.5" />
                        {entry.created_at ? new Date(entry.created_at).toLocaleString('zh-CN') : '-'}
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center justify-center gap-2">
                        <button
                          onClick={() => handleRetry(entry.id)}
                          disabled={retrying === entry.id}
                          className="p-2.5 bg-gradient-to-br from-blue-50 to-blue-100 text-blue-600 rounded-2xl hover:from-blue-100 hover:to-blue-200 transition-all shadow-md hover:shadow-lg hover:scale-110 disabled:opacity-50"
                          title="重试"
                        >
                          {retrying === entry.id ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <RotateCw className="w-4 h-4" />
                          )}
                        </button>
                        <button
                          onClick={() => handleDelete(entry.id)}
                          className="p-2.5 bg-gradient-to-br from-red-50 to-red-100 text-red-500 rounded-2xl hover:from-red-100 hover:to-red-200 transition-all shadow-md hover:shadow-lg hover:scale-110"
                          title="删除"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default DeliveryRetryQueue;
