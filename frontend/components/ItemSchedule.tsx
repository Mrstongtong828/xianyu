import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ItemSchedule as ItemScheduleType, AccountDetail, Item } from '../types';
import { getItemSchedules, addItemSchedule, updateItemSchedule, deleteItemSchedule, getAccountDetails, getItems } from '../services/api';
import { Clock, Trash2, Loader2, Plus, X, Calendar, ShoppingBag, ToggleLeft, ToggleRight } from 'lucide-react';

const ItemSchedule: React.FC = () => {
  const STORAGE_KEY = 'item_schedule_form';
  const savedForm = (() => { try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); } catch { return {}; } })();

  const [schedules, setSchedules] = useState<ItemScheduleType[]>([]);
  const [accounts, setAccounts] = useState<AccountDetail[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    cookie_id: savedForm.cookie_id || '',
    item_id: savedForm.item_id || '',
    item_title: savedForm.item_title || '',
    schedule_type: (savedForm.schedule_type || 'list') as 'list' | 'delist',
    schedule_time: savedForm.schedule_time || '',
    cron_expression: savedForm.cron_expression || ''
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(form));
  }, [form]);

  useEffect(() => {
    loadSchedules();
    getAccountDetails().then(setAccounts);
    getItems().then(setItems);
  }, []);

  const loadSchedules = async () => {
    setLoading(true);
    try {
      const res = await getItemSchedules();
      setSchedules(res.data || []);
    } catch (e) {
      console.error('加载上下架计划失败', e);
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = async (schedule: ItemScheduleType) => {
    try {
      await updateItemSchedule(schedule.id, { enabled: !schedule.enabled });
      await loadSchedules();
    } catch (e) {
      console.error('切换状态失败', e);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('确认删除该上下架计划吗？')) return;
    try {
      await deleteItemSchedule(id);
      loadSchedules();
    } catch (e) {
      alert('删除失败');
    }
  };

  const handleAdd = async () => {
    if (!form.cookie_id || !form.item_id || !form.schedule_time) {
      alert('请填写完整信息');
      return;
    }
    setSaving(true);
    try {
      await addItemSchedule({
        cookie_id: form.cookie_id,
        item_id: form.item_id,
        item_title: form.item_title,
        schedule_type: form.schedule_type,
        schedule_time: form.schedule_time
      });
      setShowModal(false);
      setForm({
        cookie_id: '', item_id: '', item_title: '',
        schedule_type: 'list', schedule_time: '', cron_expression: ''
      });
      localStorage.removeItem(STORAGE_KEY);
      loadSchedules();
    } catch (e) {
      alert('添加失败');
    } finally {
      setSaving(false);
    }
  };

  const handleAccountChange = (cookieId: string) => {
    setForm({
      ...form,
      cookie_id: cookieId,
      item_id: '',
      item_title: ''
    });
  };

  const handleItemSelect = (itemId: string) => {
    const item = items.find(i => i.item_id === itemId);
    setForm({
      ...form,
      item_id: itemId,
      item_title: item ? (item.item_title || '') : form.item_title
    });
  };

  const getAccountNickname = (cookieId: string) => {
    const acc = accounts.find(a => a.id === cookieId);
    return acc?.nickname || acc?.remark || cookieId.substring(0, 8) + '...';
  };

  const filteredItems = form.cookie_id
    ? items.filter(i => i.cookie_id === form.cookie_id)
    : [];

  return (
    <div className="space-y-8 animate-fade-in">
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100">智能上下架计划</h2>
          <p className="text-gray-500 dark:text-gray-400 mt-2 text-sm">定时自动上架或下架商品，按计划时间执行。</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={loadSchedules}
            className="flex items-center gap-2 px-5 py-3 rounded-2xl font-bold bg-gray-100 hover:bg-gray-200 transition-all shadow-lg"
          >
            <Loader2 className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
          <button
            onClick={() => setShowModal(true)}
            className="px-5 py-3 rounded-2xl font-bold bg-[#FFE815] text-black hover:bg-[#FFD700] transition-all flex items-center gap-2 shadow-lg shadow-yellow-200"
          >
            <Plus className="w-4 h-4" />
            添加计划
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
        ) : schedules.length === 0 ? (
          <div className="py-24 text-center">
            <div className="w-24 h-24 bg-gradient-to-br from-[#FFE815]/20 to-[#FFD700]/20 rounded-full flex items-center justify-center mx-auto mb-6 shadow-inner">
              <Clock className="w-12 h-12 text-[#FFE815]" />
            </div>
            <h3 className="text-2xl font-bold text-gray-900 mb-2">暂无计划</h3>
            <p className="text-gray-500 text-lg">点击"添加计划"来创建智能上下架任务</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] md:min-w-0">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  <th className="text-left px-5 py-5 text-sm font-bold text-gray-600">账号</th>
                  <th className="text-left px-5 py-5 text-sm font-bold text-gray-600">商品名称</th>
                  <th className="text-left px-5 py-5 text-sm font-bold text-gray-600">商品ID</th>
                  <th className="text-center px-5 py-5 text-sm font-bold text-gray-600">类型</th>
                  <th className="text-left px-5 py-5 text-sm font-bold text-gray-600">计划时间</th>
                  <th className="text-center px-5 py-5 text-sm font-bold text-gray-600">状态</th>
                  <th className="text-left px-5 py-5 text-sm font-bold text-gray-600">最后执行</th>
                  <th className="text-center px-5 py-5 text-sm font-bold text-gray-600">操作</th>
                </tr>
              </thead>
              <tbody>
                {schedules.map((schedule) => (
                  <tr key={schedule.id} className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
                    <td className="px-5 py-4">
                      <span className="text-xs bg-gray-100 px-2 py-1 rounded-lg font-mono">
                        {getAccountNickname(schedule.cookie_id)}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <span className="font-bold text-gray-900 text-sm">
                        {schedule.item_title || '-'}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <span className="text-xs bg-gray-100 px-2 py-1 rounded-lg font-mono text-gray-600">
                        {schedule.item_id}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-center">
                      {schedule.schedule_type === 'list' ? (
                        <span className="px-3 py-1.5 rounded-xl text-xs font-bold bg-green-100 text-green-700 shadow-sm">
                          📈 上架
                        </span>
                      ) : (
                        <span className="px-3 py-1.5 rounded-xl text-xs font-bold bg-orange-100 text-orange-700 shadow-sm">
                          📉 下架
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-2">
                        <Calendar className="w-4 h-4 text-gray-400" />
                        <span className="text-sm text-gray-700">
                          {schedule.schedule_time ? new Date(schedule.schedule_time).toLocaleString('zh-CN') : '-'}
                        </span>
                      </div>
                    </td>
                    <td className="px-5 py-4 text-center">
                      <button
                        onClick={() => handleToggle(schedule)}
                        className="transition-colors"
                        title={schedule.enabled ? '点击禁用' : '点击启用'}
                      >
                        {schedule.enabled ? (
                          <ToggleRight className="w-8 h-8 text-green-500 hover:text-green-600" />
                        ) : (
                          <ToggleLeft className="w-8 h-8 text-gray-400 hover:text-gray-500" />
                        )}
                      </button>
                    </td>
                    <td className="px-5 py-4">
                      <span className="text-sm text-gray-500">
                        {schedule.last_run_at ? new Date(schedule.last_run_at).toLocaleString('zh-CN') : '未执行'}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-center">
                      <button
                        onClick={() => handleDelete(schedule.id)}
                        className="p-3 bg-gradient-to-br from-red-50 to-red-100 text-red-500 rounded-2xl hover:from-red-100 hover:to-red-200 transition-all shadow-md hover:shadow-lg hover:scale-110"
                        title="删除"
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
                    <Clock className="w-7 h-7 text-gray-900" />
                  </div>
                  <h3 className="text-3xl font-black text-gray-900">添加上下架计划</h3>
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
                <label className="flex items-center gap-2 text-sm font-bold text-gray-900 mb-3">
                  <Clock className="w-5 h-5 text-[#FFE815]" />
                  选择账号 <span className="text-red-500">*</span>
                </label>
                <select
                  value={form.cookie_id}
                  onChange={(e) => handleAccountChange(e.target.value)}
                  className="w-full px-5 py-4 rounded-2xl font-medium border-2 border-gray-200 focus:border-[#FFE815] focus:ring-4 focus:ring-[#FFE815]/20 transition-all bg-gray-50"
                >
                  <option value="">请选择账号</option>
                  {accounts.map(acc => (
                    <option key={acc.id} value={acc.id}>{acc.nickname || acc.remark || acc.id}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-bold text-gray-900 mb-3">
                  <ShoppingBag className="w-5 h-5 text-[#FFE815]" />
                  选择商品 <span className="text-red-500">*</span>
                </label>
                <select
                  value={form.item_id}
                  onChange={(e) => handleItemSelect(e.target.value)}
                  className="w-full px-5 py-4 rounded-2xl font-medium border-2 border-gray-200 focus:border-[#FFE815] focus:ring-4 focus:ring-[#FFE815]/20 transition-all bg-gray-50"
                  disabled={!form.cookie_id}
                >
                  <option value="">请选择商品</option>
                  {filteredItems.map(item => (
                    <option key={`${item.cookie_id}-${item.item_id}`} value={item.item_id}>
                      {item.item_title || item.item_id}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-bold text-gray-900 mb-3">
                  <ShoppingBag className="w-5 h-5 text-[#FFE815]" />
                  商品ID（手动输入）
                </label>
                <input
                  type="text"
                  value={form.item_id}
                  onChange={(e) => setForm({ ...form, item_id: e.target.value })}
                  placeholder="手动输入商品ID"
                  className="w-full px-5 py-4 rounded-2xl font-medium border-2 border-gray-200 focus:border-[#FFE815] focus:ring-4 focus:ring-[#FFE815]/20 transition-all bg-gray-50"
                />
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-bold text-gray-900 mb-3">
                  <ShoppingBag className="w-5 h-5 text-[#FFE815]" />
                  商品标题
                </label>
                <input
                  type="text"
                  value={form.item_title}
                  onChange={(e) => setForm({ ...form, item_title: e.target.value })}
                  placeholder="商品标题（选填）"
                  className="w-full px-5 py-4 rounded-2xl font-medium border-2 border-gray-200 focus:border-[#FFE815] focus:ring-4 focus:ring-[#FFE815]/20 transition-all bg-gray-50"
                />
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-bold text-gray-900 mb-3">
                  <Clock className="w-5 h-5 text-[#FFE815]" />
                  类型 <span className="text-red-500">*</span>
                </label>
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => setForm({ ...form, schedule_type: 'list' })}
                    className={`flex-1 py-4 rounded-2xl font-bold text-sm transition-all ${
                      form.schedule_type === 'list'
                        ? 'bg-green-500 text-white shadow-lg shadow-green-200'
                        : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                    }`}
                  >
                    📈 上架
                  </button>
                  <button
                    type="button"
                    onClick={() => setForm({ ...form, schedule_type: 'delist' })}
                    className={`flex-1 py-4 rounded-2xl font-bold text-sm transition-all ${
                      form.schedule_type === 'delist'
                        ? 'bg-orange-500 text-white shadow-lg shadow-orange-200'
                        : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                    }`}
                  >
                    📉 下架
                  </button>
                </div>
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-bold text-gray-900 mb-3">
                  <Calendar className="w-5 h-5 text-[#FFE815]" />
                  计划时间 <span className="text-red-500">*</span>
                </label>
                <input
                  type="datetime-local"
                  value={form.schedule_time}
                  onChange={(e) => setForm({ ...form, schedule_time: e.target.value })}
                  className="w-full px-5 py-4 rounded-2xl font-medium border-2 border-gray-200 focus:border-[#FFE815] focus:ring-4 focus:ring-[#FFE815]/20 transition-all bg-gray-50"
                />
              </div>
            </div>

            <div className="px-8 pb-8 flex gap-4">
              <button
                onClick={() => setShowModal(false)}
                className="flex-1 py-4 rounded-2xl font-bold bg-gray-100 text-gray-700 hover:bg-gray-200 transition-all"
              >
                取消
              </button>
              <button
                onClick={handleAdd}
                disabled={saving}
                className="flex-1 py-4 rounded-2xl font-bold bg-[#FFE815] text-black hover:bg-[#FFD700] transition-all shadow-lg shadow-yellow-200 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {saving ? <Loader2 className="w-5 h-5 animate-spin" /> : null}
                保存计划
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
};

export default ItemSchedule;
