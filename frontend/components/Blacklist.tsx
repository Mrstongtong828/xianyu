import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { BlacklistEntry } from '../types';
import { getBlacklist, addToBlacklist, removeFromBlacklist } from '../services/api';
import { Plus, Trash2, ShieldOff, X, Save, Loader2, User, MessageSquare, Clock } from 'lucide-react';

const Blacklist: React.FC = () => {
  const [entries, setEntries] = useState<BlacklistEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ buyer_id: '', buyer_name: '', reason: '' });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadEntries();
  }, []);

  const loadEntries = async () => {
    setLoading(true);
    try {
      const res = await getBlacklist();
      setEntries(res.data || []);
    } catch (e) {
      console.error('加载黑名单失败', e);
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = () => {
    setForm({ buyer_id: '', buyer_name: '', reason: '' });
    setShowModal(true);
  };

  const handleSave = async () => {
    if (!form.buyer_id.trim()) {
      alert('请输入买家ID');
      return;
    }
    setSaving(true);
    try {
      await addToBlacklist(form.buyer_id, form.buyer_name, form.reason);
      setShowModal(false);
      loadEntries();
      alert('添加成功！');
    } catch (e) {
      alert('添加失败：' + (e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('确认将该买家从黑名单中移除吗？')) return;
    try {
      await removeFromBlacklist(id);
      loadEntries();
      alert('移除成功！');
    } catch (e) {
      alert('移除失败：' + (e as Error).message);
    }
  };

  return (
    <div className="space-y-8 animate-fade-in">
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-4xl font-extrabold text-gray-900 dark:text-gray-100 tracking-tight">买家黑名单</h2>
          <p className="text-gray-500 dark:text-gray-400 mt-2 font-medium">管理被拉黑的买家，被拉黑的买家消息将被自动忽略</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadEntries}
            className="flex items-center gap-2 px-6 py-3 rounded-2xl font-bold bg-gradient-to-br from-gray-100 to-gray-200 hover:from-gray-200 hover:to-gray-300 transition-all shadow-lg"
          >
            <Loader2 className="w-5 h-5" />
            刷新
          </button>
          <button
            onClick={handleAdd}
            className="flex items-center gap-2 px-8 py-3 rounded-2xl font-bold bg-gradient-to-r from-[#FFE815] to-[#FFD700] hover:from-[#FFD700] hover:to-[#FFC800] text-gray-900 shadow-xl hover:shadow-2xl hover:scale-105 transition-all"
          >
            <Plus className="w-5 h-5" />
            添加到黑名单
          </button>
        </div>
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
              <ShieldOff className="w-12 h-12 text-[#FFE815]" />
            </div>
            <h3 className="text-2xl font-bold text-gray-900 mb-2">黑名单为空</h3>
            <p className="text-gray-500 text-lg">点击右上角添加买家到黑名单</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[800px] md:min-w-0">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  <th className="text-left px-6 py-5 text-sm font-bold text-gray-600">买家ID</th>
                  <th className="text-left px-6 py-5 text-sm font-bold text-gray-600">昵称</th>
                  <th className="text-left px-6 py-5 text-sm font-bold text-gray-600">拉黑原因</th>
                  <th className="text-left px-6 py-5 text-sm font-bold text-gray-600">添加时间</th>
                  <th className="text-center px-6 py-5 text-sm font-bold text-gray-600">操作</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id} className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
                    <td className="px-6 py-5">
                      <span className="font-bold text-gray-900 font-mono text-sm">{entry.buyer_id}</span>
                    </td>
                    <td className="px-6 py-5">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 bg-gradient-to-br from-gray-100 to-gray-200 rounded-xl flex items-center justify-center">
                          <User className="w-4 h-4 text-gray-500" />
                        </div>
                        <span className="font-medium text-gray-700">{entry.buyer_name || '-'}</span>
                      </div>
                    </td>
                    <td className="px-6 py-5">
                      <div className="flex items-center gap-2">
                        <MessageSquare className="w-4 h-4 text-gray-400" />
                        <span className="text-gray-600 max-w-xs truncate block">{entry.reason || '-'}</span>
                      </div>
                    </td>
                    <td className="px-6 py-5">
                      <div className="flex items-center gap-2 text-gray-500 text-sm">
                        <Clock className="w-4 h-4" />
                        {entry.created_at ? new Date(entry.created_at).toLocaleString('zh-CN') : '-'}
                      </div>
                    </td>
                    <td className="px-6 py-5 text-center">
                      <button
                        onClick={() => handleDelete(entry.id)}
                        className="p-3 bg-gradient-to-br from-red-50 to-red-100 text-red-500 rounded-2xl hover:from-red-100 hover:to-red-200 transition-all shadow-md hover:shadow-lg hover:scale-110"
                        title="移除"
                      >
                        <Trash2 className="w-5 h-5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showModal && createPortal(
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in">
          <div className="bg-white rounded-[2.5rem] shadow-2xl max-w-xl w-full overflow-hidden animate-scale-in">
            <div className="bg-gradient-to-r from-[#FFE815] to-[#FFD700] p-8">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-14 h-14 bg-white/30 backdrop-blur-sm rounded-2xl flex items-center justify-center">
                    <ShieldOff className="w-7 h-7 text-gray-900" />
                  </div>
                  <h3 className="text-3xl font-black text-gray-900">添加到黑名单</h3>
                </div>
                <button
                  onClick={() => setShowModal(false)}
                  className="p-3 bg-white/30 backdrop-blur-sm rounded-2xl hover:bg-white/40 transition-colors"
                >
                  <X className="w-6 h-6 text-gray-900" />
                </button>
              </div>
            </div>

            <div className="p-8 space-y-6">
              <div>
                <label className="flex items-center gap-2 text-sm font-black text-gray-900 mb-3">
                  <User className="w-5 h-5 text-[#FFE815]" />
                  买家ID <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={form.buyer_id}
                  onChange={(e) => setForm({ ...form, buyer_id: e.target.value })}
                  placeholder="输入买家的闲鱼ID"
                  className="w-full px-6 py-4 rounded-2xl font-medium border-2 border-gray-200 focus:border-[#FFE815] focus:ring-4 focus:ring-[#FFE815]/20 transition-all bg-gray-50"
                />
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-black text-gray-900 mb-3">
                  <User className="w-5 h-5 text-[#FFE815]" />
                  买家昵称
                </label>
                <input
                  type="text"
                  value={form.buyer_name}
                  onChange={(e) => setForm({ ...form, buyer_name: e.target.value })}
                  placeholder="可选，方便识别"
                  className="w-full px-6 py-4 rounded-2xl font-medium border-2 border-gray-200 focus:border-[#FFE815] focus:ring-4 focus:ring-[#FFE815]/20 transition-all bg-gray-50"
                />
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-black text-gray-900 mb-3">
                  <MessageSquare className="w-5 h-5 text-[#FFE815]" />
                  拉黑原因
                </label>
                <textarea
                  value={form.reason}
                  onChange={(e) => setForm({ ...form, reason: e.target.value })}
                  placeholder="可选，记录拉黑原因..."
                  rows={3}
                  className="w-full px-6 py-4 rounded-2xl font-medium border-2 border-gray-200 focus:border-[#FFE815] focus:ring-4 focus:ring-[#FFE815]/20 transition-all bg-gray-50 resize-none"
                />
              </div>
            </div>

            <div className="p-8 bg-gray-50 border-t border-gray-100">
              <div className="flex gap-4">
                <button
                  onClick={() => setShowModal(false)}
                  className="flex-1 px-8 py-4 rounded-2xl font-bold bg-white border-2 border-gray-200 hover:bg-gray-50 hover:border-gray-300 text-gray-700 transition-all shadow-lg hover:shadow-xl"
                >
                  取消
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="flex-1 px-8 py-4 rounded-2xl font-bold bg-gradient-to-r from-[#FFE815] to-[#FFD700] hover:from-[#FFD700] hover:to-[#FFC800] text-gray-900 shadow-xl hover:shadow-2xl hover:scale-105 transition-all flex items-center justify-center gap-2 disabled:opacity-70"
                >
                  <Save className="w-5 h-5" />
                  {saving ? '保存中...' : '保存'}
                </button>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
};

export default Blacklist;
